"""bin/interface/{apply,doctor}: class-agnostic UI merge, JSON-only stdout, idempotence."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(home: Path, cdir: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "MISE_"))}
    env.update(HOME=str(home), CLAUDE_CONFIG_DIR=str(cdir), PROFILE_DIR=str(ROOT),
               ZSH_SYNC_HOME=str(home), AGENTIC_HOST_CLASS="personal")
    return env


def _run(args, env):
    return subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)


def test_apply_merges_ui_keys_and_preserves_hooks(tmp_path):
    cdir = tmp_path / ".claude-personal"
    cdir.mkdir()
    (cdir / "settings.json").write_text(json.dumps(
        {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "true"}]}]},
         "permissions": {"allow": ["Read"]}, "theme": "dark", "tui": "default"}))
    env = _env(tmp_path, cdir)

    r = _run([str(ROOT / "bin/interface/apply"), "--class", "personal"], env)
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert len(lines) == 1
    summary = json.loads(lines[0])
    assert summary["schema"] == "profile.interface.apply.v1" and summary["failed"] == []

    s = json.loads((cdir / "settings.json").read_text())
    assert s["hooks"]["Stop"][0]["hooks"][0]["command"] == "true"
    assert s["permissions"] == {"allow": ["Read"]}
    assert s["theme"] == "dark"
    assert s["tui"] == "fullscreen" and s["outputStyle"] == "Concise" and s["editorMode"] == "vim"
    assert s["statusLine"]["command"] == "bash ~/.claude-personal/statusline-command.sh"
    assert (cdir / "statusline-command.sh").resolve() == ROOT / "config/claude/statusline-command.sh"

    before = (cdir / "settings.json").read_text()
    r2 = _run([str(ROOT / "bin/interface/apply"), "--class", "personal"], env)
    assert r2.returncode == 0, r2.stderr
    assert (cdir / "settings.json").read_text() == before
    assert len(list(cdir.glob("settings.json.bak-interface-*"))) == 1


def test_doctor_reports_drift_as_json(tmp_path):
    cdir = tmp_path / ".claude"
    cdir.mkdir()
    (cdir / "settings.json").write_text("{}")
    r = _run([str(ROOT / "bin/interface/doctor")], _env(tmp_path, cdir))
    assert r.returncode == 1
    report = json.loads(r.stdout)
    assert report["schema"] == "profile.interface.doctor.v1"
    assert "claude:outputStyle" in report["drift"]
    assert any(d.startswith("link:") for d in report["drift"])


def test_dry_run_changes_nothing(tmp_path):
    cdir = tmp_path / ".claude"
    cdir.mkdir()
    (cdir / "settings.json").write_text("{}")
    r = _run([str(ROOT / "bin/interface/apply"), "--dry-run"], _env(tmp_path, cdir))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["dry_run"] is True
    assert (cdir / "settings.json").read_text() == "{}"
    assert not (tmp_path / ".tmux.conf").exists()
