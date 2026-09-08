import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from blackkeys.commands.turso_init_schema import TursoInitSchema
from blackkeys.commands.turso_pull_schema import TursoPullSchema
from blackkeys.commands.turso_push_schema import TursoPushSchema
from blackkeys.commands.turso_validate_schema import TursoValidateSchema
from blackkeys.persistence.schema import SchemaValidationError

unittest.defaultTestLoader.testMethodPrefix = "Test"


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
