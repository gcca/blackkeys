from pathlib import Path

import sanic
from blackkeys.blueprints.auth import blueprint as auth_blueprint
from blackkeys.blueprints.events import blueprint as events_blueprint
from blackkeys.blueprints.index import blueprint as index_blueprint
from blackkeys.blueprints.search import blueprint as search_blueprint
from blackkeys.blueprints.stores import blueprint as stores_blueprint

STATIC_DIRECTORY = Path(__file__).parent / "blackkeys" / "static"

app = sanic.Sanic("blackkeys-dwa")
app.static(
    "/static",
    STATIC_DIRECTORY,
    name="static",
    stream_large_files=True,
    use_content_range=True,
)
app.blueprint(index_blueprint)
app.blueprint(auth_blueprint)
app.blueprint(stores_blueprint)
app.blueprint(events_blueprint)
app.blueprint(search_blueprint)
