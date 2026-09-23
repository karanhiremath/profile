from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin/hermes/hermes_agents.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hermes_agents_fresh", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FreshCoswBootstrapTest(unittest.TestCase):
    def test_fresh_materialization_injects_dispatch_contract_and_safe_docker_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / "profiles"
            profiles.mkdir()
            (profiles / "chief-of-staff-work.yaml").write_text(
                yaml.safe_dump(
                    {
                        "name": "chief-of-staff-work",
                        "tts": {"enabled": False},
                        "stt": {"enabled": False},
                        "toolsets": ["terminal", "file"],
                        "persona": "Generic work dispatcher.",
                    }
                )
            )
            appendix = root / "dispatch.md"
            appendix.write_text("Run `cosw-hostctl bootstrap`, then use `cosw-hostctl dispatch-pm`.\n")
            env = {
                "XDG_DATA_HOME": str(root / "fresh-data"),
                "HERMES_AGENT_PROFILE_PATH": str(profiles),
                "HERMES_AGENT_TERMINAL_BACKEND": "docker",
                "TERMINAL_CWD": "/workspace",
                "TERMINAL_DOCKER_VOLUMES": json.dumps(["/host/socket:/run/hermes-manager:ro"]),
                "TERMINAL_DOCKER_EXTRA_ARGS": json.dumps(["--userns=keep-id:uid=1000,gid=1000"]),
                "TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES": "true",
                "TERMINAL_DOCKER_ENV": json.dumps({
                    "COSW_HOST_CONTROL_SOCKET": "/run/hermes-manager/manager.sock",
                    "HERMES_SANDBOX_ID": "chief-of-staff-work",
                }),
                "HERMES_PERSONA_APPEND_FILE": str(appendix),
            }
            with patch.dict(os.environ, env, clear=False):
                module = load_module()
                home = module.materialize("chief-of-staff-work")
            self.assertTrue(home.is_dir())
            config = yaml.safe_load((home / "config.yaml").read_text())
            terminal = config["terminal"]
            self.assertEqual(terminal["cwd"], "/workspace")
            self.assertTrue(terminal["docker_persist_across_processes"])
            self.assertEqual(terminal["docker_extra_args"], ["--userns=keep-id:uid=1000,gid=1000"])
            self.assertEqual(
                terminal["docker_env"]["COSW_HOST_CONTROL_SOCKET"],
                "/run/hermes-manager/manager.sock",
            )
            soul = (home / "SOUL.md").read_text()
            self.assertIn("Generic work dispatcher", soul)
            self.assertIn("cosw-hostctl bootstrap", soul)
            self.assertIn("cosw-hostctl dispatch-pm", soul)


if __name__ == "__main__":
    unittest.main()
