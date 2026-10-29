"""Read-only release gates. Manual checks are evidence, not automatically marked passes."""
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from paperdesk import __version__

CHECKS = ('fresh_mac_install', 'minimum_macos_15', 'native_selection_hover_and_regions',
          'codex_and_claude_live_requests', 'sleep_disconnect_cancel_and_resume',
          'backup_restore_and_disk_failure', 'signed_upgrade_preserves_library', 'privacy_and_license_review')


def dependency_issues() -> list[str]:
    issues = []
    if sys.version_info[:2] != (3, 12):
        issues.append('The macOS beta build requires Python 3.12')
    for line in (ROOT/'requirements/macos-build.lock').read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        name, expected = line.split('==')
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = 'missing'
        if actual != expected:
            issues.append(f'{name}: expected {expected}, found {actual}')
    return issues


def check_release(path: Path, *, version: str, build: int, architecture: str) -> None:
    if not (ROOT/'LICENSE').is_file():
        raise ValueError('Choose the project license and add LICENSE before public release')
    data = json.loads(path.read_text())
    if (data.get('version'), data.get('build'), data.get('architecture')) != (version, build, architecture):
        raise ValueError('The manual verification record must match this exact release')
    if not data.get('tester') or not data.get('date') or any(data.get(key) is not True for key in CHECKS):
        raise ValueError('Complete and record all manual release checks; do not mark untested checks as passed')


if __name__ == '__main__':
    issues = dependency_issues()
    for issue in issues:
        print(issue)
    raise SystemExit(bool(issues))
