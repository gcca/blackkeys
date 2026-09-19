import asyncio
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from argon2 import PasswordHasher
from turso.lib_aio import connect as connect_local

import ws
from blackkeys.commands.boot import Main, RunCommand
from blackkeys.commands.local_create_user import LocalCreateUser
from blackkeys.commands.turso_init_schema import TursoInitSchema
from blackkeys.commands.turso_pull_schema import TursoPullSchema
from blackkeys.commands.turso_push_schema import TursoPushSchema
from blackkeys.commands.turso_validate_schema import TursoValidateSchema
from blackkeys.persistence.schema import InitSchema, SchemaValidationError

unittest.defaultTestLoader.testMethodPrefix = "Test"


class LocalCreateUserTests(unittest.TestCase):
    def TestRegistersTheCommandAndLongOptionParameters(self) -> None:
        commands = {
            command.name: command.func for command in ws.app._future_commands
        }

        self.assertIs(
            inspect.unwrap(commands["local-create_user"]), LocalCreateUser
        )
        self.assertEqual(
            list(inspect.signature(LocalCreateUser).parameters),
            ["username", "password", "email", "db"],
        )
        self.assertEqual(
            inspect.signature(LocalCreateUser).parameters["db"].default,
            "./blackkeys.db",
        )

    def TestInsertsArgon2idCredentialsIntoTheSuppliedDatabase(self) -> None:
        async def CreateAndRead(path: str) -> tuple[str, str, str]:
            db = await connect_local(path)
            try:
                await InitSchema(db)
            finally:
                await db.close()

            await LocalCreateUser(
                "alice", "correct-password", "alice@example.com", path
            )

            db = await connect_local(path)
            try:
                row = await (
                    await db.execute(
                        'SELECT username, password, email FROM "user"'
                    )
                ).fetchone()
                assert row is not None
                return row
            finally:
                await db.close()

        with tempfile.TemporaryDirectory() as directory:
            row = asyncio.run(CreateAndRead(str(Path(directory) / "users.db")))

        self.assertEqual(row[0], "alice")
        self.assertEqual(row[2], "alice@example.com")
        self.assertTrue(row[1].startswith("$argon2id$"))
        self.assertTrue(PasswordHasher().verify(row[1], "correct-password"))

    def TestClosesConnectionWhenInsertFails(self) -> None:
        connection = AsyncMock()
        connection.execute.side_effect = RuntimeError("write failed")

        with patch(
            "blackkeys.commands.local_create_user.connect_local",
            AsyncMock(return_value=connection),
        ) as connect, self.assertRaisesRegex(RuntimeError, "write failed"):
            asyncio.run(
                LocalCreateUser(
                    "alice", "correct-password", "alice@example.com", "users.db"
                )
            )

        connect.assert_awaited_once_with("users.db")
        connection.close.assert_awaited_once_with()
        connection.commit.assert_not_awaited()

    def TestClosesConnectionAfterSuccessfulInsert(self) -> None:
        connection = AsyncMock()

        with patch(
            "blackkeys.commands.local_create_user.connect_local",
            AsyncMock(return_value=connection),
        ):
            asyncio.run(
                LocalCreateUser(
                    "alice", "correct-password", "alice@example.com"
                )
            )

        self.assertEqual(connection.execute.await_count, 1)
        self.assertEqual(connection.commit.await_count, 1)
        connection.close.assert_awaited_once_with()

    def TestRejectsEmptyPasswordAndEmail(self) -> None:
        for password, email in (("", "alice@example.com"), ("password", "")):
            with self.subTest(
                password=password, email=email
            ), self.assertRaises(ValueError):
                asyncio.run(LocalCreateUser("alice", password, email))

    def TestDoesNotCreateSchemaOrReplaceDuplicateUsers(self) -> None:
        async def Exercise(path: str) -> tuple[int, str, str]:
            with self.assertRaises(Exception):
                await LocalCreateUser(
                    "alice", "correct-password", "alice@example.com", path
                )

            db = await connect_local(path)
            try:
                await InitSchema(db)
            finally:
                await db.close()

            await LocalCreateUser(
                "alice", "correct-password", "alice@example.com", path
            )
            with self.assertRaises(Exception):
                await LocalCreateUser(
                    "alice", "replacement", "new@example.com", path
                )

            db = await connect_local(path)
            try:
                row = await (
                    await db.execute(
                        'SELECT COUNT(*), password, email FROM "user"'
                    )
                ).fetchone()
                assert row is not None
                return row
            finally:
                await db.close()

        with tempfile.TemporaryDirectory() as directory:
            count = asyncio.run(Exercise(str(Path(directory) / "users.db")))

        self.assertEqual(count[0], 1)
        self.assertEqual(count[2], "alice@example.com")
        self.assertTrue(PasswordHasher().verify(count[1], "correct-password"))


