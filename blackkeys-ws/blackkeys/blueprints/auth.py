import time

import sanic
import sanic.response

from blackkeys.application import AuthService
from blackkeys.core.auth import SignSession
from blackkeys.core.conf import settings
from blackkeys.repositories import (
    AuthenticationUnavailable,
    MakeAuthRepository,
    SignupConflict,
    SignupUnavailable,
)

blueprint = sanic.Blueprint("auth", url_prefix="/auth", version=1)
auth_repository = MakeAuthRepository(settings)
auth_service = AuthService(auth_repository)


def ReadCredentials(payload: object) -> tuple[str, str] | None:
    if not isinstance(payload, dict):
        return None

    username = payload.get("username")
    password = payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    if not username or not password:
        return None
    if not auth_repository.ValidUsername(username):
        return None
    return username, password


@blueprint.before_server_start
async def OpenAuthRepository(app: sanic.Sanic) -> None:
    await auth_repository.Open(getattr(app.ctx, "db", None))


@blueprint.after_server_stop
async def CloseAuthRepository(_: sanic.Sanic) -> None:
    await auth_repository.Close()


@blueprint.post("/signin")
async def SignIn(request: sanic.Request) -> sanic.HTTPResponse:
    credentials = ReadCredentials(request.json)
    if credentials is None:
        return sanic.response.json({"error": "invalid-request"}, status=400)
    username, password = credentials

    try:
        authenticated = await auth_service.Authenticate(username, password)
    except AuthenticationUnavailable:
        return sanic.response.json(
            {"error": "authentication-unavailable"}, status=503
        )

    if not authenticated:
        return sanic.response.json({"error": "invalid-credentials"}, status=401)

    issued_at = int(time.time())
    token = SignSession(
        {
            "sub": username,
            "iat": issued_at,
            "exp": issued_at + settings.auth_ttl_seconds,
        },
        secret=settings.secret,
    )
    return sanic.response.json({"token": f"blackkeys-v1_{token}"})


@blueprint.post("/signup")
async def SignUp(request: sanic.Request) -> sanic.HTTPResponse:
    credentials = ReadCredentials(request.json)
    if credentials is None:
        return sanic.response.json({"error": "invalid-request"}, status=400)
    username, password = credentials
    payload = request.json
    email = payload.get("email") if isinstance(payload, dict) else None
    if not isinstance(email, str) or not email:
        return sanic.response.json({"error": "invalid-request"}, status=400)

    try:
        await auth_repository.CreateUser(username, password, email)
    except SignupConflict:
        return sanic.response.json({"error": "signup-conflict"}, status=409)
    except SignupUnavailable:
        return sanic.response.json({"error": "signup-unavailable"}, status=503)

    return sanic.response.json({"status": "accepted"}, status=202)
