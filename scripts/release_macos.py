#!/usr/bin/env python3
"""Prepare signed Sparkle feeds and a Homebrew Cask from final, notarized DMGs.

Example: python3 scripts/release_macos.py --repo OWNER/paperdesk --sparkle-bin /path/to/Sparkle/bin \
  --dmg dist/macos/Paperdesk-0.1.0-1-arm64.dmg [--dmg ...-x86_64.dmg]

This writes local release files only. It never publishes a release, pushes a tap, or reads a private key.
Sparkle's generate_appcast uses the signing key in the operator's macOS Keychain.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPARKLE = "http://www.andymatuschak.org/xml-namespaces/sparkle"


def artifact(path: Path) -> dict:
    meta = json.loads(path.with_suffix(".json").read_text())
    if not all(meta.get(k) for k in ("updates", "signed", "notarized")):
        raise ValueError("Only signed, notarized builds configured for Sparkle can be released")
    if meta.get("arch") not in ("arm64", "x86_64") or not isinstance(meta.get("build"), int) or meta["build"] < 1:
        raise ValueError("Invalid release architecture or build number")
    if not re.fullmatch(r"\d+\.\d+\.\d+", meta.get("version", "")):
        raise ValueError("Use a numeric major.minor.patch release version")
    expected = f"Paperdesk-{meta['version']}-{meta['build']}-{meta['arch']}.dmg"
    if path.name != expected:
        raise ValueError(f"Artifact must be named {expected}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {**meta, "path": path, "sha256": digest.hexdigest()}


def render_cask(repo: str, artifacts: list[dict]) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Use a GitHub OWNER/REPOSITORY")
    if not artifacts or len({a['arch'] for a in artifacts}) != len(artifacts):
        raise ValueError("Supply one final DMG per architecture")
    first = artifacts[0]
    if any((a['version'], a['build'], a['bundle_id']) != (first['version'], first['build'], first['bundle_id']) for a in artifacts):
        raise ValueError("Both architectures must use the same version, build number and bundle identifier")
    by_arch = {a['arch']: a for a in artifacts}
    lines = ['cask "paperdesk" do']
    if len(by_arch) == 2:
        lines += ['  arch arm: "arm64", intel: "x86_64"']
    lines += [f'  version "{first["version"]},{first["build"]}"']
    if len(by_arch) == 2:
        for cpu, kind in [('arm64', 'arm'), ('x86_64', 'intel')]:
            lines += [f'  on_{kind} do', f'    sha256 "{by_arch[cpu]["sha256"]}"', '  end']
        arch_part = '#{arch}'
    else:
        cpu = first['arch']
        lines += [f'  sha256 "{first["sha256"]}"']
        arch_part = cpu
    lines += ['', f'  url "https://github.com/{repo}/releases/download/v#{{version.csv.first}}/Paperdesk-#{{version.csv.first}}-#{{version.csv.second}}-{arch_part}.dmg"',
              '  name "Paperdesk"', '  desc "Local paper reader with pluggable AI assistants"',
              f'  homepage "https://github.com/{repo}"', '', '  auto_updates true', '  depends_on macos: ">= :monterey"']
    if len(by_arch) == 1:
        lines += ['  depends_on arch: ' + (':arm64' if first['arch'] == 'arm64' else ':x86_64')]
    lines += ['', '  app "Paperdesk.app"',
              '  binary "#{appdir}/Paperdesk.app/Contents/MacOS/Paperdesk", target: "paperdesk"',
              '', f'  uninstall quit: "{first["bundle_id"]}"', 'end', '']
    # User-created papers, chat history and notes intentionally have no uninstall/zap deletion rules.
    return '\n'.join(lines)


def verify_feed(path: Path, release: dict, expected_url: str) -> None:
    root = ET.parse(path).getroot()
    found = False
    for item in root.findall('./channel/item'):
        enclosure = item.find('enclosure')
        if enclosure is None or enclosure.get('url') != expected_url:
            continue
        signature = enclosure.get(f'{{{SPARKLE}}}edSignature', '')
        if len(base64.b64decode(signature, validate=True)) != 64:
            raise ValueError("Sparkle did not sign the archive with Ed25519")
        # Sparkle versions may put these attributes on enclosure or on item elements.
        version = enclosure.get(f'{{{SPARKLE}}}version') or item.findtext(f'{{{SPARKLE}}}version')
        if version != str(release['build']):
            raise ValueError("Appcast build number does not match the app bundle")
        if enclosure.get('length') != str(release['path'].stat().st_size):
            raise ValueError("Appcast archive size does not match the final DMG")
        found = True
    if not found:
        raise ValueError("Appcast does not contain the expected signed update")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--dmg', type=Path, action='append', required=True)
    parser.add_argument('--sparkle-bin', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'dist/release')
    args = parser.parse_args()
    try:
        releases = [artifact(path.resolve()) for path in args.dmg]
        cask = render_cask(args.repo, releases)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    tool = args.sparkle_bin / 'generate_appcast'
    if not tool.is_file():
        parser.error('--sparkle-bin must contain Sparkle 2 generate_appcast')
    args.out.mkdir(parents=True, exist_ok=True)
    prefix = f'https://github.com/{args.repo}/releases/download/v{releases[0]["version"]}/'
    for release in releases:
        folder = args.out / release['arch']
        folder.mkdir(exist_ok=True)
        target = folder / release['path'].name
        if target.exists():
            parser.error(f'Refusing to overwrite existing release staging: {target}')
        shutil.copy2(release['path'], target)
        feed = folder / f'appcast-{release["arch"]}.xml'
        subprocess.run([str(tool.resolve()), '--download-url-prefix', prefix, '-o', str(feed.resolve()),
                        str(folder.resolve())], check=True)
        verify_feed(feed, release, prefix + release['path'].name)
        shutil.copy2(feed, args.out / f'appcast-{release["arch"]}.xml')
    (args.out / 'paperdesk.rb').write_text(cask)
    print(f'Prepared {args.out}: upload the final DMGs and appcast-*.xml; copy paperdesk.rb into your tap Casks/.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
