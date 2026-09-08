import json
import unittest
from types import SimpleNamespace

import httpx2
from blackkeys.blueprints.auth import (
    CloseApiClient,
    OpenApiClient,
    Signin,
    SigninPage,
    Signup,
    SignupPage,
)
from blackkeys.blueprints.events import Events
from blackkeys.blueprints.index import DemoPulse, Healthcheck, Home
from blackkeys.blueprints.search import Search
from blackkeys.blueprints.stores import Stores
from blackkeys.branding import WordmarkContext
from blackkeys.core.conf import Settings, settings
from blackkeys.navigation import NavPrimaryItems, NavSearchItem
from blackkeys.templating import RenderTemplate
from blackkeys.themes import THEMES, ThemeChoices
from dwa import app as dwa_app

unittest.defaultTestLoader.testMethodPrefix = "Test"


class ThemeTests(unittest.TestCase):
    def TestAllDaisyThemesAreAvailable(self) -> None:
        self.assertEqual(len(THEMES), 35)
        self.assertEqual(len({name for name, _ in THEMES}), 35)
        self.assertIn(("caramellatte", "Caramellatte"), THEMES)
        self.assertIn(("abyss", "Abyss"), THEMES)
        self.assertIn(("silk", "Silk"), THEMES)

    def TestThemeChoicesAreMustacheFriendly(self) -> None:
        choices = ThemeChoices()
        self.assertEqual(choices[0], {"name": "light", "label": "Light"})


class TemplateTests(unittest.TestCase):
    def TestMustacheEscapesValues(self) -> None:
        result = RenderTemplate(
            "demo_notice",
            {"kind": "info", "title": "Demo", "message": "<script>"},
        )
        self.assertIn("&lt;script&gt;", result)
        self.assertNotIn("<script>", result)


class SettingsTests(unittest.TestCase):
    def TestDefaultApiUrl(self) -> None:
        self.assertEqual(
            Settings.FromEnv({}).api_url,
            "http://localhost:8001",
        )

    def TestApiUrlOverride(self) -> None:
        self.assertEqual(
            Settings.FromEnv({"API_URL": "https://api.example.test/"}).api_url,
            "https://api.example.test",
        )

    def TestEmptyApiUrlIsRejected(self) -> None:
        with self.assertRaises(ValueError):
            Settings.FromEnv({"API_URL": ""})


class StaticAssetTests(unittest.TestCase):
    def TestVideoStaticRouteIsRegistered(self) -> None:
        route_paths = {route.path for route in dwa_app.router.routes}
        self.assertIn("static/<__file_uri__:path>", route_paths)


class NavigationTests(unittest.TestCase):
    def TestNavPrimaryItemsMarksActiveTab(self) -> None:
        items = NavPrimaryItems("stores")
        self.assertEqual(
            [item["active"] for item in items if item["key"] == "stores"],
            [True],
        )
        self.assertEqual(
            [item["active"] for item in items if item["key"] == "events"],
            [False],
        )

    def TestNavSearchItemMarksActiveTab(self) -> None:
        self.assertTrue(NavSearchItem("search")[0]["active"])
        self.assertFalse(NavSearchItem("stores")[0]["active"])


class WordmarkTests(unittest.TestCase):
    def TestWordmarkContextLightTone(self) -> None:
        context = WordmarkContext(
            tone="light", align="text-center", title_size="text-4xl"
        )
        self.assertEqual(context["wordmark_align_class"], "text-center")
        self.assertIn("text-white", context["wordmark_title_class"])
        self.assertIn("text-4xl", context["wordmark_title_class"])
        self.assertIn("text-white/80", context["wordmark_subtitle_class"])

    def TestWordmarkContextThemedTone(self) -> None:
        context = WordmarkContext(
            tone="themed", align="text-left", title_size="text-lg"
        )
        self.assertIn("text-base-content", context["wordmark_title_class"])
        self.assertIn(
            "text-base-content/70", context["wordmark_subtitle_class"]
        )


