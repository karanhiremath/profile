"""Phase-one notes sync planning: metadata only, no write path exists."""

from __future__ import annotations

import re
from typing import Any

from .core import (
    Git,
    Rejected,
    checkout,
    display_path,
    now,
    object_keys,
    path_list,
    repo_id,
    safe_file,
    schema_version,
)


def validate_config(data: Any) -> dict[str, Any]:
    object_keys(
        data, {"schema_version", "scope", "repo", "checkout_env", "target_branch", "allowed_roots"}
    )
    schema_version(data)
    repo_id(data["repo"])
    if data["scope"] != "personal":
        raise Rejected("personal_scope_required")
    path_list(data["allowed_roots"], allow_empty=True)
    if any(display_path(p) is None for p in data["allowed_roots"]):
        raise Rejected("unsafe_capture_root")
    branch = data["target_branch"]
    if branch is not None and (
        not isinstance(branch, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", branch)
        or ".." in branch
        or "//" in branch
        or branch.endswith(("/", ".", ".lock"))
    ):
        raise Rejected("invalid_target_branch")
    return data


def plan(data: Any, override: str | None, operation: str) -> dict[str, Any]:
    config = validate_config(data)
    git = Git(checkout(config["checkout_env"], override))
    git.verify(config["repo"])
    initial_head = git.head()
    branch = git.branch()
    changes = git.changes()
    target = config["target_branch"]
    blockers = ["publication_not_implemented", "content_and_history_review_not_run"]
    if not target:
        blockers.append("target_branch_not_configured")
    elif branch != target:
        blockers.append("source_not_on_target_branch")
    if not config["allowed_roots"]:
        blockers.append("capture_roots_not_configured")
    if any(change["status"][0] not in {" ", "?"} for change in changes):
        blockers.append("staged_changes_preserved")
    if any("U" in change["status"] or change["status"] in {"AA", "DD"} for change in changes):
        blockers.append("unmerged_index")
    local_target = None
    if target:
        local_target = git.optional("rev-parse", "--verify", f"refs/remotes/origin/{target}")
        if local_target != initial_head:
            blockers.append("source_baseline_unverified")
    candidates: list[dict[str, Any]] = []
    omitted = 0
    for change in changes:
        path = display_path(change["path"])
        if path is None or not any(
            path == root or path.startswith(root + "/") for root in config["allowed_roots"]
        ):
            omitted += 1
            continue
        reasons: list[str] = []
        if "original_path" in change:
            reasons.append("rename_requires_review")
        if "D" in change["status"]:
            reasons.append("deletion_not_enabled")
        reason = safe_file(git.root, path)
        if reason:
            reasons.append(reason)
        if not path.lower().endswith((".md", ".json", ".yaml", ".yml", ".csv", ".txt")):
            reasons.append("file_type_not_enabled")
        candidates.append(
            {
                "path": path,
                "git_status": change["status"],
                "state": "blocked" if reasons else "needs-review",
                "reasons": reasons or ["content_not_read"],
            }
        )
    if omitted:
        blockers.append("out_of_scope_or_unsafe_changes_omitted")
    if git.head() != initial_head or git.branch() != branch or git.changes() != changes:
        blockers.append("source_changed_during_inspection")
    return {
        "schema_version": 1,
        "operation": operation,
        "state": "blocked",
        "dry_run": True,
        "repo": config["repo"],
        "observed_at": now(),
        "head": initial_head,
        "source_branch": branch,
        "target_branch": target,
        "remote_evidence": "not_refreshed",
        "local_target_head": local_target,
        "content_read": False,
        "publication_enabled": False,
        "candidates": candidates,
        "omitted_count": omitted,
        "change_count": len(changes),
        "blockers": blockers,
        "delivery": {
            "last_attempt": None,
            "last_success": None,
            "pending_count": None,
            "state": "not_implemented",
        },
        "next": "review_candidate_content_and_select_publication_policy",
    }
