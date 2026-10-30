# Installing Paperdesk

This guide is written so that a person **or an AI coding agent** (Claude Code, Codex, …) can follow it step by step.
Paperdesk is in beta: there is no signed installer yet, so it is installed from source with one script.
The script creates its own Python environment and never touches your library (PDFs, notes, translations, settings).

## What you need

| | macOS | Windows |
| --- | --- | --- |
| System | Apple Silicon, macOS 15 or later | Windows 10/11, x64 |
| Python | 3.12 (`brew install python@3.12`) | 3.12 from python.org (`winget install Python.Python.3.12`) |
| git | Xcode Command Line Tools or `brew install git` | `winget install Git.Git` |
| Disk | about 1.5 GB (packages) plus about 170 MB for the layout model downloaded on first use | same |
| AI | at least one: Codex CLI or Claude Code (signed in), an OpenAI/Claude API key, Ollama, or a vLLM/OpenAI-compatible server | same |

git is needed for automatic updates. Without it (for example a ZIP download) Paperdesk still installs, but you update by hand.

On Windows, use Python from python.org. Its `python.exe` is signed. Windows 11 Smart App Control blocks unsigned programs, and Python installed by uv or conda is unsigned.

## Install on macOS

```sh
git clone --depth 1 https://github.com/HojooonKim/PaperDesk.git
cd PaperDesk
python3.12 scripts/install_source.py --auto-update
```

Open **Paperdesk (beta)** from Applications, Launchpad or Spotlight. From a terminal you can also run `~/.paperdesk-beta/venv/bin/python -m paperdesk`.

## Install on Windows (PowerShell or Command Prompt)

```bat
git clone --depth 1 https://github.com/HojooonKim/PaperDesk.git
cd PaperDesk
py -3.12 scripts\install_source.py --auto-update
```

Open **Paperdesk (beta)** from the Start menu.

## What the script does

- It creates a Python environment in `~/.paperdesk-beta` (macOS) or `%LOCALAPPDATA%\Programs\Paperdesk-beta` (Windows). Change this with `--prefix`.
- It installs the same pinned packages as the release builds from `requirements/*.lock`. This is about 1.3 GB and takes several minutes.
- It makes its own clone of the repository inside that folder, checks out the newest release, and installs Paperdesk from it. The folder you cloned above is not used afterwards, and you can delete it.
- It adds **Paperdesk (beta)** to Applications on macOS (to `~/Applications` if your account can't write to `/Applications`), or to the Start menu on Windows.
- At the end it prints a summary: how to run Paperdesk, the MCP setup command, the update mode, and where your library is.

**Updates.** `--auto-update` lets Paperdesk download new releases (version tags) from GitHub in the background and apply them the next time it opens, or right away when you choose **Restart now** in Settings. Only the changed files are transferred, and packages are reinstalled only when the pinned versions change. If an update fails, Paperdesk keeps running the previous version.

Use `--no-auto-update` instead to update only when you choose **Settings → About and updates → Check for updates**, or when you run the script again. If you leave out both flags, the script asks once in an interactive terminal; when nothing can answer the prompt (scripts, agents) it uses no automatic updates.

## Check the install

```sh
# macOS
~/.paperdesk-beta/venv/bin/python -m paperdesk --version
~/.paperdesk-beta/venv/bin/python -m paperdesk doctor
```

```bat
:: Windows
"%LOCALAPPDATA%\Programs\Paperdesk-beta\venv\Scripts\python.exe" -m paperdesk --version
"%LOCALAPPDATA%\Programs\Paperdesk-beta\venv\Scripts\python.exe" -m paperdesk doctor
```

`doctor` prints the version, the data folder, whether the native window is available (`native_window True`), and which AI connections it found.

## Connect an AI

Open Paperdesk, then go to **Settings → AI connection**.

- If you have already signed in to the **Codex CLI** (`codex login`) or **Claude Code**, Paperdesk finds the CLI and selects it on first launch. It never reads or stores those sign-ins.
- To use an **API key** (OpenAI or Claude), paste it in Settings. Keys are kept in the macOS Keychain or the Windows Credential Manager.
- **Ollama** and **vLLM or OpenAI-compatible servers** only need their address.

Choose **Test connection** to send one small request.

## Use Paperdesk from Claude Desktop or Codex (optional)

Paperdesk includes an MCP server, so these apps can read papers from your library. Print the configuration and add it to the client's settings:

```sh
~/.paperdesk-beta/venv/bin/python -m paperdesk mcp-config claude   # or: codex
```

On Windows, run the same command with the `python.exe` path shown above.

## Uninstall

Run the install command again with `--uninstall`. This removes the environment, the clone and the app or Start menu shortcut, and keeps your library:

- macOS: `~/Library/Application Support/Paperdesk`
- Windows: `%LOCALAPPDATA%\Paperdesk`

If you deleted the folder you cloned, use the copy inside the install folder:

```sh
python3.12 ~/.paperdesk-beta/source/scripts/install_source.py --uninstall
```

```bat
py -3.12 "%LOCALAPPDATA%\Programs\Paperdesk-beta\source\scripts\install_source.py" --uninstall
```

## Troubleshooting

| Message or symptom | What to do |
| --- | --- |
| `Paperdesk needs Python 3.12` | Install Python 3.12 (see the table above) and run the script with it (`python3.12`, `py -3.12`). |
| `Run this with the system Python, not from inside a virtual environment` | Run `deactivate` (or open a new terminal), then run the command again. |
| `… exists and was not created by this script` | Something else uses that folder. Pass `--prefix` with a new folder. |
| `Automatic updates need git …` | Install git, then run the script again. |
| Windows: "Smart App Control blocked …" | Use Python from python.org. If paper analysis fails once, retry it in the reader: a library file may be blocked the first time. Event Viewer → `Microsoft-Windows-CodeIntegrity/Operational` (event 3077) shows which file was blocked. |
| The window does not open | Run `doctor`. If `native_window` is `False`, run the install script again. |

## For AI agents installing Paperdesk for a user

Follow the steps above in order, and keep to these rules.

1. **Detect, don't assume.** Check the OS and architecture, the output of `python3.12 --version` or `py -3.12 --version`, and `git --version`. Only Apple Silicon Macs and x64 Windows are supported. On anything else, stop and tell the user.
2. **Ask before installing system software.** That means Python 3.12, git, or Homebrew. On Windows, never substitute Python from uv, conda or the Microsoft Store.
3. **Ask the user about automatic updates.** Then pass `--auto-update` or `--no-auto-update` explicitly. The script cannot ask in a non-interactive shell.
4. **Expect a long run.** The package install downloads about 1.3 GB. Allow at least 20 minutes before treating it as stuck. Don't run it with `sudo` or as administrator.
5. **Never handle credentials.** Don't sign in to Codex or Claude for the user, and don't ask for API keys in chat. The user signs in with the provider's own CLI, or enters keys in Paperdesk's Settings.
6. **Leave the user's data alone.** Don't create, edit or delete anything in the data folder above.
7. **Verify, then report.** Run `--version` and `doctor`, then tell the user:
   - how to open Paperdesk, from the summary the script printed;
   - whether automatic updates are on;
   - which AI connections `doctor` found, and what the user still needs to do (for example, run `codex login`, or add a key in Settings).
