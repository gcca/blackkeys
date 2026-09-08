import asyncio
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pylibmc
from argon2 import PasswordHasher, Type

from blackkeys.application import AuthService
from blackkeys.backends.stores.cache import (
    CachedUserAuth,
    DecodeUserAuth,
    EncodeUserAuth,
    MakeAuthCache,
    ReadUserAuth,
    UserAuthKey,
    WriteUserAuth,
)
from blackkeys.backends.stores.local import (
    LocalCacheClear,
    LocalCacheGet,
    LocalCacheSet,
)
from blackkeys.blueprints.auth import SignIn
from blackkeys.core.auth import RandomString, SignSession, VerifySession
from blackkeys.core.conf import Settings, settings
from blackkeys.repositories import AuthenticationUnavailable, AuthRepository

unittest.defaultTestLoader.testMethodPrefix = "Test"


class SessionTokenTests(unittest.TestCase):
    secret = "test-secret"
    payload = {"iat": 1_000, "exp": 1_100}

    def TestValidTokenReturnsPayload(self) -> None:
        token = SignSession(self.payload, self.secret)

        verified = VerifySession(token, self.secret, timestamp=1_050)

        self.assertIsNotNone(verified)
        assert verified is not None
        self.assertEqual(verified["iat"], self.payload["iat"])
        self.assertEqual(verified["exp"], self.payload["exp"])
        self.assertEqual(len(verified["salt"]), 16)

    def TestExpiredTokenIsRejected(self) -> None:
        token = SignSession(self.payload, self.secret)

        self.assertIsNone(VerifySession(token, self.secret, timestamp=1_101))

    def TestTamperedTokenIsRejected(self) -> None:
        token = SignSession(self.payload, self.secret)

        self.assertIsNone(
            VerifySession(token + "x", self.secret, timestamp=1_050)
        )

    def TestWrongSecretIsRejected(self) -> None:
        token = SignSession(self.payload, self.secret)

        self.assertIsNone(VerifySession(token, "wrong-secret", timestamp=1_050))

    def TestEachTokenHasRandomSalt(self) -> None:
        first = VerifySession(
            SignSession(self.payload, self.secret),
            self.secret,
            timestamp=1_050,
        )
        second = VerifySession(
            SignSession(self.payload, self.secret),
            self.secret,
            timestamp=1_050,
        )

        assert first is not None
        assert second is not None
        self.assertNotEqual(first["salt"], second["salt"])

    def TestRandomStringUsesRequestedLength(self) -> None:
        self.assertEqual(len(RandomString()), 16)
        self.assertEqual(len(RandomString(32)), 32)


