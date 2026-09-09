import json
from pathlib import Path

import sanic
import sanic.response
from sanic.log import logger

from blackkeys.blueprints.middlewares import RequireSession

STORES_PATH = Path(__file__).resolve().parents[2] / "stores.json"

blueprint = sanic.Blueprint("stores", url_prefix="/stores", version=1)


def ReadStores() -> list | None:
    try:
        stores = json.loads(STORES_PATH.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        logger.warning("stores snapshot read failed: %s", error)
        return None
    return stores if isinstance(stores, list) else None


@blueprint.get("/list")
@RequireSession
async def List(_: sanic.Request) -> sanic.HTTPResponse:
    stores = ReadStores()
    if stores is None:
        return sanic.response.json({"error": "stores-unavailable"}, status=503)
    return sanic.response.json(stores)
