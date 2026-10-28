#!/usr/bin/env python3
"""Build a self-contained macOS .app and DMG with optional signed Sparkle updates.

Run on the target Mac architecture. Release builds require --feed-url, --public-key,
--sparkle-framework and --identity. --development builds a local test app without updates.
No private signing keys are read by Python: codesign/notarytool use the macOS Keychain.
"""
from __future__ import annotations

import argparse
import json
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from paperdesk import APP_NAME, MAC_BUNDLE_ID, __version__
from paperdesk.infrastructure.macos_updates import valid_update_configuration


def bundle_metadata(*, version: str, build: int, feed_url: str = "", public_key: str = "") -> dict:
    if build < 1:
        raise ValueError("Build number must be a positive integer and must increase for every release")
    if bool(feed_url) != bool(public_key) or (feed_url and not valid_update_configuration(feed_url, public_key)):
        raise ValueError("Updates require an HTTPS feed URL and a base64-encoded 32-byte Ed25519 public key")
    data = {"CFBundleIdentifier": MAC_BUNDLE_ID, "CFBundleName": APP_NAME,
            "CFBundleShortVersionString": version, "CFBundleVersion": str(build),
            "NSHighResolutionCapable": True, "NSPrincipalClass": "NSApplication",
            "LSMinimumSystemVersion": "12.0"}
    if feed_url:
        data.update(SUFeedURL=feed_url, SUPublicEDKey=public_key, SUEnableAutomaticChecks=False,
                    SUAutomaticallyUpdate=False, SUAllowsAutomaticUpdates=False,
                    SUEnableSystemProfiling=False, SUVerifyUpdateBeforeExtraction=True)
    return data


def run(*args) -> None:
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT)


