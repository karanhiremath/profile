from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "bin/hermes/cosw-host-control"


def load_module():
    loader = importlib.machinery.SourceFileLoader("cosw_host_control", str(MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(module, **extra):
    value = {
        "id": "unit-test",
        "action": "cloudbuild-trigger-create-readback",
        "project": "kh133-v1alpha2",
        "cloudProject": module.KH133_TRIGGER_PROJECT,
        "region": module.KH133_TRIGGER_REGION,
        "triggerName": module.KH133_TRIGGER_NAME,
    }
    value.update(extra)
    return value


class CloudBuildTriggerBrokerTest(unittest.TestCase):
    def readback(self, module):
        config = module._kh133_trigger_config()
        value = {**config, "id": "12345678-1234-1234-1234-123456789abc"}
        value["resourceName"] = (
            "projects/base-391403/locations/us-central1/triggers/"
            "12345678-1234-1234-1234-123456789abc"
        )
        return value

    def test_broker_uses_exact_gcloud_create_and_two_describes(self):
        module = load_module()
        readback = self.readback(module)
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            if argv[:4] == ["gcloud", "builds", "triggers", "describe"] and argv[4] == module.KH133_TRIGGER_NAME:
                return SimpleNamespace(returncode=1, stdout="", stderr="NOT_FOUND")
            if argv[:5] == ["gcloud", "builds", "triggers", "create", "manual"]:
                self.assertTrue(any(arg.startswith("--trigger-config=") for arg in argv))
                self.assertNotIn(f"--region={module.KH133_TRIGGER_REGION}", argv)
                self.assertEqual(kwargs["env"]["CLOUDSDK_BUILDS_REGION"], module.KH133_TRIGGER_REGION)
                return SimpleNamespace(returncode=0, stdout=json.dumps({"id": readback["id"]}), stderr="")
            if argv[:4] == ["gcloud", "builds", "triggers", "describe"] and argv[4] == readback["id"]:
                return SimpleNamespace(returncode=0, stdout=json.dumps(readback, sort_keys=True), stderr="")
            raise AssertionError(argv)

        with mock.patch.object(subprocess, "run", side_effect=fake_run):
            result = module.cloudbuild_trigger_create_readback(request(module))
        self.assertTrue(result["created"])
        self.assertFalse(result["invoked"])
        self.assertEqual(
            [call[:5] for call in calls],
            [
                ["gcloud", "builds", "triggers", "describe", module.KH133_TRIGGER_NAME],
                ["gcloud", "builds", "triggers", "create", "manual"],
                ["gcloud", "builds", "triggers", "describe", readback["id"]],
                ["gcloud", "builds", "triggers", "describe", readback["id"]],
            ],
        )
        self.assertFalse(any("run" in call for call in calls))

    def test_broker_rejects_existing_trigger_before_create(self):
        module = load_module()
        readback = self.readback(module)
        with mock.patch.object(module, "_describe_trigger", return_value=readback):
            with self.assertRaisesRegex(ValueError, "already exists"):
                module.cloudbuild_trigger_create_readback(request(module))

    def test_broker_rejects_extra_request_fields(self):
        module = load_module()
        with self.assertRaisesRegex(ValueError, "unsupported request fields"):
            module.cloudbuild_trigger_create_readback(request(module, triggerConfig={}))

    def test_broker_rejects_wrong_exact_trigger_name(self):
        module = load_module()
        with self.assertRaisesRegex(ValueError, "triggerName"):
            module.cloudbuild_trigger_create_readback(request(module, triggerName="kh133-fips-v1alpha2-temp-other"))

    def test_broker_rejects_extra_non_cbuild_substitution_in_readback(self):
        module = load_module()
        config = module._kh133_trigger_config()
        config["substitutions"] = {**config["substitutions"], "_OTHER": "value"}
        with self.assertRaisesRegex(ValueError, "substitutions must be exactly"):
            module._validate_kh133_trigger_config(config)

    def test_broker_rejects_injected_credential_environment(self):
        module = load_module()
        with mock.patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "/tmp/key.json"}):
            with self.assertRaisesRegex(ValueError, "injected credential"):
                module.cloudbuild_trigger_create_readback(request(module))

    def test_config_uses_nonexistent_refs_ref_and_exact_gitfile_commit(self):
        module = load_module()
        config = module._kh133_trigger_config()
        self.assertEqual(
            config["sourceToBuild"]["ref"],
            f"refs/tags/cbuild-no-default-kh133-{module.KH133_BIFROST_COMMIT}",
        )
        self.assertEqual(config["gitFileSource"]["revision"], module.KH133_BIFROST_COMMIT)


