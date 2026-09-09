import unittest
from unittest.mock import patch

from blackkeys.core.conf import Settings
from blackkeys.monitor import InitMonitor, NotifyEvent, NotifyServerStarted

unittest.defaultTestLoader.testMethodPrefix = "Test"


class InitMonitorTests(unittest.TestCase):
    def TestInitializesSentryWhenDsnIsConfigured(self) -> None:
        settings = Settings.FromEnv(
            {"SECRET": "secret", "SENTRY_DSN": "https://key@sentry.io/1"}
        )

        with patch("blackkeys.monitor.sentry_sdk.init") as init:
            InitMonitor(settings)

        init.assert_called_once_with(dsn="https://key@sentry.io/1")

    def TestSkipsInitializationWithoutADsn(self) -> None:
        settings = Settings.FromEnv({"SECRET": "secret"})

        with patch("blackkeys.monitor.sentry_sdk.init") as init:
            InitMonitor(settings)

        init.assert_not_called()


class NotifyEventTests(unittest.TestCase):
    def TestCapturesAnInfoMessageByDefault(self) -> None:
        with patch("blackkeys.monitor.sentry_sdk.capture_message") as capture:
            NotifyEvent("something happened")

        capture.assert_called_once_with("something happened", level="info")

    def TestCapturesAtTheRequestedLevel(self) -> None:
        with patch("blackkeys.monitor.sentry_sdk.capture_message") as capture:
            NotifyEvent("something failed", level="error")

        capture.assert_called_once_with("something failed", level="error")


class NotifyServerStartedTests(unittest.TestCase):
    def TestNotifiesThatTheServerStarted(self) -> None:
        with patch("blackkeys.monitor.sentry_sdk.capture_message") as capture:
            NotifyServerStarted()

        capture.assert_called_once_with(
            "blackkeys server started", level="info"
        )
