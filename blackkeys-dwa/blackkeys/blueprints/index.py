import sanic
import sanic.response
from blackkeys.branding import WordmarkContext
from blackkeys.templating import RenderPage, RenderTemplate
from blackkeys.themes import ThemeChoices

blueprint = sanic.Blueprint("index")


@blueprint.get("/")
async def Home(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.html(
        RenderPage(
            "home",
            title="Home",
            show_theme_picker=True,
            themes=ThemeChoices(),
            **WordmarkContext(
                tone="light",
                align="text-center",
                title_size="text-4xl sm:text-5xl",
            ),
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
