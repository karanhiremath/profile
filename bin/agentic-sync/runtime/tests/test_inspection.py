from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_inspect.core import remote_identity
from agentic_inspect.notes import plan

REPO = "example/notes"
PACKAGE = Path(__file__).resolve().parents[1]
WRAPPER = PACKAGE.parent / "agentic-sync"


def git(root: Path, *args: str) -> str:
    return (
        subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)
        .decode()
        .strip()
    )


def write_json(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data))
    return path


def snapshot(root: Path) -> dict[str, bytes | str]:
    return {
        str(p.relative_to(root)): os.readlink(p) if p.is_symlink() else p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() or p.is_symlink()
    }


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".state"))
    for key in list(os.environ):
        if key.startswith(("GIT_", "CARTESIA_EVENT_")) or key in {
            "REPO_CONTEXT_REGISTRY",
            "AGENTIC_SYNC_NOTES_CONFIG",
        }:
            monkeypatch.delenv(key)
    root = tmp_path / "repo with spaces"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "remote", "add", "origin", f"https://github.com/{REPO}.git")
    (root / "notes").mkdir()
    (root / "notes" / "one.md").write_text("original\n")
    (root / "CLAUDE.md").write_text("Personal fixture guidance.\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "Initialize fixture")
    git(root, "update-ref", "refs/remotes/origin/main", git(root, "rev-parse", "HEAD"))
    monkeypatch.setenv("TEST_NOTES_ROOT", str(root))
    config = {
        "schema_version": 1,
        "scope": "personal",
        "repo": REPO,
        "checkout_env": "TEST_NOTES_ROOT",
        "target_branch": "main",
        "allowed_roots": ["notes"],
    }
    registry = {
        "schema_version": 1,
        "repositories": [
            {
                "repo": REPO,
                "visibility": "private",
                "owner_project": "graph-engineering",
                "checkout_env": "TEST_NOTES_ROOT",
                "canonical_paths": ["notes"],
                "guidance": ["CLAUDE.md"],
                "routes": ["notes-context"],
            }
        ],
    }
    proposal = {
        "schema_version": 1,
        "repo": REPO,
        "paths": ["notes/one.md"],
        "intent": "Check placement; do not mutate.",
    }
    fixture = {
        "info": {"nameWithOwner": REPO, "isPrivate": True, "defaultBranchRef": {"name": "main"}},
        "prs": [],
    }
    fixture_path = write_json(tmp_path / "gh-fixture.json", fixture)
    tools = tmp_path / "tools"
    tools.mkdir()
    fake_gh = tools / "gh"
    fake_gh.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "data = json.loads(Path(os.environ['GH_FIXTURE_FILE']).read_text())\n"
        "if data.get('fail'):\n"
        "    sys.stderr.write('fixture-private-diagnostic-do-not-emit')\n"
        "    sys.exit(1)\n"
        "if sys.argv[1:3] == ['repo', 'view']:\n"
        "    print(json.dumps(data['info']))\n"
        "elif sys.argv[1:3] == ['pr', 'list']:\n"
        "    print(json.dumps(data['prs']))\n"
        "else:\n"
        "    sys.exit(9)\n"
    )
    fake_gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("GH_FIXTURE_FILE", str(fixture_path))
    return {
        "root": root,
        "home": home,
        "tmp": tmp_path,
        "config": config,
        "registry": registry,
        "proposal": proposal,
        "fixture": fixture,
        "fixture_path": fixture_path,
        "config_file": write_json(tmp_path / "config.json", config),
        "registry_file": write_json(tmp_path / "registry.json", registry),
        "proposal_file": write_json(tmp_path / "proposal.json", proposal),
    }


def invoke(
    args: list[str], stdin: str | None = None, pass_fds: tuple[int, ...] = ()
) -> tuple[int, dict, str]:
    result = subprocess.run(
        args, input=stdin, text=True, capture_output=True, pass_fds=pass_fds, timeout=20
    )
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    assert len(result.stdout.splitlines()) == 1
    return result.returncode, payload, result.stderr


def notes_args(env: dict, command: str = "plan") -> list[str]:
    return ["bash", str(WRAPPER), "notes", command, "--config", str(env["config_file"])]


def oracle_args(env: dict) -> list[str]:
    return [
        "repo-context",
        "inspect",
        "--registry",
        str(env["registry_file"]),
        "--route",
        "notes-context",
        "--proposal-file",
        str(env["proposal_file"]),
    ]


