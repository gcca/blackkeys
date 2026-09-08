from __future__ import annotations

from sanic.log import logger
from turso.lib_aio import Connection
from turso.lib_aio import connect as connect_local
from turso.lib_sync_aio import connect_sync

from blackkeys.core.conf import Settings


async def OpenDatabase(settings: Settings) -> Connection | None:
    try:
        if settings.turso_database_url is None:
            return await connect_local(settings.turso_local_path)
        return await connect_sync(
            settings.turso_local_path,
            settings.turso_database_url,
            auth_token=settings.turso_auth_token,
        )
    except Exception as error:
        logger.warning("turso open failed at startup: %s", error)
        return None


async def PullDatabase(db: Connection | None) -> None:
    if db is None:
        return
    pull = getattr(db, "pull", None)
    if pull is None:
        return
    try:
        await pull()
    except Exception as error:
        logger.warning("turso pull failed at startup: %s", error)


async def PushDatabase(db: Connection | None) -> None:
    if db is None:
        return
    push = getattr(db, "push", None)
    if push is None:
        return
    try:
        await push()
    except Exception as error:
        logger.warning("turso push failed: %s", error)


async def CloseDatabase(db: Connection | None) -> None:
    if db is None:
        return
    await db.close()
