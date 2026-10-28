"""Entry point frozen into Paperdesk.app; CLI subcommands (including MCP) remain available."""
from paperdesk.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
