from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
ZSH = shutil.which("zsh")


@unittest.skipUnless(ZSH, "zsh required")
class TestZshStartup(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.repo = self.home / "profile"
        self.bin = self.home / "bin"
        self.bin.mkdir()
        (self.repo / "bin/zsh").mkdir(parents=True)
        for name in ("interactive.zsh", "refresh-completions", "prompt.zsh"):
            shutil.copy2(ROOT / "bin/zsh" / name, self.repo / "bin/zsh" / name)
        shutil.copy2(ROOT / "zshrc.bootstrap", self.repo / "zshrc.bootstrap")
        shutil.copy2(ROOT / "zsh_profile.sh", self.repo / "zsh_profile.sh")
        (self.repo / "myprofile.sh").write_text(
            "(( TEST_PROFILE_LOADS += 1 ))\n"
        )
        (self.home / ".config").mkdir()
        (self.home / ".config/.vars").write_text("# isolated test config\n")
        (self.home / ".zshrc.d").mkdir()
        (self.home / ".zshrc.d/10-test.zsh").write_text(
            'export TEST_LOCAL_PATH="$PATH"\n'
        )
        self.cache_dir = self.home / "cache/profile/zsh"
        self.cache = self.cache_dir / "omp.zsh"
        self.log = self.home / "calls"
        self.release = self.home / "release"
        self.started = self.home / "started"
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            PROFILE_DIR=str(self.repo),
            XDG_CACHE_HOME=str(self.home / "cache"),
            PATH=f"{self.bin}:/usr/bin:/bin",
            TERM_PROGRAM="startup-test",
            BOOT=str(self.repo / "zshrc.bootstrap"),
            TEST_LOG=str(self.log),
            TEST_RELEASE=str(self.release),
            TEST_STARTED=str(self.started),
            MISE_DATA_DIR=str(self.home / "data/mise"),
            PROFILE_MISE_MODE="shims",
        )
        self.script("mise", '''printf 'mise\\n' >> "$TEST_LOG"
if [[ "${1:-}" == activate ]]; then
    printf '%s\\n' 'export TEST_MISE_PATH="$PATH"' 'mise() { command mise "$@"; }'
else
    printf '%s\\n' fake-mise
fi
''')
        self.script("brew", 'printf "brew\\n" >> "$TEST_LOG"\nexit 1\n')
        self.script("fzf", "exit 0\n")
        self.script("omp", 'printf "omp\\n" >> "$TEST_LOG"\nprintf "%s\\n" \'export TEST_COMPLETIONS=loaded\'\n')

    def script(self, name: str, body: str) -> Path:
        target = self.bin / name
        target.write_text("#!/bin/bash\nset -euo pipefail\n" + body)
        target.chmod(0o755)
        return target

    def shell(self, code: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [ZSH, "-dfi", "-c", code], env=self.env,
            capture_output=True, text=True, timeout=15,
        )

    def refresh(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [ZSH, "-df", str(self.repo / "bin/zsh/refresh-completions"),
             str(self.cache_dir), str(self.bin / "omp")],
            env=self.env, capture_output=True, text=True, timeout=15,
        )

    def wait_for(self, path: Path) -> None:
        deadline = time.monotonic() + 10
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.025)
        self.assertTrue(path.exists(), str(path))

    def seed_cache(self, body: str = "export TEST_COMPLETIONS=loaded\n") -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache.write_text(body)

    def slow_omp(self) -> None:
        self.script("omp", '''printf 'omp\\n' >> "$TEST_LOG"
: > "$TEST_STARTED"
for ((i=0; i<100; i++)); do
    [[ -f "$TEST_RELEASE" ]] && break
    sleep 0.05
done
[[ -f "$TEST_RELEASE" ]]
printf '%s\\n' 'export TEST_COMPLETIONS=loaded'
''')

    def test_warm_start_no_cli_generation_or_brew_and_no_duplicate_setup(self) -> None:
        self.seed_cache()
        result = self.shell(
            'source "$BOOT"; print -r -- "$TEST_PROFILE_LOADS:$TEST_COMPLETIONS"; '
            '[[ "$path[1]" == "$MISE_DATA_DIR/shims" ]]'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1:loaded")
        self.assertFalse(self.log.exists(), "warm startup must not invoke a CLI")

    def test_mise_activation_is_lazy_and_forwards_arguments(self) -> None:
        self.seed_cache()
        result = self.shell(
            'source "$BOOT"; [[ ! -e "$TEST_LOG" ]] || exit 1; '
            'mise --version; [[ -n "$TEST_MISE_PATH" ]]'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "fake-mise")
        self.assertEqual(self.log.read_text().splitlines(), ["mise", "mise"])

    def test_full_mise_activation_remains_available(self) -> None:
        self.seed_cache()
        self.env["PROFILE_MISE_MODE"] = "activate"
        result = self.shell(
            'source "$BOOT"; [[ "$TEST_MISE_PATH" == "$TEST_LOCAL_PATH" ]]'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ["mise"])

    def test_cold_start_returns_before_generator_finishes(self) -> None:
        self.slow_omp()
        try:
            result = self.shell('source "$BOOT"; print -r -- ready')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "ready")
            self.wait_for(self.started)
            self.assertFalse(self.cache.exists())
        finally:
            self.release.touch()
        self.wait_for(self.cache)
        self.assertEqual(self.cache.stat().st_mode & 0o777, 0o600)

    def test_cold_cache_is_loaded_into_current_shell_on_next_prompt(self) -> None:
        result = self.shell(
            'source "$BOOT"; '
            'for i in {1..100}; do [[ -f "$_profile_omp_cache" ]] && break; sleep .05; done; '
            '_profile_omp_load_cache; print -r -- "$TEST_COMPLETIONS"; '
            '(( ! $+functions[_profile_omp_load_cache] ))'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "loaded")

    def test_failed_or_invalid_generation_retains_old_cache(self) -> None:
        for body in ("exit 1\n", "printf '%s\\n' \"if then\"\n", "exit 0\n"):
            with self.subTest(body=body):
                self.script("omp", body)
                self.seed_cache("# previous cache\n")
                os.utime(self.cache, (1, 1))
                result = self.refresh()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.cache.read_text(), "# previous cache\n")
                self.assertEqual(list(self.cache_dir.glob(".omp.*")), [])

    def test_concurrent_workers_only_generate_once_and_lock_releases(self) -> None:
        self.slow_omp()
        args = [ZSH, "-df", str(self.repo / "bin/zsh/refresh-completions"),
                str(self.cache_dir), str(self.bin / "omp")]
        workers = []
        try:
            workers.append(subprocess.Popen(args, env=self.env, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL))
            self.wait_for(self.started)
            for _ in range(3):
                workers.append(subprocess.Popen(args, env=self.env, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL))
        finally:
            self.release.touch()
            for worker in workers:
                self.assertEqual(worker.wait(timeout=15), 0)
        self.assertEqual(self.log.read_text().splitlines(), ["omp"])
        self.assertEqual(self.refresh().stdout.strip(), '{"refreshed":false}')

    def test_prompt_does_not_wait_for_git(self) -> None:
        self.seed_cache()
        self.script("git", '''printf 'git\\n' >> "$TEST_LOG"
: > "$TEST_STARTED"
for ((i=0; i<100; i++)); do
    [[ -f "$TEST_RELEASE" ]] && break
    sleep 0.05
done
[[ -f "$TEST_RELEASE" ]]
printf '%s\\n' '## topic...origin/topic'
: > "$TEST_FINISHED"
''')
        finished = self.home / "finished"
        self.env["TEST_FINISHED"] = str(finished)
        try:
            result = self.shell('source "$BOOT"; precmd; precmd; print -r -- ready')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "ready")
            self.wait_for(self.started)
            self.assertFalse(finished.exists())
        finally:
            self.release.touch()
        self.wait_for(finished)
        self.assertEqual(self.log.read_text().splitlines(), ["git"])

    def test_async_prompt_escapes_branch_and_does_not_execute_it(self) -> None:
        self.seed_cache()
        pwn = self.home / "pwn"
        self.env["TEST_PWN"] = str(pwn)
        self.script("git", "printf '%s\\n' '## topic%$(touch${IFS}$TEST_PWN)...origin/topic' ' M file'\n")
        result = self.shell(
            'source "$BOOT"; precmd; _profile_git_ready "$_profile_git_fd"; '
            'print -P -- "$PROMPT"; [[ "$_profile_git_segment" == *"%F{9}"* ]]'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('topic%$(touch${IFS}$TEST_PWN)', result.stdout)
        self.assertFalse(pwn.exists())

    def test_async_prompt_discards_stale_cwd_results(self) -> None:
        self.seed_cache()
        self.script("git", "printf '%s\\n' '## old-topic'\n")
        other = self.home / "other"
        other.mkdir()
        self.env["TEST_OTHER"] = str(other)
        result = self.shell(
            'source "$BOOT"; precmd; cd "$TEST_OTHER"; '
            '_profile_git_ready "$_profile_git_fd"; [[ -z "$_profile_git_segment" ]]'
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fork_env_resolver_uses_no_external_grep(self) -> None:
        self.seed_cache()
        overlay = self.home / "overlay"
        (overlay / "agent").mkdir(parents=True)
        (overlay / "agent/cursor_sdk_client.py").write_text("_operator_run_timeout_seconds = 0\n")
        self.env["COSW_TIMEOUT_FREE_PYTHONPATH"] = str(overlay)
        self.env["FORK_ENV"] = str(ROOT / "bin/hermes/fork-env.sh")
        self.script("grep", 'printf "grep\\n" >> "$TEST_LOG"\nexit 1\n')
        result = self.shell(
            'source "$FORK_ENV"; [[ "$HERMES_AGENT_ROOT" == "$COSW_TIMEOUT_FREE_PYTHONPATH" ]]'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())

    def test_binary_upgrade_refreshes_cache(self) -> None:
        self.seed_cache("# previous cache\n")
        os.utime(self.bin / "omp", (time.time() + 2, time.time() + 2))
        result = self.refresh()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TEST_COMPLETIONS", self.cache.read_text())


if __name__ == "__main__":
    unittest.main()
