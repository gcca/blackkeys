import asyncio
import hashlib
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import grpc
import pylibmc

from blackkeys.backends.services.brands import (
    BrandImageNotFound,
    BrandsFromResponse,
    BrandsService,
    MakeBrandsService,
)
from blackkeys.backends.stores.cache import (
    BRAND_IMAGE_CACHE_MAGIC,
    BRANDS_LIST_CACHE_KEY,
    BrandImageKey,
    CachedBrandImage,
    DecodeBrandImage,
    EncodeBrandImage,
    MakeBrandsCache,
    ReadBrandImage,
    ReadBrandsList,
    WriteBrandImage,
    WriteBrandsList,
)
from blackkeys.blueprints.brands import Get, List, Logo, Picture, blueprint
from blackkeys.core.conf import Settings
from blackkeys.gen.v1 import messages_pb2
from blackkeys.repositories import BrandsRepository, MakeBrandsRepository
from tests import AuthorizedRequest

unittest.defaultTestLoader.testMethodPrefix = "Test"


def SampleBrand() -> messages_pb2.Brand:
    return messages_pb2.Brand(
        name="ADIDAS",
        display_name="Adidas",
        description="desc",
        is_active=True,
        kiosk_id=12,
        amenities=[messages_pb2.Amenity(name="wifi", value="yes")],
        stores=[messages_pb2.Store(id=4, name="Corredor Mantaro, 2do nivel")],
        tags=["sports", "outdoor"],
    )


class BrandsMappingTests(unittest.TestCase):
    def TestMapsProtobufBrandsToCamelCaseJson(self) -> None:
        brands = BrandsFromResponse(
            messages_pb2.ListResponse(brands=[SampleBrand()])
        )

        self.assertEqual(
            brands,
            [
                {
                    "name": "ADIDAS",
                    "displayName": "Adidas",
                    "description": "desc",
                    "isActive": True,
                    "kioskId": 12,
                    "amenities": [{"name": "wifi", "value": "yes"}],
                    "stores": [
                        {"id": 4, "name": "Corredor Mantaro, 2do nivel"}
                    ],
                    "tags": ["sports", "outdoor"],
                }
            ],
        )

    def TestMapsAnEmptyResponseToAnEmptyList(self) -> None:
        self.assertEqual(BrandsFromResponse(messages_pb2.ListResponse()), [])


class BrandsServiceTests(unittest.TestCase):
    def TestReturnsTheMappedBrands(self) -> None:
        service = BrandsService("127.0.0.1:9")
        stub = AsyncMock()
        stub.List.return_value = messages_pb2.ListResponse(
            brands=[SampleBrand()]
        )
        service._stub = stub

        brands = asyncio.run(service.List())

        assert brands is not None
        self.assertEqual(brands[0]["name"], "ADIDAS")
        stub.List.assert_awaited_once()

    def TestReturnsNoneWhenTheRpcFails(self) -> None:
        service = BrandsService("127.0.0.1:9")
        stub = AsyncMock()
        stub.List.side_effect = grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE, details="unavailable"
        )
        service._stub = stub

        with patch("blackkeys.backends.services.brands.logger"):
            self.assertIsNone(asyncio.run(service.List()))

    def TestNotifiesSentryWithDetailsWhenTheRpcFails(self) -> None:
        service = BrandsService("127.0.0.1:9")
        stub = AsyncMock()
        stub.List.side_effect = grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE, details="unavailable"
        )
        service._stub = stub

        with patch("blackkeys.backends.services.brands.logger"), patch(
            "blackkeys.backends.services.brands.NotifyEvent"
        ) as notify:
            asyncio.run(service.List())

        notify.assert_called_once_with(
            "brands list request failed: target=127.0.0.1:9 "
            "code=StatusCode.UNAVAILABLE details=unavailable",
            level="error",
        )

    def TestMakeBrandsServiceReturnsNoneWhenTheTargetIsMissing(self) -> None:
        self.assertIsNone(MakeBrandsService(None))
        self.assertIsNone(MakeBrandsService(""))

    def TestLogoReturnsDataAndContentType(self) -> None:
        service = BrandsService("127.0.0.1:9")
        stub = AsyncMock()
        stub.Logo.return_value = messages_pb2.ImageResponse(
            data=b"png-bytes", content_type="image/png"
        )
        service._stub = stub

        result = asyncio.run(service.Logo("ADIDAS"))

        self.assertEqual(result, (b"png-bytes", "image/png"))
        stub.Logo.assert_awaited_once()
        self.assertEqual(
            stub.Logo.await_args.args[0],
            messages_pb2.ImageRequest(name="ADIDAS"),
        )

    def TestPictureReturnsDataAndContentType(self) -> None:
        service = BrandsService("127.0.0.1:9")
        stub = AsyncMock()
        stub.Picture.return_value = messages_pb2.ImageResponse(
            data=b"picture-bytes", content_type="image/png"
        )
        service._stub = stub

        result = asyncio.run(service.Picture("ADIDAS"))

        self.assertEqual(result, (b"picture-bytes", "image/png"))
        stub.Picture.assert_awaited_once()

    def TestLogoRaisesNotFoundOnNotFoundStatus(self) -> None:
        service = BrandsService("127.0.0.1:9")
        stub = AsyncMock()
        stub.Logo.side_effect = grpc.aio.AioRpcError(
            grpc.StatusCode.NOT_FOUND, details="not found"
        )
        service._stub = stub

        with self.assertRaises(BrandImageNotFound):
            asyncio.run(service.Logo("MISSING"))

    def TestLogoReturnsNoneWhenTheRpcFails(self) -> None:
        service = BrandsService("127.0.0.1:9")
        stub = AsyncMock()
        stub.Logo.side_effect = grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE, details="unavailable"
        )
        service._stub = stub

        with patch("blackkeys.backends.services.brands.logger"), patch(
            "blackkeys.backends.services.brands.NotifyEvent"
        ) as notify:
            self.assertIsNone(asyncio.run(service.Logo("ADIDAS")))

        notify.assert_called_once()


