from __future__ import annotations

from blackkeys.core.conf import settings
from blackkeys.persistence.schema import ValidateSchema
from blackkeys.persistence.turso import (
    CloseDatabase,
    OpenDatabase,
    PullDatabase,
)


async def TursoValidateSchema() -> None:
    db = await OpenDatabase(settings)
    if db is None:
        raise RuntimeError("no database connection")
    try:
        await PullDatabase(db)
        await ValidateSchema(db)
    finally:
        await CloseDatabase(db)
