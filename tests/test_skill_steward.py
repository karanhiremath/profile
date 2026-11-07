"""Tests for bin/skill-steward/skill-steward against a throwaway HOME + git repo."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "bin" / "skill-steward" / "skill-steward"


def sh(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def write_skill(d: Path, name: str, description: str = "does a thing") -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n\nbody\n")


@pytest.fixture()
def env(tmp_path: Path):
    repo = tmp_path / "src" / "tools"
    repo.mkdir(parents=True)
    sh("git", "init", "-q", "-b", "main", cwd=repo)
    sh("git", "config", "user.email", "t@example.com", cwd=repo)
    sh("git", "config", "user.name", "t", cwd=repo)
    write_skill(repo / "skills" / "alpha", "alpha")
    write_skill(repo / "skills" / "beta", "beta")
    sh("git", "add", ".", cwd=repo)
    sh("git", "commit", "-qm", "init", cwd=repo)

    claude = tmp_path / "home" / ".claude" / "skills"
    codex = tmp_path / "home" / ".codex" / "skills"
    claude.mkdir(parents=True)
    codex.mkdir(parents=True)
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(f"""
[harnesses]
claude = "{claude}"
codex = "{codex}"

[sources.tools]
repo = "{repo}"
ref = "main"

[external]
claude = ["synced"]

[[skill]]
source = "tools"
path = "skills/alpha"
harnesses = ["claude", "codex"]

[[skill]]
source = "tools"
path = "skills/beta"
harnesses = ["codex"]
""")
    state = tmp_path / "state"
    e = dict(os.environ, SKILL_STEWARD_STATE=str(state), SKILL_STEWARD_CONFIG=str(tmp_path / "cfg"))
    e.pop("SKILL_STEWARD_MANIFESTS", None)
    return {"repo": repo, "claude": claude, "codex": codex, "manifest": manifest,
            "state": state, "env": e}


def run(env, *args: str) -> tuple[int, str, str]:
    p = subprocess.run([sys.executable, str(TOOL), *args, "--manifest", str(env["manifest"])],
                       capture_output=True, text=True, env=env["env"])
    return p.returncode, p.stdout, p.stderr


def kinds(report: dict) -> set[tuple[str, str, str]]:
    return {(f["kind"], f["harness"], f["name"]) for f in report["findings"]}


def test_audit_stdout_is_json_and_reports_missing(env):
    rc, out, _ = run(env, "audit")
    assert rc == 1
    r = json.loads(out)
    assert ("source-missing", "-", "tools") in kinds(r)
    assert ("missing", "codex", "beta") in kinds(r)


def test_sync_plan_changes_nothing(env):
    rc, out, _ = run(env, "sync", "--no-fetch")
    assert rc == 0
    assert json.loads(out)["applied"] is False
    assert os.listdir(env["codex"]) == []
    assert not (env["state"] / "sources").exists()


def test_sync_apply_links_from_pinned_worktree(env):
    rc, out, _ = run(env, "sync", "--apply", "--no-fetch")
    r = json.loads(out)
    assert rc == 0, r
    assert r["remaining_findings"] == []
    link = env["codex"] / "beta"
    assert link.is_symlink()
    assert Path(os.readlink(link)).is_relative_to(env["state"] / "sources" / "tools")


def test_pinned_link_survives_primary_checkout_branch_switch(env):
    run(env, "sync", "--apply", "--no-fetch")
    sh("git", "checkout", "-q", "--orphan", "other", cwd=env["repo"])
    sh("git", "rm", "-rqf", ".", cwd=env["repo"])
    assert (env["codex"] / "alpha" / "SKILL.md").exists()
    rc, out, _ = run(env, "audit")
    assert rc == 0, out


def test_broken_undeclared_link_is_removed_and_copy_is_quarantined(env):
    run(env, "sync", "--apply", "--no-fetch")
    (env["codex"] / "gone").symlink_to(env["repo"] / "does-not-exist")
    (env["codex"] / "alpha").unlink()
    write_skill(env["codex"] / "alpha", "alpha", "stale hand copy")
    rc, out, _ = run(env, "audit")
    assert {("broken-link", "codex", "gone"), ("copy", "codex", "alpha")} <= kinds(json.loads(out))

    rc, out, _ = run(env, "sync", "--apply", "--no-fetch")
    r = json.loads(out)
    assert rc == 0, r
    assert not (env["codex"] / "gone").is_symlink()
    assert (env["codex"] / "alpha").is_symlink()
    q = [a["quarantined_to"] for a in r["actions"] if a.get("quarantine_existing")]
    assert q and "stale hand copy" in (Path(q[0]) / "SKILL.md").read_text()


def test_unmanaged_kept_unless_prune_and_external_never_touched(env):
    run(env, "sync", "--apply", "--no-fetch")
    write_skill(env["claude"] / "stray", "stray")
    (env["claude"] / "synced").mkdir()
    run(env, "sync", "--apply", "--no-fetch")
    assert (env["claude"] / "stray").is_dir()

    rc, out, _ = run(env, "sync", "--apply", "--prune", "--no-fetch")
    assert rc == 0, out
    assert not (env["claude"] / "stray").exists()
    assert (env["claude"] / "synced").is_dir()
    assert list(env["state"].glob("quarantine/*/claude/stray/SKILL.md"))


def test_source_advances_to_new_ref_commit(env):
    run(env, "sync", "--apply", "--no-fetch")
    write_skill(env["repo"] / "skills" / "alpha", "alpha", "v2")
    sh("git", "commit", "-qam", "v2", cwd=env["repo"])
    rc, out, _ = run(env, "audit")
    assert ("source-stale", "-", "tools") in kinds(json.loads(out))
    run(env, "sync", "--apply", "--no-fetch")
    assert "v2" in (env["codex"] / "alpha" / "SKILL.md").read_text()


def test_invalid_skill_and_oversized_description_flagged(env):
    run(env, "sync", "--apply", "--no-fetch")
    (env["claude"] / "nofm").mkdir()
    (env["claude"] / "nofm" / "SKILL.md").write_text("no frontmatter\n")
    write_skill(env["claude"] / "big", "big", "x" * 1100)
    r = json.loads(run(env, "audit")[1])
    probs = {f["name"]: f["problems"] for f in r["findings"] if f["kind"] == "invalid-skill"}
    assert probs["nofm"] == ["missing-or-invalid-SKILL.md"]
    assert probs["big"] == ["description-over-1024-chars"]


def test_hook_silent_when_clean_one_line_otherwise(env):
    rc, out, _ = run(env, "hook")
    assert rc == 0 and out.count("\n") == 1 and out.startswith("skill-steward:")
    run(env, "sync", "--apply", "--no-fetch")
    rc, out, _ = run(env, "hook")
    assert rc == 0 and out == ""


def test_hook_never_fails_without_manifest(env, tmp_path):
    p = subprocess.run([sys.executable, str(TOOL), "hook"], capture_output=True, text=True,
                       env=env["env"])
    assert p.returncode == 0 and p.stdout == ""
