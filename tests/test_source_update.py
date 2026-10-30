import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from paperdesk.infrastructure.source_update import CONFIG, SourceInstall, SourceUpdates, git_command, lock_digest

GIT = shutil.which("git")
LOCKS = ["requirements/app.lock"]


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, path, text, message):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")
    git(repo, "add", path)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


class FakePip:
    """Records pip runs and lets a test make them fail; git commands go to the real git."""

    def __init__(self):
        self.calls, self.fail = [], False

    def __call__(self, command, **options):
        if command[1:3] == ["-m", "pip"]:
            self.calls.append(command)
            return subprocess.CompletedProcess(command, 1 if self.fail else 0, "", "")
        return subprocess.run(command, **options)


@unittest.skipUnless(GIT, "git is needed for source-install updates")
class SourceUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.upstream, self.prefix = root / "upstream", root / "install"
        self.upstream.mkdir()
        git(self.upstream, "init", "-q", "-b", "main")
        commit(self.upstream, "requirements/app.lock", "pywebview==6.2.1\n", "locks")
        self.first = commit(self.upstream, "src/paperdesk/__init__.py", "__version__ = '0.1.0'\n", "first")
        self.prefix.mkdir()
        git(self.prefix, "clone", "-q", "--config", "core.autocrlf=false", str(self.upstream), "source")
        self.pip = FakePip()
        self.write_config(auto_update=True)

    def write_config(self, **data):
        source = self.prefix / "source"
        record = {"source": str(source), "branch": "main", "commit": self.first, "lock_files": LOCKS,
                  "locks": lock_digest(source, LOCKS), "error": "", **data}
        (self.prefix / CONFIG).write_text(json.dumps(record), encoding="utf-8")

    def install(self, **options):
        return SourceInstall.load(self.prefix, run=self.pip, **options)

    def test_new_commits_are_fetched_then_applied_without_pip_when_locks_are_unchanged(self):
        second = commit(self.upstream, "src/paperdesk/__init__.py", "__version__ = '0.1.1'\n", "second")
        install = self.install()
        self.assertIsNone(install.pending())  # nothing downloaded yet: the running version stays
        self.assertTrue(install.fetch())
        self.assertEqual((install.pending(), install.behind()), (second, 1))
        self.assertIn("1", SourceUpdates(install).state().message)
        self.assertTrue(SourceUpdates(install).state().ready)  # Settings offers "Restart now"
        self.assertTrue(install.apply("python"))
        self.assertEqual(git(self.prefix / "source", "rev-parse", "HEAD"), second)
        self.assertEqual(self.pip.calls, [])
        reopened = self.install()
        self.assertEqual((reopened.data["commit"], reopened.pending(), reopened.apply("python")), (second, None, False))
        self.assertFalse(SourceUpdates(reopened).state().ready)

    def test_changed_locks_reinstall_dependencies_and_a_failed_install_keeps_the_running_version(self):
        second = commit(self.upstream, "requirements/app.lock", "pywebview==6.3.0\n", "bump")
        install = self.install()
        install.fetch()
        self.pip.fail = True
        self.assertFalse(install.apply("python"))
        self.assertEqual(git(self.prefix / "source", "rev-parse", "HEAD"), self.first)
        self.assertEqual(self.install().data["error"], "apply_failed")
        self.assertTrue(self.install().fetch())  # the automatic check right after launch keeps the failure visible
        self.assertEqual(self.install().data["error"], "apply_failed")
        self.assertIn(self.first[:7], SourceUpdates(self.install()).state().message)
        self.assertEqual(len(self.pip.calls), 2)  # the new locks, then the previous ones restored
        self.pip.fail, self.pip.calls = False, []
        self.assertTrue(self.install().apply("python"))
        self.assertEqual(git(self.prefix / "source", "rev-parse", "HEAD"), second)
        self.assertEqual([c[-1] for c in self.pip.calls], [str(self.prefix / "source" / LOCKS[0])])

    def test_a_failure_notice_clears_once_upstream_has_nothing_left_to_apply(self):
        commit(self.upstream, "requirements/app.lock", "missing-package==1\n", "broken")
        install = self.install()
        install.fetch()
        self.pip.fail = True
        self.assertFalse(install.apply("python"))
        git(self.upstream, "reset", "-q", "--hard", self.first)  # the broken commit is withdrawn upstream
        self.assertTrue(self.install().fetch())
        self.assertFalse(self.install().apply("python"))
        self.assertEqual(self.install().data["error"], "")
        self.assertIn(self.first[:7], SourceUpdates(self.install()).state().message)

    def test_once_tagged_only_releases_are_applied_and_never_backwards(self):
        released = commit(self.upstream, "src/paperdesk/__init__.py", "__version__ = '0.2.0'\n", "release 0.2.0")
        git(self.upstream, "tag", "v0.2.0")
        work = commit(self.upstream, "src/paperdesk/__init__.py", "__version__ = '0.2.0' # work in progress\n", "work")
        git(self.upstream, "tag", "v0.3.0-beta.1")  # pre-releases are not offered
        install = self.install()
        self.assertTrue(install.fetch())
        self.assertEqual((install.release(), install.pending()), ("v0.2.0", released))
        self.assertIn("0.2.0", SourceUpdates(install).state().message)
        self.assertTrue(install.apply("python"))
        self.assertIsNone(self.install().pending())  # main moved on, but there is no newer release
        # An install made from a newer main already contains v0.2.0; it is never moved back to it.
        self.write_config(auto_update=True, commit=work)
        self.assertIsNone(self.install().pending())
        newer = commit(self.upstream, "src/paperdesk/__init__.py", "__version__ = '0.2.1'\n", "release 0.2.1")
        git(self.upstream, "tag", "v0.2.1")
        install = self.install()
        install.fetch()
        self.assertEqual(install.pending(), newer)

    def test_rewritten_history_upstream_is_followed(self):
        git(self.upstream, "commit", "-q", "--amend", "-m", "rewritten first")
        rewritten = git(self.upstream, "rev-parse", "HEAD")
        install = self.install()
        install.fetch()
        self.assertTrue(install.apply("python"))
        self.assertEqual(git(self.prefix / "source", "rev-parse", "HEAD"), rewritten)

    def test_local_changes_skip_the_update_and_fetch_failures_are_reported_not_raised(self):
        commit(self.upstream, "src/paperdesk/__init__.py", "__version__ = '0.2.0'\n", "second")
        install = self.install()
        install.fetch()
        (self.prefix / "source/src/paperdesk/__init__.py").write_text("edited\n", encoding="utf-8")
        self.assertFalse(install.apply("python"))
        self.assertEqual(self.install().data["error"], "local_changes")
        self.assertFalse(SourceUpdates(self.install()).state().ready)  # restarting would not apply it
        git(self.prefix / "source", "remote", "set-url", "origin", str(self.prefix / "missing"))
        self.assertFalse(self.install().fetch())
        self.assertEqual(self.install().data["error"], "local_changes")  # still needs the user, so it stays
        self.write_config(auto_update=True)
        self.assertFalse(self.install().fetch())
        self.assertEqual(self.install().data["error"], "fetch_failed")

    def test_without_git_updates_are_unavailable_and_settings_toggle_automatic_checks(self):
        install = self.install(git=None)
        self.assertFalse(install.auto_update)
        self.assertIsNone(install.pending())
        self.assertFalse(SourceUpdates(install).state().available)
        updates = SourceUpdates(self.install())
        self.assertTrue(updates.state().automatic_checks)
        updates.set_automatic_checks(False)
        self.assertFalse(self.install().auto_update)
        self.assertFalse(SourceUpdates(self.install()).state().automatic_checks)

    def test_git_never_prompts_and_keeps_line_endings(self):
        seen = {}
        def capture(command, **options):
            seen.update(command=command, env=options["env"], stdin=options["stdin"])
            return subprocess.CompletedProcess(command, 0, "", "")
        install = SourceInstall.load(self.prefix, run=capture, git="git")
        install.fetch(timeout=5)
        self.assertEqual(seen["command"][:5], git_command("git")[:5])
        self.assertIn("core.autocrlf=false", seen["command"])
        self.assertEqual((seen["env"]["GIT_TERMINAL_PROMPT"], seen["env"]["GCM_INTERACTIVE"]), ("0", "never"))
        self.assertEqual(seen["stdin"], subprocess.DEVNULL)


