import sanic

from blackkeys.blueprints.auth import blueprint as auth_blueprint
from blackkeys.blueprints.index import blueprint as index_blueprint

app = sanic.Sanic("blackkeys-dwa")
app.blueprint(index_blueprint)
app.blueprint(auth_blueprint)
