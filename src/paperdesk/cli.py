from __future__ import annotations

import argparse
import os
import json
import logging
import shutil
import sys
import threading
import urllib.request
from contextlib import ExitStack, contextmanager
from pathlib import Path

from . import APP_ID, APP_NAME, __version__
from .app import Application
from .i18n import from_header, translate

DEFAULT_PORT = 47615


@contextmanager
def _application(*, restore: bool = False):
    from .config import AppPaths
    from .infrastructure.instance import downgrade_lock, library_access
    paths = AppPaths.default()
    root = paths.root.resolve()
    exclusive = not paths.database.exists() or (restore and (
        (root/'pending-restore.json').exists() or root.with_name('.'+root.name+'-restore.json').exists()))
    with library_access(root, exclusive=exclusive) as stream:
        app = Application.build(paths=paths, restore=restore)
        if exclusive:
            downgrade_lock(stream)
        try:
            yield app
        finally:
            app.analysis.close()
            app.jobs.close()


def _running_instance(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5) as response:
            return json.load(response).get("app") == APP_ID
    except (OSError, ValueError):
        return False


def command_open(args: argparse.Namespace) -> int:
    from .desktop import choose_shell
    from .web.server import create_server

    if _running_instance(args.port):
        from .domain.errors import InvalidInput
        from .i18n import _
        raise InvalidInput(_("이 서재를 사용하는 앱이 이미 실행 중이에요. 먼저 앱을 종료해 주세요."))
    with _application(restore=True) as app:
        shell = choose_shell(args.shell, app.platform, app.paths.webview_storage, app.updates)
        try:
            server = create_server(app, "127.0.0.1", args.port)
        except OSError:
            server = create_server(app, "127.0.0.1", 0)  # port taken by something else
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"{APP_NAME} {server.url} ({shell.name})", flush=True)
        try:
            shell.run(server.url)
            if not shell.blocks:
                print("Press Ctrl+C to quit", flush=True)
                thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
        return 0


def command_serve(args: argparse.Namespace) -> int:
    from .web.server import create_server

    with _application(restore=True) as app:
        server = create_server(app, args.host, args.port)
        print(f"{APP_NAME} {server.url}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0


def command_mcp(args: argparse.Namespace) -> int:
    from .mcp import StdioMcpServer

    with _application() as app:
        StdioMcpServer.for_app(app).serve()
    return 0


def _launcher() -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False):
        return sys.executable, ["mcp"]
    script = shutil.which(APP_ID)
    if script:
        return str(Path(script).resolve()), ["mcp"]
    return sys.executable, ["-m", "paperdesk", "mcp"]


def command_mcp_config(args: argparse.Namespace) -> int:
    command, arguments = _launcher()
    if args.client == "claude":
        print("# Claude Desktop: Settings > Developer > Edit Config (claude_desktop_config.json)")
        print(json.dumps({"mcpServers": {APP_ID: {"command": command, "args": arguments}}}, indent=2))
    else:
        print("# Codex: ~/.codex/config.toml")
        print(f"[mcp_servers.{APP_ID}]\ncommand = {json.dumps(command)}\nargs = {json.dumps(arguments)}")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    from .desktop import NativeWindowShell

    with _application() as app:
        lang = from_header(os.environ.get("LC_ALL") or os.environ.get("LANG") or "en")
        report = {
            "version": __version__,
            "python": sys.version.split()[0],
            "platform": app.platform.name,
            "platform_supported": app.platform.supported,
            "data_dir": str(app.paths.root),
            "native_window": NativeWindowShell.is_available(),
            "active_provider": app.settings.load().provider or None,
            "providers": {p["id"]: {"available": p["available"], "detail": translate(p["detail"], lang)} for p in app.settings.view()["providers"]},
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for key, value in report.items():
                if key != "providers":
                    print(f"{key:18} {value}")
            for pid, state in report["providers"].items():
                print(f"  {'✓' if state['available'] else '·'} {pid:18} {state['detail']}")
        return 0


def command_backup(args: argparse.Namespace) -> int:
    from .config import AppPaths
    from .infrastructure.archives import LibraryArchives, apply_pending_restore
    from .infrastructure.sqlite import Database
    paths = AppPaths.default().ensure()
    archive = LibraryArchives(paths)
    if args.action == 'export':
        Database(paths.database)
        source = archive.export()
        destination = Path(args.path).expanduser().resolve()
        if destination.exists():
            raise ValueError('Refusing to overwrite an existing backup')
        shutil.copy2(source, destination)
        print(destination)
    elif args.action == 'inspect':
        print(json.dumps(archive.prepare(Path(args.path).expanduser().resolve()), indent=2))
    else:
        if not args.replace_library:
            raise ValueError('Inspect the backup first; restoring requires --replace-library. Close the app before restoring.')
        checked = archive.prepare(Path(args.path).expanduser().resolve())
        archive.schedule(checked['token'])
        apply_pending_restore(paths)
        print('Restored. Previous library retained in the adjacent .before-restore directory. Recheck AI connections.')
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME}: AI paper reader")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    open_cmd = sub.add_parser("open", help="open the app window (default)")
    open_cmd.add_argument("--port", type=int, default=DEFAULT_PORT)
    open_cmd.add_argument("--shell", choices=("auto", "native", "browser"), default="auto")
    open_cmd.set_defaults(func=command_open)

    serve = sub.add_parser("serve", help="run the local server only (development)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.set_defaults(func=command_serve)

    sub.add_parser("mcp", help="MCP server for Claude Desktop and Codex (stdio)").set_defaults(func=command_mcp)

    config = sub.add_parser("mcp-config", help="print MCP client configuration")
    config.add_argument("client", choices=("claude", "codex"))
    config.set_defaults(func=command_mcp_config)

    doctor = sub.add_parser("doctor", help="check the installation and AI connections")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=command_doctor)
    backup = sub.add_parser('backup', help='export, inspect or restore a complete library (close the app first)')
    backup.add_argument('action', choices=('export', 'inspect', 'restore'))
    backup.add_argument('path')
    backup.add_argument('--replace-library', action='store_true')
    backup.set_defaults(func=command_backup)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, stream=sys.stderr)
    if not getattr(args, "func", None):
        args = parser.parse_args(["open", *(argv if argv is not None else sys.argv[1:])])
    from .config import AppPaths
    from .infrastructure.instance import library_access, library_lock
    from .domain.errors import ReaderError
    try:
        with ExitStack() as stack:
            root = AppPaths.default().root
            if args.command in ('open', 'serve', 'backup'):
                stack.enter_context(library_lock(root))
            if args.command == 'backup':
                stack.enter_context(library_access(root, exclusive=args.action == 'restore'))
            return args.func(args)
    except ReaderError as error:
        print(str(error), file=sys.stderr)
        return 1
