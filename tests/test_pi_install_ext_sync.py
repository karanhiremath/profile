from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT_SYNC = ROOT / "bin/pi/ext-sync.sh"
INSTALL = ROOT / "bin/pi/install"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class ExtSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.profile = root / "profile"
        self.profile_ext = self.profile / "config/pi/extensions"
        self.overlay = root / "home/.pi/work-agent/extensions"
        self.dst = root / "home/.pi/agent/extensions"
        (self.dst / "lib").mkdir(parents=True)
        (self.dst / "subagent").mkdir()
        for rel in (
            "handoff.ts",
            "compact-handoff.ts",
            "together-spend.ts",
            "lib/handoff-brief.ts",
            "lib/compact-snapshot.ts",
            "subagent/jobs.ts",
            "subagent/job-runner.mjs",
        ):
            write(self.profile_ext / rel, f"profile {rel}\n")

    def sync(self, src: Path, dst: Path, prefix: str = "") -> subprocess.CompletedProcess[str]:
        script = '. "$1"; sync_ext_files "$2" "$3" "$4"'
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", script, "ext-sync", str(EXT_SYNC), str(src), str(dst), prefix],
            env={"PROFILE_DIR": str(self.profile), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            check=True,
        )

    def test_stale_overlay_handoff_cannot_replace_the_profile_stack(self) -> None:
        write(self.overlay / "handoff.ts", "stale overlay fork\n")
        write(self.overlay / "compact-handoff.ts", "stale overlay lane\n")
        write(self.overlay / "cwd-title.ts", "overlay cwd-title\n")
        # harness-sync apply ran first and installed the profile copy.
        write(self.dst / "handoff.ts", "profile handoff.ts\n")

        result = self.sync(self.overlay, self.dst)

        self.assertEqual((self.dst / "handoff.ts").read_text(), "profile handoff.ts\n")
        self.assertEqual((self.dst / "compact-handoff.ts").read_text(), "profile compact-handoff.ts\n")
        self.assertEqual((self.dst / "cwd-title.ts").read_text(), "overlay cwd-title\n")
        self.assertIn("ignoring", result.stderr)
        self.assertIn("the profile owns handoff.ts", result.stderr)
        self.assertIn("the profile owns compact-handoff.ts", result.stderr)
        self.assertNotIn("cwd-title", result.stderr)

    def test_profile_copy_is_installed_even_if_harness_sync_did_not_run(self) -> None:
        write(self.overlay / "handoff.ts", "stale overlay fork\n")

        self.sync(self.overlay, self.dst)

        self.assertEqual((self.dst / "handoff.ts").read_text(), "profile handoff.ts\n")

    def test_overlay_keeps_names_harness_sync_does_not_install(self) -> None:
        # together-spend.ts exists in the profile, but harness-sync does not
        # install it on a work host, so the overlay copy must still land.
        write(self.overlay / "together-spend.ts", "overlay together-spend\n")

        result = self.sync(self.overlay, self.dst)

        self.assertEqual((self.dst / "together-spend.ts").read_text(), "overlay together-spend\n")
        self.assertEqual(result.stderr, "")

    def test_lib_and_subagent_prefixes_are_guarded(self) -> None:
        write(self.overlay / "lib/handoff-brief.ts", "stale lib\n")
        write(self.overlay / "lib/local-only.ts", "overlay local lib\n")
        write(self.overlay / "subagent/jobs.ts", "stale jobs\n")
        write(self.overlay / "subagent/job-runner.mjs", "stale runner\n")
        write(self.overlay / "subagent/index.ts", "overlay subagent index\n")

        lib = self.sync(self.overlay / "lib", self.dst / "lib", "lib/")
        sub = self.sync(self.overlay / "subagent", self.dst / "subagent", "subagent/")

        self.assertEqual((self.dst / "lib/handoff-brief.ts").read_text(), "profile lib/handoff-brief.ts\n")
        self.assertEqual((self.dst / "lib/local-only.ts").read_text(), "overlay local lib\n")
        self.assertEqual((self.dst / "subagent/jobs.ts").read_text(), "profile subagent/jobs.ts\n")
        self.assertEqual((self.dst / "subagent/job-runner.mjs").read_text(), "profile subagent/job-runner.mjs\n")
        self.assertEqual((self.dst / "subagent/index.ts").read_text(), "overlay subagent index\n")
        self.assertIn("the profile owns lib/handoff-brief.ts", lib.stderr)
        self.assertIn("the profile owns subagent/jobs.ts", sub.stderr)

    def test_identical_overlay_copy_is_silent(self) -> None:
        write(self.overlay / "handoff.ts", "profile handoff.ts\n")

        result = self.sync(self.overlay, self.dst)

        self.assertEqual((self.dst / "handoff.ts").read_text(), "profile handoff.ts\n")
        self.assertEqual(result.stderr, "")

    def test_personal_install_from_the_profile_itself(self) -> None:
        # harness-sync symlinks personal extensions; cp onto such a link fails.
        (self.dst / "together-spend.ts").symlink_to(self.profile_ext / "together-spend.ts")

        result = self.sync(self.profile_ext, self.dst)

        self.assertTrue((self.dst / "together-spend.ts").is_symlink())
        self.assertEqual((self.dst / "handoff.ts").read_text(), "profile handoff.ts\n")
        self.assertEqual(result.stderr, "")

    def test_install_sources_the_helper_and_passes_each_prefix(self) -> None:
        text = INSTALL.read_text(encoding="utf-8")
        self.assertIn('. "${SCRIPT_DIR}/ext-sync.sh"', text)
        self.assertNotIn("sync_ext_files() {", text)
        self.assertIn('sync_ext_files "$extensions_src" "$extensions_dir"\n', text)
        self.assertIn('sync_ext_files "$extensions_src/lib" "$extensions_dir/lib" "lib/"', text)
        self.assertIn('sync_ext_files "$extensions_src/subagent" "$extensions_dir/subagent" "subagent/"', text)


if __name__ == "__main__":
    unittest.main()
