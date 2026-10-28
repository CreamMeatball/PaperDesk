#!/usr/bin/env python3
"""Render the Homebrew formula for a tagged release.

Typical flow (after pushing tag vX.Y.Z to GitHub):
  python3 scripts/release.py --repo OWNER/paperdesk --license Apache-2.0
It downloads the GitHub tag tarball, computes its sha256 and writes Formula/paperdesk.rb.
Use --tarball path/to/file.tar.gz to hash a local file instead (testing).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "packaging" / "homebrew" / "paperdesk.rb.in"


def current_version() -> str:
    text = (ROOT / "src" / "paperdesk" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def sha256_of(source: str) -> str:
    digest = hashlib.sha256()
    if re.match(r"^https?://", source):
        with urllib.request.urlopen(source, timeout=60) as response:
            for chunk in iter(lambda: response.read(1 << 16), b""):
                digest.update(chunk)
    else:
        with open(source, "rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 16), b""):
                digest.update(chunk)
    return digest.hexdigest()


def render(*, homepage: str, url: str, sha256: str, license_id: str | None, resources: str) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    license_line = f'  license "{license_id}"\n' if license_id else ""
    return (text.replace("@HOMEPAGE@", homepage).replace("@URL@", url).replace("@SHA256@", sha256)
                .replace("@LICENSE_LINE@\n", license_line).replace("@RESOURCES@\n", resources))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="GitHub OWNER/NAME")
    parser.add_argument("--version", default=current_version())
    parser.add_argument("--license", dest="license_id", help="SPDX id, e.g. Apache-2.0 or MIT")
    parser.add_argument("--tarball", help="local tarball to hash instead of downloading the tag archive")
    parser.add_argument("--resources", help="file with resource blocks from 'brew update-python-resources'")
    parser.add_argument("--out", default=str(ROOT / "Formula" / "paperdesk.rb"))
    args = parser.parse_args(argv)

    url = f"https://github.com/{args.repo}/archive/refs/tags/v{args.version}.tar.gz"
    sha = sha256_of(args.tarball or url)
    resources = Path(args.resources).read_text(encoding="utf-8") if args.resources else ""
    if resources and not resources.endswith("\n"):
        resources += "\n"
    formula = render(homepage=f"https://github.com/{args.repo}", url=url, sha256=sha,
                     license_id=args.license_id, resources=resources)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(formula, encoding="utf-8")
    print(f"wrote {out} (v{args.version}, sha256 {sha[:12]}…)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

