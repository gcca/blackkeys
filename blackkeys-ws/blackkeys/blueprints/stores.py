import sanic
import sanic.response

from blackkeys.blueprints.middlewares import RequireSession
from blackkeys.core.conf import settings
from blackkeys.repositories import MakeStoresRepository

blueprint = sanic.Blueprint("stores", url_prefix="/stores", version=1)
stores_repository = MakeStoresRepository(settings)


@blueprint.before_server_start
async def OpenStoresRepository(_: sanic.Sanic) -> None:
    await stores_repository.Open()


@blueprint.after_server_stop
async def CloseStoresRepository(_: sanic.Sanic) -> None:
    await stores_repository.Close()


@blueprint.get("/list")
@RequireSession
async def List(_: sanic.Request) -> sanic.HTTPResponse:
    stores = await stores_repository.List()
    if stores is None:
        return sanic.response.json({"error": "stores-unavailable"}, status=503)
    return sanic.response.json(stores)
