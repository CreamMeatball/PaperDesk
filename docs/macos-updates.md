# macOS app distribution and updates

The app supports two update paths: Sparkle's native update window, and Homebrew Cask upgrades. Both replace the app bundle while papers, conversations, annotations and settings remain in `~/Library/Application Support/Paperdesk`. API keys remain in the macOS Keychain.

The initial source checkout has no update service URL, release credentials or bundled Sparkle framework. It displays that app updates are unavailable, rather than claiming that the installed build is current. Actual signed installation and relaunch must be tested on a Mac before publishing. Nothing in these scripts publishes a release or modifies an external repository.

## App behavior

Settings → About and updates includes the current version, **Check for updates**, an opt-in **Automatically check for updates** checkbox, and the Homebrew command `brew upgrade --cask paperdesk`.

A native macOS release uses Sparkle 2's `SPUStandardUpdaterController`. All Cocoa calls are dispatched to the main thread. Sparkle displays progress, the release notes (when supplied), the install confirmation, and handles download, signature verification, application replacement and relaunch. The web API only opens this native workflow; it never accepts an executable URL or replaces files itself.

Automatic checks and silent installation default to off (`SUEnableAutomaticChecks=false`, `SUAutomaticallyUpdate=false`, `SUAllowsAutomaticUpdates=false`). Users can enable periodic checks; Sparkle stores this choice in local macOS preferences. Even with checks enabled, installing an update requires confirmation. Sparkle's default check interval is one day. System profiling is disabled. With automatic checks off, startup does not contact an update server.

The updater is a port (`ports/updates.py`) with a macOS adapter (`infrastructure/macos_updates.py`); UI and services do not depend on Cocoa. Windows can later add another implementation.

## Prepare the Mac build environment

Use a Mac with the same architecture as the target (Apple silicon/arm64 or Intel/x86_64), a Python supported by the targeted macOS releases, and Xcode Command Line Tools. Install the build dependencies into a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[mac-build]'
```

Download the official [Sparkle 2 distribution](https://sparkle-project.org/documentation/), including `Sparkle.framework`, `bin/`, and `LICENSE`. Use a current Sparkle version supporting `SUVerifyUpdateBeforeExtraction` (2.7.3 or newer). Keep its original symlinks and executable permissions. Generate the update signing key with its `bin/generate_keys` tool. The private key stays in the Mac Keychain; save the displayed public key for builds, and keep a secure recovery copy of the private key following Sparkle's guidance. Never commit private keys.

The following commands use example paths and the placeholder account `OWNER`; they are not published download locations.

## Build a local test DMG

```sh
python3 scripts/build_analysis_runtime.py /absolute/path/analysis-runtime
python3 scripts/build_macos.py --development --build-number 1 --analysis-runtime /absolute/path/analysis-runtime
```

This produces an ad-hoc-signed `.app` inside a DMG for testing on your own Mac. Python, the web UI, native window dependencies and a separate portable Docling runtime are bundled; the user's Mac does not need a separate Python installation. The first icon concept is converted to ICNS using macOS tools. This development artifact has no native updater and cannot be passed to the release renderer.

## Build a release with updates

Choose the final GitHub repository and a stable HTTPS feed location before the first release. For example, GitHub Releases can host `appcast-arm64.xml` and `appcast-x86_64.xml`; the stable feed URL redirects to the latest release's corresponding asset. Release each supported architecture together so `latest` always contains both feeds.

Use the **same public key** on subsequent builds, the same bundle identifier (`org.paperdesk.Paperdesk`), and a strictly increasing build number across all versions. A version such as `0.1.0` is for display; `CFBundleVersion` is the monotonically increasing integer Sparkle compares.

```sh
python3 scripts/build_macos.py \
  --build-number 1 \
  --analysis-runtime /absolute/path/analysis-runtime \
  --feed-url https://github.com/OWNER/paperdesk/releases/latest/download/appcast-arm64.xml \
  --public-key 'PUBLIC_ED25519_KEY_FROM_GENERATE_KEYS' \
  --sparkle-framework /path/to/Sparkle.framework \
  --sparkle-license /path/to/Sparkle/LICENSE \
  --identity 'Developer ID Application: YOUR NAME (TEAMID)' \
  --notary-profile YOUR_NOTARYTOOL_KEYCHAIN_PROFILE
