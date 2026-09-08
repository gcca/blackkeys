from __future__ import annotations

from blackkeys.core.conf import settings
from blackkeys.persistence.turso import (
    CloseDatabase,
    OpenDatabase,
    PullDatabase,
)


async def TursoPullSchema() -> None:
    db = await OpenDatabase(settings)
    if db is None:
        raise RuntimeError("no database connection")
    try:
        await PullDatabase(db)
    finally:
        await CloseDatabase(db)