class TursoValidateSchemaTests(unittest.TestCase):
    def TestOpensPullsValidatesAndCloses(self) -> None:
        db = object()

        with patch(
            "blackkeys.commands.turso_validate_schema.OpenDatabase",
            AsyncMock(return_value=db),
        ), patch(
            "blackkeys.commands.turso_validate_schema.PullDatabase",
            AsyncMock(),
        ) as pull, patch(
            "blackkeys.commands.turso_validate_schema.ValidateSchema",
            AsyncMock(),
        ) as validate, patch(
            "blackkeys.commands.turso_validate_schema.CloseDatabase",
            AsyncMock(),
        ) as close:
            asyncio.run(TursoValidateSchema())

        pull.assert_awaited_once_with(db)
        validate.assert_awaited_once_with(db)
        close.assert_awaited_once_with(db)

    def TestRaisesWhenDatabaseIsUnavailable(self) -> None:
        with patch(
            "blackkeys.commands.turso_validate_schema.OpenDatabase",
            AsyncMock(return_value=None),
        ), patch(
            "blackkeys.commands.turso_validate_schema.ValidateSchema",
            AsyncMock(),
        ) as validate, patch(
            "blackkeys.commands.turso_validate_schema.CloseDatabase",
            AsyncMock(),
        ) as close, self.assertRaises(
            RuntimeError
        ):
            asyncio.run(TursoValidateSchema())

        validate.assert_not_called()
        close.assert_not_called()

    def TestClosesAndReraisesOnValidationFailure(self) -> None:
        db = object()

        with patch(
            "blackkeys.commands.turso_validate_schema.OpenDatabase",
            AsyncMock(return_value=db),
        ), patch(
            "blackkeys.commands.turso_validate_schema.PullDatabase",
            AsyncMock(),
        ), patch(
            "blackkeys.commands.turso_validate_schema.ValidateSchema",
            AsyncMock(side_effect=SchemaValidationError("missing table")),
        ), patch(
            "blackkeys.commands.turso_validate_schema.CloseDatabase",
            AsyncMock(),
        ) as close, self.assertRaises(
            SchemaValidationError
        ):
            asyncio.run(TursoValidateSchema())

        close.assert_awaited_once_with(db)


class TursoPushSchemaTests(unittest.TestCase):
    def TestOpensPushesAndCloses(self) -> None:
        db = object()

        with patch(
            "blackkeys.commands.turso_push_schema.OpenDatabase",
            AsyncMock(return_value=db),
        ), patch(
            "blackkeys.commands.turso_push_schema.PushDatabase",
            AsyncMock(),
        ) as push, patch(
            "blackkeys.commands.turso_push_schema.CloseDatabase",
            AsyncMock(),
        ) as close:
            asyncio.run(TursoPushSchema())

        push.assert_awaited_once_with(db)
        close.assert_awaited_once_with(db)

    def TestRaisesWhenDatabaseIsUnavailable(self) -> None:
        with patch(
            "blackkeys.commands.turso_push_schema.OpenDatabase",
            AsyncMock(return_value=None),
        ), patch(
            "blackkeys.commands.turso_push_schema.PushDatabase",
            AsyncMock(),
        ) as push, patch(
            "blackkeys.commands.turso_push_schema.CloseDatabase",
            AsyncMock(),
        ) as close, self.assertRaises(
            RuntimeError
        ):
            asyncio.run(TursoPushSchema())

        push.assert_not_called()
        close.assert_not_called()


class TursoPullSchemaTests(unittest.TestCase):
    def TestOpensPullsAndCloses(self) -> None:
        db = object()

        with patch(
            "blackkeys.commands.turso_pull_schema.OpenDatabase",
            AsyncMock(return_value=db),
        ), patch(
            "blackkeys.commands.turso_pull_schema.PullDatabase",
            AsyncMock(),
        ) as pull, patch(
            "blackkeys.commands.turso_pull_schema.CloseDatabase",
            AsyncMock(),
        ) as close:
            asyncio.run(TursoPullSchema())

        pull.assert_awaited_once_with(db)
        close.assert_awaited_once_with(db)

    def TestRaisesWhenDatabaseIsUnavailable(self) -> None:
        with patch(
            "blackkeys.commands.turso_pull_schema.OpenDatabase",
            AsyncMock(return_value=None),
        ), patch(
            "blackkeys.commands.turso_pull_schema.PullDatabase",
            AsyncMock(),
        ) as pull, patch(
            "blackkeys.commands.turso_pull_schema.CloseDatabase",
            AsyncMock(),
        ) as close, self.assertRaises(
            RuntimeError
        ):
            asyncio.run(TursoPullSchema())

        pull.assert_not_called()
        close.assert_not_called()


