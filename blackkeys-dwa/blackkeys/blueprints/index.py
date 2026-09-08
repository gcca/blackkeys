import sanic
import sanic.response

from blackkeys.templating import RenderPage, RenderTemplate
from blackkeys.themes import ThemeChoices

blueprint = sanic.Blueprint("index")


@blueprint.get("/")
async def Home(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.html(
        RenderPage(
            "home",
            title="Home",
            home_active=True,
            themes=ThemeChoices(),
        )
    )


@blueprint.get("/demo/pulse/")
async def DemoPulse(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.html(
        RenderTemplate(
            "demo_notice",
            {
                "kind": "success",
                "title": "Update received",
                "message": "This section changed without a full page reload.",
            },
        )
    )


@blueprint.get("/healthcheck")
async def Healthcheck(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.text("🍻")