def sign_bundle(app: Path, identity: str) -> None:
    # Sign nested Mach-O code and bundles from the inside out; do not rely on codesign --deep to sign.
    magic = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
             b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}
    paths = sorted(app.rglob("*"), key=lambda p: len(p.parts), reverse=True)
    for path in paths:
        if path.is_symlink():
            continue
        is_bundle = path.is_dir() and path.suffix in (".framework", ".app", ".xpc")
        is_code = False
        if path.is_file():
            with path.open("rb") as stream:
                is_code = stream.read(4) in magic
        if is_bundle or is_code:
            run("codesign", "--force", "--timestamp", "--options", "runtime", "--preserve-metadata=entitlements",
                "--sign", identity, path)
    run("codesign", "--force", "--timestamp", "--options", "runtime", "--sign", identity,
        "--entitlements", ROOT / "packaging/macos/entitlements.plist", app)
    run("codesign", "--verify", "--deep", "--strict", app)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-number", required=True, type=int)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--feed-url", default="")
    parser.add_argument("--public-key", default="")
    parser.add_argument("--sparkle-framework", type=Path)
    parser.add_argument("--sparkle-license", type=Path, help="LICENSE from the same Sparkle distribution")
    parser.add_argument("--identity", help="Developer ID Application identity in the macOS Keychain")
    parser.add_argument("--notary-profile", help="notarytool Keychain profile (never an inline password)")
    parser.add_argument("--out", type=Path, default=ROOT / "dist/macos")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Build this app on macOS, once on arm64 and once on x86_64 if supporting both")
    if not args.development and not all([args.feed_url, args.public_key, args.sparkle_framework, args.identity]):
        parser.error("Release builds need --feed-url, --public-key, --sparkle-framework and --identity")
    if args.development and any([args.feed_url, args.public_key, args.sparkle_framework]):
        parser.error("Use a release build for Sparkle updates; development builds have no updater")
    if args.notary_profile and not args.identity:
        parser.error("Notarization requires --identity")
    try:
        metadata = bundle_metadata(version=__version__, build=args.build_number,
                                   feed_url=args.feed_url, public_key=args.public_key)
    except ValueError as error:
        parser.error(str(error))
    if args.sparkle_framework and not (args.sparkle_framework / "Sparkle").is_file():
        parser.error("--sparkle-framework must point to Sparkle.framework from an official Sparkle 2 release")
    sparkle_license = args.sparkle_license
    if args.sparkle_framework and sparkle_license is None:
        for candidate in (args.sparkle_framework.parent / "LICENSE", args.sparkle_framework.parent / "LICENSE.txt"):
            if candidate.is_file():
                sparkle_license = candidate
                break
    if args.sparkle_framework and (sparkle_license is None or not sparkle_license.is_file()):
        parser.error("Supply --sparkle-license with the LICENSE from your Sparkle distribution")
    arch = platform.machine()
    if arch not in ("arm64", "x86_64"):
        parser.error("Unsupported build architecture")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{APP_NAME}-{__version__}-{args.build_number}-{arch}"
    dmg = out / (stem + ".dmg")
    if dmg.exists():
        parser.error(f"Refusing to overwrite a release artifact: {dmg}")
    work = ROOT / "build/macos" / stem
    work.mkdir(parents=True, exist_ok=True)
    iconset = work / "AppIcon.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            name = f"icon_{size}x{size}" + ("@2x" if scale == 2 else "") + ".png"
            run("sips", "-z", size * scale, size * scale, ROOT / "packaging/macos/icon-concept-v1.png",
                "--out", iconset / name)
    icon = work / "AppIcon.icns"
    run("iconutil", "-c", "icns", iconset, "-o", icon)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir", "--name", APP_NAME,
        "--osx-bundle-identifier", MAC_BUNDLE_ID, "--icon", icon, "--paths", ROOT / "src",
        "--add-data", f"{ROOT / 'src/paperdesk/web/static'}:paperdesk/web/static",
        "--hidden-import", "webview.platforms.cocoa", "--hidden-import", "PyObjCTools.AppHelper",
        "--exclude-module", "PyQt5", "--exclude-module", "PyQt6", "--exclude-module", "PySide6",
        "--specpath", work, "--workpath", work / "freeze", "--distpath", work / "dist",
        ROOT / "packaging/macos/launcher.py")
    app = work / "dist" / (APP_NAME + ".app")
    plist = app / "Contents/Info.plist"
    data = plistlib.loads(plist.read_bytes())
    data.update(metadata)
    plist.write_bytes(plistlib.dumps(data))
    resources = app / "Contents/Resources"
    resources.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", resources / "THIRD_PARTY_NOTICES.md")
    if args.sparkle_framework:
        frameworks = app / "Contents/Frameworks"
        frameworks.mkdir(exist_ok=True)
        shutil.copytree(args.sparkle_framework.resolve(), frameworks / "Sparkle.framework", symlinks=True)
        shutil.copy2(sparkle_license, resources / "Sparkle-LICENSE.txt")
        executable = app / "Contents/MacOS" / APP_NAME
        commands = subprocess.run(["otool", "-l", str(executable)], check=True, capture_output=True, text=True).stdout
        if "path @executable_path/../Frameworks " not in commands:
            run("install_name_tool", "-add_rpath", "@executable_path/../Frameworks", executable)
    if args.identity:
        sign_bundle(app, args.identity)
    else:
        run("codesign", "--force", "--deep", "--sign", "-", app)
    if args.notary_profile:
        archive = work / "notarize.zip"
        run("ditto", "-c", "-k", "--keepParent", app, archive)
        run("xcrun", "notarytool", "submit", archive, "--keychain-profile", args.notary_profile, "--wait")
        run("xcrun", "stapler", "staple", app)
    stage = work / "image"
    stage.mkdir(exist_ok=True)
    # ditto preserves framework symlinks, signatures, and metadata.
    run("ditto", app, stage / app.name)
    (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
    run("hdiutil", "create", "-volname", APP_NAME, "-srcfolder", stage, "-format", "UDZO", dmg)
    if args.identity:
        run("codesign", "--force", "--timestamp", "--sign", args.identity, dmg)
    if args.notary_profile:
        run("xcrun", "notarytool", "submit", dmg, "--keychain-profile", args.notary_profile, "--wait")
        run("xcrun", "stapler", "staple", dmg)
    # Used by the release renderer to reject unsigned/development artifacts.
    receipt = {"version": __version__, "build": args.build_number, "arch": arch,
               "updates": bool(args.feed_url), "signed": bool(args.identity),
               "notarized": bool(args.notary_profile), "bundle_id": MAC_BUNDLE_ID}
    dmg.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(dmg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