def test_notes_preserves_index_head_files_and_home(env: dict) -> None:
    root = env["root"]
    (root / "notes" / "one.md").write_text("changed\n")
    (root / "notes" / "日本語 space.md").write_text("new\n")
    (root / "unrelated.txt").write_text("staged unrelated\n")
    git(root, "add", "unrelated.txt")
    before, home = snapshot(root), snapshot(env["home"])
    code, output, stderr = invoke(notes_args(env))
    assert code == 0 and not stderr
    assert output["state"] == "blocked" and not output["publication_enabled"]
    assert output["omitted_count"] == 1
    assert "staged_changes_preserved" in output["blockers"]
    assert {p["path"] for p in output["candidates"]} == {"notes/one.md", "notes/日本語 space.md"}
    assert snapshot(root) == before and snapshot(env["home"]) == home


@pytest.mark.parametrize(
    "args",
    [["run"], ["run", "--publish"], ["plan", "--publish"], ["run", "--dry-run", "--publish"]],
)
def test_mutation_is_unconditionally_disabled(env: dict, args: list[str]) -> None:
    before = snapshot(env["root"])
    code, output, _ = invoke(["agentic-sync-notes", *args, "--config", str(env["config_file"])])
    assert code == 2 and output["reason"] == "publication_disabled_use_dry_run"
    assert snapshot(env["root"]) == before


def test_dry_run_no_state_and_no_host_env_sourcing(env: dict) -> None:
    config_dir = env["home"] / ".config" / "agentic-sync"
    config_dir.mkdir(parents=True)
    sentinel = env["tmp"] / "must-not-exist"
    (config_dir / "host.env").write_text(f"touch '{sentinel}'\n")
    before = snapshot(env["home"])
    code, output, _ = invoke([*notes_args(env, "run"), "--dry-run"])
    assert code == 0 and output["dry_run"]
    assert not sentinel.exists() and snapshot(env["home"]) == before


@pytest.mark.parametrize(
    "payload", ["{", '{"schema_version":1,"schema_version":1}', '{"unexpected":true}', "[]"]
)
def test_stdin_schema_rejection(env: dict, payload: str) -> None:
    code, output, _ = invoke(["agentic-sync-notes", "plan", "--config", "-"], payload)
    assert code == 2 and output["state"] == "rejected"


def test_stdin_config_and_structured_pipeline(env: dict) -> None:
    code, output, _ = invoke(
        ["agentic-sync-notes", "status", "--config", "-"], json.dumps(env["config"])
    )
    assert code == 0 and output["delivery"]["last_success"] is None
    # A previous status payload is NOT silently accepted as a policy/config.
    code, rejected, _ = invoke(["agentic-sync-notes", "plan", "--config", "-"], json.dumps(output))
    assert code == 2 and rejected["reason"] == "invalid_schema"


@pytest.mark.parametrize(
    "relative",
    [
        "../escape",
        "/absolute",
        "notes/../escape",
        ".git/config",
        "notes//one.md",
        "notes/line\nbreak",
        "notes\\escape",
    ],
)
def test_path_schema(env: dict, relative: str) -> None:
    env["config"]["allowed_roots"] = [relative]
    code, output, _ = invoke(
        ["agentic-sync-notes", "plan", "--config", "-"], json.dumps(env["config"])
    )
    assert code == 2 and output["state"] == "rejected"


def test_unsafe_symlink_nested_binary_deleted_and_rename(env: dict) -> None:
    root = env["root"]
    (root / "notes" / "auth.json").write_text("fake-sensitive-content")
    (root / "notes" / "image.png").write_bytes(b"\x00PNG")
    (root / "notes" / "link.md").symlink_to(env["config_file"])
    git(root, "mv", "notes/one.md", "notes/moved.md")
    nested = root / "notes" / "nested"
    nested.mkdir()
    git(nested, "init")
    (nested / "nested.md").write_text("nested")
    code, output, stderr = invoke(notes_args(env))
    assert code == 0
    text = json.dumps(output) + stderr
    assert "fake-sensitive-content" not in text and "auth.json" not in text
    candidates = {p["path"]: p for p in output["candidates"]}
    assert candidates["notes/link.md"]["reasons"] == ["symlink"]
    assert "rename_requires_review" in candidates["notes/moved.md"]["reasons"]
    assert "file_type_not_enabled" in candidates["notes/image.png"]["reasons"]


def test_feature_branch_never_plans_publication(env: dict) -> None:
    git(env["root"], "switch", "-c", "feature")
    code, output, _ = invoke(notes_args(env))
    assert code == 0 and "source_not_on_target_branch" in output["blockers"]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/example/notes.git",
        "https://fake-userinfo@github.com/example/notes.git",
        "file:///tmp/fake",
        "git@github.com:other/notes.git",
    ],
)
def test_remote_identity_failure_redacted(env: dict, url: str) -> None:
    git(env["root"], "remote", "set-url", "origin", url)
    code, output, stderr = invoke(notes_args(env))
    assert code == 2 and output["reason"] == "repository_identity_mismatch"
    assert url not in json.dumps(output) + stderr