class SettingsTests(unittest.TestCase):
    def TestDefaultsToSevenDays(self) -> None:
        loaded = Settings.FromEnv({"SECRET": "secret"})

        self.assertEqual(
            loaded.auth_ttl_seconds, Settings.AUTH_TTL_SECONDS_DEFAULT
        )

    def TestLoadsValuesFromEnvironment(self) -> None:
        loaded = Settings.FromEnv(
            {
                "SECRET": "secret",
                "AUTH_TTL_SECONDS": "90",
                "CACHE_NODES": "cache-a:11211,cache-b:11211",
            }
        )

        self.assertEqual(
            loaded,
            Settings("secret", 90, ("cache-a:11211", "cache-b:11211")),
        )

    def TestRejectsInvalidTtl(self) -> None:
        with self.assertRaises(ValueError):
            Settings.FromEnv(
                {
                    "SECRET": "secret",
                    "AUTH_TTL_SECONDS": "not-a-number",
                }
            )

    def TestDefaultsReplicationToOne(self) -> None:
        loaded = Settings.FromEnv({"SECRET": "secret"})

        self.assertEqual(loaded.replication, Settings.REPLICATION_DEFAULT)

    def TestDefaultsBrandImageCacheTtlToSeventyFiveMinutes(self) -> None:
        loaded = Settings.FromEnv({"SECRET": "secret"})

        self.assertEqual(
            loaded.brand_image_cache_ttl_seconds,
            Settings.BRAND_IMAGE_CACHE_TTL_SECONDS_DEFAULT,
        )

    def TestLoadsBrandImageCacheTtlFromEnvironment(self) -> None:
        loaded = Settings.FromEnv(
            {"SECRET": "secret", "BRAND_IMAGE_CACHE_TTL_SECONDS": "900"}
        )

        self.assertEqual(loaded.brand_image_cache_ttl_seconds, 900)

    def TestRejectsInvalidBrandImageCacheTtl(self) -> None:
        for value in ("0", "-1", "not-a-number"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Settings.FromEnv(
                    {
                        "SECRET": "secret",
                        "BRAND_IMAGE_CACHE_TTL_SECONDS": value,
                    }
                )

    def TestLoadsTheReplicationFromEnvironment(self) -> None:
        loaded = Settings.FromEnv({"SECRET": "secret", "REPLICATION": "2"})

        self.assertEqual(loaded.replication, 2)

    def TestAllowsZeroReplication(self) -> None:
        loaded = Settings.FromEnv({"SECRET": "secret", "REPLICATION": "0"})

        self.assertEqual(loaded.replication, 0)

    def TestRejectsANegativeReplication(self) -> None:
        with self.assertRaises(ValueError):
            Settings.FromEnv({"SECRET": "secret", "REPLICATION": "-1"})

    def TestRejectsANonIntegerReplication(self) -> None:
        with self.assertRaises(ValueError):
            Settings.FromEnv(
                {"SECRET": "secret", "REPLICATION": "not-a-number"}
            )

    def TestDefaultsToNoSentryDsn(self) -> None:
        loaded = Settings.FromEnv({"SECRET": "secret"})

        self.assertIsNone(loaded.sentry_dsn)

    def TestLoadsTheSentryDsnFromEnvironment(self) -> None:
        loaded = Settings.FromEnv(
            {"SECRET": "secret", "SENTRY_DSN": "https://key@sentry.io/1"}
        )

        self.assertEqual(loaded.sentry_dsn, "https://key@sentry.io/1")

    def TestDefaultsTheAssetsGrpcTarget(self) -> None:
        loaded = Settings.FromEnv({"SECRET": "secret"})

        self.assertEqual(
            loaded.assets_grpc_target, Settings.ASSETS_GRPC_TARGET_DEFAULT
        )

    def TestLoadsTheAssetsGrpcTargetFromEnvironment(self) -> None:
        loaded = Settings.FromEnv(
            {"SECRET": "secret", "ASSETS_GRPC_TARGET": "127.0.0.1:50555"}
        )

        self.assertEqual(loaded.assets_grpc_target, "127.0.0.1:50555")

    def TestRejectsAnEmptyAssetsGrpcTarget(self) -> None:
        with self.assertRaises(ValueError):
            Settings.FromEnv({"SECRET": "secret", "ASSETS_GRPC_TARGET": ""})


def WriteCache(
    start: int, replication: int, nodes: tuple[str, ...]
) -> MagicMock:
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


class CachedUserAuthTests(unittest.TestCase):
    password = PasswordHasher(type=Type.ID).hash("correct-password")

    @patch("blackkeys.backends.stores.cache.pylibmc.ClientPool")
    @patch("blackkeys.backends.stores.cache.pylibmc.Client")
    def TestAuthCacheUsesConsistentHashing(
        self, client_constructor: MagicMock, pool_constructor: MagicMock
    ) -> None:
        client = client_constructor.return_value

        cache = MakeAuthCache(("cache-a:11211", "cache-b:11211"))

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
        self.assertEqual(cache.nodes, ("cache-a:11211", "cache-b:11211"))
        self.assertEqual(cache.replication, 1)

    def TestFlatBufferRoundTrip(self) -> None:
        encoded = EncodeUserAuth("alice", self.password)

        decoded = DecodeUserAuth(encoded)

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.username, "alice")
        self.assertEqual(decoded.password, self.password)

    def TestInvalidFlatBufferIsRejected(self) -> None:
        self.assertIsNone(DecodeUserAuth(b"not-a-user-auth-record"))

    def TestUsesExpectedCacheKey(self) -> None:
        self.assertEqual(UserAuthKey("alice"), "auth:user:alice")

    def TestReadsCachedUserWithoutValidatingThePassword(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = EncodeUserAuth("alice", self.password)

        user_auth = ReadUserAuth(cache, "alice")

        self.assertEqual(user_auth, CachedUserAuth("alice", self.password))
        client.get.assert_called_once_with("auth:user:alice")

    def TestWritesThePrimaryAndTheNextSibling(self) -> None:
        nodes = ("cache-a:11211", "cache-b:11211", "cache-c:11211")
        cache = WriteCache(1, 1, nodes)
        user_auth = CachedUserAuth("alice", self.password)

        stored = WriteUserAuth(cache, user_auth)

        self.assertTrue(stored)
        client = cache.reserve.return_value.__enter__.return_value
        client.hash.assert_called_once_with("auth:user:alice")
        client.set.assert_not_called()
        client.disconnect_all.assert_not_called()
        for node in ("cache-b:11211", "cache-c:11211"):
            key, encoded = cache.node_clients[node].set.call_args.args
            self.assertEqual(key, "auth:user:alice")
            self.assertEqual(DecodeUserAuth(encoded), user_auth)
        cache.node_clients["cache-a:11211"].set.assert_not_called()

    def TestWriteWrapsToTheFirstNode(self) -> None:
        nodes = ("cache-a:11211", "cache-b:11211", "cache-c:11211")
        cache = WriteCache(2, 1, nodes)

        self.assertTrue(
            WriteUserAuth(cache, CachedUserAuth("alice", self.password))
        )

        cache.node_clients["cache-c:11211"].set.assert_called_once()
        cache.node_clients["cache-a:11211"].set.assert_called_once()
        cache.node_clients["cache-b:11211"].set.assert_not_called()

    def TestReplicationZeroWritesOnlyThePrimary(self) -> None:
        nodes = ("cache-a:11211", "cache-b:11211", "cache-c:11211")
        cache = WriteCache(0, 0, nodes)

        self.assertTrue(
            WriteUserAuth(cache, CachedUserAuth("alice", self.password))
        )

        cache.node_clients["cache-a:11211"].set.assert_called_once()
        cache.node_clients["cache-b:11211"].set.assert_not_called()
        cache.node_clients["cache-c:11211"].set.assert_not_called()

    def TestWriteReturnsFalseWhenAnyReplicaRejects(self) -> None:
        nodes = ("cache-a:11211", "cache-b:11211")
        cache = WriteCache(0, 1, nodes)
        cache.node_clients["cache-b:11211"].set.return_value = False

        self.assertFalse(
            WriteUserAuth(cache, CachedUserAuth("alice", self.password))
        )

        cache.node_clients["cache-a:11211"].set.assert_called_once()
        cache.node_clients["cache-b:11211"].set.assert_called_once()


class AuthServiceTests(unittest.TestCase):
    password = PasswordHasher(type=Type.ID).hash("correct-password")

    def TestAuthenticatesAnArgon2idPassword(self) -> None:
        repository = AsyncMock(spec=AuthRepository)
        repository.UserBy.return_value = CachedUserAuth("alice", self.password)
        service = AuthService(repository)

        authenticated = asyncio.run(
            service.Authenticate("alice", "correct-password")
        )

        self.assertTrue(authenticated)
        repository.UserBy.assert_awaited_once_with("alice")

    def TestRejectsAWrongPassword(self) -> None:
        repository = AsyncMock(spec=AuthRepository)
        repository.UserBy.return_value = CachedUserAuth("alice", self.password)
        service = AuthService(repository)

        self.assertFalse(
            asyncio.run(service.Authenticate("alice", "wrong-password"))
        )

    def TestRejectsANonArgon2idPassword(self) -> None:
        repository = AsyncMock(spec=AuthRepository)
        repository.UserBy.return_value = CachedUserAuth("alice", "not-argon2id")
        service = AuthService(repository)

        self.assertFalse(
            asyncio.run(service.Authenticate("alice", "correct-password"))
        )

    def TestRejectsAMismatchedUsername(self) -> None:
        repository = AsyncMock(spec=AuthRepository)
        repository.UserBy.return_value = CachedUserAuth("bob", self.password)
        service = AuthService(repository)

        self.assertFalse(
            asyncio.run(service.Authenticate("alice", "correct-password"))
        )


class FakeAuthCursor:
    def __init__(self, row: tuple[str, str] | None) -> None:
        self.row = row

    async def fetchone(self) -> tuple[str, str] | None:
        return self.row


class FakeAuthDatabase:
    def __init__(self, row: tuple[str, str] | None) -> None:
        self.row = row
        self.executed: list[tuple[str, object]] = []

    async def execute(
        self, sql: str, parameters: object = ()
    ) -> FakeAuthCursor:
        self.executed.append((sql, parameters))
        return FakeAuthCursor(self.row)


class FailingAuthDatabase:
    async def execute(self, _: str, __: object = ()) -> None:
        raise RuntimeError("database unavailable")


class AuthRepositoryTests(unittest.TestCase):
    password = PasswordHasher(type=Type.ID).hash("correct-password")
    select_sql = 'SELECT username, password FROM "user" WHERE username = ?'

    def setUp(self) -> None:
        LocalCacheClear()

    def tearDown(self) -> None:
        LocalCacheClear()

    def TestIgnoresLocalCacheAndReadsSharedCache(self) -> None:
        LocalCacheSet(
            UserAuthKey("alice"),
            CachedUserAuth("alice", "stale-local-password"),
        )
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = EncodeUserAuth("alice", self.password)
        db = FakeAuthDatabase(None)
        repository = AuthRepository(cache, None, db)

        found = asyncio.run(repository.UserBy("alice"))

        self.assertEqual(found, CachedUserAuth("alice", self.password))
        self.assertEqual(db.executed, [])
        self.assertEqual(
            LocalCacheGet(UserAuthKey("alice")),
            CachedUserAuth("alice", "stale-local-password"),
        )

    def TestReturnsFromSharedCacheWithoutTouchingTurso(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = EncodeUserAuth("alice", self.password)
        db = FakeAuthDatabase(None)
        repository = AuthRepository(cache, None, db)

        found = asyncio.run(repository.UserBy("alice"))

        self.assertEqual(found, CachedUserAuth("alice", self.password))
        self.assertIsNone(LocalCacheGet(UserAuthKey("alice")))
        self.assertEqual(db.executed, [])
        client.set.assert_not_called()

    def TestFallsBackToTursoAndPopulatesSharedCache(self) -> None:
        nodes = ("cache-a:11211", "cache-b:11211")
        cache = WriteCache(0, 1, nodes)
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = None
        db = FakeAuthDatabase(("alice", self.password))
        repository = AuthRepository(cache, None, db)

        found = asyncio.run(repository.UserBy("alice"))

        self.assertEqual(found, CachedUserAuth("alice", self.password))
        self.assertEqual(db.executed, [(self.select_sql, ("alice",))])
        self.assertIsNone(LocalCacheGet(UserAuthKey("alice")))
        for node in nodes:
            key, encoded = cache.node_clients[node].set.call_args.args
            self.assertEqual(key, UserAuthKey("alice"))
            self.assertEqual(DecodeUserAuth(encoded), found)

    def TestFallsBackToTursoWhenSharedCacheReadFails(self) -> None:
        cache = WriteCache(0, 1, ("cache-a:11211", "cache-b:11211"))
        client = cache.reserve.return_value.__enter__.return_value
        client.get.side_effect = pylibmc.Error("cache unavailable")
        db = FakeAuthDatabase(("alice", self.password))
        repository = AuthRepository(cache, None, db)

        with patch("blackkeys.repositories.logger") as logger:
            found = asyncio.run(repository.UserBy("alice"))

        self.assertEqual(found, CachedUserAuth("alice", self.password))
        self.assertEqual(db.executed, [(self.select_sql, ("alice",))])
        self.assertIsNone(LocalCacheGet(UserAuthKey("alice")))
        logger.warning.assert_called_once_with(
            "auth cache read failed: %s", client.get.side_effect
        )

    def TestKeepsTursoResultWhenSharedCacheWriteFails(self) -> None:
        cache = WriteCache(0, 1, ("cache-a:11211", "cache-b:11211"))
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = None
        error = pylibmc.Error("cache unavailable")
        cache.node_clients["cache-a:11211"].set.side_effect = error
        db = FakeAuthDatabase(("alice", self.password))
        repository = AuthRepository(cache, None, db)

        with patch("blackkeys.repositories.logger") as logger:
            found = asyncio.run(repository.UserBy("alice"))

        self.assertEqual(found, CachedUserAuth("alice", self.password))
        self.assertIsNone(LocalCacheGet(UserAuthKey("alice")))
        logger.warning.assert_called_once_with(
            "auth cache write failed: %s", error
        )

    def TestReturnsNoneWhenTursoDoesNotContainTheUser(self) -> None:
        db = FakeAuthDatabase(None)
        repository = AuthRepository(None, None, db)

        self.assertIsNone(asyncio.run(repository.UserBy("alice")))
        self.assertEqual(db.executed, [(self.select_sql, ("alice",))])

    def TestRaisesWhenNoAuthenticationSourceIsAvailable(self) -> None:
        repository = AuthRepository(None, None)

        with self.assertRaises(AuthenticationUnavailable):
            asyncio.run(repository.UserBy("alice"))

    def TestRaisesWhenTursoQueryFails(self) -> None:
        repository = AuthRepository(None, None, FailingAuthDatabase())

        with (
            patch("blackkeys.repositories.logger") as logger,
            self.assertRaises(AuthenticationUnavailable),
        ):
            asyncio.run(repository.UserBy("alice"))
        logger.warning.assert_called_once()


class SigninTests(unittest.TestCase):
    password = PasswordHasher(type=Type.ID).hash("correct-password")

    def TestSigninReturnsASevenDaySession(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = EncodeUserAuth("alice", self.password)
        request = SimpleNamespace(
            json={"username": "alice", "password": "correct-password"}
        )
        repository = AuthRepository(cache, None)
        service = AuthService(repository)

        with patch("blackkeys.blueprints.auth.auth_service", service):
            response = asyncio.run(SignIn(request))
        token = json.loads(response.body)["token"]

        self.assertEqual(response.status, 200)
        self.assertTrue(token.startswith("blackkeys-v1_"))
        payload = VerifySession(
            token.removeprefix("blackkeys-v1_"), settings.secret
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["sub"], "alice")
        self.assertEqual(
            payload["exp"] - payload["iat"], settings.auth_ttl_seconds
        )

    def TestSigninRejectsWrongPassword(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = EncodeUserAuth("alice", self.password)
        request = SimpleNamespace(
            json={"username": "alice", "password": "wrong-password"}
        )
        repository = AuthRepository(cache, None)
        service = AuthService(repository)

        with patch("blackkeys.blueprints.auth.auth_service", service):
            response = asyncio.run(SignIn(request))

        self.assertEqual(response.status, 401)
        self.assertEqual(
            json.loads(response.body), {"error": "invalid-credentials"}
        )

    def TestSigninRequiresAnAuthenticationSource(self) -> None:
        request = SimpleNamespace(
            json={"username": "alice", "password": "correct-password"}
        )
        repository = AuthRepository(None, None)
        service = AuthService(repository)

        with patch("blackkeys.blueprints.auth.auth_service", service):
            response = asyncio.run(SignIn(request))

        self.assertEqual(response.status, 503)
