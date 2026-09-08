import sanic

from blackkeys.blueprints.auth import blueprint as auth_blueprint
from blackkeys.blueprints.events import blueprint as events_blueprint
from blackkeys.blueprints.index import blueprint as index_blueprint
from blackkeys.commands.turso_init_schema import TursoInitSchema
from blackkeys.commands.turso_pull_schema import TursoPullSchema
from blackkeys.commands.turso_push_schema import TursoPushSchema
from blackkeys.commands.turso_validate_schema import TursoValidateSchema

app = sanic.Sanic(__name__)
app.blueprint(index_blueprint)
app.blueprint(auth_blueprint)
app.blueprint(events_blueprint)
app.command(name="turso-validate_schema")(TursoValidateSchema)
app.command(name="turso-init_schema")(TursoInitSchema)
app.command(name="turso-push_schema")(TursoPushSchema)
app.command(name="turso-pull_schema")(TursoPullSchema)
