import json
import unittest
from types import SimpleNamespace

import httpx2

from blackkeys.blueprints.auth import (
    CloseApiClient,
    OpenApiClient,
    Signin,
    SigninPage,
    SignupDemo,
    SignupPage,
)
from blackkeys.blueprints.index import DemoPulse, Healthcheck, Home
from blackkeys.core.conf import Settings, settings
from blackkeys.templating import RenderTemplate
from blackkeys.themes import THEMES, ThemeChoices

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
        self.assertEqual(body.count("<option value="), 35)

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
        self.assertIn('hx-post="/signin/"', response.body.decode())

    async def TestSignupPage(self) -> None:
        response = await SignupPage(None)
        self.assertIn('hx-post="/signup/"', response.body.decode())

    async def TestSigninCallsApi(self) -> None:
        def ApiResponse(request):
            self.assertEqual(request.url.path, "/v1/signin/")
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
        self.assertIn("Credentials accepted", body)
        self.assertNotIn("signed-token", body)
        self.assertNotIn("<!doctype html>", body)

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

    async def TestSignupFallbackDemo(self) -> None:
        request = SimpleNamespace(headers={})
        response = await SignupDemo(request)
        body = response.body.decode()
        self.assertIn("Demo only", body)
        self.assertIn("<!doctype html>", body)

    async def TestDemoPulse(self) -> None:
        response = await DemoPulse(None)
        self.assertIn("Update received", response.body.decode())

    async def TestHealthcheck(self) -> None:
        response = await Healthcheck(None)
        self.assertTrue(response.content_type.startswith("text/html"))
        self.assertIn("🍻", response.body.decode())


if __name__ == "__main__":
    unittest.main()
