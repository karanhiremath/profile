"""Registry-backed ground-truth evidence. Semantic review stays with the caller."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .core import (
    ENV_NAME,
    Git,
    Rejected,
    checkout,
    command,
    display_path,
    now,
    object_keys,
    overlap,
    path_list,
    repo_id,
    safe_file,
    schema_version,
    visible_paths,
)


def registry(data: Any) -> list[dict[str, Any]]:
    object_keys(data, {"schema_version", "repositories"})
    schema_version(data)
    entries = data["repositories"]
    if not isinstance(entries, list) or not entries or len(entries) > 256:
        raise Rejected("invalid_registry")
    ids: set[str] = set()
    routes: set[str] = set()
    for entry in entries:
        object_keys(
            entry,
            {
                "repo",
                "visibility",
                "owner_project",
                "checkout_env",
                "canonical_paths",
                "guidance",
                "routes",
            },
        )
        repo_id(entry["repo"])
        if entry["repo"] in ids:
            raise Rejected("duplicate_repo")
        ids.add(entry["repo"])
        if entry["visibility"] not in {"public", "private"}:
            raise Rejected("invalid_visibility")
        if not isinstance(entry["owner_project"], str) or not re.fullmatch(
            r"[a-z][a-z0-9-]{0,63}", entry["owner_project"]
        ):
            raise Rejected("invalid_owner_project")
        if not isinstance(entry["checkout_env"], str) or not ENV_NAME.fullmatch(
            entry["checkout_env"]
        ):
            raise Rejected("invalid_checkout_env")
        for key in ("canonical_paths", "guidance"):
            path_list(entry[key], allow_empty=True)
            if any(display_path(p) is None for p in entry[key]):
                raise Rejected("unsafe_registry_path")
        aliases = entry["routes"]
        if not isinstance(aliases, list) or not aliases:
            raise Rejected("invalid_routes")
        for alias in aliases:
            if not isinstance(alias, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", alias):
                raise Rejected("invalid_route")
            if alias in routes:
                raise Rejected("duplicate_route")
            routes.add(alias)
    return entries


def proposal(data: Any) -> dict[str, Any]:
    object_keys(data, {"schema_version", "repo", "paths", "intent"})
    schema_version(data)
    repo_id(data["repo"])
    path_list(data["paths"])
    if not isinstance(data["intent"], str) or not 1 <= len(data["intent"]) <= 4000:
        raise Rejected("invalid_intent")
    if any(display_path(p) is None for p in data["paths"]):
        raise Rejected("unsafe_proposal_path")
    return data


def remote(repo: str) -> dict[str, Any]:
    """Explicit --refresh only. Read-only API metadata, never titles/body/comments."""
    try:
        info = json.loads(
            command(
                ["gh", "repo", "view", repo, "--json", "nameWithOwner,isPrivate,defaultBranchRef"]
            )
        )
        if info["nameWithOwner"] != repo or type(info["isPrivate"]) is not bool:
            raise Rejected("remote_identity_mismatch")
        prs = json.loads(
            command(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "open",
                    "--limit",
                    "100",
                    "--json",
                    "number,headRefName,headRefOid,baseRefName,files,updatedAt",
                ]
            )
        )
        if not isinstance(prs, list):
            raise Rejected("invalid_remote_evidence")
        safe_prs = []
        incomplete = len(prs) >= 100
        for pr in prs:
            if type(pr["number"]) is not int or pr["number"] <= 0:
                raise Rejected("invalid_remote_evidence")
            files = [item["path"] for item in pr["files"]]
            if len(files) >= 100:
                # gh nested connection pagination is not assumed complete.
                incomplete = True
            path_list(files, allow_empty=True)
            safe_prs.append(
                {
                    "number": pr["number"],
                    "files": files,
                    "head": pr["headRefOid"],
                    "branch": pr["headRefName"],
                }
            )
        return {
            "state": "partial" if incomplete else "fresh",
            "observed_at": now(),
            "visibility": "private" if info["isPrivate"] else "public",
            "default_branch": info["defaultBranchRef"]["name"],
            "prs": safe_prs,
        }
    except (Rejected, ValueError, KeyError, TypeError, UnicodeError):
        return {"state": "unavailable", "observed_at": now(), "prs": []}


def sibling_evidence(git: Git, paths: list[str]) -> dict[str, Any]:
    worktree_records = git.raw("worktree", "list", "--porcelain", "-z").decode().split("\0\0")
    evidence: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    missing: list[str] = []
    common = Path(git.text("rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    for number, record in enumerate(worktree_records):
        fields = record.split("\0")
        roots = [field[9:] for field in fields if field.startswith("worktree ")]
        if not roots or Path(roots[0]).resolve() == git.root:
            continue
        if number >= 64:
            missing.append("worktree_inventory_truncated")
            break
        try:
            sibling = Git(Path(roots[0]))
            sibling_common = Path(
                sibling.text("rev-parse", "--path-format=absolute", "--git-common-dir")
            ).resolve()
            if sibling_common != common:
                raise Rejected("sibling_identity_mismatch")
            changes = sibling.changes()
            hits = {
                item[key]
                for item in changes
                for key in ("path", "original_path")
                if key in item and any(overlap(item[key], p) for p in paths)
            }
            row = {
                "worktree_id": number,
                "head": sibling.head(),
                "branch": sibling.branch(),
                "dirty_count": len(changes),
                "overlap": visible_paths(sorted(hits)),
            }
            evidence.append(row)
            if hits:
                conflicts.append({"source": "sibling_worktree", **row})
        except (Rejected, OSError, UnicodeError):
            missing.append("sibling_unavailable")
    branches = git.text("for-each-ref", "--format=%(objectname) %(refname:short)", "refs/heads/")
    head = git.head()
    branch_rows: list[dict[str, Any]] = []
    for number, line in enumerate(branches.splitlines()):
        if number >= 128:
            missing.append("branch_inventory_truncated")
            break
        tip, name = line.split(" ", 1)
        if tip == head:
            continue
        try:
            touched = git.diff_paths(head, tip)
            hits = [f for f in touched if any(overlap(f, p) for p in paths)]
            if hits:
                row = {
                    "source": "local_branch",
                    "branch": name,
                    "head": tip,
                    "overlap": visible_paths(hits),
                }
                branch_rows.append(row)
                conflicts.append(row)
        except Rejected:
            missing.append("branch_comparison_unavailable")
    return {
        "worktrees": evidence,
        "branch_overlaps": branch_rows,
        "conflicts": conflicts,
        "missing": sorted(set(missing)),
    }


def inspect(
    data: Any, request: Any, route: str, override: str | None, refresh: bool, audience: str
) -> dict[str, Any]:
    entries = registry(data)
    request = proposal(request)
    entry = next((e for e in entries if route == e["repo"] or route in e["routes"]), None)
    if entry is None:
        raise Rejected("unregistered_repo_or_route")
    if request["repo"] != entry["repo"]:
        raise Rejected("proposal_repo_mismatch")
    if audience == "public" and entry["visibility"] != "public":
        raise Rejected("private_repo_public_audience")
    git = Git(checkout(entry["checkout_env"], override))
    git.verify(entry["repo"])
    initial_head = git.head()
    initial_branch = git.branch()
    initial_changes = git.changes()
    network = remote(entry["repo"]) if refresh else {"state": "not_refreshed", "prs": []}
    if network.get("visibility", entry["visibility"]) != entry["visibility"]:
        raise Rejected("registry_visibility_mismatch")
    # Public output deliberately excludes all local/sibling branch and dirty-file
    # metadata; a public repo can have private uncommitted material. Use private
    # reports for actual review and explicitly curate anything intended to ship.
    if audience == "public":
        return {
            "schema_version": 1,
            "operation": "repo-context.inspect",
            "state": "unknown",
            "repo": entry["repo"],
            "audience": audience,
            "observed_at": now(),
            "remote_evidence": network["state"],
            "local_evidence": "withheld",
            "next": "perform_private_review_and_curate_public_summary",
        }
    siblings = sibling_evidence(git, request["paths"])
    dirty_hits = {
        item[key]
        for item in initial_changes
        for key in ("path", "original_path")
        if key in item and any(overlap(item[key], p) for p in request["paths"])
    }
    conflicts = siblings["conflicts"]
    if dirty_hits:
        conflicts.append(
            {"source": "current_worktree", "overlap": visible_paths(sorted(dirty_hits))}
        )
    pr_rows = []
    for pr in network["prs"]:
        hits = [f for f in pr["files"] if any(overlap(f, p) for p in request["paths"])]
        row = {
            "number": pr["number"],
            "head": pr["head"],
            "url": f"https://github.com/{entry['repo']}/pull/{pr['number']}",
            "overlap": visible_paths(hits),
        }
        pr_rows.append(row)
        if hits:
            conflicts.append({"source": "open_pr", **row})
    missing = siblings["missing"]
    if not entry["canonical_paths"] or not entry["guidance"]:
        missing.append("placement_inventory_incomplete")
    if network["state"] != "fresh":
        missing.append("remote_evidence_incomplete")
    outside = [
        p
        for p in request["paths"]
        if not any(p == root or p.startswith(root + "/") for root in entry["canonical_paths"])
    ]
    if outside:
        missing.append("proposal_outside_canonical_paths")
    guidance = []
    for path in sorted(set(["AGENTS.md", "CLAUDE.md", *entry["guidance"]])):
        # Symlinks are not opened by the oracle, nor recommended for automatic read.
        reason = safe_file(git.root, path)
        if reason is None:
            guidance.append(path)
        elif path in entry["guidance"]:
            missing.append("registered_guidance_unavailable")
    if (
        git.head() != initial_head
        or git.branch() != initial_branch
        or git.changes() != initial_changes
    ):
        missing.append("source_changed_during_inspection")
    state = "overlap" if conflicts else "unknown" if missing else "needs-decision"
    return {
        "schema_version": 1,
        "operation": "repo-context.inspect",
        "state": state,
        "repo": entry["repo"],
        "audience": "private",
        "owner_project": entry["owner_project"],
        "route": route,
        "observed_at": now(),
        "head": initial_head,
        "branch": initial_branch,
        "dirty_count": len(initial_changes),
        "remote_evidence": network["state"],
        "open_prs": pr_rows,
        "worktrees": siblings["worktrees"],
        "conflicts": conflicts,
        "missing": sorted(set(missing)),
        "outside_canonical_paths": outside,
        "canonical_paths": entry["canonical_paths"],
        "guidance_to_read": guidance,
        "semantic_review_required": True,
        "mutation_authorized": False,
        "next": "read_guidance_then_resolve_placement_and_overlap_with_cited_evidence",
    }
