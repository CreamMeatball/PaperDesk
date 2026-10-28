"""Server-side messages in the user's language.

Source strings are Korean and double as message ids, like the web UI. Mark user-facing text with _():
    raise NotFound(_("폴더를 찾지 못했어요."))
    raise InvalidInput(_("같은 위치에 '{name}' 폴더가 이미 있어요.", name=name))
_() returns a Msg: a str (the Korean text, so logs and tests stay readable) that remembers its template and
parameters so the web layer can render it in another language. Catalogs: web/static/i18n/<code>.json.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CATALOG_DIR = Path(__file__).with_name("web") / "static" / "i18n"
SUPPORTED = ("ko", "en", "ja", "zh")


class Msg(str):
    template: str
    params: dict

    def __new__(cls, template: str, **params) -> "Msg":
        text = template.format(**params) if params else template
        obj = super().__new__(cls, text)
        obj.template = template
        obj.params = params
        return obj


def _(template: str, **params) -> Msg:
    return Msg(template, **params)


@lru_cache(maxsize=None)
def catalog(code: str) -> dict[str, str]:
    if code == "ko":
        return {}
    try:
        return json.loads((CATALOG_DIR / f"{code}.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def normalize(code: str | None) -> str:
    value = (code or "").lower().replace("_", "-").split("-")[0]
    return value if value in SUPPORTED else "en"


def from_header(header: str | None) -> str:
    """X-Paperdesk-Lang or Accept-Language → supported code (default English)."""
    for part in (header or "").split(","):
        code = part.split(";")[0].strip().lower().replace("_", "-").split("-")[0]
        if code in SUPPORTED:
            return code
    return "en"


def translate(text, lang: str) -> str:
    """Translate a Msg (template + params) or a plain source string; unknown text is returned unchanged."""
    if text is None:
        return text
    table = catalog(normalize(lang))
    if isinstance(text, Msg):
        template = table.get(text.template, text.template)
        try:
            return template.format(**{k: (translate(v, lang) if isinstance(v, Msg) else v) for k, v in text.params.items()})
        except (KeyError, IndexError, ValueError):
            return str(text)
    return table.get(str(text), str(text))

