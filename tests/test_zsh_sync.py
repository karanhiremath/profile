from __future__ import annotations

import json
import os
import subprocess
import tempfile
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZSH_SYNC = ROOT / "bin/zsh/zsh-sync"
ZSH_INSTALL = ROOT / "bin/zsh/install"


class ZshSyncEnv:
    """Isolated home + git repo fixture for zsh-sync runs."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.repo = Path(self.tmp.name) / "repo"
        self.home.mkdir()
        self._make_repo()

    def _make_repo(self):
        self.repo.mkdir()
        (self.repo / "zsh.d").mkdir()
        (self.repo / "bin" / "pi").mkdir(parents=True)
        (self.repo / "zshrc.bootstrap").write_text("# profile-managed bootstrap\n")
        (self.repo / "zsh.d/10-example.zsh").write_text("export EXAMPLE=ok\n")
        (self.repo / "bin/pi/pi-update-wrapper.sh").write_text("# wrapper\n")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        for cmd in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "t@t"],
            ["git", "config", "user.name", "t"],
            ["git", "add", "-A"],
            ["git", "commit", "-qm", "init"],
        ):
            subprocess.run(cmd, cwd=self.repo, check=True, env=env, capture_output=True)

    def install(self):
        r = subprocess.run(
            [str(ZSH_INSTALL)],
            capture_output=True,
            text=True,
            env=self.env(),
        )
        if r.returncode != 0:
            raise AssertionError(f"install failed rc={r.returncode}:\n{r.stdout}\n{r.stderr}")

    def env(self, **over):
        e = dict(
            os.environ,
            ZSH_SYNC_HOME=str(self.home),
            ZSH_BASELINE_DIR=str(self.home / ".cache/profile/zsh-baseline"),
            PROFILE_DIR=str(self.repo),
            HOME=str(self.home),
            GIT_AUTHOR_NAME="t",
            GIT_AUTHOR_EMAIL="t@t",
            GIT_COMMITTER_NAME="t",
            GIT_COMMITTER_EMAIL="t@t",
        )
        e.update(over)
        return e

    def run(self, *args, **kw):
        return subprocess.run([str(ZSH_SYNC), *args], capture_output=True, text=True, env=self.env(**kw))

    def cleanup(self):
        self.tmp.cleanup()


class TestZshSyncSecretGuard(unittest.TestCase):
    def setUp(self):
        self.env = ZshSyncEnv()
        self.env.install()
        self.addCleanup(self.env.cleanup)

    def test_capture_refuses_secret_fragment(self):
        frag = self.env.home / ".zshrc.d/20-leaky.zsh"
        frag.write_text("export DD_API_KEY=deadbeefcafe0123456789abcdef0123\n")
        r = self.env.run("capture", "--yes")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("secret", (r.stdout + r.stderr).lower())
        pending = self.env.repo / "merge-queue/pending"
        if pending.exists():
            self.assertEqual(list(pending.iterdir()), [], "secret fragment must not reach the queue")

    def test_capture_refuses_secret_repo_diff(self):
        prof = self.env.repo / "zsh_profile.sh"
        prof.write_text("# shared\nexport AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIb7PX\n")
        subprocess.run(["git", "add", "zsh_profile.sh"], cwd=self.env.repo, check=True, capture_output=True)
        r = self.env.run("capture", "--yes")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_capture_allows_clean_fragment_and_queues_promote(self):
        frag = self.env.home / ".zshrc.d/30-fzf.zsh"
        frag.write_text("export FZF_DEFAULT_OPTS='--height 40%'\n")
        r = self.env.run("capture", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pending = sorted((self.env.repo / "merge-queue/pending").iterdir())
        self.assertEqual(len(pending), 1)
        meta = json.loads((pending[0] / "meta.json").read_text())
        self.assertEqual(meta["kind"], "promote")
        self.assertEqual(meta["target"], "zsh.d/30-fzf.zsh")


class TestZshSyncMerge(unittest.TestCase):
    def setUp(self):
        self.env = ZshSyncEnv()
        self.env.install()
        self.addCleanup(self.env.cleanup)

    def head(self):
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.env.repo, capture_output=True, text=True
        ).stdout.strip()

    def test_merge_applies_promote_item_with_validation(self):
        frag = self.env.home / ".zshrc.d/30-alias.zsh"
        frag.write_text("alias gs='git status'\n")
        self.assertEqual(self.env.run("capture", "--yes").returncode, 0)
        before = self.head()
        r = self.env.run("merge", "--all")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.env.repo / "zsh.d/30-alias.zsh").read_text(), frag.read_text())
        self.assertNotEqual(self.head(), before, "merge must commit the applied item")
        merged = self.env.repo / "merge-queue/merged"
        self.assertEqual(len(list(merged.iterdir())), 1, "applied item moves to merged/")

    @unittest.skipUnless(shutil.which("zsh"), "zsh not available; revert contract not exercisable")
    def test_merge_rejects_syntactically_broken_promote(self):
        frag = self.env.home / ".zshrc.d/40-broken.zsh"
        frag.write_text("export UNCLOSED='oops\n")
        self.assertEqual(self.env.run("capture", "--yes").returncode, 0)
        before = self.head()
        r = self.env.run("merge", "--all")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.env.repo / "zsh.d/40-broken.zsh").exists(), "invalid payload must be reverted")
        self.assertEqual(self.head(), before, "no commit for invalid payload")


class TestZshSyncStatus(unittest.TestCase):
    def setUp(self):
        self.env = ZshSyncEnv()
        self.env.install()
        self.addCleanup(self.env.cleanup)

    def test_status_json_clean_after_install(self):
        r = self.env.run("status", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["installed_drift"], "")
        self.assertEqual(data["fragment_drift"], "")

    def test_status_detects_edited_installed_copy(self):
        zshrc = self.env.home / ".zshrc"
        zshrc.write_text(zshrc.read_text() + "\n# host tweak\n")
        r = self.env.run("status", "--json")
        data = json.loads(r.stdout)
        self.assertIn("zshrc", data["installed_drift"])


if __name__ == "__main__":
    unittest.main()