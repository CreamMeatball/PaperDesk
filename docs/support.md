# Supported beta scope

Paperdesk is installed from source ([INSTALL.md](../INSTALL.md)) on Apple Silicon (arm64) with macOS 15 or later, and on Windows 10/11 x64 with Python 3.12 from python.org. Intel Macs are not supported by this beta. Packaged installers (a macOS DMG, a signed Windows installer) are not provided yet. Linux is a development shell.

PDF limits: 200 MB per file, 500 pages, page dimensions at most 14,400 PDF points, bounded rendering canvases and image decoding. Text PDFs, including multiple columns, are the supported reading/translation input. Scanned pages can be displayed but have no OCR or selectable text. Password-protected PDFs are not supported. Corrupt files display an error. Large, mixed-layout and multilingual PDFs still need hands-on checks.

## AI setup

Install and sign in to the provider's official CLI yourself. In Paperdesk settings choose **Install and model check**, select and save a model, then **Test connection**. Login checks do not prove that a model is usable. The test sends a small actual request and counts toward provider usage. CLI discovery compares installed versions and uses the official Codex app-server `model/list` RPC; it never reads credential files. Custom executable paths are retained when explicitly configured. Models are never silently substituted and connections never switch to another billed provider automatically.

Codex's current desktop application has a newer CLI than some standalone installations. Its internal path can change during an app update; run discovery again if the saved path stops existing. Paperdesk does not redistribute Codex or Claude binaries. Use `codex login` or the official Claude Code `/login` flow when prompted. Claude's account limit and reset time come from the provider, not a limit imposed by Paperdesk.

## Translation recovery and quality

Translation queues are stored in SQLite, separately from the window. Navigating to another paper does not cancel a job. Each job retains its selected provider, non-secret options, model and answer language. If the app exits or crashes, queued/running jobs become paused next time; they do not send automatically. The translation menu shows resume/cancel actions. An interrupted external request may already have consumed usage, so resuming requires confirmation. Cancel prevents remaining batches; a batch already sent can finish and be saved. Provider requests have a timeout. CLI child process groups are terminated on normal server shutdown.

Existing translations remain when the selected model changes. **Translate this page again** explicitly requests replacement using the current model, with usage confirmation. Sentence-count mismatches show a paragraph-level warning rather than pretending sentence alignment. Equal sentence counts alone do not prove correct semantic alignment. Keep the source visible and check numbers, citations, formulas and terminology.

## Backup and recovery

Settings exports PDF files, a consistent SQLite online backup and non-secret settings in a `.paperdesk` ZIP archive. Archives contain private reading data and are not encrypted. Store them securely. Credentials, browser state and CLI sign-in data are excluded. Export copies kept under `backups/exports` are not automatically pruned.

Restore first validates the manifest, paths, hashes, PDF inventory, SQLite integrity, foreign keys and schema compatibility. The UI accepts archives up to 200 MB; expanded archives are bounded to 4 GiB. Confirmed restore happens on the next complete app restart. The prior entire data directory is retained next to the restored directory as `Paperdesk.before-restore-<id>`. Keep it until you have checked the result; it may contain credentials from development-only Linux storage. A failed directory swap rolls back. Recheck AI connections on a new Mac. Closing and reopening the window in an already-running process is not a full restart.

For larger compressed backups within the expanded limit, close the app and use:

```sh
paperdesk backup export ~/Desktop/library.paperdesk
paperdesk backup inspect ~/Desktop/library.paperdesk
paperdesk backup restore ~/Desktop/library.paperdesk --replace-library
```

The CLI refuses an existing export destination. An OS file lock prevents two owning CLI/app processes from opening the same library. The app, MCP and doctor hold shared access for their entire session; restore requires exclusive access and refuses to run while any of them is using the library. Close connected MCP clients before restoring, then reconnect after the app opens. MCP reads do not apply pending restores. Do not run old app versions or independent source scripts against a library during restore. Schema migration backups cover the DB; complete archives cover PDFs as well.

Backup validation checks the actual database schema and migrates a disposable copy before accepting it. If a scheduled restore fails and the original library is usable, startup quarantines the failed request as `failed-restore-<id>.json`, opens the original library and displays a notice. A failed rollback retains its recovery journal for the next start. Any unexpected directory created during a swap is preserved as `Paperdesk.restore-conflict-<id>` rather than replacing the original library.

## Reporting an issue

**Save diagnostics without content** exports only application/Python/OS versions, architecture and DB schema. It excludes paths, paper names, source text, conversations, options, keys and logs. Nothing is sent automatically. Share a synthetic or public PDF separately if you choose to report a rendering problem.
