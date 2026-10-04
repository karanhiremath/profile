#!/usr/bin/env python3
"""Restore default AppleHV virtiofs mounts on the Podman machine.

Podman 5 default shares are /Users, /private, and /var/folders. A machine
with Mounts=[] cannot bind-mount host paths into containers.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_SHARES = ("/Users", "/private", "/var/folders")
NFS_CONTEXT = 'context="system_u:object_r:nfs_t:s0"'


def virtiofs_tag(target: str) -> str:
    return hashlib.sha256(target.encode()).hexdigest()[:36]


def systemd_unit_name(target: str) -> str:
    return target.strip("/").replace("/", "-") + ".mount"


def mount_entry(path: str) -> dict:
    tag = virtiofs_tag(path)
    return {
        "OriginalInput": f"{path}:{path}",
        "ReadOnly": False,
        "Source": path,
        "Tag": tag,
        "Target": path,
        "Type": "virtiofs",
        "VSockNumber": None,
    }


def mount_unit(path: str) -> dict:
    tag = virtiofs_tag(path)
    contents = (
        "[Mount]\n"
        f"What={tag}\n"
        f"Where={path}\n"
        "Type=virtiofs\n"
        f"Options={NFS_CONTEXT}\n"
        "\n"
        "[Install]\n"
        "WantedBy=local-fs.target\n"
    )
    return {"contents": contents, "enabled": True, "name": systemd_unit_name(path)}


def repair(config_path: Path, ignition_path: Path) -> list[str]:
    cfg = json.loads(config_path.read_text())
    mounts = [mount_entry(path) for path in DEFAULT_SHARES]
    cfg["Mounts"] = mounts
    config_path.write_text(json.dumps(cfg, indent=2) + "\n")

    ign = json.loads(ignition_path.read_text())
    units = ign.setdefault("systemd", {}).setdefault("units", [])
    keep = []
    drop_names = {systemd_unit_name(path) for path in DEFAULT_SHARES}
    drop_names.add("Volumes-harmony.mount")
    for unit in units:
        if unit.get("name") in drop_names:
            continue
        keep.append(unit)
    keep.extend(mount_unit(path) for path in DEFAULT_SHARES)
    ign["systemd"]["units"] = keep
    ignition_path.write_text(json.dumps(ign, separators=(",", ":")) + "\n")
    return [f"{path} tag={virtiofs_tag(path)}" for path in DEFAULT_SHARES]


def live_mount_script() -> str:
    lines = [
        "set -eu",
        "ok=0",
    ]
    for path in DEFAULT_SHARES:
        tag = virtiofs_tag(path)
        lines.append(
            f"sudo mkdir -p {path}\n"
            f"if findmnt {path} >/dev/null 2>&1; then echo mounted {path}; ok=1; "
            f"elif sudo mount -t virtiofs {tag} {path}; then echo mounted {path} tag={tag}; ok=1; "
            f"else echo missing-device {path} tag={tag}; fi"
        )
    lines.append("ls -ld /Users /private /var/folders 2>/dev/null || true")
    lines.append("exit 0")
    return "\n".join(lines)


def apply_live(podman: str = "podman") -> int:
    """Mount virtiofs tags inside a running machine. Ignition is first-boot only."""
    inspect = subprocess.run(
        [podman, "machine", "inspect", "--format", "{{.State}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    state = (inspect.stdout or "").strip().lower()
    if inspect.returncode != 0 or state not in {"running", "currently running"}:
        print("podman-mounts: machine is not running; start it then rerun --apply")
        return 0
    proc = subprocess.run(
        [podman, "machine", "ssh", "--", "bash", "-lc", live_mount_script()],
        check=False,
    )
    return proc.returncode


def main() -> int:
    home = Path.home()
    paths = [item for item in sys.argv[1:] if not item.startswith("-")]
    cfg = Path(
        paths[0]
        if len(paths) > 0
        else home / ".config/containers/podman/machine/applehv/podman-machine-default.json"
    )
    ign = Path(
        paths[1]
        if len(paths) > 1
        else home / ".config/containers/podman/machine/applehv/podman-machine-default.ign"
    )
    if not cfg.exists() or not ign.exists():
        print(f"podman-mounts: missing {cfg} or {ign}", file=sys.stderr)
        return 2
    backup_cfg = cfg.with_suffix(".json.bak-mounts")
    backup_ign = ign.with_suffix(".ign.bak-mounts")
    if "--rewrite-config" in sys.argv:
        backup_cfg.write_text(cfg.read_text())
        backup_ign.write_text(ign.read_text())
        restored = repair(cfg, ign)
        print("backed up", backup_cfg)
        print("backed up", backup_ign)
        for row in restored:
            print("mount", row)
        print("note: rewriting Mounts on this 6-month AppleHV VM can crash vfkit; prefer a new machine with podman machine init -v")
    else:
        print("skipping JSON rewrite (use --rewrite-config only on a disposable machine)")
    if "--apply" in sys.argv or "--rewrite-config" not in sys.argv:
        return apply_live()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
