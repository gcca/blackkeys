from __future__ import annotations

from blackkeys.core.conf import settings
from blackkeys.persistence.turso import (
    CloseDatabase,
    OpenDatabase,
    PushDatabase,
)


async def TursoPushSchema() -> None:
    db = await OpenDatabase(settings)
    if db is None:
        raise RuntimeError("no database connection")
    try:
        await PushDatabase(db)
    finally:
        await CloseDatabase(db)
