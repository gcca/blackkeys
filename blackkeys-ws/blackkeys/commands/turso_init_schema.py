from __future__ import annotations

from blackkeys.core.conf import settings
from blackkeys.persistence.schema import InitSchema, ValidateSchema
from blackkeys.persistence.turso import (
    CloseDatabase,
    OpenDatabase,
    PullDatabase,
    PushDatabase,
)


async def TursoInitSchema() -> None:
    db = await OpenDatabase(settings)
    if db is None:
        raise RuntimeError("no database connection")
    try:
        await PullDatabase(db)
        await InitSchema(db)
        await PushDatabase(db)
        await ValidateSchema(db)
    finally:
        await CloseDatabase(db)
