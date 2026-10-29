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
import importlib.metadata
import hashlib
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from paperdesk import APP_NAME, MAC_BUNDLE_ID, MAC_MINIMUM_VERSION, __version__
from paperdesk.infrastructure.macos_updates import valid_update_configuration


def verify_production_modules(executable: Path) -> None:
    """Reject accidental inclusion of development fixtures or unfinished integrations."""
    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(executable)).open_embedded_archive("PYZ.pyz")
    blocked = {"paperdesk.providers.demo", "paperdesk.providers.chatgpt_plan"}
    unexpected = sorted(name for name in archive.toc
                        if name.split(".")[0] in {"tests", "experiments"} or name in blocked)
    if unexpected:
        raise ValueError("Development modules in app bundle: " + ", ".join(unexpected))


def bundle_metadata(*, version: str, build: int, feed_url: str = "", public_key: str = "") -> dict:
    if build < 1:
        raise ValueError("Build number must be a positive integer and must increase for every release")
    if bool(feed_url) != bool(public_key) or (feed_url and not valid_update_configuration(feed_url, public_key)):
        raise ValueError("Updates require an HTTPS feed URL and a base64-encoded 32-byte Ed25519 public key")
    data = {"CFBundleIdentifier": MAC_BUNDLE_ID, "CFBundleName": APP_NAME,
            "CFBundleShortVersionString": version, "CFBundleVersion": str(build),
            "NSHighResolutionCapable": True, "NSPrincipalClass": "NSApplication",
            "LSMinimumSystemVersion": MAC_MINIMUM_VERSION}
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
    parser.add_argument("--analysis-runtime", type=Path, required=True, help="Portable runtime from scripts/build_analysis_runtime.py")
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
    analysis_runtime = args.analysis_runtime.resolve()
    if not (analysis_runtime / "bin/python3.12").is_file() or not (analysis_runtime / "paperdesk-analysis.json").is_file():
        parser.error("Build the portable Docling runtime first")
    analysis_manifest = json.loads((analysis_runtime / "paperdesk-analysis.json").read_text())
    if analysis_manifest.get("lock_sha256") != hashlib.sha256((ROOT / "requirements/docling-macos.lock").read_bytes()).hexdigest():
        parser.error("The Docling runtime does not match requirements/docling-macos.lock")
    from release_preflight import dependency_issues
    issues = dependency_issues()
    if issues:
        parser.error('Install requirements/macos-build.lock first: ' + '; '.join(issues))
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
    if arch != "arm64":
        parser.error("The initial macOS beta supports Apple Silicon (arm64) only")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{APP_NAME}-{__version__}-{args.build_number}-{arch}"
    dmg = out / (stem + ".dmg")
    if dmg.exists():
        parser.error(f"Refusing to overwrite a release artifact: {dmg}")
    work = ROOT / "build/macos" / stem
    work.mkdir(parents=True, exist_ok=True)
    icon_output = work / "icons"
    icon_output.mkdir(exist_ok=True)
    icon_info = work / "icon-info.plist"
    run("xcrun", "actool", "--compile", icon_output, "--platform", "macosx",
        "--minimum-deployment-target", "15.0", "--app-icon", APP_NAME,
        "--output-partial-info-plist", icon_info, ROOT / "packaging/macos/Paperdesk.icon")
    icon = icon_output / (APP_NAME + ".icns")
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir", "--name", APP_NAME,
        "--osx-bundle-identifier", MAC_BUNDLE_ID, "--icon", icon, "--paths", ROOT / "src",
        "--add-data", f"{ROOT / 'src/paperdesk/web/static'}:paperdesk/web/static",
        "--add-data", f"{ROOT / 'src/paperdesk/infrastructure/docling_worker.py'}:paperdesk/infrastructure",
        "--hidden-import", "webview.platforms.cocoa", "--hidden-import", "PyObjCTools.AppHelper",
        "--exclude-module", "tests", "--exclude-module", "experiments",
        "--exclude-module", "PyQt5", "--exclude-module", "PyQt6", "--exclude-module", "PySide6",
        "--specpath", work, "--workpath", work / "freeze", "--distpath", work / "dist",
        ROOT / "packaging/macos/launcher.py")
    app = work / "dist" / (APP_NAME + ".app")
    verify_production_modules(app / "Contents/MacOS" / APP_NAME)
    plist = app / "Contents/Info.plist"
    data = plistlib.loads(plist.read_bytes())
    data.update(metadata)
    data.update(plistlib.loads(icon_info.read_bytes()))
    plist.write_bytes(plistlib.dumps(data))
    resources = app / "Contents/Resources"
    resources.mkdir(exist_ok=True)
    shutil.copytree(analysis_runtime, resources / "analysis-runtime", symlinks=True)
    shutil.copy2(icon_output / "Assets.car", resources / "Assets.car")
    shutil.copy2(icon, resources / icon.name)
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", resources / "THIRD_PARTY_NOTICES.md")
    for name in ('LICENSE', 'NOTICE', 'docs/privacy.md', 'docs/support.md'):
        source = ROOT/name
        if source.is_file():
            shutil.copy2(source, resources/source.name)
    dependencies = {line.split('==')[0]: importlib.metadata.version(line.split('==')[0])
                    for line in (ROOT/'requirements/macos-build.lock').read_text().splitlines()
                    if line and not line.startswith('#')}
    source_hash = hashlib.sha256()
    sources = [p for folder in ('src', 'scripts', 'packaging', 'requirements') for p in (ROOT/folder).rglob('*')
               if p.is_file() and '__pycache__' not in p.parts]
    sources += [ROOT/'pyproject.toml', ROOT/'THIRD_PARTY_NOTICES.md']
    for name in ('LICENSE', 'NOTICE'):
        if (ROOT/name).is_file():
            sources.append(ROOT/name)
    for source in sorted(sources):
        source_hash.update(str(source.relative_to(ROOT)).encode()+b'\0'+source.read_bytes())
    manifest = {'version': __version__, 'build': args.build_number, 'arch': arch,
                'python': platform.python_version(), 'dependencies': dependencies,
                'analysis_runtime': analysis_manifest,
                'source_tree_sha256': source_hash.hexdigest(),
                'lock_sha256': hashlib.sha256((ROOT/'requirements/macos-build.lock').read_bytes()).hexdigest()}
    (resources/'build-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    licenses = resources/'licenses'
    licenses.mkdir(exist_ok=True)
    python_license = Path(sysconfig.get_path('stdlib'))/'LICENSE.txt'
    if not python_license.is_file():
        parser.error('The Python distribution LICENSE.txt is required for bundling')
    shutil.copy2(python_license, licenses/'CPython-LICENSE.txt')
    for dependency in dependencies:
        distribution = importlib.metadata.distribution(dependency)
        for entry in distribution.files or ():
            name = str(entry)
            if '.dist-info/' in name and ('/licenses/' in name or entry.name.upper().startswith(('LICENSE','COPYING'))):
                source = Path(distribution.locate_file(entry))
                if source.is_file():
                    destination = licenses/dependency/name.split('.dist-info/', 1)[1]
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
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
    receipt = {**manifest,
               "updates": bool(args.feed_url), "signed": bool(args.identity),
               "notarized": bool(args.notary_profile), "bundle_id": MAC_BUNDLE_ID}
    dmg.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(dmg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
