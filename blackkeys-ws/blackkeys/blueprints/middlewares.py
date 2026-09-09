from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

import sanic
import sanic.response

from blackkeys.core.auth import VerifySession
from blackkeys.core.conf import settings

SESSION_TOKEN_PREFIX = "blackkeys-v1_"
AUTHORIZATION_SCHEME = "Bearer "

Handler = Callable[..., Awaitable[sanic.HTTPResponse]]


def ReadSessionToken(request: sanic.Request) -> str | None:
    header = request.headers.get("Authorization")
    if not isinstance(header, str):
        return None
    if not header.startswith(AUTHORIZATION_SCHEME):
        return None
    token = header[len(AUTHORIZATION_SCHEME) :]
    if not token.startswith(SESSION_TOKEN_PREFIX):
        return None
    return token.removeprefix(SESSION_TOKEN_PREFIX)


def ReadSession(request: sanic.Request) -> dict[str, Any] | None:
    token = ReadSessionToken(request)
    if token is None:
        return None
    return VerifySession(token, settings.secret)


def RequireSession(handler: Handler) -> Handler:
    @wraps(handler)
    async def Guarded(
        request: sanic.Request, *args: Any, **kwargs: Any
    ) -> sanic.HTTPResponse:
        session = ReadSession(request)
        if session is None:
            return sanic.response.json({"error": "invalid-token"}, status=401)
        request.ctx.session = session
        return await handler(request, *args, **kwargs)

    return Guarded
