import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts.show_memcached_keys import (
    DisplayKey,
    HumanExpiry,
    HumanSize,
    Palette,
    Render,
)

unittest.defaultTestLoader.testMethodPrefix = "Test"


class ShowMemcachedKeysTests(unittest.TestCase):
    def TestFormatsSizes(self) -> None:
        self.assertEqual(HumanSize(217), "217 B")
        self.assertEqual(HumanSize(211308), "206.4 KiB")

    def TestFormatsExpiry(self) -> None:
        self.assertEqual(HumanExpiry(-1, 100), "no expiry")
        self.assertEqual(HumanExpiry(3800, 100), "expires in 1h 1m")
        self.assertEqual(HumanExpiry(225, 100), "expires in 2m 5s")

    def TestRedactsAuthKeysByDefault(self) -> None:
        key = "auth:user:private-user"

        self.assertEqual(DisplayKey(key, False), "auth:user:<redacted>")
        self.assertEqual(DisplayKey(key, True), key)

    def TestRendersNodesAndSummaryWithoutColor(self) -> None:
        nodes = [
            {
                "index": 1,
                "node": "cache-a:11211",
                "stats": {"get_hits": "3", "get_misses": "1"},
                "keys": [
                    {
                        "key": "blackkeys-brands-list",
                        "size": 2048,
                        "expires_at": 400,
                    },
                    {
                        "key": "auth:user:private-user",
                        "size": 217,
                        "expires_at": -1,
                    },
                ],
                "error": None,
            },
            {
                "index": 2,
                "node": "cache-b:11211",
                "stats": {},
                "keys": [],
                "error": None,
            },
        ]
        output = io.StringIO()

        with patch(
            "scripts.show_memcached_keys.time.time", return_value=100
        ), redirect_stdout(output):
            Render(nodes, "machine-id", False, Palette(False))

        rendered = output.getvalue()
        self.assertIn("2 nodes · 2 unique keys · 2 replica entries", rendered)
        self.assertIn(
            "blackkeys-brands-list · 2.0 KiB · expires in 5m 0s", rendered
        )
        self.assertIn("auth:user:<redacted> · 217 B · no expiry", rendered)
        self.assertIn("Node 02", rendered)
        self.assertIn("empty", rendered)
        self.assertNotIn("private-user", rendered)


if __name__ == "__main__":
    unittest.main()