```

On an Intel Mac, use the x86_64 feed instead. The builder signs nested code from the inside out, notarizes and staples the app before putting it in a DMG, then signs, notarizes and staples the final DMG. Output names include display version, build number and architecture, e.g. `Paperdesk-0.1.0-1-arm64.dmg`. Its adjacent JSON receipt records build metadata for release preparation. Final artifacts are never overwritten by the builder. Versioned work directories can be reused after an interrupted build only after clearing the prior staging directory.

## Prepare Sparkle feeds and the Homebrew Cask

Run this on the Mac holding the update signing key, after **all signing/notarization/stapling is finished**:

```sh
python3 scripts/release_macos.py \
  --repo OWNER/paperdesk \
  --sparkle-bin /path/to/Sparkle/bin \
  --dmg dist/macos/Paperdesk-0.1.0-1-arm64.dmg \
  --dmg dist/macos/Paperdesk-0.1.0-1-x86_64.dmg
```

You can initially supply one architecture; its Cask explicitly restricts installation to that architecture. Only artifacts recorded as signed, notarized and configured for Sparkle are accepted.

The renderer uses Sparkle's official `generate_appcast`, which signs update archives using the operator's Keychain key. It checks the expected archive URL, size, signature field and build number in the feed. Cryptographic archive verification at installation is performed by Sparkle using the public key pinned in the app. Keep the exact DMG bytes: changing them after this step invalidates the signature and checksum.

Upload the final DMGs and `dist/release/appcast-*.xml` as assets on release tag `v0.1.0`. Optional release notes can be supplied by placing matching `.html` or `.md` files next to archives before appcast generation, following Sparkle's documentation. Copy `dist/release/paperdesk.rb` into `Casks/paperdesk.rb` in your `homebrew-tap` repository. It includes:

- Native app and command-line launcher installation.
- Separate arm64/Intel hashes and a version/build pair.
- `auto_updates true`, reflecting the app's native updater.
- An uninstall quit rule, with no deletion of user papers or app data.

After publication, users install with `brew install --cask OWNER/tap/paperdesk` and update with `brew upgrade --cask paperdesk`, or use the app's update window. Updating a tap is a separate publication step; these scripts do not push it automatically.

## Data migrations and testing

Before upgrading an existing database schema, Paperdesk makes a SQLite online backup (including committed WAL content) in `backups/migrations/`. Each schema migration is transactional. A failed migration rolls back, and an older app refuses to open a database whose schema is newer than it supports. App updates do not perform destructive file moves or delete user data. Backups are not pruned automatically.

Test a real signed/notarized older build → newer build on a Mac: manual check, automatic-check opt-in persistence, cancel, failed download, install/relaunch, Homebrew upgrade, and preservation of PDF files, notes, translations and chats. Linux tests cover the settings/API contract, unavailable-build behavior, release metadata validation, Cask generation and database migration safeguards; they do not execute Sparkle or notarization.

Sources: [Sparkle setup](https://sparkle-project.org/documentation/), [programmatic setup](https://sparkle-project.org/documentation/programmatic-setup/), [settings and signature configuration](https://sparkle-project.org/documentation/customization/), [Homebrew Cask cookbook](https://docs.brew.sh/Cask-Cookbook).

## Beta release gates added after the first Mac verification

The first packaged beta is arm64/macOS 15+, built with Python 3.12 and `requirements/macos-build.lock`. Install that lock before the project (`pip install --no-deps .`). The builder checks pinned dependencies and embeds a build manifest; other architectures are currently refused. The earlier dual-architecture examples describe the eventual format, not a claim that Intel is supported now.

Before invoking `release_macos.py`, complete the exact build's `packaging/macos/release-checks.example.json` record and pass `--checks /absolute/path/to/completed-checks.json`. A selected project LICENSE and all release checks are required. The script also verifies the final DMG's code signature and stapled notarization ticket on macOS. See `docs/release-readiness.md` for key ownership, clean-install testing, backup/restore, interrupted translation and signed-update verification. Do not change an artifact after computing its release signature or checksum.

The native app icon is compiled from `packaging/macos/Paperdesk.icon` with Xcode 27 or newer (`xcrun actool`). Keep the generated `Assets.car` and fallback ICNS together in the app resources so macOS 15 and newer systems use the appropriate icon format.

## Local document analysis

Docling 2.142.1 runs in a separate CPU process. The portable runtime uses CPython 3.12.12 and requirements/docling-macos.lock; it is copied into Contents/Resources/analysis-runtime. The first analysis downloads the pinned Heron model revision from Hugging Face to the private application data directory. Cached model runs use offline mode. OCR, table-cell reconstruction, formula transcription, remote services and telemetry are disabled. PDFs stay local. Runtime and model preparation states appear in the reader; failures keep the original readable and offer an explicit retry. Model memory is released when the worker exits.

Build the runtime on Apple Silicon using the pinned uv in requirements/macos-build.lock. It is relocatable and does not require Python or pip on the recipient's Mac. Its dependency license files remain in the runtime's site-packages metadata. The runtime significantly increases the DMG size. A source/CLI Formula must also provision the analysis extra; the signed Cask uses the self-contained app.
