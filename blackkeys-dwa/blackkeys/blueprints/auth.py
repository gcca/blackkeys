from collections.abc import Mapping

import httpx2
import sanic
import sanic.response
from sanic.log import logger

from blackkeys.blueprints.utils import IsHtmx
from blackkeys.core.conf import settings
from blackkeys.templating import RenderPage, RenderTemplate

blueprint = sanic.Blueprint("auth")


@blueprint.before_server_start
async def OpenApiClient(app: sanic.Sanic) -> None:
    app.ctx.api_client = httpx2.AsyncClient(
        base_url=settings.api_url,
        headers={"Accept": "application/json"},
    )


@blueprint.after_server_stop
async def CloseApiClient(app: sanic.Sanic) -> None:
    client = getattr(app.ctx, "api_client", None)
    if client is not None:
        await client.aclose()


def ReadCredentials(payload: object) -> tuple[str, str] | None:
    if not isinstance(payload, Mapping):
        return None
    username = payload.get("username")
    password = payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    if not username or not password:
        return None
    return username, password


def SigninResponse(
    request: sanic.Request,
    *,
    kind: str,
    title: str,
    message: str,
    status: int,
    username: str = "",
) -> sanic.HTTPResponse:
    if IsHtmx(request):
        return sanic.response.html(
            RenderTemplate(
                "demo_notice",
                {"kind": kind, "title": title, "message": message},
            ),
            status=status,
        )
    return sanic.response.html(
        RenderPage(
            "signin",
            title="Sign in",
            signin_active=True,
            show_notice=True,
            notice_kind=kind,
            notice_title=title,
            notice_message=message,
            username=username,
        ),
        status=status,
    )


def DemoResponse(request: sanic.Request, page: str) -> sanic.HTTPResponse:
    title = "Demo only"
    message = (
        f"The {page} form reached the application, but no account operation "
        "runs yet."
    )
    if IsHtmx(request):
        return sanic.response.html(
            RenderTemplate(
                "demo_notice",
                {"kind": "info", "title": title, "message": message},
            )
        )
    return sanic.response.html(
        RenderPage(
            page,
            title=page.title(),
            **{f"{page}_active": True},
            show_notice=True,
            notice_title=title,
            notice_message=message,
        )
    )


@blueprint.get("/signin/")
async def SigninPage(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.html(
        RenderPage("signin", title="Sign in", signin_active=True)
    )


@blueprint.post("/signin/")
async def Signin(request: sanic.Request) -> sanic.HTTPResponse:
    credentials = ReadCredentials(request.form)
    if credentials is None:
        return SigninResponse(
            request,
            kind="warning",
            title="Missing credentials",
            message="Enter both a username and password.",
            status=400,
        )
    username, password = credentials

    try:
        response = await request.app.ctx.api_client.post(
            "/v1/signin/",
            json={"username": username, "password": password},
        )
    except httpx2.RequestError as error:
        logger.warning("signin API unavailable: %s", error)
        return SigninResponse(
            request,
            kind="error",
            title="Sign-in unavailable",
            message="Blackkeys could not be reached. Try again shortly.",
            status=503,
            username=username,
        )

    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("token"), str)
            and payload["token"]
        ):
            return SigninResponse(
                request,
                kind="success",
                title="Credentials accepted",
                message=(
                    "Blackkeys accepted your sign-in. Browser session handling "
                    "will be added next."
                ),
                status=200,
                username=username,
            )
        return SigninResponse(
            request,
            kind="error",
            title="Unexpected API response",
            message="Blackkeys returned an invalid sign-in response.",
            status=502,
            username=username,
        )

    if response.status_code == 400:
        return SigninResponse(
            request,
            kind="warning",
            title="Invalid request",
            message="Check the submitted credentials and try again.",
            status=400,
            username=username,
        )
    if response.status_code == 401:
        return SigninResponse(
            request,
            kind="error",
            title="Sign-in failed",
            message="The username or password is incorrect.",
            status=401,
            username=username,
        )
    if response.status_code == 503:
        return SigninResponse(
            request,
            kind="error",
            title="Sign-in unavailable",
            message="Blackkeys authentication is temporarily unavailable.",
            status=503,
            username=username,
        )
    return SigninResponse(
        request,
        kind="error",
        title="Unexpected API response",
        message="Blackkeys could not complete the sign-in request.",
        status=502,
        username=username,
    )


@blueprint.get("/signup/")
async def SignupPage(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.html(
        RenderPage("signup", title="Sign up", signup_active=True)
    )


@blueprint.post("/signup/")
async def SignupDemo(request: sanic.Request) -> sanic.HTTPResponse:
    return DemoResponse(request, "signup")