def test_origin_pushurl_also_verified(env: dict) -> None:
    git(env["root"], "config", "remote.origin.pushurl", "git@github.com:other/notes.git")
    code, output, _ = invoke(notes_args(env))
    assert code == 2 and output["reason"] == "push_identity_mismatch"


def test_ambient_git_redirect_and_external_filters_cannot_execute(
    env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = env["root"]
    sentinel = env["tmp"] / "external-hook-ran"
    git(root, "config", "core.fsmonitor", f"touch '{sentinel}'")
    git(root, "config", "filter.bad.clean", f"touch '{sentinel}'")
    git(root, "config", "filter.bad.process", f"touch '{sentinel}'")
    git(root, "config", "filter.bad.required", "true")
    (root / ".gitattributes").write_text("*.md filter=bad\n")
    (root / "notes" / "one.md").write_text("changed to force content check")
    monkeypatch.setenv("GIT_INDEX_FILE", str(env["tmp"] / "redirected-index"))
    monkeypatch.setenv("GIT_WORK_TREE", str(env["home"]))
    before = snapshot(root)
    code, output, _ = invoke(notes_args(env))
    assert code == 0 and output["repo"] == REPO
    assert not sentinel.exists() and not (env["tmp"] / "redirected-index").exists()
    assert snapshot(root) == before


def test_oracle_offline_never_all_clear(env: dict) -> None:
    before = snapshot(env["root"])
    code, output, _ = invoke(oracle_args(env))
    assert code == 0 and output["state"] == "unknown"
    assert output["remote_evidence"] == "not_refreshed"
    assert output["guidance_to_read"] == ["CLAUDE.md"]
    assert output["semantic_review_required"] and not output["mutation_authorized"]
    assert snapshot(env["root"]) == before


def test_oracle_live_fake_pr_overlap_and_redaction(env: dict) -> None:
    env["fixture"]["prs"] = [
        {
            "number": 7,
            "headRefName": "feature",
            "headRefOid": "a" * 40,
            "files": [{"path": "notes/one.md"}],
        }
    ]
    write_json(env["fixture_path"], env["fixture"])
    code, output, _ = invoke([*oracle_args(env), "--refresh"])
    assert code == 0 and output["state"] == "overlap"
    assert output["conflicts"][0]["number"] == 7
    assert output["remote_evidence"] == "fresh"
    assert "Check placement" not in json.dumps(output)


def test_oracle_fresh_still_requires_semantic_review(env: dict) -> None:
    code, output, _ = invoke([*oracle_args(env), "--refresh"])
    assert code == 0 and output["state"] == "needs-decision"


def test_oracle_failed_network_does_not_leak_diagnostics(env: dict) -> None:
    env["fixture"]["fail"] = True
    write_json(env["fixture_path"], env["fixture"])
    code, output, stderr = invoke([*oracle_args(env), "--refresh"])
    assert code == 0 and output["state"] == "unknown"
    assert "fixture-private-diagnostic" not in json.dumps(output) + stderr


def test_oracle_detects_sibling_dirty_and_branch_overlap(env: dict) -> None:
    root = env["root"]
    sibling = env["tmp"] / "sibling"
    git(root, "worktree", "add", "-b", "sibling", str(sibling))
    (sibling / "notes" / "one.md").write_text("committed sibling change")
    git(sibling, "add", "notes/one.md")
    git(sibling, "commit", "-m", "Sibling change")
    (sibling / "notes" / "one.md").write_text("uncommitted sibling change")
    before = snapshot(root), snapshot(sibling)
    code, output, _ = invoke([*oracle_args(env), "--refresh"])
    assert code == 0 and output["state"] == "overlap"
    sources = {c["source"] for c in output["conflicts"]}
    assert {"sibling_worktree", "local_branch"} <= sources
    assert str(sibling) not in json.dumps(output)
    assert before == (snapshot(root), snapshot(sibling))


@pytest.mark.parametrize("route", ["unknown-context", "other/repo"])
def test_unregistered_route(env: dict, route: str) -> None:
    args = oracle_args(env)
    args[args.index("notes-context")] = route
    code, output, _ = invoke(args)
    assert code == 2 and output["reason"] == "unregistered_repo_or_route"


def test_registry_route_enumeration_and_alias_parity(env: dict) -> None:
    code, output, _ = invoke(
        ["repo-context", "routes", "--registry", "-"], json.dumps(env["registry"])
    )
    assert code == 0 and output["routes"][0]["routes"] == ["notes-context"]
    direct = oracle_args(env)
    direct[direct.index("--route")] = "--repo"
    direct[direct.index("notes-context")] = REPO
    _, via_repo, _ = invoke(direct)
    _, via_route, _ = invoke(oracle_args(env))
    assert via_repo["repo"] == via_route["repo"] and via_repo["state"] == via_route["state"]


def test_private_public_boundary_and_public_local_withholding(env: dict) -> None:
    code, output, _ = invoke([*oracle_args(env), "--audience", "public"])
    assert code == 2 and output["reason"] == "private_repo_public_audience"
    env["registry"]["repositories"][0]["visibility"] = "public"
    write_json(env["registry_file"], env["registry"])
    (env["root"] / "notes" / "private-description.md").write_text("private local draft")
    code, output, _ = invoke([*oracle_args(env), "--audience", "public"])
    assert code == 0 and output["local_evidence"] == "withheld"
    assert "private-description" not in json.dumps(output)


def test_visibility_mismatch(env: dict) -> None:
    env["fixture"]["info"]["isPrivate"] = False
    write_json(env["fixture_path"], env["fixture"])
    code, output, _ = invoke([*oracle_args(env), "--refresh"])
    assert code == 2 and output["reason"] == "registry_visibility_mismatch"


def test_partial_pr_inventory_never_complete(env: dict) -> None:
    env["fixture"]["prs"] = [
        {
            "number": 7,
            "headRefName": "feature",
            "headRefOid": "a" * 40,
            "files": [{"path": f"other/{i}.md"} for i in range(100)],
        }
    ]
    write_json(env["fixture_path"], env["fixture"])
    code, output, _ = invoke([*oracle_args(env), "--refresh"])
    assert code == 0 and output["state"] == "unknown" and output["remote_evidence"] == "partial"


def test_multi_sink_events_and_stdout_redaction(env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    pipes = [os.pipe(), os.pipe()]
    try:
        monkeypatch.setenv("CARTESIA_EVENT_SINKS", ",".join(f"fd:{w}" for _, w in pipes))
        code, output, _ = invoke(notes_args(env), pass_fds=tuple(w for _, w in pipes))
        assert code == 0 and output["repo"] == REPO
        for r, _ in pipes:
            event = json.loads(os.read(r, 4096))
            assert set(event) == {"schema_version", "event", "operation", "state"}
            assert REPO not in json.dumps(event)
    finally:
        for r, w in pipes:
            os.close(r)
            os.close(w)


@pytest.mark.parametrize(
    "sink", ["fd:1", "fd:2", "file:/tmp/must-not-create", "https://example.invalid"]
)
def test_invalid_event_sink_rejected_before_inspection(
    env: dict, monkeypatch: pytest.MonkeyPatch, sink: str
) -> None:
    monkeypatch.setenv("CARTESIA_EVENT_SINKS", sink)
    code, output, _ = invoke(notes_args(env))
    assert code == 2 and output["state"] == "rejected"


def test_regular_file_event_sink_not_written(env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    path = env["tmp"] / "sink"
    with path.open("wb") as stream:
        monkeypatch.setenv("CARTESIA_EVENT_SINKS", f"fd:{stream.fileno()}")
        code, output, _ = invoke(notes_args(env), pass_fds=(stream.fileno(),))
    assert code == 2 and output["reason"] == "event_sink_must_be_pipe_or_socket"
    assert path.read_bytes() == b""


def test_no_raw_argument_in_error_and_help_json(env: dict) -> None:
    code, output, stderr = invoke(["repo-context", "fake-private-value"])
    assert code == 2 and "fake-private-value" not in json.dumps(output) + stderr
    for binary in ("repo-context", "agentic-sync-notes"):
        code, output, _ = invoke([binary, "--help"])
        assert code == 0 and output["state"] == "help"


def test_source_race_reported(env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentic_inspect.core import Git

    original = Git.changes
    calls = 0

    def racing(self: Git) -> list[dict[str, str]]:
        nonlocal calls
        calls += 1
        if calls == 2:
            (self.root / "notes" / "race.md").write_text("concurrent writer")
        return original(self)

    monkeypatch.setattr(Git, "changes", racing)
    result = plan(env["config"], None, "test")
    assert "source_changed_during_inspection" in result["blockers"]


def test_remote_identity_supported_forms() -> None:
    assert remote_identity("https://github.com/example/notes.git") == REPO
    assert remote_identity("git@github.com:example/notes.git") == REPO
    assert remote_identity("https://github.com/example/notes") == REPO
    assert remote_identity("https://github.com/example/../notes") is None
