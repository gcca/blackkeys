import html
from functools import lru_cache
from pathlib import Path
from typing import Any

import pystache

TEMPLATE_DIRECTORY = Path(__file__).parent / "templates"


def EscapeHtml(value: str) -> str:
    return html.escape(value, quote=True)


@lru_cache(maxsize=None)
def LoadTemplate(name: str) -> str:
    return (TEMPLATE_DIRECTORY / f"{name}.html").read_text(encoding="utf-8")


def RenderTemplate(name: str, context: dict[str, Any] | None = None) -> str:
    renderer = pystache.Renderer(escape=EscapeHtml)
    return renderer.render(LoadTemplate(name), context or {})


def RenderPage(template: str, **context: Any) -> str:
    page = RenderTemplate(template, context)
    shell_context = {
        "app_name": "Blackkeys",
        "default_theme": "dim",
        "title": context["title"],
        "content": page,
        "home_active": context.get("home_active", False),
        "signin_active": context.get("signin_active", False),
        "signup_active": context.get("signup_active", False),
    }
    return RenderTemplate("shell", shell_context)
