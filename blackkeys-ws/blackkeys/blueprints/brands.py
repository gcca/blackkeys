import sanic
import sanic.response

from blackkeys.backends.services.brands import BrandImageNotFound
from blackkeys.blueprints.middlewares import RequireSession
from blackkeys.core.conf import settings
from blackkeys.repositories import MakeBrandsRepository

blueprint = sanic.Blueprint("brands", url_prefix="/brands", version=1)
brands_repository = MakeBrandsRepository(settings)


@blueprint.before_server_start
async def OpenBrandsRepository(_: sanic.Sanic) -> None:
    await brands_repository.Open()


@blueprint.after_server_stop
async def CloseBrandsRepository(_: sanic.Sanic) -> None:
    await brands_repository.Close()


@blueprint.get("/list")
@RequireSession
async def List(_: sanic.Request) -> sanic.HTTPResponse:
    brands = await brands_repository.List()
    if brands is None:
        return sanic.response.json({"error": "brands-unavailable"}, status=503)
    return sanic.response.json(brands)


@blueprint.get("/<name:str>")
@RequireSession
async def Get(_: sanic.Request, name: str) -> sanic.HTTPResponse:
    brands = await brands_repository.List()
    if brands is None:
        return sanic.response.json({"error": "brands-unavailable"}, status=503)
    brand = next((brand for brand in brands if brand.get("name") == name), None)
    if brand is None:
        return sanic.response.json({"error": "brand-not-found"}, status=404)
    return sanic.response.json(brand)


@blueprint.get("/<name:str>/logo")
@RequireSession
async def Logo(_: sanic.Request, name: str) -> sanic.HTTPResponse:
    return await Image(brands_repository.Logo, name)


@blueprint.get("/<name:str>/picture")
@RequireSession
async def Picture(_: sanic.Request, name: str) -> sanic.HTTPResponse:
    return await Image(brands_repository.Picture, name)


async def Image(fetch, name: str) -> sanic.HTTPResponse:
    try:
        result = await fetch(name)
    except BrandImageNotFound:
        return sanic.response.json({"error": "brand-not-found"}, status=404)
    if result is None:
        return sanic.response.json({"error": "brands-unavailable"}, status=503)
    data, content_type = result
    return sanic.response.raw(data, content_type=content_type)
