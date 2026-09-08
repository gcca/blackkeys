from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from typing import Any

APP_DEFAULT = "blackkeys-ws"
REMOTE_PROGRAM = r"""
import json
import socket
import sys
import urllib.parse

sys.path.insert(0, "/app")

from blackkeys.core.conf import Settings


def ReadResponse(stream):
    lines = []
    for raw in stream:
        if raw == b"END\r\n":
            break
        lines.append(raw.decode("utf-8", "replace").strip())
    return lines


def ReadStats(host, port):
    with socket.create_connection((host, port), timeout=5) as connection:
        connection.sendall(b"stats\r\n")
        lines = ReadResponse(connection.makefile("rb"))
    stats = {}
    for line in lines:
        fields = line.split()
        if len(fields) == 3 and fields[0] == "STAT":
            stats[fields[1]] = fields[2]
    return stats


def ReadKeys(host, port):
    with socket.create_connection((host, port), timeout=10) as connection:
        connection.sendall(b"lru_crawler metadump all\r\n")
        lines = ReadResponse(connection.makefile("rb"))
    keys = []
    for line in lines:
        fields = dict(
            field.split("=", 1) for field in line.split() if "=" in field
        )
        if "key" not in fields:
            continue
        keys.append(
            {
                "key": urllib.parse.unquote(fields["key"]),
                "size": int(fields.get("size", "0")),
                "expires_at": int(fields.get("exp", "-1")),
            }
        )
    return keys


results = []
for index, node in enumerate(Settings.FromEnv().cache_nodes, 1):
    host, port_text = node.rsplit(":", 1)
    try:
        stats = ReadStats(host, int(port_text))
        keys = ReadKeys(host, int(port_text))
        results.append(
            {
                "index": index,
                "node": node,
                "stats": stats,
                "keys": keys,
                "error": None,
            }
        )
    except Exception as error:
        results.append(
            {
                "index": index,
                "node": node,
                "stats": {},
                "keys": [],
                "error": f"{type(error).__name__}: {error}",
            }
        )

print("MEMCACHED_KEYS_JSON=" + json.dumps(results, separators=(",", ":")))
"""


class Palette:
    def __init__(self, enabled: bool) -> None:
        self.bold = "\033[1m" if enabled else ""
        self.dim = "\033[2m" if enabled else ""
        self.red = "\033[31m" if enabled else ""
        self.green = "\033[32m" if enabled else ""
        self.yellow = "\033[33m" if enabled else ""
        self.blue = "\033[34m" if enabled else ""
        self.magenta = "\033[35m" if enabled else ""
        self.cyan = "\033[36m" if enabled else ""
        self.reset = "\033[0m" if enabled else ""


def ParseArguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show key metadata from every Fly Memcached node."
    )
    parser.add_argument("--app", default=APP_DEFAULT)
    parser.add_argument("--machine")
    parser.add_argument("--show-sensitive", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    return parser.parse_args()


def RunFly(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["flyctl", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def FindMachine(app: str) -> str:
    result = RunFly(["machine", "list", "--app", app, "--json"])
    machines = json.loads(result.stdout)
    started = [
        machine for machine in machines if machine.get("state") == "started"
    ]
    if not started:
        raise RuntimeError(f"no started Machine found for {app}")
    return started[0]["id"]


def ReadNodes(app: str, machine: str) -> list[dict[str, Any]]:
    encoded = base64.b64encode(REMOTE_PROGRAM.encode()).decode()
    command = (
        "/usr/bin/python -c "
        f"'import base64;exec(base64.b64decode(\"{encoded}\"))'"
    )
    result = RunFly(
        [
            "machine",
            "exec",
            machine,
            "--app",
            app,
            "--timeout",
            "60",
            command,
        ]
    )
    prefix = "MEMCACHED_KEYS_JSON="
    for line in result.stdout.splitlines():
        if line.startswith(prefix):
            return json.loads(line.removeprefix(prefix))
    raise RuntimeError("the remote probe returned no key metadata")


def HumanSize(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError


def HumanExpiry(expires_at: int, now: int) -> str:
    if expires_at < 0:
        return "no expiry"
    remaining = max(expires_at - now, 0)
    minutes, seconds = divmod(remaining, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"expires in {hours}h {minutes}m"
    if minutes:
        return f"expires in {minutes}m {seconds}s"
    return f"expires in {seconds}s"


def DisplayKey(key: str, show_sensitive: bool) -> str:
    if key.startswith("auth:user:") and not show_sensitive:
        return "auth:user:<redacted>"
    return key


def KeyColor(key: str, palette: Palette) -> str:
    if key == "blackkeys-brands-list":
        return palette.magenta
    if key.startswith("blackkeys-brand-image:logo:"):
        return palette.yellow
    if key.startswith("blackkeys-brand-image:picture:"):
        return palette.blue
    if key.startswith("auth:user:"):
        return palette.red
    if key == "blackkeys-events-list":
        return palette.cyan
    return palette.reset


def WriteLine(text: str = "") -> None:
    sys.stdout.write(f"{text}\n")


def Render(
    nodes: list[dict[str, Any]],
    machine: str,
    show_sensitive: bool,
    palette: Palette,
) -> None:
    now = int(time.time())
    total_entries = sum(len(node["keys"]) for node in nodes)
    unique_keys = {item["key"] for node in nodes for item in node["keys"]}
    WriteLine(
        f"{palette.bold}{palette.cyan}Fly Memcached key map{palette.reset}"
    )
    WriteLine(
        f"{palette.dim}via Machine {machine} · {len(nodes)} nodes · "
        f"{len(unique_keys)} unique keys · {total_entries} replica entries"
        f"{palette.reset}"
    )
    WriteLine()
    for node in nodes:
        index = node["index"]
        endpoint = node["node"]
        error = node["error"]
        if error is not None:
            WriteLine(
                f"{palette.red}✗ Node {index:02d}{palette.reset} "
                f"{palette.dim}{endpoint}{palette.reset}"
            )
            WriteLine(f"  {palette.red}{error}{palette.reset}")
            WriteLine()
            continue
        stats = node["stats"]
        keys = node["keys"]
        hits = stats.get("get_hits", "0")
        misses = stats.get("get_misses", "0")
        WriteLine(
            f"{palette.green}● Node {index:02d}{palette.reset} "
            f"{palette.dim}{endpoint}{palette.reset}"
        )
        WriteLine(
            f"  {palette.dim}{len(keys)} keys · {hits} hits · "
            f"{misses} misses{palette.reset}"
        )
        if not keys:
            WriteLine(f"  {palette.dim}└─ empty{palette.reset}")
            WriteLine()
            continue
        for position, item in enumerate(keys):
            branch = "└─" if position == len(keys) - 1 else "├─"
            raw_key = item["key"]
            key = DisplayKey(raw_key, show_sensitive)
            color = KeyColor(raw_key, palette)
            size = HumanSize(item["size"])
            expiry = HumanExpiry(item["expires_at"], now)
            WriteLine(
                f"  {branch} {color}{key}{palette.reset} "
                f"{palette.dim}· {size} · {expiry}{palette.reset}"
            )
        WriteLine()


def Main() -> None:
    arguments = ParseArguments()
    machine = arguments.machine or FindMachine(arguments.app)
    nodes = ReadNodes(arguments.app, machine)
    color = (
        not arguments.no_color
        and "NO_COLOR" not in os.environ
        and sys.stdout.isatty()
    )
    Render(nodes, machine, arguments.show_sensitive, Palette(color))


if __name__ == "__main__":
    try:
        Main()
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as error:
        sys.stderr.write(f"error: {error}\n")
        raise SystemExit(1) from error
