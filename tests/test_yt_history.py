"""Contained yt-history regression tests: no real yt-dlp, homes or mounts."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "bin/yt-history/yt-history"
ZSH = shutil.which("zsh")
FAKE_YTDLP = r'''
import json
import os
from pathlib import Path
import re
import sys

args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")

def option(name):
    return args[args.index(name) + 1]

if "--download-archive" in args:
    vid = os.environ.get("FAKE_SYNC_ID", "Sync_123")
    if "FAKE_SYNC_ID" in os.environ:
        if "--match-filter" not in args:
            sys.exit(98)
        pattern = option("--match-filter").split('"')[1]
        if not re.search(pattern, vid):
            sys.exit(0)
        # Never let a broken script's filter cause the fake to write unsafe paths.
        if not re.fullmatch(r"[A-Za-z0-9_-]+", vid):
            sys.exit(97)
    archive = Path(option("--download-archive"))
    lines = os.environ.get("FAKE_ARCHIVE_LINES", f"youtube {vid}\n")
    with archive.open("a", encoding="utf-8") as fh:
        fh.write(lines)
    if os.environ.get("FAKE_INFO") == "1":
        template = option("-o")
        output = Path(template.replace("%(id)s", vid).replace("%(ext)s", "info.json"))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({
            "id": vid, "title": "A\tB\nC", "channel": "Test channel",
            "duration": 12,
        }), encoding="utf-8")
else:
    output = Path(option("-o").replace("%(id)s", "Video_123-xy").replace("%(ext)s", "mp4"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"fake video")
sys.exit(int(os.environ.get("FAKE_RC", "0")))
'''


@unittest.skipUnless(ZSH, "yt-history requires zsh")
class YtHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yt-history-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "archive"
        self.krop = self.base / "promotion"
        self.outside = self.base / "outside"
        self.bin = self.base / "bin"
        self.home = self.base / "home"
        for path in (self.root, self.krop, self.outside, self.bin, self.home):
            path.mkdir()
        self.sentinel = self.outside / "sentinel.txt"
        self.sentinel.write_bytes(b"must remain unchanged")
        self.log = self.base / "calls.jsonl"
        # A closed PATH: the only yt-dlp is our fake, and no browser tools exist.
        for name in ("mkdir", "date", "mktemp", "cp", "grep", "cat", "rm",
                     "awk", "sort", "wc", "tail", "cut"):
            command = shutil.which(name)
            if not command:
                self.skipTest(f"missing utility: {name}")
            (self.bin / name).symlink_to(command)
        (self.bin / "python3").symlink_to(sys.executable)
        fake = self.bin / "yt-dlp"
        fake.write_text(f"#!{sys.executable}\n" + FAKE_YTDLP, encoding="utf-8")
        fake.chmod(0o755)
        self.env = {
            "HOME": str(self.home), "PATH": str(self.bin), "LC_ALL": "C",
            "TMPDIR": str(self.base), "YT_HISTORY_ROOT": str(self.root),
            "YT_HISTORY_KROP_ROOT": str(self.krop),
            "YT_HISTORY_KROP_ENABLED": "1", "FAKE_LOG": str(self.log),
        }

    def run_cli(self, *args, ok=True, **environment):
        result = subprocess.run(
            [ZSH, "-f", str(SCRIPT), *args],
            env={**self.env, **environment}, cwd=self.base,
            text=True, capture_output=True, timeout=15,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def item(self, vid="Video_123-xy", root=None):
        directory = (root or self.root) / "items" / vid
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "metadata.txt").write_text("metadata", encoding="utf-8")
        return directory

    def assert_outside_unchanged(self):
        self.assertEqual(self.sentinel.read_bytes(), b"must remain unchanged")
        self.assertEqual(sorted(p.name for p in self.outside.iterdir()), ["sentinel.txt"])

    def test_raw_id_validation_for_all_item_commands(self):
        invalid = ("", "..", "../..", "../outside", "a/b", "a\\b", "a.b",
                   "a b", "a\tb", "a\nb", "a\rb", "a\x01b", "é", "%2e%2e")
        for command in ("get", "tag", "promote"):
            for vid in invalid:
                with self.subTest(command=command, vid=repr(vid)):
                    args = [command, vid] + (["label"] if command == "tag" else [])
                    self.run_cli(*args, ok=False)
                    self.assert_outside_unchanged()
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.root / "items").exists())
        self.assertFalse((self.krop / "items").exists())

    def test_supported_urls_and_normal_download_options(self):
        vid = "Video_123-xy"
        urls = (
            vid,
            f"https://www.youtube.com/watch?list=abc&v={vid}&t=2",
            f"http://m.youtube.com/watch?v={vid}#chapter",
            f"https://youtu.be/{vid}?t=2",
            f"https://www.youtube.com/shorts/{vid}?feature=share",
            f"https://youtube.com/embed/{vid}",
        )
        for url in urls:
            with self.subTest(url=url):
                self.run_cli("get", url, "--height", "720")
                self.assertEqual((self.root / "items" / vid / f"{vid}.mp4").read_bytes(),
                                 b"fake video")
                args = self.calls()[-1]
                self.assertEqual(args[-2:], ["--", f"https://www.youtube.com/watch?v={vid}"])
                self.assertIn("bv*[height<=720]+ba/b[height<=720]/b", args)
                self.assertEqual(args[args.index("--merge-output-format") + 1], "mp4")
                self.assertEqual(args[args.index("--remux-video") + 1], "mp4")
        self.run_cli("tag", urls[1], "krop")
        self.run_cli("promote", urls[3])
        self.assertTrue((self.krop / "items" / vid / f"{vid}.mp4").is_file())

    def test_url_ids_are_not_truncated_decoded_or_repaired(self):
        urls = (
            "https://youtube.com/watch?v=../..",
            "https://youtube.com/watch?v=",
            "https://youtube.com/watch?list=abc",
            "https://youtube.com/watch?v=bad%2Fid",
            "https://youtube.com/watch?v=bad\\id",
            "https://youtube.com/watch?v=bad\nid",
            "https://youtube.com/watch?v=One&v=Two",
            "https://youtube.com/watch?v=&v=Good",
            "https://youtu.be/../..", "https://youtu.be/Good/extra",
            "https://youtube.com/shorts/../..",
            "https://youtube.com/embed/Good/extra",
            "https://youtu.be/", "https://evil.example/youtube.com/watch?v=Good",
        )
        for command in ("get", "tag", "promote"):
            for url in urls:
                with self.subTest(command=command, url=repr(url)):
                    self.run_cli(command, url, *(["label"] if command == "tag" else []),
                                 ok=False)
                    self.assert_outside_unchanged()
        self.assertEqual(self.calls(), [])

    def test_preexisting_archive_ids_are_validated_before_download(self):
        lines = ("youtube ../..\n", "youtube a/b\n", "youtube a\\b\n",
                 "youtube \n", "youtube bad\tid\n", "youtube bad\rid\n",
                 "youtube bad\x01id\n", "youtube Good extra\n", "\n", "youtube\n")
        for line in lines:
            with self.subTest(line=repr(line)):
                (self.root / "archive.txt").write_text(line, encoding="utf-8")
                self.run_cli("sync", ok=False)
                self.assert_outside_unchanged()
        self.assertEqual(self.calls(), [])

    def test_new_archive_ids_rejected_before_indexing(self):
        for line in ("youtube ../..\n", "youtube bad/id\n", "youtube \n",
                     "youtube bad\x01id\n", "youtube ../outside"):
            with self.subTest(line=repr(line)):
                (self.root / "archive.txt").write_text("", encoding="utf-8")
                result = self.run_cli("sync", ok=False, FAKE_ARCHIVE_LINES=line)
                self.assertIn("invalid", result.stderr)
                self.assertEqual((self.root / "index.tsv").read_text().splitlines(),
                                 ["synced_at\tid\ttitle\tchannel\turl\tduration"])
                self.assert_outside_unchanged()
        args = self.calls()[0]
        self.assertEqual(args[args.index("--match-filter") + 1],
                         r'id ~= "^[A-Za-z0-9_-]+\Z"')
        self.assertIn("--skip-download", args)

    def test_sync_filter_rejects_metadata_ids_including_final_newline(self):
        for vid in ("", "..", "../..", "a/b", "a\\b", "Good\n", "bad\x01id"):
            with self.subTest(vid=repr(vid)):
                self.run_cli("sync", FAKE_SYNC_ID=vid, FAKE_INFO="1")
                self.assertEqual((self.root / "archive.txt").read_text(), "")
                self.assertEqual(len((self.root / "index.tsv").read_text().splitlines()), 1)
                self.assertEqual(list((self.root / "items").iterdir()), [])
                self.assert_outside_unchanged()

    def test_item_and_items_directory_symlink_escapes(self):
        items = self.root / "items"
        items.mkdir()
        item = items / "Video_123-xy"
        item.symlink_to(self.outside, target_is_directory=True)
        for command in ("get", "tag", "promote"):
            self.run_cli(command, "Video_123-xy", *(["label"] if command == "tag" else []),
                         ok=False)
            self.assert_outside_unchanged()
        self.run_cli("sync", ok=False)
        item.unlink()
        items.rmdir()
        items.symlink_to(self.outside, target_is_directory=True)
        for command in ("get", "promote"):
            self.run_cli(command, "Video_123-xy", ok=False)
        self.run_cli("sync", ok=False)
        self.run_cli("status", ok=False)
        self.assertEqual(self.calls(), [])
        self.assert_outside_unchanged()

    def test_source_contents_symlinks_are_rejected_before_copy(self):
        item = self.item()
        nested = item / "nested"
        nested.mkdir()
        for target in (self.sentinel, self.outside, self.outside / "missing", self.root):
            with self.subTest(target=target):
                link = nested / ".link"
                link.symlink_to(target)
                self.run_cli("promote", "Video_123-xy", ok=False)
                self.assertFalse((self.krop / "items").exists())
                self.assert_outside_unchanged()
                link.unlink()

    def test_destination_symlink_escapes_at_each_level(self):
        self.item()
        items = self.krop / "items"
        items.symlink_to(self.outside, target_is_directory=True)
        self.run_cli("promote", "Video_123-xy", ok=False)
        items.unlink()
        items.mkdir()
        dest = items / "Video_123-xy"
        dest.symlink_to(self.outside, target_is_directory=True)
        self.run_cli("promote", "Video_123-xy", ok=False)
        dest.unlink()
        dest.mkdir()
        (dest / "metadata.txt").symlink_to(self.sentinel)
        self.run_cli("promote", "Video_123-xy", ok=False)
        (dest / "metadata.txt").unlink()
        (dest / "nested").symlink_to(self.outside, target_is_directory=True)
        self.run_cli("promote", "Video_123-xy", ok=False)
        self.assert_outside_unchanged()

    def test_layout_file_symlink_escapes(self):
        for name in ("archive.txt", "index.tsv", "tags.tsv"):
            with self.subTest(name=name):
                path = self.root / name
                path.symlink_to(self.sentinel)
                self.run_cli("tag", "Good", "label", ok=False)
                self.run_cli("sync", ok=False)
                self.run_cli("status", ok=False)
                self.assert_outside_unchanged()
                path.unlink()
        self.assertEqual(self.calls(), [])

    def test_repeated_promotion_copies_contents_without_id_nesting(self):
        item = self.item()
        (item / ".hidden").write_text("hidden")
        (item / "nested").mkdir()
        (item / "nested" / "transcript.vtt").write_text("first")
        self.run_cli("promote", "Video_123-xy")
        dest = self.krop / "items" / "Video_123-xy"
        (item / "metadata.txt").write_text("updated")
        self.run_cli("promote", "Video_123-xy")
        self.run_cli("promote", "Video_123-xy")
        self.assertFalse((dest / "Video_123-xy").exists())
        self.assertEqual((dest / "metadata.txt").read_text(), "updated")
        self.assertEqual((dest / ".hidden").read_text(), "hidden")
        self.assertEqual((dest / "nested" / "transcript.vtt").read_text(), "first")
        self.assert_outside_unchanged()

    def test_configured_promotion_root_availability_and_enablement(self):
        self.item()
        result = self.run_cli("promote", "Video_123-xy", ok=False,
                              YT_HISTORY_KROP_ENABLED="0")
        self.assertEqual(result.returncode, 3)
        self.assertFalse((self.krop / "items").exists())
        missing = self.base / "missing-parent" / "promotion"
        self.run_cli("promote", "Video_123-xy", ok=False,
                     YT_HISTORY_KROP_ROOT=str(missing))
        self.assertFalse(missing.exists())
        # A new configured root may be created if its actual parent exists.
        new_root = self.base / "new-promotion"
        self.run_cli("promote", "Video_123-xy", YT_HISTORY_KROP_ROOT=str(new_root))
        self.assertTrue((new_root / "items" / "Video_123-xy" / "metadata.txt").is_file())
        self.assertFalse((self.home / "Library").exists())

    def test_configured_symlink_roots_use_their_resolved_boundaries(self):
        archive_alias = self.base / "archive-alias"
        promotion_alias = self.base / "promotion-alias"
        archive_alias.symlink_to(self.root, target_is_directory=True)
        promotion_alias.symlink_to(self.krop, target_is_directory=True)
        self.item()
        overrides = {"YT_HISTORY_ROOT": str(archive_alias),
                     "YT_HISTORY_KROP_ROOT": str(promotion_alias)}
        self.run_cli("promote", "Video_123-xy", **overrides)
        dest = self.krop / "items" / "Video_123-xy"
        (dest / "metadata.txt").unlink()
        (dest / "metadata.txt").symlink_to(self.sentinel)
        self.run_cli("promote", "Video_123-xy", ok=False, **overrides)
        self.assert_outside_unchanged()

    def test_configured_dotdot_is_resolved_after_directory_symlinks(self):
        physical = self.base / "physical"
        (physical / "subdir").mkdir(parents=True)
        archive = physical / "archive"
        archive.mkdir()
        alias = self.base / "alias"
        alias.symlink_to(physical / "subdir", target_is_directory=True)
        configured = str(alias) + "/../archive"
        item = self.item(root=archive)
        self.run_cli("promote", "Video_123-xy", YT_HISTORY_ROOT=configured)
        (item / "metadata.txt").unlink()
        item.rmdir()
        item.symlink_to(self.outside, target_is_directory=True)
        # A lexical collapse would check this innocent item instead of the link.
        self.item()
        self.run_cli("promote", "Video_123-xy", ok=False, YT_HISTORY_ROOT=configured)
        self.assert_outside_unchanged()

    def test_tags_and_status_are_real_tsv_with_label_counts(self):
        self.item()
        self.item("Another_123")
        for vid, label in (("Video_123-xy", "krop"), ("Another_123", "krop"),
                           ("Video_123-xy", "research notes")):
            self.run_cli("tag", vid, label)
        rows = [line.split("\t") for line in (self.root / "tags.tsv").read_text().splitlines()]
        self.assertTrue(all(len(row) == 3 for row in rows))
        self.assertEqual([row[1] for row in rows], ["krop", "krop", "research notes"])
        for label in ("", "bad\tlabel", "bad\nlabel", "bad\rlabel", "bad\x01label"):
            self.run_cli("tag", "Video_123-xy", label, ok=False)
        self.assertEqual(len((self.root / "tags.tsv").read_text().splitlines()), 3)
        output = self.run_cli("status").stdout
        self.assertNotIn("\\t", output)
        fields = [line.split("\t") for line in output.splitlines()]
        self.assertIn(["root", str(self.root)], fields)
        self.assertIn(["drive", str(self.root)], fields)
        self.assertIn(["krop_root", str(self.krop)], fields)
        self.assertIn(["items", "2"], fields)
        self.assertIn(["last_sync", "never"], fields)
        self.assertIn(["tag", "krop", "2"], fields)
        self.assertIn(["tag", "research notes", "1"], fields)
        self.assertNotIn("GoogleDrive", output)

    def test_sync_index_fallback_tabs_and_last_sync(self):
        self.run_cli("sync", "--limit", "2", FAKE_RC="101")
        args = self.calls()[-1]
        self.assertEqual(args[args.index("--playlist-end") + 1], "2")
        self.assertIn("--force-write-archive", args)
        lines = (self.root / "index.tsv").read_text().splitlines()
        self.assertEqual(len(lines), 2)
        fields = lines[1].split("\t")
        self.assertEqual(len(fields), 6)
        self.assertEqual(fields[1:], ["Sync_123", "", "",
                                     "https://www.youtube.com/watch?v=Sync_123", ""])
        self.assertIn("last_sync\t" + fields[0], self.run_cli("status").stdout)
        # An unchanged archive must not append a duplicate index row.
        self.run_cli("sync", FAKE_ARCHIVE_LINES="")
        self.assertEqual((self.root / "index.tsv").read_text().splitlines(), lines)

    def test_info_json_and_no_python_fallback_are_six_column_tsv(self):
        self.run_cli("sync", FAKE_INFO="1")
        row = (self.root / "index.tsv").read_text().splitlines()[1].split("\t")
        self.assertEqual(len(row), 6)
        self.assertEqual(row[1:4], ["Sync_123", "A B C", "Test channel"])
        self.assertEqual(row[5], "12")
        (self.root / "archive.txt").write_text("")
        (self.root / "index.tsv").write_text("")
        (self.bin / "python3").unlink()
        self.run_cli("sync", FAKE_INFO="1")
        row = (self.root / "index.tsv").read_text().splitlines()[1].split("\t")
        self.assertEqual(len(row), 6)
        self.assertEqual(row[1:], ["Sync_123", "", "", "", ""])


if __name__ == "__main__":
    unittest.main()
