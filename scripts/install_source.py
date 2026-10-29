#!/usr/bin/env python3
"""Install Paperdesk from this source folder (beta; there is no signed installer yet).

    Windows:  py -3.12 scripts/install_source.py
    macOS:    python3.12 scripts/install_source.py

Creates a separate Python environment with the same pinned packages as the release builds
(native window and Docling analysis, about 1.3 GB), clones this repository's origin into the install
folder and installs Paperdesk from that clone (editable) and, on Windows, adds a "Paperdesk (beta)"
Start menu shortcut. With automatic updates on (asked once, or --auto-update), the app fetches new
commits from GitHub in the background and applies them the next time it opens; running this script
again also updates. --uninstall removes the environment, the clone and the shortcut. Your library
(PDFs, notes, translations, settings) lives in a separate data folder and is never touched.

On Windows use Python 3.12 from python.org: its python.exe is signed, so Smart App Control lets it
run. Smart App Control blocks unsigned programs, including ones you build yourself.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
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


def updater():
    """The app's own update helpers (git without prompts, the install record), so both sides agree."""
    sys.path.insert(0, str(ROOT / "src"))
    from paperdesk.infrastructure import source_update

    return source_update


def origin_url() -> str | None:
    git = updater().find_git()
    if git is None:
        return None
    try:
        done = updater().run_git(git, "-C", str(ROOT), "remote", "get-url", "origin", timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None


def prepare_source(prefix: Path, url: str | None, branch: str) -> Path | None:
    """The install's own clone at origin/<branch>, or None (no git or remote): then install from this folder without updates."""
    module, clone = updater(), prefix / "source"
    git = module.find_git()
    if git is None or not url:
        print("Automatic updates need git and a repository with an origin remote; installing this folder as it is.", file=sys.stderr)
        return None
    try:
        if (clone / ".git").is_dir():
            steps = [("fetch", "--quiet", "--no-tags", "origin", branch), ("reset", "--quiet", "--hard", f"origin/{branch}")]
            cwd = clone
        else:
            steps = [("clone", "--quiet", "--config", "core.autocrlf=false", "--branch", branch, "--single-branch", url, str(clone))]
            cwd = prefix
        for step in steps:
            print("+ git", " ".join(step), flush=True)
            done = module.run_git(git, *step, cwd=cwd, timeout=600)
            if done.returncode != 0:
                raise OSError(done.stderr.strip() or f"git {step[0]} failed")
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Could not prepare the update clone ({error}); installing this folder without automatic updates.", file=sys.stderr)
        return None
    return clone


def ask_auto_update(previous: bool | None) -> bool:
    if previous is not None:
        return previous
    if not sys.stdin.isatty():
        return False
    answer = input("Check GitHub for new versions when Paperdesk opens and update automatically? [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")


def record(prefix: Path, source: Path | None, branch: str, auto_update: bool | None) -> bool | None:
    """Write (or, without a clone, remove) the install record that the app reads for updates."""
    module = updater()
    config = prefix / module.CONFIG
    if source is None:
        config.unlink(missing_ok=True)
        return None
    previous = module.SourceInstall.load(prefix)
    enabled = ask_auto_update(auto_update if auto_update is not None else previous.data.get("auto_update") if previous else None)
    git = module.find_git()
    commit = module.run_git(git, "rev-parse", "HEAD", cwd=source).stdout.strip()
    names = [f"requirements/{path.name}" for path in locks()]
    data = {"source": str(source), "branch": branch, "commit": commit, "lock_files": names,
            "locks": module.lock_digest(source, names), "auto_update": enabled, "error": ""}
    module.SourceInstall(prefix, data, git=git).save()
    return enabled


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


def install(prefix: Path, *, url: str | None = None, branch: str = "main", auto_update: bool | None = None) -> None:
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
    source = prepare_source(prefix, url or origin_url(), branch)
    tree = source or ROOT
    pip = (python, "-m", "pip", "install", "--disable-pip-version-check", "--require-virtualenv")
    run(*pip, *[arg for lock in requirements for arg in ("-r", tree / "requirements" / lock.name)])
    # Paperdesk itself: dependencies come only from the pinned locks above (they include setuptools, so no
    # build download). The clone is installed editable: an update is then just a checkout of new commits.
    if source:
        run(*pip, "--no-deps", "--no-build-isolation", "-e", source)
    else:
        run(*pip, "--no-deps", "--no-build-isolation", "--force-reinstall", ROOT)
    run(python, "-m", "paperdesk", "--version")
    automatic = record(prefix, source, branch, auto_update)

    print("\nPaperdesk (beta) is installed.")
    if WINDOWS:
        print(f"  Start menu:  {create_shortcut(prefix, environment).stem}")
        print(f"  or run:      \"{environment_python(environment, window=True)}\" -m paperdesk")
    else:
        print(f"  Run:         {python} -m paperdesk")
    print(f"  MCP setup:   \"{python}\" -m paperdesk mcp-config claude   (or codex)")
    if automatic:
        print(f"  Update:      automatic; new commits from GitHub apply the next time Paperdesk opens (Settings to turn off)")
    elif source:
        print(f"  Update:      Settings → check for updates, or run this script again (automatic updates are off)")
    else:
        print(f"  Update:      not automatic (no git clone with an origin). Get the new version (a new ZIP, or git pull "
              f"in a clone) and run this script again; installing from a git clone enables automatic updates")
    print(f"  Uninstall:   run this script with --uninstall")
    print(f"  Library:     {data_folder()} (kept on update and uninstall)")


def _remove_read_only(function, path, _error) -> None:
    # Git makes its object files read-only, and Windows refuses to delete read-only files.
    os.chmod(path, stat.S_IWRITE)
    function(path)


def uninstall(prefix: Path) -> None:
    if WINDOWS:
        shortcut_path().unlink(missing_ok=True)
    if prefix.exists():
        if not (prefix / MARKER).is_file():
            raise SystemExit(f"{prefix} was not created by this script; not removing it.")
        # Remove the marker last, so an interrupted uninstall can simply be run again.
        for child in sorted(prefix.iterdir(), key=lambda p: p.name == MARKER):
            if child.is_dir() and not child.is_symlink():
                if sys.version_info >= (3, 12):
                    shutil.rmtree(child, onexc=_remove_read_only)
                else:
                    shutil.rmtree(child, onerror=lambda f, p, e: _remove_read_only(f, p, e))
            else:
                _remove_read_only(Path.unlink, child, None)
        prefix.rmdir()
    print(f"Removed {prefix}. Your library in {data_folder()} was kept.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prefix", type=Path, default=default_prefix(), help="Where to put the Python environment")
    parser.add_argument("--uninstall", action="store_true", help="Remove the environment and shortcut (keeps your library)")
    parser.add_argument("--source-url", help="Repository to clone for updates (default: this folder's origin remote)")
    parser.add_argument("--branch", default="main", help="Branch to follow for updates (default: main)")
    parser.add_argument("--auto-update", action=argparse.BooleanOptionalAction, default=None,
                        help="Update automatically from GitHub when the app opens (asked once if omitted)")
    args = parser.parse_args()
    prefix = args.prefix.expanduser().resolve()
    if args.uninstall:
        uninstall(prefix)
    else:
        install(prefix, url=args.source_url, branch=args.branch, auto_update=args.auto_update)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
