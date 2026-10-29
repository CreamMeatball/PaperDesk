# Release readiness

The implementation is a local-first macOS beta. Passing unit tests, an ad-hoc build and a live AI request does not establish readiness for public distribution.

## Fixed identity

`APP_NAME` is presentation only. Keep `DATA_DIR_NAME=Paperdesk`, `STORAGE_ID=paperdesk`, `KEYCHAIN_SERVICE=paperdesk` and `MAC_BUNDLE_ID=org.paperdesk.Paperdesk` fixed across renaming and updates. The first migration to durable translation jobs is schema v5 and uses the existing pre-migration online backup path. Never copy a live WAL-mode DB as a standalone raw file.

## Rebuildable environment

Use an arm64 Mac and Python 3.12. Record the exact interpreter patch version in the generated build manifest. Install pinned runtime/build dependencies:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements/macos-build.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/python scripts/release_preflight.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
.venv/bin/python scripts/i18n.py check
.venv/bin/python scripts/build_macos.py --development --build-number 2
```

The builder refuses a dependency version mismatch or another architecture. `build-manifest.json` inside the app and the DMG receipt record versions and the lock checksum. This pins dependency versions; it is not a claim of byte-identical builds across SDKs, signing timestamps or Python builds. Archive the exact interpreter/SDK details, lock, build log and final SHA-256 with each release. Check upstream security advisories before choosing new pins; do not silently update them in a release job.

## Signing and distribution ownership

The owner selected Apache-2.0 on 2026-10-29; the root LICENSE, NOTICE and package metadata record that decision. Before public release choose the final product name, repository owner, support address and privacy page URL. Dependency notices and their manual review are separate. Do not imply an unpublished OWNER/tap address already works.

Developer ID, Apple notarization access and the Sparkle Ed25519 private key belong to the release owner. Keep the updater key in the Keychain and a secure offline recovery copy, separate from the download/feed host. Protect certificates and recovery material; never place them in the repository. A replacement key or signing identity needs a documented transition plan before the old one is lost.

Build signed candidates using `docs/macos-updates.md`. Notarize/staple the app and final DMG. Verify the actual downloaded archive on a clean Mac, not only the source build folder. Stable feed URLs and strictly increasing build numbers must remain valid. Keep beta and stable release feeds separate if distributing both. Homebrew and the app updater should refer to the same final immutable artifacts.

Copy `packaging/macos/release-checks.example.json` to a private release record, set the exact version/build/architecture and complete every check with a tester/date. Never manufacture passing evidence. Then run the release renderer with `--checks /path/to/completed-checks.json`. The renderer verifies DMG signing/stapling on macOS and refuses incomplete verification or an unset project license. It only prepares files; publishing is a separate user-authorized step.

## Current evidence and remaining gates

A development arm64 app on macOS 27.0.1 has rendered/imported PDFs. The app-bundled Codex CLI 0.165.0-alpha.1.2 has answered a real request with `gpt-6-luna`; an older standalone CLI rejected the same model. Claude login was confirmed but a live response was blocked by the user's usage limit. Mac native selection/hover/region checks were interrupted by the locked screen. These facts are not portable account guarantees or a completed release checklist.

Actual Developer ID signing, notarization, Sparkle install/relaunch, the macOS 15 minimum, another clean Mac, Homebrew installation and Claude live requests still need evidence. Start with a small invited beta, collect installation/connection failures and data-loss reports, and promote a build only after all mandatory checks pass. Shipping new features must not bypass these gates.
