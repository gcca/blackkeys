import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from turso.lib_aio import connect as connect_local

from blackkeys.blueprints.index import Close, Pull, StartMonitor
from blackkeys.core.conf import Settings, settings
from blackkeys.persistence.schema import (
    InitSchema,
    SchemaValidationError,
    ValidateSchema,
)
from blackkeys.persistence.turso import (
    CloseDatabase,
    OpenDatabase,
    PullDatabase,
    PushDatabase,
)

unittest.defaultTestLoader.testMethodPrefix = "Test"


class FakeCursor:
    def __init__(self, rows: list[object] | None = None) -> None:
        self._rows = list(rows or [])

    async def fetchone(self) -> object | None:
        if not self._rows:
            return None
        return self._rows.pop(0)

    async def fetchall(self) -> list[object]:
        rows = self._rows
        self._rows = []
        return rows


class FakeDatabase:
    def __init__(
        self,
        *,
        pull_error: Exception | None = None,
        push_error: Exception | None = None,
        has_pull: bool = True,
        has_push: bool = True,
        execute_map: dict[str, FakeCursor] | None = None,
    ) -> None:
        self.closed = False
        self.pulled = 0
        self.pushed = 0
        self.executed: list[tuple[str, object]] = []
        self.pull_error = pull_error
        self.push_error = push_error
        self.has_pull = has_pull
        self.has_push = has_push
        self.execute_map = execute_map or {}

    async def pull(self) -> bool:
        if self.pull_error is not None:
            raise self.pull_error
        self.pulled += 1
        return True

    async def push(self) -> bool:
        if self.push_error is not None:
            raise self.push_error
        self.pushed += 1
        return True

    async def close(self) -> None:
        self.closed = True

    async def execute(self, sql: str, parameters: object = ()) -> FakeCursor:
        self.executed.append((sql, parameters))
        for prefix, cursor in self.execute_map.items():
            if sql.startswith(prefix):
                return cursor
        return FakeCursor()

    def __getattribute__(self, name: str):
        if name == "pull" and not object.__getattribute__(self, "has_pull"):
            raise AttributeError(name)
        if name == "push" and not object.__getattribute__(self, "has_push"):
            raise AttributeError(name)
        return object.__getattribute__(self, name)


class OpenDatabaseTests(unittest.TestCase):
    def TestOpensLocalConnectionWhenUrlIsUnset(self) -> None:
        settings = Settings.FromEnv({"SECRET": "secret"})
        db = FakeDatabase(has_pull=False)

        with patch(
            "blackkeys.persistence.turso.connect_local",
            AsyncMock(return_value=db),
        ) as connect_local, patch(
            "blackkeys.persistence.turso.connect_sync",
            AsyncMock(),
        ) as connect_sync:
            opened = asyncio.run(OpenDatabase(settings))

        self.assertIs(opened, db)
        connect_local.assert_awaited_once_with(settings.turso_local_path)
        connect_sync.assert_not_called()

    def TestOpensSyncConnectionWhenUrlIsSet(self) -> None:
        settings = Settings.FromEnv(
            {
                "SECRET": "secret",
                "TURSO_DATABASE_URL": "https://example.turso.io",
                "TURSO_AUTH_TOKEN": "token",
                "TURSO_LOCAL_PATH": "scratch.db",
            }
        )
        db = FakeDatabase()

        with patch(
            "blackkeys.persistence.turso.connect_sync",
            AsyncMock(return_value=db),
        ) as connect_sync, patch(
            "blackkeys.persistence.turso.connect_local",
            AsyncMock(),
        ) as connect_local:
            opened = asyncio.run(OpenDatabase(settings))

        self.assertIs(opened, db)
        connect_sync.assert_awaited_once_with(
            "scratch.db",
            "https://example.turso.io",
            auth_token="token",
        )
        connect_local.assert_not_called()

    def TestReturnsNoneWhenOpenFails(self) -> None:
        settings = Settings.FromEnv({"SECRET": "secret"})

        with patch(
            "blackkeys.persistence.turso.connect_local",
            AsyncMock(side_effect=RuntimeError("unavailable")),
        ), patch("blackkeys.persistence.turso.logger") as logger:
            opened = asyncio.run(OpenDatabase(settings))

        self.assertIsNone(opened)
        logger.warning.assert_called_once()


