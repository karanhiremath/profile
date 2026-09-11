from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "bin/hermes/cosw-hostctl"


def load():
    loader = importlib.machinery.SourceFileLoader("cosw_hostctl", str(PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class HostControlClientTest(unittest.TestCase):
    def setUp(self):
        self.module = load()

    def test_host_defaults_find_the_profile_manager(self):
        env = {
            "HOME": "/home/operator",
            "XDG_DATA_HOME": "/home/operator/.local/share",
            "XDG_RUNTIME_DIR": "/run/user/2005",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(Path, "exists", return_value=False):
            state = self.module.default_state()
            socket = self.module.default_socket()
        self.assertEqual(
            state,
            Path("/home/operator/.local/share/hermes-agents/chief-of-staff-work/profiles/chief-of-staff-work/host-control"),
        )
        self.assertEqual(socket, Path("/run/user/2005/hermes-sandbox-manager/chief-of-staff-work/manager.sock"))

    def test_explicit_paths_override_host_and_sandbox_detection(self):
        env = {
            "COSW_HOST_CONTROL_MOUNT": "/state",
            "COSW_HOST_CONTROL_SOCKET": "/socket/manager.sock",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(self.module.default_state(), Path("/state"))
            self.assertEqual(self.module.default_socket(), Path("/socket/manager.sock"))


if __name__ == "__main__":
    unittest.main()
