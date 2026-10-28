#!/usr/bin/env python3
"""Message catalog tool.

  python3 scripts/i18n.py check            # list missing / unused entries per language (exit 1 if any are missing)
  python3 scripts/i18n.py missing en       # print missing message ids for one language as a JSON object to fill in

Message ids are the Korean source strings: every Korean string literal in the web UI and every _("...") in Python.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "paperdesk"
STATIC = PACKAGE / "web" / "static"
CATALOGS = STATIC / "i18n"
LANGS = ("en", "ja", "zh")
HANGUL = re.compile(r"[가-힣]")
JS_STRING = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
JS_SKIP = {"i18n.js"}


def js_ids() -> set[str]:
    ids: set[str] = set()
    files = [STATIC / "app.js", *sorted((STATIC / "js").glob("*.js"))]
    for path in files:
        if path.name in JS_SKIP:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            code = line.split("//", 1)[0] if not line.strip().startswith("//") else ""
            for match in JS_STRING.finditer(code):
                raw = match.group(1)
                if HANGUL.search(raw):
                    ids.add(json.loads('"' + raw + '"'))
    return ids


def py_ids() -> set[str]:
    ids: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                ids.add(node.args[0].value)
    return ids


def all_ids() -> set[str]:
    return js_ids() | py_ids()


def load(lang: str) -> dict[str, str]:
    path = CATALOGS / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def problems() -> dict[str, dict[str, list[str]]]:
    ids = all_ids()
    report = {}
    for lang in LANGS:
        table = load(lang)
        report[lang] = {
            "missing": sorted(ids - table.keys()),
            "unused": sorted(table.keys() - ids),
            "placeholders": sorted(k for k, v in table.items() if k in ids and placeholders(k) != placeholders(v)),
        }
    return report


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "check"
    if command == "missing":
        lang = argv[1]
        table = load(lang)
        print(json.dumps({k: "" for k in sorted(all_ids() - table.keys())}, ensure_ascii=False, indent=1))
        return 0
    report = problems()
    failed = False
    for lang, items in report.items():
        print(f"{lang}: {len(load(lang))} entries, missing {len(items['missing'])}, unused {len(items['unused'])}, bad placeholders {len(items['placeholders'])}")
        for key in ("missing", "placeholders"):
            for text in items[key][:20]:
                print(f"  {key}: {text}")
        failed = failed or bool(items["missing"] or items["placeholders"])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