class RouteTests(unittest.IsolatedAsyncioTestCase):
    def Request(self, client, form, *, htmx=True):
        headers = {"HX-Request": "true"} if htmx else {}
        return SimpleNamespace(
            app=SimpleNamespace(
                ctx=SimpleNamespace(api_client=client),
            ),
            form=form,
            headers=headers,
        )

    async def TestHome(self) -> None:
        response = await Home(None)
        body = response.body.decode()
        self.assertTrue(response.content_type.startswith("text/html"))
        self.assertIn("htmx.org@4.0.0", body)
        self.assertIn("daisyui@5/themes.css", body)
        self.assertIn("Plaza San Miguel", body)
        self.assertIn("Black Keys", body)
        self.assertIn("SplashBackground.mp4", body)
        self.assertIn("min-h-svh", body)
        self.assertIn("theme-select", body)
        self.assertIn("/signin/", body)
        self.assertIn("/signup/", body)
        self.assertIn("Live demo", body)
        self.assertNotIn("<header", body)
        self.assertNotIn("<footer", body)

    async def TestApiClientLifecycle(self) -> None:
        app = SimpleNamespace(ctx=SimpleNamespace())
        await OpenApiClient(app)
        client = app.ctx.api_client
        self.assertIsInstance(client, httpx2.AsyncClient)
        self.assertEqual(str(client.base_url), settings.api_url)
        await CloseApiClient(app)
        self.assertTrue(client.is_closed)

    async def TestSigninPage(self) -> None:
        response = await SigninPage(None)
        body = response.body.decode()
        self.assertIn('hx-post="/signin/"', body)
        self.assertIn('id="theme-select"', body)
        self.assertIn("min-h-svh", body)
        self.assertIn("SignInBackground.mp4", body)
        self.assertIn("Plaza San Miguel", body)
        self.assertEqual(body.count("<option value="), 35)

    async def TestSignupPage(self) -> None:
        response = await SignupPage(None)
        body = response.body.decode()
        self.assertIn('hx-post="/signup/"', body)
        self.assertIn('name="username"', body)
        self.assertIn('name="password"', body)
        self.assertIn('name="email"', body)
        self.assertIn('type="email"', body)
        self.assertIn('autocomplete="email" required', body)
        self.assertIn('id="theme-select"', body)
        self.assertIn("min-h-svh", body)
        self.assertIn("SignInBackground.mp4", body)
        self.assertEqual(body.count("<option value="), 35)

    async def TestSigninCallsApi(self) -> None:
        def ApiResponse(request):
            self.assertEqual(request.url.path, "/v1/auth/signin")
            self.assertEqual(
                json.loads(request.content),
                {"username": "demo", "password": "example123"},
            )
            return httpx2.Response(200, json={"token": "signed-token"})

        async with httpx2.AsyncClient(
            base_url="http://api.test",
            transport=httpx2.MockTransport(ApiResponse),
        ) as client:
            response = await Signin(
                self.Request(
                    client,
                    {"username": "demo", "password": "example123"},
                )
            )
        body = response.body.decode()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["HX-Redirect"], "/")
        self.assertEqual(body, "")
        self.assertNotIn("signed-token", body)

    async def TestSigninRedirectsWithoutHtmx(self) -> None:
        def ApiResponse(_):
            return httpx2.Response(200, json={"token": "signed-token"})

        async with httpx2.AsyncClient(
            base_url="http://api.test",
            transport=httpx2.MockTransport(ApiResponse),
        ) as client:
            response = await Signin(
                self.Request(
                    client,
                    {"username": "demo", "password": "example123"},
                    htmx=False,
                )
            )
        body = response.body.decode()
        self.assertEqual(response.status, 303)
        self.assertEqual(response.headers["location"], "/")
        self.assertNotIn("signed-token", body)

    async def TestSigninRejectsInvalidCredentials(self) -> None:
        def ApiResponse(_):
            return httpx2.Response(401, json={"error": "invalid_credentials"})

        async with httpx2.AsyncClient(
            base_url="http://api.test",
            transport=httpx2.MockTransport(ApiResponse),
        ) as client:
            response = await Signin(
                self.Request(
                    client,
                    {"username": "demo", "password": "wrong-password"},
                )
            )
        self.assertEqual(response.status, 401)
        self.assertIn(
            "username or password is incorrect", response.body.decode()
        )

    async def TestSigninHandlesUnavailableApi(self) -> None:
        def ApiResponse(request):
            raise httpx2.ConnectError("connection failed", request=request)

        async with httpx2.AsyncClient(
            base_url="http://api.test",
            transport=httpx2.MockTransport(ApiResponse),
        ) as client:
            response = await Signin(
                self.Request(
                    client,
                    {"username": "demo", "password": "example123"},
                    htmx=False,
                )
            )
        body = response.body.decode()
        self.assertEqual(response.status, 503)
        self.assertIn("Sign-in unavailable", body)
        self.assertIn("<!doctype html>", body)

    async def TestSigninValidatesFormBeforeApiCall(self) -> None:
        response = await Signin(self.Request(None, {"username": "demo"}))
        self.assertEqual(response.status, 400)
        self.assertIn("Missing credentials", response.body.decode())

    async def TestSignupCallsApi(self) -> None:
        def ApiResponse(request):
            self.assertEqual(request.url.path, "/v1/auth/signup")
            self.assertEqual(
                json.loads(request.content),
                {
                    "username": "demo",
                    "password": "example123",
                    "email": "demo@example.com",
                },
            )
            return httpx2.Response(202, json={"status": "accepted"})

        async with httpx2.AsyncClient(
            base_url="http://api.test",
            transport=httpx2.MockTransport(ApiResponse),
        ) as client:
            response = await Signup(
                self.Request(
                    client,
                    {
                        "username": "demo",
                        "password": "example123",
                        "email": "demo@example.com",
                    },
                )
            )
        body = response.body.decode()
        self.assertEqual(response.status, 202)
        self.assertIn("Sign-up accepted", body)
        self.assertNotIn("<!doctype html>", body)

    async def TestSignupValidatesFormBeforeApiCall(self) -> None:
        for form in (
            {},
            {"username": "demo", "password": "example123"},
            {
                "username": "demo",
                "password": "",
                "email": "demo@example.com",
            },
            {
                "username": "demo",
                "password": "example123",
                "email": "",
            },
        ):
            response = await Signup(self.Request(None, form))
            self.assertEqual(response.status, 400)
            self.assertIn("Missing account details", response.body.decode())

    async def TestSignupReportsAnExistingUsername(self) -> None:
        def ApiResponse(_):
            return httpx2.Response(409, json={"error": "signup-conflict"})

        async with httpx2.AsyncClient(
            base_url="http://api.test",
            transport=httpx2.MockTransport(ApiResponse),
        ) as client:
            response = await Signup(
                self.Request(
                    client,
                    {
                        "username": "demo",
                        "password": "example123",
                        "email": "demo@example.com",
                    },
                )
            )
        self.assertEqual(response.status, 409)
        self.assertIn("Username unavailable", response.body.decode())

    async def TestSignupValidationFallbackPreservesSafeFields(self) -> None:
        response = await Signup(
            self.Request(
                None,
                {
                    "username": "demo",
                    "email": "demo@example.com",
                },
                htmx=False,
            )
        )
        body = response.body.decode()
        self.assertEqual(response.status, 400)
        self.assertIn('value="demo"', body)
        self.assertIn('value="demo@example.com"', body)
        self.assertNotIn('name="password" value=', body)

    async def TestSignupHandlesUnavailableApi(self) -> None:
        def ApiResponse(request):
            raise httpx2.ConnectError("connection failed", request=request)

        async with httpx2.AsyncClient(
            base_url="http://api.test",
            transport=httpx2.MockTransport(ApiResponse),
        ) as client:
            response = await Signup(
                self.Request(
                    client,
                    {
                        "username": "demo",
                        "password": "example123",
                        "email": "demo@example.com",
                    },
                    htmx=False,
                )
            )
        body = response.body.decode()
        self.assertEqual(response.status, 503)
        self.assertIn("Sign-up unavailable", body)
        self.assertIn("<!doctype html>", body)
        self.assertIn('value="demo"', body)
        self.assertIn('value="demo@example.com"', body)
        self.assertNotIn("example123", body)

    async def TestSignupRejectsInvalidSuccessResponse(self) -> None:
        def ApiResponse(_):
            return httpx2.Response(202, content=b"not-json")

        async with httpx2.AsyncClient(
            base_url="http://api.test",
            transport=httpx2.MockTransport(ApiResponse),
        ) as client:
            response = await Signup(
                self.Request(
                    client,
                    {
                        "username": "demo",
                        "password": "example123",
                        "email": "demo@example.com",
                    },
                )
            )
        self.assertEqual(response.status, 502)
        self.assertIn("Unexpected API response", response.body.decode())

    async def TestSignupMapsApiErrors(self) -> None:
        for api_status, expected_status, title in (
            (400, 400, "Invalid request"),
            (503, 503, "Sign-up unavailable"),
            (418, 502, "Unexpected API response"),
        ):

            def ApiResponse(_, status=api_status):
                return httpx2.Response(status)

            async with httpx2.AsyncClient(
                base_url="http://api.test",
                transport=httpx2.MockTransport(ApiResponse),
            ) as client:
                response = await Signup(
                    self.Request(
                        client,
                        {
                            "username": "demo",
                            "password": "example123",
                            "email": "demo@example.com",
                        },
                    )
                )
            self.assertEqual(response.status, expected_status)
            self.assertIn(title, response.body.decode())

    async def TestStoresPage(self) -> None:
        response = await Stores(None)
        body = response.body.decode()
        self.assertEqual(response.status, 200)
        self.assertIn("Featured", body)
        self.assertIn("Samsung", body)
        self.assertIn("Ibero Librerias", body)
        self.assertIn("carousel", body)
        self.assertIn("columns-2", body)
        self.assertIn('id="theme-select"', body)
        self.assertIn('href="/events/"', body)
        self.assertIn('href="/search/"', body)

    async def TestEventsPage(self) -> None:
        response = await Events(None)
        body = response.body.decode()
        self.assertEqual(response.status, 200)
        self.assertIn("Live Jazz Night", body)
        self.assertIn("OCT", body)
        self.assertIn('id="theme-select"', body)
        self.assertIn('href="/stores/"', body)

    async def TestSearchPage(self) -> None:
        response = await Search(None)
        body = response.body.decode()
        self.assertEqual(response.status, 200)
        self.assertIn("Search Plaza San Miguel", body)
        self.assertIn('id="theme-select"', body)

    async def TestDemoPulse(self) -> None:
        response = await DemoPulse(None)
        self.assertIn("Update received", response.body.decode())

    async def TestHealthcheck(self) -> None:
        response = await Healthcheck(None)
        self.assertTrue(response.content_type.startswith("text/html"))
        self.assertIn("🍻", response.body.decode())


if __name__ == "__main__":
    unittest.main()
