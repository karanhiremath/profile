from __future__ import annotations

import json

import pytest
from test_inspection import env, git, invoke, notes_args, oracle_args, snapshot, write_json

from agentic_inspect.core import Git, Rejected
from agentic_inspect.oracle import inspect

__all__ = ["env"]


def test_oracle_detects_same_commit_branch_switch(
    env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Git.branch
    calls = 0

    def racing(self: Git) -> str | None:
        nonlocal calls
        calls += 1
        if calls == 2:
            git(self.root, "switch", "-c", "concurrent-branch")
        return original(self)

    monkeypatch.setattr(Git, "branch", racing)
    output = inspect(env["registry"], env["proposal"], "notes-context", None, False, "private")
    assert output["branch"] == "main"
    assert "source_changed_during_inspection" in output["missing"]


def test_outside_canonical_path_is_explicitly_incomplete(env: dict) -> None:
    env["proposal"]["paths"] = ["unexpected/new.md"]
    write_json(env["proposal_file"], env["proposal"])
    code, output, _ = invoke([*oracle_args(env), "--refresh"])
    assert code == 0 and output["state"] == "unknown"
    assert output["outside_canonical_paths"] == ["unexpected/new.md"]
    assert "proposal_outside_canonical_paths" in output["missing"]


def test_unknown_placement_is_not_complete(env: dict) -> None:
    entry = env["registry"]["repositories"][0]
    entry["canonical_paths"] = []
    entry["guidance"] = []
    write_json(env["registry_file"], env["registry"])
    code, output, _ = invoke([*oracle_args(env), "--refresh"])
    assert code == 0 and output["state"] == "unknown"
    assert "placement_inventory_incomplete" in output["missing"]


def test_huge_event_fd_rejected_as_json(env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARTESIA_EVENT_SINKS", "fd:" + "9" * 100)
    code, output, stderr = invoke(notes_args(env))
    assert code == 2 and output["reason"] == "invalid_event_sink" and not stderr


def test_notes_submodule_content_is_never_scanned(env: dict) -> None:
    root = env["root"]
    source = env["tmp"] / "submodule-source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "Fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    git(source, "config", "commit.gpgsign", "false")
    (source / "one.md").write_text("original")
    git(source, "add", ".")
    git(source, "commit", "-m", "Initialize submodule fixture")
    git(root, "-c", "protocol.file.allow=always", "submodule", "add", str(source), "notes/child")
    git(root, "commit", "-m", "Add fixture gitlink")
    child = root / "notes" / "child"
    sentinel = env["tmp"] / "submodule-filter-ran"
    git(child, "config", "filter.child.clean", f"touch '{sentinel}'")
    (child / ".gitattributes").write_text("*.md filter=child\n")
    (child / "one.md").write_text("dirty child file")
    before = snapshot(root)
    code, output, _ = invoke(notes_args(env))
    assert code == 0 and not sentinel.exists()
    assert snapshot(root) == before
    assert not any("child/" in p["path"] for p in output["candidates"])


def test_notes_symlink_ancestor_never_recommends_external_file(env: dict) -> None:
    root = env["root"]
    external = env["tmp"] / "external"
    external.mkdir()
    (external / "one.md").write_text("outside")
    (root / "notes" / "external").symlink_to(external, target_is_directory=True)
    before = snapshot(external)
    code, output, _ = invoke(notes_args(env))
    assert code == 0 and snapshot(external) == before
    assert not any(p["path"].endswith("external/one.md") for p in output["candidates"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", "work"),
        ("schema_version", True),
        ("allowed_roots", ["notes/auth.json"]),
        ("target_branch", "-main"),
        ("target_branch", "main..other"),
        ("unexpected", True),
    ],
)
def test_policy_schema_variants(env: dict, field: str, value: object) -> None:
    env["config"][field] = value
    code, output, _ = invoke(
        ["agentic-sync-notes", "plan", "--config", "-"], json.dumps(env["config"])
    )
    assert code == 2 and output["state"] == "rejected"


def test_guidance_symlink_is_not_recommended(env: dict) -> None:
    root = env["root"]
    (root / "CLAUDE.md").unlink()
    (root / "CLAUDE.md").symlink_to(env["config_file"])
    code, output, _ = invoke(oracle_args(env))
    assert code == 0 and "CLAUDE.md" not in output["guidance_to_read"]
    assert "registered_guidance_unavailable" in output["missing"]


def test_git_prefix_excludes_readonly_violations(env: dict) -> None:
    repo = Git(env["root"])
    assert "--no-optional-locks" in repo.prefix
    assert "core.fsmonitor=false" in repo.prefix
    assert "core.hooksPath=/dev/null" in repo.prefix
    with pytest.raises(Rejected):
        repo.diff_paths("HEAD", "refs/heads/main")
