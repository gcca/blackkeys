import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import grpc

from blackkeys.backends.services.stores import (
    MakeStoresService,
    StoresFromResponse,
    StoresService,
)
from blackkeys.blueprints.stores import List, blueprint
from blackkeys.gen.v1 import messages_pb2
from blackkeys.repositories import StoresRepository
from tests import AuthorizedRequest

unittest.defaultTestLoader.testMethodPrefix = "Test"


def SampleStore() -> messages_pb2.Store:
    return messages_pb2.Store(
        id=81,
        name="ADIDAS",
        directory_id=63,
        is_active=True,
        is_new=False,
        logo="https://example/logo",
        store_photo="",
        description="desc",
        phone="(01) 705 9568",
        website="https://www.adidas.pe/",
        facebook="",
        instagram="",
        tiktok="",
        subcategory=messages_pb2.Subcategory(
            id=7,
            name="Deportes y Outdoor",
            category=messages_pb2.Category(
                id=5, name="Tiendas por departamento"
            ),
        ),
        stores=[
            messages_pb2.StoreLocation(
                location=messages_pb2.Location(
                    id=4, name="Corredor Mantaro, 2do nivel"
                )
            )
        ],
    )


class StoresMappingTests(unittest.TestCase):
    def TestMapsProtobufStoresToCamelCaseJson(self) -> None:
        stores = StoresFromResponse(
            messages_pb2.ListResponse(stores=[SampleStore()])
        )

        self.assertEqual(
            stores,
            [
                {
                    "id": 81,
                    "name": "ADIDAS",
                    "directoryId": 63,
                    "isActive": True,
                    "logo": "https://example/logo",
                    "description": "desc",
                    "phone": "(01) 705 9568",
                    "website": "https://www.adidas.pe/",
                    "subcategory": {
                        "id": 7,
                        "name": "Deportes y Outdoor",
                        "category": {
                            "id": 5,
                            "name": "Tiendas por departamento",
                        },
                    },
                    "stores": [
                        {
                            "location": {
                                "id": 4,
                                "name": "Corredor Mantaro, 2do nivel",
                            }
                        }
                    ],
                    "isNew": False,
                    "storePhoto": "",
                    "facebook": "",
                    "instagram": "",
                    "tiktok": "",
                }
            ],
        )

    def TestMapsAnEmptyResponseToAnEmptyList(self) -> None:
        self.assertEqual(StoresFromResponse(messages_pb2.ListResponse()), [])


class StoresServiceTests(unittest.TestCase):
    def TestReturnsTheMappedStores(self) -> None:
        service = StoresService("127.0.0.1:9")
        stub = AsyncMock()
        stub.List.return_value = messages_pb2.ListResponse(
            stores=[SampleStore()]
        )
        service._stub = stub

        stores = asyncio.run(service.List())

        assert stores is not None
        self.assertEqual(stores[0]["name"], "ADIDAS")
        stub.List.assert_awaited_once()

    def TestReturnsNoneWhenTheRpcFails(self) -> None:
        service = StoresService("127.0.0.1:9")
        stub = AsyncMock()
        stub.List.side_effect = grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE, details="unavailable"
        )
        service._stub = stub

        with patch("blackkeys.backends.services.stores.logger"):
            self.assertIsNone(asyncio.run(service.List()))

    def TestNotifiesSentryWithDetailsWhenTheRpcFails(self) -> None:
        service = StoresService("127.0.0.1:9")
        stub = AsyncMock()
        stub.List.side_effect = grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE, details="unavailable"
        )
        service._stub = stub

        with patch("blackkeys.backends.services.stores.logger"), patch(
            "blackkeys.backends.services.stores.NotifyEvent"
        ) as notify:
            asyncio.run(service.List())

        notify.assert_called_once_with(
            "stores list request failed: target=127.0.0.1:9 "
            "code=StatusCode.UNAVAILABLE details=unavailable",
            level="error",
        )

    def TestMakeStoresServiceReturnsNoneWhenTheTargetIsMissing(self) -> None:
        self.assertIsNone(MakeStoresService(None))
        self.assertIsNone(MakeStoresService(""))


class StoresRepositoryTests(unittest.TestCase):
    def TestReturnsTheServiceValue(self) -> None:
        service = AsyncMock()
        service.List.return_value = [{"id": 81, "name": "ADIDAS"}]
        repository = StoresRepository(service)

        self.assertEqual(
            asyncio.run(repository.List()),
            [{"id": 81, "name": "ADIDAS"}],
        )

    def TestReturnsNoneWhenTheServiceIsMissing(self) -> None:
        self.assertIsNone(asyncio.run(StoresRepository(None).List()))


class StoresEndpointTests(unittest.TestCase):
    request = AuthorizedRequest()

    def TestReturnsTheStoresList(self) -> None:
        repository = AsyncMock()
        repository.List.return_value = [{"id": 81, "name": "ADIDAS"}]

        with patch("blackkeys.blueprints.stores.stores_repository", repository):
            response = asyncio.run(List(self.request))

        self.assertEqual(response.status, 200)
        self.assertEqual(
            json.loads(response.body), [{"id": 81, "name": "ADIDAS"}]
        )

    def TestReportsUnavailableWhenTheServiceMisses(self) -> None:
        repository = AsyncMock()
        repository.List.return_value = None

        with patch("blackkeys.blueprints.stores.stores_repository", repository):
            response = asyncio.run(List(self.request))

        self.assertEqual(response.status, 503)
        self.assertEqual(
            json.loads(response.body), {"error": "stores-unavailable"}
        )

    def TestRejectsARequestWithoutAToken(self) -> None:
        request = SimpleNamespace(json=None, headers={}, ctx=SimpleNamespace())

        response = asyncio.run(List(request))

        self.assertEqual(response.status, 401)
        self.assertEqual(json.loads(response.body), {"error": "invalid-token"})

    def TestRegistersTheGuardedHandler(self) -> None:
        routes = {
            route.uri: route.handler for route in blueprint._future_routes
        }

        self.assertIs(routes["/list"], List)
        self.assertTrue(hasattr(routes["/list"], "__wrapped__"))
