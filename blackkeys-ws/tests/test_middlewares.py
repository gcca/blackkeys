import asyncio
import json
import unittest
from types import SimpleNamespace

import sanic
import sanic.response

from blackkeys.blueprints.middlewares import RequireSession
from tests import AuthorizedRequest, PrefixedToken, SignedToken

unittest.defaultTestLoader.testMethodPrefix = "Test"


def GuardedRequest(header: str | None = None) -> SimpleNamespace:
    headers = {} if header is None else {"Authorization": header}
    return SimpleNamespace(json=None, headers=headers, ctx=SimpleNamespace())


class RequireSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[object] = []

        @RequireSession
        async def Handler(request: sanic.Request) -> sanic.HTTPResponse:
            self.calls.append(request)
            return sanic.response.json({"status": "ok"})

        self.handler = Handler

    def AssertRejected(self, request: SimpleNamespace) -> None:
        response = asyncio.run(self.handler(request))

        self.assertEqual(response.status, 401)
        self.assertEqual(json.loads(response.body), {"error": "invalid-token"})
        self.assertEqual(self.calls, [])

    def TestAllowsAValidToken(self) -> None:
        request = AuthorizedRequest()

        response = asyncio.run(self.handler(request))

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.body), {"status": "ok"})
        self.assertEqual(request.ctx.session["sub"], "alice")
        self.assertEqual(self.calls, [request])

    def TestPreservesTheHandlerName(self) -> None:
        self.assertEqual(self.handler.__name__, "Handler")

    def TestRejectsAMissingHeader(self) -> None:
        self.AssertRejected(GuardedRequest())

    def TestRejectsAnEmptyHeader(self) -> None:
        self.AssertRejected(GuardedRequest(""))

    def TestRejectsAnotherScheme(self) -> None:
        token = PrefixedToken()

        self.AssertRejected(GuardedRequest(f"Token {token}"))
        self.AssertRejected(GuardedRequest(f"bearer {token}"))
        self.AssertRejected(GuardedRequest(token))

    def TestRejectsASchemeWithoutAValue(self) -> None:
        self.AssertRejected(GuardedRequest("Bearer"))
        self.AssertRejected(GuardedRequest("Bearer "))

    def TestRejectsAMissingPrefix(self) -> None:
        self.AssertRejected(GuardedRequest(f"Bearer {SignedToken()}"))

    def TestRejectsATamperedSignature(self) -> None:
        token = PrefixedToken()
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

        self.AssertRejected(GuardedRequest(f"Bearer {tampered}"))

    def TestRejectsAnExpiredToken(self) -> None:
        expired = PrefixedToken(ttl=-10)

        self.AssertRejected(GuardedRequest(f"Bearer {expired}"))

    def TestRejectsATokenSignedWithAnotherSecret(self) -> None:
        foreign = PrefixedToken(secret="another-secret")

        self.AssertRejected(GuardedRequest(f"Bearer {foreign}"))

    def TestExposesTheVerifiedSubject(self) -> None:
        request = GuardedRequest(f"Bearer {PrefixedToken(sub='bob')}")

        asyncio.run(self.handler(request))

        self.assertEqual(request.ctx.session["sub"], "bob")
