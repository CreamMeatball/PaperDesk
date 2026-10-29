#!/usr/bin/env python3
"""Build a relocatable local Docling runtime. Does not install anything into system Python."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = sys.platform == "win32"
# Same Docling and dependency versions on both systems; the Windows lock only adds Windows-only packages.
LOCK = ROOT / ("requirements/docling-windows.lock" if WINDOWS else "requirements/docling-macos.lock")
PYTHON = "python.exe" if WINDOWS else "bin/python3.12"
SITE_PACKAGES = "Lib/site-packages" if WINDOWS else "lib/python3.12/site-packages"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new directory")
    lock = LOCK
    with tempfile.TemporaryDirectory(prefix="paperdesk-analysis-build-") as temp:
        root = Path(temp)
        subprocess.run([sys.executable, "-m", "uv", "python", "install", "--install-dir", str(root), "--no-bin", "3.12.12"], check=True)
        runtime = next(p for p in root.glob("cpython-3.12.12-*") if not p.is_symlink())
        subprocess.run([sys.executable, "-m", "uv", "pip", "install", "--python", str(runtime / PYTHON),
                        "--target", str(runtime / SITE_PACKAGES), "-r", str(lock)], check=True)
        manifest = {"python": "3.12.12", "docling": "2.142.1", "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()}
        (runtime / "paperdesk-analysis.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        shutil.copytree(runtime, args.output, symlinks=True)
    subprocess.run([str(args.output / PYTHON), "-I", "-c", "from docling.document_converter import DocumentConverter"], check=True)
    print(args.output)


if __name__ == "__main__":
    main()