class Kh133GkeAddonIamBrokerTest(unittest.TestCase):
    def test_gke_update_accepts_non_object_json_before_authoritative_readback(self):
        module = load_module()
        completed = SimpleNamespace(returncode=0, stdout="[]", stderr="")
        with mock.patch.object(module.subprocess, "run", return_value=completed):
            self.assertEqual(
                module._run_json(["gcloud", "container", "clusters", "update"], object_required=False),
                [],
            )
            with self.assertRaisesRegex(ValueError, "not an object"):
                module._run_json(["gcloud", "container", "clusters", "describe"])

    def cluster(self, module, *, enabled: bool):
        return {
            "name": module.KH133_GKE_CLUSTER,
            "location": module.KH133_GKE_REGION,
            "status": "RUNNING",
            "addonsConfig": {"gcsFuseCsiDriverConfig": {"enabled": enabled}},
        }

    def policy(self, module, *, creator: bool = False, conflicting: bool = False):
        bindings = [
            {
                "role": module.KH133_OBJECT_VIEWER_ROLE,
                "members": [module.KH133_GSA_MEMBER],
            },
            {
                "role": "roles/storage.legacyBucketReader",
                "members": ["projectViewer:base-391403"],
            },
        ]
        if creator:
            bindings.append(
                {
                    "role": module.KH133_OBJECT_CREATOR_ROLE,
                    "members": [module.KH133_GSA_MEMBER],
                    "condition": (
                        {"title": "wrong", "expression": "true"}
                        if conflicting
                        else dict(module.KH133_CREATOR_CONDITION)
                    ),
                }
            )
        return {"version": 3, "bindings": bindings}

    def request(self):
        return {
            "id": "unit-test",
            "action": "kh133-gke-addon-iam-prepare",
            "project": "kh133-v1alpha2",
        }

    def test_exact_addon_and_conditioned_creator_effect(self):
        module = load_module()
        cluster_before = self.cluster(module, enabled=False)
        cluster_after = self.cluster(module, enabled=True)
        policy_before = self.policy(module)
        policy_after = self.policy(module, creator=True)
        reads = iter([cluster_before, policy_before, {}, cluster_after, policy_after, policy_after])
        calls = []

        def fake_run_json(argv, **_kwargs):
            calls.append(argv)
            return next(reads)

        with mock.patch.object(module, "_run_json", side_effect=fake_run_json):
            result = module.kh133_gke_addon_iam_prepare(self.request())
        self.assertTrue(result["gcsFuseCsiEnabled"])
        self.assertTrue(result["conditionedObjectCreatorPresent"])
        updates = [call for call in calls if call[:4] == ["gcloud", "container", "clusters", "update"]]
        self.assertEqual(len(updates), 1)
        self.assertIn("--update-addons=GcsFuseCsiDriver=ENABLED", updates[0])
        iam = [call for call in calls if call[:4] == ["gcloud", "storage", "buckets", "add-iam-policy-binding"]]
        self.assertEqual(len(iam), 1)
        self.assertIn(f"--member={module.KH133_GSA_MEMBER}", iam[0])
        self.assertIn(f"--role={module.KH133_OBJECT_CREATOR_ROLE}", iam[0])
        self.assertTrue(any(module.KH133_CREATOR_CONDITION["expression"] in arg for arg in iam[0]))

    def test_idempotent_readback_performs_no_mutation(self):
        module = load_module()
        cluster = self.cluster(module, enabled=True)
        policy = self.policy(module, creator=True)
        reads = iter([cluster, policy, cluster, policy])
        calls = []

        def fake_run_json(argv, **_kwargs):
            calls.append(argv)
            return next(reads)

        with mock.patch.object(module, "_run_json", side_effect=fake_run_json):
            result = module.kh133_gke_addon_iam_prepare(self.request())
        self.assertFalse(result["gcsFuseCsiChanged"])
        self.assertFalse(result["conditionedObjectCreatorChanged"])
        self.assertFalse(any("update" in call for call in calls))
        self.assertFalse(any("add-iam-policy-binding" in call for call in calls))

    def test_conflicting_creator_binding_fails_before_mutation(self):
        module = load_module()
        cluster = self.cluster(module, enabled=False)
        policy = self.policy(module, creator=True, conflicting=True)
        calls = []

        def fake_run_json(argv, **_kwargs):
            calls.append(argv)
            return cluster if argv[1:4] == ["container", "clusters", "describe"] else policy

        with mock.patch.object(module, "_run_json", side_effect=fake_run_json):
            with self.assertRaisesRegex(ValueError, "conflicting objectCreator"):
                module.kh133_gke_addon_iam_prepare(self.request())
        self.assertFalse(any("update" in call for call in calls))
        self.assertFalse(any("add-iam-policy-binding" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
