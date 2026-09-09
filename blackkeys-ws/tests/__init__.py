import time
from types import SimpleNamespace

from blackkeys.blueprints.middlewares import SESSION_TOKEN_PREFIX
from blackkeys.core.auth import SignSession
from blackkeys.core.conf import settings


def SignedToken(
    sub: str = "alice",
    ttl: int | None = None,
    secret: str | None = None,
) -> str:
    issued_at = int(time.time())
    seconds = settings.auth_ttl_seconds if ttl is None else ttl
    return SignSession(
        {"sub": sub, "iat": issued_at, "exp": issued_at + seconds},
        secret=settings.secret if secret is None else secret,
    )


def PrefixedToken(
    sub: str = "alice",
    ttl: int | None = None,
    secret: str | None = None,
) -> str:
    return f"{SESSION_TOKEN_PREFIX}{SignedToken(sub, ttl, secret)}"


def AuthorizedRequest(**fields: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "json": None,
        "headers": {"Authorization": f"Bearer {PrefixedToken()}"},
        "ctx": SimpleNamespace(),
    }
    values.update(fields)
    return SimpleNamespace(**values)
