from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class Settings:

    API_URL_DEFAULT: ClassVar[str] = "http://localhost:8001"

    api_url: str

    @staticmethod
    def FromEnv(environ: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if environ is None else environ
        api_url = values.get("API_URL", Settings.API_URL_DEFAULT).rstrip("/")
        if not api_url:
            raise ValueError("API_URL must not be empty")
        return Settings(api_url=api_url)


settings = Settings.FromEnv()