class PullDatabaseTests(unittest.TestCase):
    def TestPullsWhenConnectionSupportsIt(self) -> None:
        db = FakeDatabase()

        asyncio.run(PullDatabase(db))

        self.assertEqual(db.pulled, 1)

    def TestSkipsWhenConnectionHasNoPull(self) -> None:
        db = FakeDatabase(has_pull=False)

        asyncio.run(PullDatabase(db))

        self.assertEqual(db.pulled, 0)

    def TestSkipsWhenConnectionIsMissing(self) -> None:
        asyncio.run(PullDatabase(None))

    def TestWarnsWhenPullFails(self) -> None:
        db = FakeDatabase(pull_error=RuntimeError("no route"))

        with patch("blackkeys.persistence.turso.logger") as logger:
            asyncio.run(PullDatabase(db))

        logger.warning.assert_called_once()
        self.assertEqual(db.pulled, 0)


class PushDatabaseTests(unittest.TestCase):
    def TestPushesWhenConnectionSupportsIt(self) -> None:
        db = FakeDatabase()

        asyncio.run(PushDatabase(db))

        self.assertEqual(db.pushed, 1)

    def TestSkipsWhenConnectionHasNoPush(self) -> None:
        db = FakeDatabase(has_push=False)

        asyncio.run(PushDatabase(db))

        self.assertEqual(db.pushed, 0)

    def TestSkipsWhenConnectionIsMissing(self) -> None:
        asyncio.run(PushDatabase(None))

    def TestWarnsWhenPushFails(self) -> None:
        db = FakeDatabase(push_error=RuntimeError("no route"))

        with patch("blackkeys.persistence.turso.logger") as logger:
            asyncio.run(PushDatabase(db))

        logger.warning.assert_called_once()
        self.assertEqual(db.pushed, 0)


class CloseDatabaseTests(unittest.TestCase):
    def TestClosesAnOpenConnection(self) -> None:
        db = FakeDatabase()

        asyncio.run(CloseDatabase(db))

        self.assertTrue(db.closed)

    def TestSkipsWhenConnectionIsMissing(self) -> None:
        asyncio.run(CloseDatabase(None))


class ValidateSchemaTests(unittest.TestCase):
    def TestSkipsWhenSchemaIsEmpty(self) -> None:
        db = FakeDatabase()

        with patch("blackkeys.persistence.schema.EXPECTED_SCHEMA", {}):
            asyncio.run(ValidateSchema(db))

        self.assertEqual(db.executed, [])

    def TestSkipsWhenConnectionIsMissing(self) -> None:
        asyncio.run(ValidateSchema(None))

    def TestRejectsAMissingTable(self) -> None:
        db = FakeDatabase(
            execute_map={"SELECT name FROM sqlite_master": FakeCursor([])}
        )

        with patch(
            "blackkeys.persistence.schema.EXPECTED_SCHEMA",
            {"user": frozenset({"id"})},
        ), self.assertRaises(SchemaValidationError) as raised:
            asyncio.run(ValidateSchema(db))

        self.assertIn("missing table 'user'", str(raised.exception))

    def TestRejectsMissingColumns(self) -> None:
        db = FakeDatabase(
            execute_map={
                "SELECT name FROM sqlite_master": FakeCursor([("user",)]),
                "PRAGMA table_info": FakeCursor([(0, "id")]),
            }
        )

        with patch(
            "blackkeys.persistence.schema.EXPECTED_SCHEMA",
            {"user": frozenset({"id", "username"})},
        ), self.assertRaises(SchemaValidationError) as raised:
            asyncio.run(ValidateSchema(db))

        self.assertIn("missing columns: username", str(raised.exception))

    def TestRejectsInvalidCreatedAtDefinition(self) -> None:
        cases = (
            ("TEXT", 1, "(unixepoch())", "must use INTEGER"),
            ("INTEGER", 0, "(unixepoch())", "must be NOT NULL"),
            ("INTEGER", 1, "(datetime('now'))", "must default"),
        )
        for column_type, not_null, default, expected in cases:
            with self.subTest(expected=expected):
                db = FakeDatabase(
                    execute_map={
                        "SELECT name FROM sqlite_master": FakeCursor(
                            [("user",)]
                        ),
                        "PRAGMA table_info": FakeCursor(
                            [
                                (0, "username", "TEXT", 1, None, 1),
                                (1, "password", "TEXT", 1, None, 0),
                                (2, "email", "TEXT", 1, None, 0),
                                (
                                    3,
                                    "created_at",
                                    column_type,
                                    not_null,
                                    default,
                                    0,
                                ),
                            ]
                        ),
                    }
                )

                with self.assertRaises(SchemaValidationError) as raised:
                    asyncio.run(ValidateSchema(db))

                self.assertIn(expected, str(raised.exception))

    def TestAcceptsAMatchingSchema(self) -> None:
        db = FakeDatabase(
            execute_map={
                "SELECT name FROM sqlite_master": FakeCursor([("user",)]),
                "PRAGMA table_info": FakeCursor(
                    [
                        (0, "username", "TEXT", 1, None, 1),
                        (1, "password", "TEXT", 1, None, 0),
                        (2, "email", "TEXT", 1, None, 0),
                        (3, "created_at", "INTEGER", 1, "(unixepoch ())", 0),
                    ]
                ),
            }
        )

        asyncio.run(ValidateSchema(db))