class TursoInitSchemaTests(unittest.TestCase):
    def TestOpensPullsInitsPushesValidatesAndCloses(self) -> None:
        db = object()

        with patch(
            "blackkeys.commands.turso_init_schema.OpenDatabase",
            AsyncMock(return_value=db),
        ), patch(
            "blackkeys.commands.turso_init_schema.PullDatabase",
            AsyncMock(),
        ) as pull, patch(
            "blackkeys.commands.turso_init_schema.InitSchema",
            AsyncMock(),
        ) as init, patch(
            "blackkeys.commands.turso_init_schema.PushDatabase",
            AsyncMock(),
        ) as push, patch(
            "blackkeys.commands.turso_init_schema.ValidateSchema",
            AsyncMock(),
        ) as validate, patch(
            "blackkeys.commands.turso_init_schema.CloseDatabase",
            AsyncMock(),
        ) as close:
            asyncio.run(TursoInitSchema())

        pull.assert_awaited_once_with(db)
        init.assert_awaited_once_with(db)
        push.assert_awaited_once_with(db)
        validate.assert_awaited_once_with(db)
        close.assert_awaited_once_with(db)

    def TestRaisesWhenDatabaseIsUnavailable(self) -> None:
        with patch(
            "blackkeys.commands.turso_init_schema.OpenDatabase",
            AsyncMock(return_value=None),
        ), patch(
            "blackkeys.commands.turso_init_schema.InitSchema",
            AsyncMock(),
        ) as init, patch(
            "blackkeys.commands.turso_init_schema.CloseDatabase",
            AsyncMock(),
        ) as close, self.assertRaises(
            RuntimeError
        ):
            asyncio.run(TursoInitSchema())

        init.assert_not_called()
        close.assert_not_called()

    def TestClosesAndReraisesWhenValidationFailsAfterInit(self) -> None:
        db = object()

        with patch(
            "blackkeys.commands.turso_init_schema.OpenDatabase",
            AsyncMock(return_value=db),
        ), patch(
            "blackkeys.commands.turso_init_schema.PullDatabase",
            AsyncMock(),
        ), patch(
            "blackkeys.commands.turso_init_schema.InitSchema",
            AsyncMock(),
        ) as init, patch(
            "blackkeys.commands.turso_init_schema.PushDatabase",
            AsyncMock(),
        ) as push, patch(
            "blackkeys.commands.turso_init_schema.ValidateSchema",
            AsyncMock(side_effect=SchemaValidationError("missing table")),
        ), patch(
            "blackkeys.commands.turso_init_schema.CloseDatabase",
            AsyncMock(),
        ) as close, self.assertRaises(
            SchemaValidationError
        ):
            asyncio.run(TursoInitSchema())

        init.assert_awaited_once_with(db)
        push.assert_awaited_once_with(db)
        close.assert_awaited_once_with(db)


class BootTests(unittest.TestCase):
    def TestRunCommandInvokesSanicExec(self) -> None:
        with patch("blackkeys.commands.boot.subprocess.run") as run:
            RunCommand("turso-pull_schema")

        run.assert_called_once_with(
            [
                sys.executable,
                "-m",
                "sanic",
                "ws:app",
                "exec",
                "turso-pull_schema",
            ],
            check=True,
        )

    def TestMainRunsPullThenInitThenExecvSanic(self) -> None:
        with patch(
            "blackkeys.commands.boot.sys.argv",
            ["boot", "ws:app", "--host=0.0.0.0", "--port=8000"],
        ), patch("blackkeys.commands.boot.RunCommand") as run_command, patch(
            "blackkeys.commands.boot.os.execv"
        ) as execv:
            Main()

        self.assertEqual(
            [call.args[0] for call in run_command.call_args_list],
            ["turso-pull_schema", "turso-init_schema"],
        )
        execv.assert_called_once_with(
            sys.executable,
            [
                sys.executable,
                "-m",
                "sanic",
                "ws:app",
                "--host=0.0.0.0",
                "--port=8000",
            ],
        )

    def TestMainSkipsPrepareWhenArgvIsExec(self) -> None:
        with patch(
            "blackkeys.commands.boot.sys.argv",
            ["boot", "ws:app", "exec", "turso-pull_schema"],
        ), patch("blackkeys.commands.boot.RunCommand") as run_command, patch(
            "blackkeys.commands.boot.os.execv"
        ) as execv:
            Main()

        run_command.assert_not_called()
        execv.assert_called_once_with(
            sys.executable,
            [
                sys.executable,
                "-m",
                "sanic",
                "ws:app",
                "exec",
                "turso-pull_schema",
            ],
        )
