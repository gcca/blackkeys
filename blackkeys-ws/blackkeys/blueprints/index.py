import sanic
import sanic.response

from blackkeys.core.conf import settings
from blackkeys.monitor import InitMonitor, NotifyServerStarted
from blackkeys.persistence.schema import ValidateSchema
from blackkeys.persistence.turso import (
    CloseDatabase,
    OpenDatabase,
    PullDatabase,
)

blueprint = sanic.Blueprint("index")


@blueprint.before_server_start
async def StartMonitor(_: sanic.Sanic) -> None:
    InitMonitor(settings)
    NotifyServerStarted()


@blueprint.before_server_start
async def Pull(app: sanic.Sanic) -> None:
    db = await OpenDatabase(settings)
    app.ctx.db = db
    await PullDatabase(db)
    await ValidateSchema(db)


@blueprint.after_server_stop
async def Close(app: sanic.Sanic) -> None:
    db = getattr(app.ctx, "db", None)
    await CloseDatabase(db)
    app.ctx.db = None


@blueprint.route("/healthcheck")
async def Healthcheck(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.text("🍻")