def WriteCache(start: int, replication: int) -> MagicMock:
    nodes = ("cache-a:11211", "cache-b:11211", "cache-c:11211")
    cache = MagicMock()
    client = cache.reserve.return_value.__enter__.return_value
    client.hash.return_value = start
    cache.nodes = nodes
    cache.replication = replication
    cache.node_clients = {node: MagicMock() for node in nodes}
    cache.node_locks = {node: threading.Lock() for node in nodes}
    for node_client in cache.node_clients.values():
        node_client.set.return_value = True
    return cache


class BrandsCacheTests(unittest.TestCase):
    @patch("blackkeys.backends.stores.cache.pylibmc.ClientPool")
    @patch("blackkeys.backends.stores.cache.pylibmc.Client")
    def TestBrandsCacheUsesConsistentHashing(
        self, client_constructor: MagicMock, pool_constructor: MagicMock
    ) -> None:
        client = client_constructor.return_value

        cache = MakeBrandsCache(("cache-a:11211", "cache-b:11211"))

        client_constructor.assert_has_calls(
            [
                call(
                    ["cache-a:11211", "cache-b:11211"],
                    binary=True,
                    behaviors={
                        "ketama": True,
                        "num_replicas": 1,
                    },
                ),
                call(["cache-a:11211"], binary=True, behaviors={}),
                call(["cache-b:11211"], binary=True, behaviors={}),
            ]
        )
        self.assertEqual(client_constructor.call_count, 3)
        pool_constructor.assert_called_once_with(client, 4)
        self.assertIs(cache, pool_constructor.return_value)

    def TestNoNodesMeansNoCache(self) -> None:
        self.assertIsNone(MakeBrandsCache(()))

    def TestReadBrandsListDecodesJson(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = json.dumps([{"name": "ADIDAS"}]).encode()

        brands = ReadBrandsList(cache)

        self.assertEqual(brands, [{"name": "ADIDAS"}])
        client.get.assert_called_once_with(BRANDS_LIST_CACHE_KEY)

    def TestReadBrandsListRejectsAMiss(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = None

        self.assertIsNone(ReadBrandsList(cache))

    def TestReadBrandsListRejectsNonListPayloads(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = json.dumps({"name": "ADIDAS"}).encode()

        self.assertIsNone(ReadBrandsList(cache))

    def TestWriteBrandsListEncodesJsonWithTtl(self) -> None:
        cache = WriteCache(1, 1)
        payload = json.dumps([{"name": "ADIDAS"}]).encode()

        stored = WriteBrandsList(cache, [{"name": "ADIDAS"}])

        self.assertTrue(stored)
        client = cache.reserve.return_value.__enter__.return_value
        client.hash.assert_called_once_with(BRANDS_LIST_CACHE_KEY)
        client.set.assert_not_called()
        client.disconnect_all.assert_not_called()
        for node in ("cache-b:11211", "cache-c:11211"):
            cache.node_clients[node].set.assert_called_once_with(
                BRANDS_LIST_CACHE_KEY,
                payload,
                time=4500,
            )
        cache.node_clients["cache-a:11211"].set.assert_not_called()

    def TestWriteBrandsListReturnsFalseWhenAnyReplicaRejects(self) -> None:
        cache = WriteCache(1, 1)
        cache.node_clients["cache-c:11211"].set.return_value = False

        self.assertFalse(WriteBrandsList(cache, [{"name": "ADIDAS"}]))

        cache.node_clients["cache-b:11211"].set.assert_called_once()
        cache.node_clients["cache-c:11211"].set.assert_called_once()

    def TestBrandImageKeysAreDeterministicAndSeparateKinds(self) -> None:
        name = "Brand Name With Spaces"
        digest = hashlib.sha256(
            name.encode(), usedforsecurity=False
        ).hexdigest()

        logo_key = BrandImageKey("logo", name)

        self.assertEqual(
            logo_key,
            f"blackkeys-brand-image:logo:{digest}",
        )
        self.assertEqual(logo_key, BrandImageKey("logo", name))
        self.assertNotEqual(logo_key, BrandImageKey("picture", name))

    def TestBrandImageKeysAcceptExcessivelyLongNames(self) -> None:
        key = BrandImageKey("logo", "brand name " * 1000)

        self.assertLessEqual(len(key.encode()), 250)
        self.assertNotIn(" ", key)

    def TestBrandImageRoundTripsBinaryData(self) -> None:
        image = CachedBrandImage(b"\x00\xffpng-bytes", "image/png")

        encoded = EncodeBrandImage(image)

        self.assertTrue(encoded.startswith(BRAND_IMAGE_CACHE_MAGIC))
        self.assertEqual(DecodeBrandImage(encoded), image)

    def TestReadBrandImageTreatsCorruptValuesAsMisses(self) -> None:
        invalid_values = (
            None,
            "not-bytes",
            b"",
            b"BKBI",
            b"WRNG\x00\x09image/pngbytes",
            b"BKBI\x00\x00bytes",
            b"BKBI\x00\x09image/png",
            b"BKBI\x00\x01\xffbytes",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                cache = MagicMock()
                client = cache.reserve.return_value.__enter__.return_value
                client.get.return_value = value

                self.assertIsNone(ReadBrandImage(cache, "logo", "ADIDAS"))

        self.assertIsNone(DecodeBrandImage("not-bytes"))

    def TestWriteBrandImageReplicatesWithConfiguredTtl(self) -> None:
        cache = WriteCache(2, 1)
        image = CachedBrandImage(b"png-bytes", "image/png")
        key = BrandImageKey("picture", "Brand Name")
        payload = EncodeBrandImage(image)

        stored = WriteBrandImage(
            cache, "picture", "Brand Name", image, ttl_seconds=4500
        )

        self.assertTrue(stored)
        for node in ("cache-c:11211", "cache-a:11211"):
            cache.node_clients[node].set.assert_called_once_with(
                key, payload, time=4500
            )
        cache.node_clients["cache-b:11211"].set.assert_not_called()

    def TestWriteBrandImageReturnsFalseWhenAReplicaRejectsIt(self) -> None:
        cache = WriteCache(2, 1)
        cache.node_clients["cache-a:11211"].set.return_value = False

        stored = WriteBrandImage(
            cache,
            "logo",
            "ADIDAS",
            CachedBrandImage(b"png-bytes", "image/png"),
            ttl_seconds=4500,
        )

        self.assertFalse(stored)
        cache.node_clients["cache-c:11211"].set.assert_called_once()
        cache.node_clients["cache-a:11211"].set.assert_called_once()


class BrandsRepositoryTests(unittest.TestCase):
    def TestFactoryPassesTheConfiguredImageTtl(self) -> None:
        settings = Settings.FromEnv(
            {
                "SECRET": "secret",
                "BRAND_IMAGE_CACHE_TTL_SECONDS": "900",
            }
        )
        with patch(
            "blackkeys.repositories.cache_store.MakeBrandsCache"
        ) as make_cache, patch(
            "blackkeys.repositories.MakeBrandsService"
        ) as make_service:
            repository = MakeBrandsRepository(settings)

        make_cache.assert_called_once_with((), replication=1)
        make_service.assert_called_once_with("127.0.0.1:50051")
        self.assertEqual(repository._image_cache_ttl_seconds, 900)

    def TestReturnsTheServiceValue(self) -> None:
        service = AsyncMock()
        service.List.return_value = [{"name": "ADIDAS", "kioskId": 12}]
        repository = BrandsRepository(None, service, 4500)

        self.assertEqual(
            asyncio.run(repository.List()),
            [{"name": "ADIDAS", "kioskId": 12}],
        )

    def TestReturnsNoneWhenTheServiceIsMissing(self) -> None:
        self.assertIsNone(
            asyncio.run(BrandsRepository(None, None, 4500).List())
        )

    def TestReturnsFromSharedCacheWithoutTouchingTheService(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = json.dumps(
            [{"name": "ADIDAS", "kioskId": 12}]
        ).encode()
        service = AsyncMock()
        repository = BrandsRepository(cache, service, 4500)

        brands = asyncio.run(repository.List())

        self.assertEqual(brands, [{"name": "ADIDAS", "kioskId": 12}])
        service.List.assert_not_called()

    def TestFallsBackToTheServiceAndPopulatesTheCache(self) -> None:
        cache = WriteCache(1, 1)
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = None
        service = AsyncMock()
        service.List.return_value = [{"name": "ADIDAS", "kioskId": 12}]
        repository = BrandsRepository(cache, service, 4500)
        payload = json.dumps([{"name": "ADIDAS", "kioskId": 12}]).encode()

        brands = asyncio.run(repository.List())

        self.assertEqual(brands, [{"name": "ADIDAS", "kioskId": 12}])
        for node in ("cache-b:11211", "cache-c:11211"):
            cache.node_clients[node].set.assert_called_once_with(
                BRANDS_LIST_CACHE_KEY,
                payload,
                        time=4500,
            )
        client.set.assert_not_called()

    def TestFallsBackToTheServiceWhenTheCacheReadFails(self) -> None:
        cache = WriteCache(1, 1)
        client = cache.reserve.return_value.__enter__.return_value
        client.get.side_effect = pylibmc.Error("read failed")
        service = AsyncMock()
        service.List.return_value = [{"name": "ADIDAS", "kioskId": 12}]
        repository = BrandsRepository(cache, service, 4500)

        with patch("blackkeys.repositories.logger") as logger:
            brands = asyncio.run(repository.List())

        self.assertEqual(brands, [{"name": "ADIDAS", "kioskId": 12}])
        logger.warning.assert_called_once()

    def TestKeepsTheServiceResultWhenTheCacheWriteFails(self) -> None:
        cache = WriteCache(1, 1)
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = None
        cache.node_clients["cache-b:11211"].set.side_effect = pylibmc.Error(
            "write failed"
        )
        service = AsyncMock()
        service.List.return_value = [{"name": "ADIDAS", "kioskId": 12}]
        repository = BrandsRepository(cache, service, 4500)

        with patch("blackkeys.repositories.logger") as logger:
            brands = asyncio.run(repository.List())

        self.assertEqual(brands, [{"name": "ADIDAS", "kioskId": 12}])
        logger.warning.assert_called_once()

    def TestReturnsNoneWhenTheServiceIsMissingAndCacheMisses(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = None
        repository = BrandsRepository(cache, None, 4500)

        self.assertIsNone(asyncio.run(repository.List()))
        client.set.assert_not_called()

    def TestLogoDelegatesToTheService(self) -> None:
        service = AsyncMock()
        service.Logo.return_value = (b"png-bytes", "image/png")
        repository = BrandsRepository(None, service, 4500)

        result = asyncio.run(repository.Logo("ADIDAS"))

        self.assertEqual(result, (b"png-bytes", "image/png"))
        service.Logo.assert_awaited_once_with("ADIDAS")

    def TestPictureDelegatesToTheService(self) -> None:
        service = AsyncMock()
        service.Picture.return_value = (b"picture-bytes", "image/png")
        repository = BrandsRepository(None, service, 4500)

        result = asyncio.run(repository.Picture("ADIDAS"))

        self.assertEqual(result, (b"picture-bytes", "image/png"))
        service.Picture.assert_awaited_once_with("ADIDAS")

    def TestLogoReturnsNoneWhenTheServiceIsMissing(self) -> None:
        repository = BrandsRepository(None, None, 4500)

        self.assertIsNone(asyncio.run(repository.Logo("ADIDAS")))

    def TestPictureReturnsNoneWhenTheServiceIsMissing(self) -> None:
        repository = BrandsRepository(None, None, 4500)

        self.assertIsNone(asyncio.run(repository.Picture("ADIDAS")))

    def TestLogoPropagatesNotFound(self) -> None:
        service = AsyncMock()
        service.Logo.side_effect = BrandImageNotFound("ADIDAS")
        repository = BrandsRepository(None, service, 4500)

        with self.assertRaises(BrandImageNotFound):
            asyncio.run(repository.Logo("ADIDAS"))

    def TestImagesReturnFromCacheWithoutTouchingTheService(self) -> None:
        for kind in ("logo", "picture"):
            with self.subTest(kind=kind):
                cache = MagicMock()
                client = cache.reserve.return_value.__enter__.return_value
                client.get.return_value = EncodeBrandImage(
                    CachedBrandImage(b"cached-bytes", "image/webp")
                )
                service = AsyncMock()
                repository = BrandsRepository(cache, service, 4500)

                result = asyncio.run(
                    getattr(repository, kind.capitalize())("Brand Name")
                )

                self.assertEqual(result, (b"cached-bytes", "image/webp"))
                client.get.assert_called_once_with(
                    BrandImageKey(kind, "Brand Name")
                )
                getattr(service, kind.capitalize()).assert_not_called()

    def TestImageMissesPopulateTheCache(self) -> None:
        for kind in ("logo", "picture"):
            with self.subTest(kind=kind):
                cache = WriteCache(1, 1)
                client = cache.reserve.return_value.__enter__.return_value
                client.get.return_value = None
                service = AsyncMock()
                getattr(service, kind.capitalize()).return_value = (
                    b"service-bytes",
                    "image/png",
                )
                repository = BrandsRepository(cache, service, 900)
                key = BrandImageKey(kind, "ADIDAS")
                payload = EncodeBrandImage(
                    CachedBrandImage(b"service-bytes", "image/png")
                )

                result = asyncio.run(
                    getattr(repository, kind.capitalize())("ADIDAS")
                )

                self.assertEqual(result, (b"service-bytes", "image/png"))
                getattr(service, kind.capitalize()).assert_awaited_once_with(
                    "ADIDAS"
                )
                for node in ("cache-b:11211", "cache-c:11211"):
                    cache.node_clients[node].set.assert_called_once_with(
                        key, payload, time=900
                    )

    def TestImageReadFailuresFallBackToTheService(self) -> None:
        for kind in ("logo", "picture"):
            with self.subTest(kind=kind):
                cache = WriteCache(1, 1)
                client = cache.reserve.return_value.__enter__.return_value
                client.get.side_effect = pylibmc.Error("read failed")
                service = AsyncMock()
                getattr(service, kind.capitalize()).return_value = (
                    b"service-bytes",
                    "image/png",
                )
                repository = BrandsRepository(cache, service, 4500)

                with patch("blackkeys.repositories.logger") as logger:
                    result = asyncio.run(
                        getattr(repository, kind.capitalize())("ADIDAS")
                    )

                self.assertEqual(result, (b"service-bytes", "image/png"))
                self.assertTrue(logger.warning.called)

    def TestImageMissesReturnNoneWithoutAService(self) -> None:
        for kind in ("logo", "picture"):
            with self.subTest(kind=kind):
                cache = MagicMock()
                client = cache.reserve.return_value.__enter__.return_value
                client.get.return_value = None
                repository = BrandsRepository(cache, None, 4500)

                result = asyncio.run(
                    getattr(repository, kind.capitalize())("ADIDAS")
                )

                self.assertIsNone(result)
                client.set.assert_not_called()

    def TestImageResultsSurviveCacheWriteFailures(self) -> None:
        for kind in ("logo", "picture"):
            with self.subTest(kind=kind):
                cache = WriteCache(1, 1)
                client = cache.reserve.return_value.__enter__.return_value
                client.get.return_value = None
                cache.node_clients["cache-b:11211"].set.side_effect = (
                    pylibmc.Error("write failed")
                )
                service = AsyncMock()
                getattr(service, kind.capitalize()).return_value = (
                    b"service-bytes",
                    "image/png",
                )
                repository = BrandsRepository(cache, service, 4500)

                with patch("blackkeys.repositories.logger") as logger:
                    result = asyncio.run(
                        getattr(repository, kind.capitalize())("ADIDAS")
                    )

                self.assertEqual(result, (b"service-bytes", "image/png"))
                logger.warning.assert_called_once()

    def TestRejectedImageWritesDoNotReplaceServiceResults(self) -> None:
        cache = WriteCache(1, 1)
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = None
        cache.node_clients["cache-c:11211"].set.return_value = False
        service = AsyncMock()
        service.Logo.return_value = (b"service-bytes", "image/png")
        repository = BrandsRepository(cache, service, 4500)

        with patch("blackkeys.repositories.logger") as logger:
            result = asyncio.run(repository.Logo("ADIDAS"))

        self.assertEqual(result, (b"service-bytes", "image/png"))
        logger.warning.assert_called_once_with(
            "brand %s cache write failed", "logo"
        )

    def TestMissingImagesAreNotCached(self) -> None:
        for kind in ("logo", "picture"):
            with self.subTest(kind=kind):
                cache = WriteCache(1, 1)
                client = cache.reserve.return_value.__enter__.return_value
                client.get.return_value = None
                service = AsyncMock()
                getattr(service, kind.capitalize()).side_effect = (
                    BrandImageNotFound("ADIDAS")
                )
                repository = BrandsRepository(cache, service, 4500)

                with self.assertRaises(BrandImageNotFound):
                    asyncio.run(
                        getattr(repository, kind.capitalize())("ADIDAS")
                    )

                for node_client in cache.node_clients.values():
                    node_client.set.assert_not_called()


class BrandsEndpointTests(unittest.TestCase):
    request = AuthorizedRequest()

    def TestReturnsTheBrandsList(self) -> None:
        repository = AsyncMock()
        repository.List.return_value = [{"name": "ADIDAS", "kioskId": 12}]

        with patch("blackkeys.blueprints.brands.brands_repository", repository):
            response = asyncio.run(List(self.request))

        self.assertEqual(response.status, 200)
        self.assertEqual(
            json.loads(response.body), [{"name": "ADIDAS", "kioskId": 12}]
        )

    def TestReportsUnavailableWhenTheServiceMisses(self) -> None:
        repository = AsyncMock()
        repository.List.return_value = None

        with patch("blackkeys.blueprints.brands.brands_repository", repository):
            response = asyncio.run(List(self.request))

        self.assertEqual(response.status, 503)
        self.assertEqual(
            json.loads(response.body), {"error": "brands-unavailable"}
        )

    def TestRejectsARequestWithoutAToken(self) -> None:
        request = SimpleNamespace(json=None, headers={}, ctx=SimpleNamespace())

        response = asyncio.run(List(request))

        self.assertEqual(response.status, 401)
        self.assertEqual(json.loads(response.body), {"error": "invalid-token"})

    def TestReturnsAMatchingBrand(self) -> None:
        repository = AsyncMock()
        repository.List.return_value = [
            {"name": "ADIDAS", "kioskId": 12},
            {"name": "LACOSTE", "kioskId": 13},
        ]

        with patch("blackkeys.blueprints.brands.brands_repository", repository):
            response = asyncio.run(Get(self.request, "LACOSTE"))

        self.assertEqual(response.status, 200)
        self.assertEqual(
            json.loads(response.body), {"name": "LACOSTE", "kioskId": 13}
        )

    def TestReturnsNotFoundForAnUnknownBrand(self) -> None:
        repository = AsyncMock()
        repository.List.return_value = [{"name": "ADIDAS", "kioskId": 12}]

        with patch("blackkeys.blueprints.brands.brands_repository", repository):
            response = asyncio.run(Get(self.request, "MISSING"))

        self.assertEqual(response.status, 404)
        self.assertEqual(
            json.loads(response.body), {"error": "brand-not-found"}
        )

    def TestReportsUnavailableWhenTheServiceMissesForGet(self) -> None:
        repository = AsyncMock()
        repository.List.return_value = None

        with patch("blackkeys.blueprints.brands.brands_repository", repository):
            response = asyncio.run(Get(self.request, "ADIDAS"))

        self.assertEqual(response.status, 503)
        self.assertEqual(
            json.loads(response.body), {"error": "brands-unavailable"}
        )

    def TestGetRejectsARequestWithoutAToken(self) -> None:
        request = SimpleNamespace(json=None, headers={}, ctx=SimpleNamespace())

        response = asyncio.run(Get(request, "ADIDAS"))

        self.assertEqual(response.status, 401)
        self.assertEqual(json.loads(response.body), {"error": "invalid-token"})

    def TestLogoReturnsTheImageBytes(self) -> None:
        repository = AsyncMock()
        repository.Logo.return_value = (b"png-bytes", "image/png")

        with patch("blackkeys.blueprints.brands.brands_repository", repository):
            response = asyncio.run(Logo(self.request, "ADIDAS"))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"png-bytes")
        self.assertEqual(response.content_type, "image/png")

    def TestLogoReturnsNotFoundWhenTheImageIsMissing(self) -> None:
        repository = AsyncMock()
        repository.Logo.side_effect = BrandImageNotFound("ADIDAS")

        with patch("blackkeys.blueprints.brands.brands_repository", repository):
            response = asyncio.run(Logo(self.request, "ADIDAS"))

        self.assertEqual(response.status, 404)
        self.assertEqual(
            json.loads(response.body), {"error": "brand-not-found"}
        )

    def TestLogoReportsUnavailableWhenTheServiceMisses(self) -> None:
        repository = AsyncMock()
        repository.Logo.return_value = None

        with patch("blackkeys.blueprints.brands.brands_repository", repository):
            response = asyncio.run(Logo(self.request, "ADIDAS"))

        self.assertEqual(response.status, 503)
        self.assertEqual(
            json.loads(response.body), {"error": "brands-unavailable"}
        )

    def TestLogoRejectsARequestWithoutAToken(self) -> None:
        request = SimpleNamespace(json=None, headers={}, ctx=SimpleNamespace())

        response = asyncio.run(Logo(request, "ADIDAS"))

        self.assertEqual(response.status, 401)
        self.assertEqual(json.loads(response.body), {"error": "invalid-token"})

    def TestPictureReturnsTheImageBytes(self) -> None:
        repository = AsyncMock()
        repository.Picture.return_value = (b"picture-bytes", "image/png")

        with patch("blackkeys.blueprints.brands.brands_repository", repository):
            response = asyncio.run(Picture(self.request, "ADIDAS"))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"picture-bytes")
        self.assertEqual(response.content_type, "image/png")

    def TestPictureReturnsNotFoundWhenTheImageIsMissing(self) -> None:
        repository = AsyncMock()
        repository.Picture.side_effect = BrandImageNotFound("ADIDAS")

        with patch("blackkeys.blueprints.brands.brands_repository", repository):
            response = asyncio.run(Picture(self.request, "ADIDAS"))

        self.assertEqual(response.status, 404)
        self.assertEqual(
            json.loads(response.body), {"error": "brand-not-found"}
        )

    def TestPictureRejectsARequestWithoutAToken(self) -> None:
        request = SimpleNamespace(json=None, headers={}, ctx=SimpleNamespace())

        response = asyncio.run(Picture(request, "ADIDAS"))

        self.assertEqual(response.status, 401)
        self.assertEqual(json.loads(response.body), {"error": "invalid-token"})

    def TestRegistersTheGuardedHandler(self) -> None:
        routes = {
            route.uri: route.handler for route in blueprint._future_routes
        }

        self.assertIs(routes["/list"], List)
        self.assertTrue(hasattr(routes["/list"], "__wrapped__"))
        self.assertIs(routes["/<name:str>"], Get)
        self.assertTrue(hasattr(routes["/<name:str>"], "__wrapped__"))
        self.assertIs(routes["/<name:str>/logo"], Logo)
        self.assertTrue(hasattr(routes["/<name:str>/logo"], "__wrapped__"))
        self.assertIs(routes["/<name:str>/picture"], Picture)
        self.assertTrue(hasattr(routes["/<name:str>/picture"], "__wrapped__"))
