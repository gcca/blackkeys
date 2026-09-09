import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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

    def TestDefaultsToNoSentryDsn(self) -> None:
        loaded = Settings.FromEnv({"SECRET": "secret"})

        self.assertIsNone(loaded.sentry_dsn)

    def TestLoadsTheSentryDsnFromEnvironment(self) -> None:
        loaded = Settings.FromEnv(
            {"SECRET": "secret", "SENTRY_DSN": "https://key@sentry.io/1"}
        )

        self.assertEqual(loaded.sentry_dsn, "https://key@sentry.io/1")


class CachedUserAuthTests(unittest.TestCase):
    password = PasswordHasher(type=Type.ID).hash("correct-password")

    @patch("blackkeys.backends.stores.cache.pylibmc.ClientPool")
    @patch("blackkeys.backends.stores.cache.pylibmc.Client")
    def TestAuthCacheUsesConsistentHashing(
        self, client_constructor: MagicMock, pool_constructor: MagicMock
    ) -> None:
        client = client_constructor.return_value

        cache = MakeAuthCache(("cache-a:11211", "cache-b:11211"))

        client_constructor.assert_called_once_with(
            ["cache-a:11211", "cache-b:11211"],
            binary=True,
            behaviors={"ketama": True, "num_replicas": 1},
        )
        pool_constructor.assert_called_once_with(client, 4)
        self.assertIs(cache, pool_constructor.return_value)

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

    def TestWritesCachedUser(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.set.return_value = True
        user_auth = CachedUserAuth("alice", self.password)

        stored = WriteUserAuth(cache, user_auth)

        self.assertTrue(stored)
        key, encoded = client.set.call_args.args
        self.assertEqual(key, "auth:user:alice")
        self.assertEqual(DecodeUserAuth(encoded), user_auth)


class AuthServiceTests(unittest.TestCase):
    password = PasswordHasher(type=Type.ID).hash("correct-password")

    def TestAuthenticatesAnArgon2idPassword(self) -> None:
        repository = AsyncMock(spec=AuthRepository)
        repository.By.return_value = CachedUserAuth("alice", self.password)
        service = AuthService(repository)

        authenticated = asyncio.run(
            service.Authenticate("alice", "correct-password")
        )

        self.assertTrue(authenticated)
        repository.By.assert_awaited_once_with("alice")

    def TestRejectsAWrongPassword(self) -> None:
        repository = AsyncMock(spec=AuthRepository)
        repository.By.return_value = CachedUserAuth("alice", self.password)
        service = AuthService(repository)

        self.assertFalse(
            asyncio.run(service.Authenticate("alice", "wrong-password"))
        )

    def TestRejectsANonArgon2idPassword(self) -> None:
        repository = AsyncMock(spec=AuthRepository)
        repository.By.return_value = CachedUserAuth("alice", "not-argon2id")
        service = AuthService(repository)

        self.assertFalse(
            asyncio.run(service.Authenticate("alice", "correct-password"))
        )

    def TestRejectsAMismatchedUsername(self) -> None:
        repository = AsyncMock(spec=AuthRepository)
        repository.By.return_value = CachedUserAuth("bob", self.password)
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

    def TestReturnsFromLocalCacheFirst(self) -> None:
        user_auth = CachedUserAuth("alice", self.password)
        LocalCacheSet(UserAuthKey("alice"), user_auth)
        cache = MagicMock()
        db = FakeAuthDatabase(None)
        repository = AuthRepository(cache, None, db)

        found = asyncio.run(repository.By("alice"))

        self.assertEqual(found, user_auth)
        cache.reserve.assert_not_called()
        self.assertEqual(db.executed, [])

    def TestReturnsFromSharedCacheAndPopulatesLocalCache(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = EncodeUserAuth("alice", self.password)
        db = FakeAuthDatabase(None)
        repository = AuthRepository(cache, None, db)

        found = asyncio.run(repository.By("alice"))

        self.assertEqual(found, CachedUserAuth("alice", self.password))
        self.assertEqual(LocalCacheGet(UserAuthKey("alice")), found)
        self.assertEqual(db.executed, [])

    def TestFallsBackToTursoAndPopulatesBothCaches(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = None
        client.set.return_value = True
        db = FakeAuthDatabase(("alice", self.password))
        repository = AuthRepository(cache, None, db)

        found = asyncio.run(repository.By("alice"))

        self.assertEqual(found, CachedUserAuth("alice", self.password))
        self.assertEqual(db.executed, [(self.select_sql, ("alice",))])
        self.assertEqual(LocalCacheGet(UserAuthKey("alice")), found)
        key, encoded = client.set.call_args.args
        self.assertEqual(key, UserAuthKey("alice"))
        self.assertEqual(DecodeUserAuth(encoded), found)

    def TestFallsBackToTursoWhenSharedCacheReadFails(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.side_effect = pylibmc.Error("cache unavailable")
        client.set.return_value = True
        db = FakeAuthDatabase(("alice", self.password))
        repository = AuthRepository(cache, None, db)

        with patch("blackkeys.repositories.logger") as logger:
            found = asyncio.run(repository.By("alice"))

        self.assertEqual(found, CachedUserAuth("alice", self.password))
        self.assertEqual(db.executed, [(self.select_sql, ("alice",))])
        self.assertEqual(LocalCacheGet(UserAuthKey("alice")), found)
        logger.warning.assert_called_once_with(
            "auth cache read failed: %s", client.get.side_effect
        )

    def TestKeepsTursoResultWhenSharedCacheWriteFails(self) -> None:
        cache = MagicMock()
        client = cache.reserve.return_value.__enter__.return_value
        client.get.return_value = None
        client.set.side_effect = pylibmc.Error("cache unavailable")
        db = FakeAuthDatabase(("alice", self.password))
        repository = AuthRepository(cache, None, db)

        with patch("blackkeys.repositories.logger") as logger:
            found = asyncio.run(repository.By("alice"))

        self.assertEqual(found, CachedUserAuth("alice", self.password))
        self.assertEqual(LocalCacheGet(UserAuthKey("alice")), found)
        logger.warning.assert_called_once_with(
            "auth cache write failed: %s", client.set.side_effect
        )

    def TestReturnsNoneWhenTursoDoesNotContainTheUser(self) -> None:
        db = FakeAuthDatabase(None)
        repository = AuthRepository(None, None, db)

        self.assertIsNone(asyncio.run(repository.By("alice")))
        self.assertEqual(db.executed, [(self.select_sql, ("alice",))])

    def TestRaisesWhenNoAuthenticationSourceIsAvailable(self) -> None:
        repository = AuthRepository(None, None)

        with self.assertRaises(AuthenticationUnavailable):
            asyncio.run(repository.By("alice"))

    def TestRaisesWhenTursoQueryFails(self) -> None:
        repository = AuthRepository(None, None, FailingAuthDatabase())

        with (
            patch("blackkeys.repositories.logger") as logger,
            self.assertRaises(AuthenticationUnavailable),
        ):
            asyncio.run(repository.By("alice"))
        logger.warning.assert_called_once()


class SigninTests(unittest.TestCase):
    password = PasswordHasher(type=Type.ID).hash("correct-password")

    def setUp(self) -> None:
        LocalCacheClear()

    def tearDown(self) -> None:
        LocalCacheClear()

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
