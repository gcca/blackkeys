from __future__ import annotations

from typing import Literal

import sentry_sdk

from blackkeys.core.conf import Settings

LogLevel = Literal["fatal", "critical", "error", "warning", "info", "debug"]


def InitMonitor(settings: Settings) -> None:
    if settings.sentry_dsn is None:
        return
    sentry_sdk.init(dsn=settings.sentry_dsn)


def NotifyEvent(message: str, level: LogLevel = "info") -> None:
    sentry_sdk.capture_message(message, level=level)


def NotifyServerStarted() -> None:
    NotifyEvent("blackkeys server started")