@unittest.skipUnless(GIT, "git is needed for source-install updates")
class SourceInstallScriptTests(unittest.TestCase):
    def setUp(self):
        from .test_updates import script
        self.installer = script("install_source")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.upstream, self.prefix = Path(self.tmp.name) / "upstream", Path(self.tmp.name) / "install"
        self.upstream.mkdir()
        self.prefix.mkdir()
        git(self.upstream, "init", "-q", "-b", "main")
        for lock in self.installer.locks():
            commit(self.upstream, f"requirements/{lock.name}", "pywebview==6.2.1\n", lock.name)

    def test_install_clones_once_records_the_choice_and_refreshes_on_rerun(self):
        with mock.patch("builtins.print"):
            source = self.installer.prepare_source(self.prefix, str(self.upstream), "main")
            self.assertEqual(source, self.prefix / "source")
            self.assertEqual(git(source, "config", "core.autocrlf"), "false")
            self.assertTrue(self.installer.record(self.prefix, source, "main", True))
            newer = commit(self.upstream, "README.md", "new\n", "newer")
            self.installer.prepare_source(self.prefix, str(self.upstream), "main")
            self.assertTrue(self.installer.record(self.prefix, source, "main", None))  # keeps the earlier choice
        saved = SourceInstall.load(self.prefix)
        self.assertEqual((saved.data["commit"], saved.auto_update), (newer, True))
        self.assertEqual(saved.data["lock_files"], [f"requirements/{lock.name}" for lock in self.installer.locks()])

    def test_install_starts_from_the_newest_release_not_the_tip_of_main(self):
        released = commit(self.upstream, "README.md", "0.2.0\n", "release 0.2.0")
        git(self.upstream, "tag", "v0.2.0")
        commit(self.upstream, "README.md", "work in progress\n", "work")
        with mock.patch("builtins.print"):
            source = self.installer.prepare_source(self.prefix, str(self.upstream), "main")
            self.assertEqual(git(source, "rev-parse", "HEAD"), released)
            newer = commit(self.upstream, "README.md", "0.2.1\n", "release 0.2.1")
            git(self.upstream, "tag", "v0.2.1")
            self.installer.prepare_source(self.prefix, str(self.upstream), "main")  # running the script again
        self.assertEqual(git(source, "rev-parse", "HEAD"), newer)

    def test_without_a_remote_the_folder_is_installed_as_is_and_no_record_remains(self):
        (self.prefix / CONFIG).write_text("{}", encoding="utf-8")
        with mock.patch("sys.stderr"), mock.patch("builtins.print"):
            self.assertIsNone(self.installer.prepare_source(self.prefix, None, "main"))
            self.assertIsNone(self.installer.prepare_source(self.prefix, str(self.prefix / "missing"), "main"))
        self.assertIsNone(self.installer.record(self.prefix, None, "main", True))
        self.assertFalse((self.prefix / CONFIG).exists())

    def test_the_consent_question_defaults_to_yes_and_never_blocks_a_script(self):
        with mock.patch("sys.stdin") as stdin, mock.patch("builtins.input", return_value=""):
            stdin.isatty.return_value = True
            self.assertTrue(self.installer.ask_auto_update(None))
            stdin.isatty.return_value = False
            self.assertFalse(self.installer.ask_auto_update(None))
            self.assertTrue(self.installer.ask_auto_update(True))


if __name__ == "__main__":
    unittest.main()
