from __future__ import annotations

import json
import os
from pathlib import Path
import pty
import select
import shlex
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
        self.prepare_completions()
        profile = (ROOT / "zsh_profile.sh").read_text()
        for prefix, directory in (
            ("/opt/homebrew/share/zsh/site-functions", self.brew_completions),
            ("/usr/local/share/zsh/site-functions", self.local_completions),
        ):
            self.assertEqual(profile.count(prefix), 1)
            profile = profile.replace(prefix, shlex.quote(str(directory)))
        (self.repo / "zsh_profile.sh").write_text(profile)
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
        # Allow only locale settings through: operator FPATH, ZDOTDIR,
        # completion/cache variables and host integration overrides are not
        # fixture inputs. Every subprocess (including benchmark and PTY) uses
        # this same explicit FPATH and fresh cache/config/data roots.
        self.env = dict(
            {key: os.environ[key] for key in ("LANG", "LC_ALL", "LC_CTYPE", "TZ")
             if key in os.environ},
            HOME=str(self.home),
            ZDOTDIR=str(self.home),
            FPATH=os.pathsep.join(map(str, self.function_dirs)),
            PROFILE_DIR=str(self.repo),
            XDG_CONFIG_HOME=str(self.home / ".config"),
            XDG_DATA_HOME=str(self.home / "data"),
            XDG_CACHE_HOME=str(self.home / "cache"),
            TMPDIR=str(self.home),
            PATH=f"{self.bin}:/usr/bin:/bin",
            TERM="dumb",
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

    def prepare_completions(self) -> None:
        """Copy only installed stock autoload sources, never ambient fpath.

        Search bounded standard install prefixes, preferring the selected zsh's
        own prefix. Do not traverse site-functions or directory symlinks, and
        do not copy file symlinks or compiled autoload/dump caches. All chmods
        apply exclusively to newly created paths below the temporary HOME.
        """
        self.completion_root = self.home / "completions"
        self.completion_root.mkdir(mode=0o700)
        self.brew_completions = self.completion_root / "homebrew"
        self.local_completions = self.completion_root / "usr-local"
        for directory in (self.brew_completions, self.local_completions):
            directory.mkdir(mode=0o700)

        prefixes = dict.fromkeys((
            Path(ZSH).resolve().parent.parent / "share/zsh",
            Path("/usr/share/zsh"),
            Path("/usr/local/share/zsh"),
            Path("/opt/homebrew/share/zsh"),
        ))
        required = {"compaudit", "compinit", "colors", "promptinit", "add-zsh-hook"}
        sources = []
        for prefix in prefixes:
            candidates = [prefix / "functions", *sorted(prefix.glob("[0-9]*/functions"))]
            for candidate in candidates:
                if not candidate.is_dir():
                    continue
                root = candidate.resolve()
                if "site-functions" in root.parts:
                    continue
                files = []
                for directory, subdirs, names in os.walk(root, followlinks=False):
                    parent = Path(directory)
                    subdirs[:] = sorted(
                        name for name in subdirs
                        if name != "site-functions" and not name.startswith(".")
                        and ".zwc" not in name and not (parent / name).is_symlink()
                    )
                    for name in sorted(names):
                        source = parent / name
                        if (not name.startswith(".") and ".zwc" not in name
                                and not source.is_symlink() and source.is_file()):
                            files.append(source)
                if required.issubset({source.name for source in files}):
                    sources = files
                    stock_root = root
                    break
            if sources:
                break
        self.assertTrue(sources, "installed stock zsh autoload functions not found")

        stock = self.completion_root / "stock"
        stock.mkdir(mode=0o700)
        self.function_dirs = []
        for source in sources:
            target = stock / source.relative_to(stock_root)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o600)
            if target.parent not in self.function_dirs:
                self.function_dirs.append(target.parent)
        # mkdir(parents=True) uses the umask for intermediate directories.
        # Normalize only our copies, not any installed function directory.
        for directory, _, _ in os.walk(self.completion_root):
            Path(directory).chmod(0o700)

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

    def test_owned_completions_pass_real_audit_and_initialization(self) -> None:
        self.seed_cache()
        result = self.shell(
            'autoload -Uz compaudit; '
            'audit="$(compaudit)" || { print -ru2 -- "$audit"; exit 1; }; '
            '[[ -z "$audit" ]] || exit 2; '
            'source "$BOOT" </dev/null; '
            '(( $+functions[compdef] )) || exit 3; '
            'audit="$(compaudit)" || { print -ru2 -- "$audit"; exit 4; }; '
            '[[ -z "$audit" ]] || exit 5; '
            'autoload -Uz compinit; compinit </dev/null || exit 6; '
            'compdef _fixture_canary fixture-canary || exit 7; '
            '[[ "${_comps[fixture-canary]}" == _fixture_canary ]] || exit 8; '
            'print -rl -- $fpath'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [
            str(self.local_completions), str(self.brew_completions),
            *map(str, self.function_dirs),
        ])

    def test_real_compaudit_rejects_group_writable_fixture_directory(self) -> None:
        insecure = self.completion_root / "insecure"
        insecure.mkdir(mode=0o700)
        insecure.chmod(0o770)
        self.env["TEST_INSECURE_COMPLETIONS"] = str(insecure)
        result = self.shell(
            'fpath=("$TEST_INSECURE_COMPLETIONS" $fpath); '
            'autoload -Uz compaudit; compaudit'
        )
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(insecure), result.stdout.splitlines())

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
            'source "$BOOT"; precmd; _profile_git_ready "$_profile_git_fd" hup; '
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
        for shell in (ZSH, "/bin/bash"):
            result = subprocess.run(
                [shell, "-c", 'source "$FORK_ENV"; [[ "$HERMES_AGENT_ROOT" == "$COSW_TIMEOUT_FREE_PYTHONPATH" ]]'],
                env=self.env, capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())

    def test_benchmark_preserves_completion_scope(self) -> None:
        self.seed_cache('_omp() { :; }; compdef _omp omp\n')
        (self.home / ".zshrc.d/20-scope.zsh").write_text(
            '_test_completion_scope() { [[ "${_comps[omp]}" == _omp ]]; }\n'
            'precmd_functions+=(_test_completion_scope)\n'
        )
        result = subprocess.run(
            [ZSH, "-dfi", str(ROOT / "bin/zsh/benchmark-startup"), str(self.repo / "zshrc.bootstrap")],
            env=self.env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["config_status"], 0)
        self.assertEqual(payload["prompt_status"], 0)
        self.assertGreaterEqual(payload["ready_ms"], payload["config_ms"])

    def test_async_prompt_updates_in_a_real_pty_without_enter(self) -> None:
        self.seed_cache()
        self.script("git", "sleep .1\nprintf '%s\\n' '## pty-topic'\n")
        (self.home / ".zshrc").write_text('source "$BOOT"\nTMOUT=5\n')
        env = dict(self.env, TERM="xterm-256color")
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.home)
            os.execve(ZSH, [ZSH, "-di"], env)
        frame = bytearray()
        try:
            deadline = time.monotonic() + 8
            while b"pty-topic" not in frame and time.monotonic() < deadline:
                readable, _, _ = select.select([fd], [], [], 0.1)
                if readable:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    frame.extend(chunk)
            self.assertIn(b"pty-topic", frame, frame.decode(errors="replace"))
        finally:
            os.write(fd, b"exit\r")
            # Drain the PTY while waiting: ZLE may be blocked on terminal output.
            deadline = time.monotonic() + 10
            exited = False
            while time.monotonic() < deadline:
                if os.waitpid(pid, os.WNOHANG)[0]:
                    exited = True
                    break
                readable, _, _ = select.select([fd], [], [], 0.1)
                if readable:
                    try:
                        frame.extend(os.read(fd, 65536))
                    except OSError:
                        break
            os.close(fd)
            self.assertTrue(exited, frame.decode(errors="replace"))

    def test_binary_upgrade_refreshes_cache(self) -> None:
        self.seed_cache("# previous cache\n")
        os.utime(self.bin / "omp", (time.time() + 2, time.time() + 2))
        result = self.refresh()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TEST_COMPLETIONS", self.cache.read_text())


if __name__ == "__main__":
    unittest.main()
