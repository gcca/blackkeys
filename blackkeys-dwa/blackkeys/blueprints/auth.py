from collections.abc import Mapping

import httpx2
import sanic
import sanic.response
from blackkeys.blueprints.utils import IsHtmx
from blackkeys.core.conf import settings
from blackkeys.templating import RenderPage, RenderTemplate
from blackkeys.themes import ThemeChoices
from sanic.log import logger

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


def ReadSignup(payload: object) -> tuple[str, str, str] | None:
    credentials = ReadCredentials(payload)
    if credentials is None or not isinstance(payload, Mapping):
        return None
    email = payload.get("email")
    if not isinstance(email, str) or not email:
        return None
    username, password = credentials
    return username, password, email


def ReadFormValue(payload: object, name: str) -> str:
    if not isinstance(payload, Mapping):
        return ""
    value = payload.get(name)
    return value if isinstance(value, str) else ""


def RenderAuthPage(template: str, **context: object) -> str:
    return RenderPage(
        template,
        show_theme_picker=True,
        themes=ThemeChoices(),
        **context,
    )


def SigninSuccessResponse(request: sanic.Request) -> sanic.HTTPResponse:
    if IsHtmx(request):
        return sanic.response.empty(
            status=200,
            headers={"HX-Redirect": "/"},
        )
    return sanic.response.redirect("/", status=303)


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
        RenderAuthPage(
            "signin",
            title="Sign in",
            show_notice=True,
            notice_kind=kind,
            notice_title=title,
            notice_message=message,
            username=username,
        ),
        status=status,
    )


def SignupResponse(
    request: sanic.Request,
    *,
    kind: str,
    title: str,
    message: str,
    status: int,
    username: str = "",
    email: str = "",
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
        RenderAuthPage(
            "signup",
            title="Sign up",
            show_notice=True,
            notice_kind=kind,
            notice_title=title,
            notice_message=message,
            username=username,
            email=email,
        ),
        status=status,
    )


@blueprint.get("/signin/")
async def SigninPage(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.html(RenderAuthPage("signin", title="Sign in"))


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
            "/v1/auth/signin",
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
            return SigninSuccessResponse(request)
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
    return sanic.response.html(RenderAuthPage("signup", title="Sign up"))


@blueprint.post("/signup/")
async def Signup(request: sanic.Request) -> sanic.HTTPResponse:
    signup = ReadSignup(request.form)
    if signup is None:
        return SignupResponse(
            request,
            kind="warning",
            title="Missing account details",
            message="Enter a username, password, and email address.",
            status=400,
            username=ReadFormValue(request.form, "username"),
            email=ReadFormValue(request.form, "email"),
        )
    username, password, email = signup

    try:
        response = await request.app.ctx.api_client.post(
            "/v1/auth/signup",
            json={
                "username": username,
                "password": password,
                "email": email,
            },
        )
    except httpx2.RequestError as error:
        logger.warning("signup API unavailable: %s", error)
        return SignupResponse(
            request,
            kind="error",
            title="Sign-up unavailable",
            message="Blackkeys could not be reached. Try again shortly.",
            status=503,
            username=username,
            email=email,
        )

    if response.status_code == 202:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("status") == "accepted":
            return SignupResponse(
                request,
                kind="success",
                title="Sign-up accepted",
                message=(
                    "Blackkeys accepted your account request. You can sign in "
                    "once processing completes."
                ),
                status=202,
            )
        return SignupResponse(
            request,
            kind="error",
            title="Unexpected API response",
            message="Blackkeys returned an invalid sign-up response.",
            status=502,
            username=username,
            email=email,
        )

    if response.status_code == 400:
        return SignupResponse(
            request,
            kind="warning",
            title="Invalid request",
            message="Check the username, password, and email and try again.",
            status=400,
            username=username,
            email=email,
        )
    if response.status_code == 409:
        return SignupResponse(
            request,
            kind="warning",
            title="Username unavailable",
            message="That username is already registered.",
            status=409,
            username=username,
            email=email,
        )
    if response.status_code == 503:
        return SignupResponse(
            request,
            kind="error",
            title="Sign-up unavailable",
            message="Blackkeys account creation is temporarily unavailable.",
            status=503,
            username=username,
            email=email,
        )
    return SignupResponse(
        request,
        kind="error",
        title="Unexpected API response",
        message="Blackkeys could not complete the sign-up request.",
        status=502,
        username=username,
        email=email,
    )
