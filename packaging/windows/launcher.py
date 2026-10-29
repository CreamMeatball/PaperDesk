"""Entry point frozen into Paperdesk.exe (window) and paperdesk-cli.exe (console: MCP, doctor, backup)."""
from paperdesk.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
