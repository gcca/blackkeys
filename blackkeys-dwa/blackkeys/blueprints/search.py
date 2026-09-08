import sanic
import sanic.response
from blackkeys.blueprints.chrome import RenderAppPage

blueprint = sanic.Blueprint("search")


@blueprint.get("/search/")
async def Search(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.html(
        RenderAppPage("search", title="Search", active_tab="search")
    )