class InitSchemaTests(unittest.TestCase):
    def TestSkipsWhenConnectionIsMissing(self) -> None:
        asyncio.run(InitSchema(None))

    def TestCreatesEachTable(self) -> None:
        db = FakeDatabase()

        with patch(
            "blackkeys.persistence.schema.TABLE_DDL",
            {"user": 'CREATE TABLE IF NOT EXISTS "user" (username TEXT)'},
        ):
            asyncio.run(InitSchema(db))

        self.assertEqual(
            db.executed,
            [('CREATE TABLE IF NOT EXISTS "user" (username TEXT)', ())],
        )


class SchemaIntegrationTests(unittest.TestCase):
    def TestCreatesFreshSchemaWithEpochTimestamp(self) -> None:
        async def CreateAndRead(path: str) -> tuple[object, list[object]]:
            db = await connect_local(path)
            try:
                await InitSchema(db)
                await ValidateSchema(db)
                await db.execute(
                    'INSERT INTO "user" (username, password, email) '
                    "VALUES (?, ?, ?)",
                    ("alice", "hash", "alice@example.com"),
                )
                await db.commit()
                timestamp = await (
                    await db.execute(
                        "SELECT typeof(created_at), created_at, unixepoch() "
                        'FROM "user"'
                    )
                ).fetchone()
                tables = await (
                    await db.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='user'"
                    )
                ).fetchall()
                return timestamp, tables
            finally:
                await db.close()

        with tempfile.TemporaryDirectory() as directory:
            timestamp, tables = asyncio.run(
                CreateAndRead(str(Path(directory) / "schema.db"))
            )

        self.assertEqual(tables, [("user",)])
        self.assertEqual(timestamp[0], "integer")
        self.assertLessEqual(abs(timestamp[1] - timestamp[2]), 1)


class IndexLifecycleTests(unittest.TestCase):
    def TestPullStoresDbOnAppContext(self) -> None:
        db = FakeDatabase()
        app = SimpleNamespace(ctx=SimpleNamespace())

        with patch(
            "blackkeys.blueprints.index.OpenDatabase",
            AsyncMock(return_value=db),
        ), patch(
            "blackkeys.blueprints.index.PullDatabase",
            AsyncMock(),
        ) as pull, patch(
            "blackkeys.blueprints.index.ValidateSchema",
            AsyncMock(),
        ) as validate:
            asyncio.run(Pull(app))

        self.assertIs(app.ctx.db, db)
        pull.assert_awaited_once_with(db)
        validate.assert_awaited_once_with(db)

    def TestPullStoresNoneWhenOpenFails(self) -> None:
        app = SimpleNamespace(ctx=SimpleNamespace())

        with patch(
            "blackkeys.blueprints.index.OpenDatabase",
            AsyncMock(return_value=None),
        ), patch(
            "blackkeys.blueprints.index.PullDatabase",
            AsyncMock(),
        ) as pull, patch(
            "blackkeys.blueprints.index.ValidateSchema",
            AsyncMock(),
        ) as validate:
            asyncio.run(Pull(app))

        self.assertIsNone(app.ctx.db)
        pull.assert_awaited_once_with(None)
        validate.assert_awaited_once_with(None)

    def TestCloseClearsAppContext(self) -> None:
        db = FakeDatabase()
        app = SimpleNamespace(ctx=SimpleNamespace(db=db))

        with patch(
            "blackkeys.blueprints.index.CloseDatabase",
            AsyncMock(),
        ) as close:
            asyncio.run(Close(app))

        close.assert_awaited_once_with(db)
        self.assertIsNone(app.ctx.db)

    def TestStartMonitorInitializesAndNotifiesOnce(self) -> None:
        app = SimpleNamespace(ctx=SimpleNamespace())

        with patch(
            "blackkeys.blueprints.index.InitMonitor",
        ) as init_monitor, patch(
            "blackkeys.blueprints.index.NotifyServerStarted",
        ) as notify:
            asyncio.run(StartMonitor(app))

        init_monitor.assert_called_once_with(settings)
        notify.assert_called_once_with()
