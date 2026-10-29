#!/usr/bin/env python3
"""Install Paperdesk from this source folder (beta; there is no signed installer yet).

    Windows:  py -3.12 scripts/install_source.py
    macOS:    python3.12 scripts/install_source.py

Creates a separate Python environment with the same pinned packages as the release builds
(native window and Docling analysis, about 1.3 GB), installs Paperdesk into it and, on Windows,
adds a "Paperdesk (beta)" Start menu shortcut. Run it again after `git pull` to update.
--uninstall removes the environment and the shortcut. Your library (PDFs, notes, translations,
settings) lives in a separate data folder and is never touched.

On Windows use Python 3.12 from python.org: its python.exe is signed, so Smart App Control lets it
run. Smart App Control blocks unsigned programs, including ones you build yourself.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
PYTHON = (3, 12)  # the pinned window and Docling locks are resolved for Python 3.12
MARKER = "paperdesk-source-install.txt"
SHORTCUT = "Paperdesk (beta).lnk"


def default_prefix() -> Path:
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Programs" / "Paperdesk-beta"
    return Path.home() / ".paperdesk-beta"


def locks() -> list[Path]:
    if WINDOWS:
        names = ("windows-app.lock", "docling-windows.lock")
    elif MACOS:
        names = ("macos-app.lock", "docling-macos.lock")
    else:
        raise SystemExit("Source installs are for Windows and macOS. On Linux run `pip install -e .` and `paperdesk serve`.")
    return [ROOT / "requirements" / name for name in names]


def environment_python(environment: Path, *, window: bool = False) -> Path:
    if WINDOWS:
        return environment / "Scripts" / ("pythonw.exe" if window else "python.exe")
    return environment / "bin" / "python"


def quote(value) -> str:
    """A PowerShell single-quoted literal."""
    return "'" + str(value).replace("'", "''") + "'"


def powershell(script: str, *, check: bool = True) -> subprocess.CompletedProcess:
    # An inline command, not a .ps1 file, so the PowerShell execution policy does not apply.
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=120, check=check)


def signature_status(path: Path) -> str:
    try:
        return powershell(f"(Get-AuthenticodeSignature -LiteralPath {quote(path)}).Status", check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def shortcut_path() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / SHORTCUT


def create_shortcut(prefix: Path, environment: Path) -> Path:
    link = shortcut_path()
    link.parent.mkdir(parents=True, exist_ok=True)
    icon = prefix / "Paperdesk.ico"
    shutil.copy2(ROOT / "packaging" / "windows" / "Paperdesk.ico", icon)
    powershell("; ".join([
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({quote(link)})",
        f"$s.TargetPath = {quote(environment_python(environment, window=True))}",
        "$s.Arguments = '-m paperdesk'",
        f"$s.WorkingDirectory = {quote(prefix)}",
        f"$s.IconLocation = {quote(icon)}",
        "$s.Description = 'Paperdesk (beta, installed from source)'",
        "$s.Save()"]))
    return link


def data_folder() -> Path:
    sys.path.insert(0, str(ROOT / "src"))
    from paperdesk.config import AppPaths

    return AppPaths.default().root


def matching_environment(environment: Path) -> bool:
    try:
        lines = (environment / "pyvenv.cfg").read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    version = next((line.split("=", 1)[1].strip() for line in lines if line.split("=", 1)[0].strip() in ("version", "version_info")), "")
    return version.split(".")[:2] == [str(n) for n in PYTHON] and environment_python(environment).is_file()


def run(*args) -> None:
    print("+", " ".join(str(arg) for arg in args), flush=True)
    subprocess.run([str(arg) for arg in args], check=True)


def install(prefix: Path) -> None:
    if sys.prefix != sys.base_prefix:
        raise SystemExit("Run this with the system Python, not from inside a virtual environment.")
    if sys.version_info[:2] != PYTHON:
        hint = ("winget install Python.Python.3.12, then: py -3.12 scripts/install_source.py" if WINDOWS else
                "brew install python@3.12, then: python3.12 scripts/install_source.py")
        raise SystemExit(f"Paperdesk needs Python 3.12 (this is {sys.version.split()[0]}). {hint}")
    requirements = locks()
    if WINDOWS and signature_status(Path(getattr(sys, "_base_executable", sys.executable))) not in ("Valid", ""):
        print("Warning: this Python is not signed (for example one installed by uv or conda). Windows Smart App Control "
              "may block it; Python from python.org is signed.", file=sys.stderr)
    if prefix.exists() and not (prefix / MARKER).is_file():
        raise SystemExit(f"{prefix} exists and was not created by this script; choose another --prefix.")
    environment = prefix / "venv"
    fresh = not matching_environment(environment)
    prefix.mkdir(parents=True, exist_ok=True)
    (prefix / MARKER).write_text(f"Paperdesk source install from {ROOT}\n", encoding="utf-8")
    if fresh:
        print(f"Creating {environment}", flush=True)
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = environment_python(environment)
    pip = (python, "-m", "pip", "install", "--disable-pip-version-check", "--require-virtualenv")
    run(*pip, *[arg for lock in requirements for arg in ("-r", lock)])
    # Paperdesk itself: dependencies come only from the pinned locks above.
    run(*pip, "--no-deps", "--force-reinstall", ROOT)
    run(python, "-m", "paperdesk", "--version")

    print("\nPaperdesk (beta) is installed.")
    if WINDOWS:
        print(f"  Start menu:  {create_shortcut(prefix, environment).stem}")
        print(f"  or run:      \"{environment_python(environment, window=True)}\" -m paperdesk")
    else:
        print(f"  Run:         {python} -m paperdesk")
    print(f"  MCP setup:   \"{python}\" -m paperdesk mcp-config claude   (or codex)")
    print(f"  Update:      git pull, then run this script again")
    print(f"  Uninstall:   run this script with --uninstall")
    print(f"  Library:     {data_folder()} (kept on update and uninstall)")


def uninstall(prefix: Path) -> None:
    if WINDOWS:
        shortcut_path().unlink(missing_ok=True)
    if prefix.exists():
        if not (prefix / MARKER).is_file():
            raise SystemExit(f"{prefix} was not created by this script; not removing it.")
        shutil.rmtree(prefix)
    print(f"Removed {prefix}. Your library in {data_folder()} was kept.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prefix", type=Path, default=default_prefix(), help="Where to put the Python environment")
    parser.add_argument("--uninstall", action="store_true", help="Remove the environment and shortcut (keeps your library)")
    args = parser.parse_args()
    prefix = args.prefix.expanduser().resolve()
    uninstall(prefix) if args.uninstall else install(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
