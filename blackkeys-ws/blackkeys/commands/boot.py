from __future__ import annotations

import os
import subprocess
import sys

NODE_EXPORTER = "/usr/bin/node_exporter"


def RunCommand(name: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "sanic", "ws:app", "exec", name],
        check=True,
    )


def StartNodeExporter() -> None:
    subprocess.Popen(
        [NODE_EXPORTER, "--web.listen-address=:9100"],
        start_new_session=True,
    )


def Main() -> None:
    if len(sys.argv) < 3 or sys.argv[2] != "exec":
        RunCommand("turso-pull_schema")
        RunCommand("turso-init_schema")
        StartNodeExporter()
    os.execv(sys.executable, [sys.executable, "-m", "sanic", *sys.argv[1:]])


if __name__ == "__main__":
    Main()
