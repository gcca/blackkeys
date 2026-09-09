import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from blackkeys.blueprints.stores import List, ReadStores, blueprint
from tests import AuthorizedRequest

unittest.defaultTestLoader.testMethodPrefix = "Test"


class StoresSnapshotTests(unittest.TestCase):
    def TestLoadsTheStoresList(self) -> None:
        stores = ReadStores()

        self.assertIsNotNone(stores)
        assert stores is not None
        self.assertEqual(len(stores), 318)
        self.assertEqual(stores[0]["name"], "ADIDAS")


class StoresEndpointTests(unittest.TestCase):
    request = AuthorizedRequest()

    def TestReturnsTheStoresList(self) -> None:
        with patch(
            "blackkeys.blueprints.stores.ReadStores",
            return_value=[{"id": 81, "name": "ADIDAS"}],
        ):
            response = asyncio.run(List(self.request))

        self.assertEqual(response.status, 200)
        self.assertEqual(
            json.loads(response.body), [{"id": 81, "name": "ADIDAS"}]
        )

    def TestReportsUnavailableWhenTheSnapshotCannotBeRead(self) -> None:
        with patch("blackkeys.blueprints.stores.ReadStores", return_value=None):
            response = asyncio.run(List(self.request))

        self.assertEqual(response.status, 503)
        self.assertEqual(
            json.loads(response.body), {"error": "stores-unavailable"}
        )

    def TestRejectsARequestWithoutAToken(self) -> None:
        request = SimpleNamespace(json=None, headers={}, ctx=SimpleNamespace())

        response = asyncio.run(List(request))

        self.assertEqual(response.status, 401)
        self.assertEqual(json.loads(response.body), {"error": "invalid-token"})

    def TestRegistersTheGuardedHandler(self) -> None:
        routes = {
            route.uri: route.handler for route in blueprint._future_routes
        }

        self.assertIs(routes["/list"], List)
        self.assertTrue(hasattr(routes["/list"], "__wrapped__"))
