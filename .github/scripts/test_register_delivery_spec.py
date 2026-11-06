import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import register_delivery_spec as delivery
import validate_specs


class DeliverySpecRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="oset-delivery-register-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / ".git").mkdir()
        self.pod, self.version = "AdSetQDMAdSDK", "1.4.16"
        self.sha = "a" * 40
        self.spec = {"name": self.pod, "version": self.version,
                     "source": {"git": delivery.delivery_repository(self.pod), "tag": self.version},
                     "dependencies": {}}
        self.raw = ("  " + json.dumps(self.spec, indent=4) + "\n\n").encode()
        self.manifest = {"schema_version": 1, "notes": ["Keep this ledger note"], "pods": []}
        self.manifest_path = self.root / "specs-manifest.json"
        self.save_manifest()
        self.requests = []
        self.tag_requests = []

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def fetch(self, url):
        self.requests.append(url)
        self.assertEqual(url, delivery.delivery_spec_url(self.pod, self.version))
        self.assertNotIn("trunk.cocoapods.org", url)
        return self.raw

    def tag(self, pod, version):
        self.tag_requests.append((pod, version))
        self.assertEqual((pod, version), (self.pod, self.version))
        return self.sha

    @staticmethod
    def compare(left, right):
        a, b = tuple(map(int, left.split("."))), tuple(map(int, right.split(".")))
        return (a > b) - (a < b)

    def register(self, apply=False, **kwargs):
        return delivery.register_delivery_spec(self.root, self.pod, self.version, apply,
                                               self.fetch, kwargs.get("tag_reader", self.tag), self.compare)

    def target(self):
        return self.root / self.pod / self.version / (self.pod + ".podspec.json")

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def add_existing_entry(self, selected="1.4.15"):
        self.manifest["pods"] = [{"name": self.pod, "order": 9,
                                  "modified_at": "2026-11-01T10:00:00+08:00",
                                  "selected_version": selected, "notes": {"preserve": True},
                                  "publication_origin": "previous-origin", "versions": []}]
        self.save_manifest()

    def test_preview_is_read_only_and_uses_tag_json_without_trunk(self):
        before = self.snapshot()
        result = self.register()
        self.assertEqual(result["mode"], "preview")
        self.assertTrue(result["new_pod"])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.target().parent.exists())
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(len(self.tag_requests), 2)

    def test_new_pod_registers_original_bytes_and_next_order(self):
        self.manifest["pods"] = [{"name": "OtherPod", "order": 7, "versions": [], "notes": ["keep"]}]
        original = copy.deepcopy(self.manifest["pods"][0])
        self.save_manifest()
        result = self.register(apply=True)
        saved = json.loads(self.manifest_path.read_bytes())
        self.assertEqual(saved["notes"], self.manifest["notes"])
        self.assertEqual(saved["pods"][0], original)
        entry = saved["pods"][1]
        self.assertEqual(entry["order"], 8)
        self.assertEqual(entry["publication_origin"], "direct_delivery")
        self.assertIn("modified_at", entry)
        self.assertEqual(entry["selected_version"], self.version)
        record = entry["versions"][0]
        self.assertEqual(self.target().read_bytes(), self.raw)
        self.assertEqual(record["sha1"], hashlib.sha1(self.raw).hexdigest())
        self.assertEqual(record["sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(record["delivery_tag_sha"], self.sha)
        self.assertEqual(record["origin_url"], self.requests[0])
        self.assertFalse(result["committed"] or result["pushed"])

    def test_existing_pod_appends_version_and_preserves_metadata(self):
        self.add_existing_entry()
        self.register(apply=True)
        entry = json.loads(self.manifest_path.read_bytes())["pods"][0]
        self.assertEqual(entry["notes"], {"preserve": True})
        self.assertEqual(entry["order"], 9)
        self.assertEqual(entry["modified_at"], "2026-11-01T10:00:00+08:00")
        self.assertEqual(entry["publication_origin"], "previous-origin")
        self.assertEqual(entry["versions"][0]["publication_origin"], "direct_delivery")

    def test_new_native_registration_passes_shared_offline_validator(self):
        self.register(apply=True)
        result = validate_specs.validate_repository(self.root)
        self.assertEqual(result["pods"], 1)
        self.assertEqual(result["specs"], 1)

    def test_same_version_is_idempotent_and_preserves_record_notes(self):
        self.register(apply=True)
        manifest = json.loads(self.manifest_path.read_bytes())
        manifest["pods"][0]["versions"][0]["notes"] = ["keep version note"]
        self.manifest_path.write_text(json.dumps(manifest))
        before = self.snapshot()
        result = self.register(apply=True)
        self.assertEqual(result["spec_action"], "unchanged")
        self.assertEqual(result["manifest_action"], "unchanged")
        self.assertEqual(self.snapshot(), before)

    def test_same_version_equivalent_json_with_different_bytes_is_rejected(self):
        self.register(apply=True)
        self.raw += b"\n"
        before = self.snapshot()
        with self.assertRaisesRegex(delivery.SyncError, "different bytes"):
            self.register(apply=True)
        self.assertEqual(self.snapshot(), before)

    def test_alternate_or_mixed_extension_cannot_bypass_existing_version(self):
        for include_json in (False, True):
            with self.subTest(include_json=include_json):
                self.target().parent.mkdir(parents=True, exist_ok=True)
                self.target().with_suffix("").write_text("Pod::Spec.new {}")
                if include_json:
                    self.target().write_bytes(self.raw)
                with self.assertRaisesRegex(delivery.SyncError, "Existing version directory"):
                    self.register()

    def test_downgrade_is_rejected_without_writes(self):
        self.add_existing_entry(selected="2.0.0")
        before = self.snapshot()
        with self.assertRaisesRegex(delivery.SyncError, "downgrade"):
            self.register()
        self.assertEqual(self.snapshot(), before)

    def test_wrong_identity_or_source_is_rejected(self):
        cases = [dict(name="WrongPod"), dict(version="9.0.0"),
                 dict(source={"git": "https://github.com/other/AdSetQDMAdSDK.git", "tag": self.version}),
                 dict(source={"git": delivery.delivery_repository(self.pod), "tag": "9.0.0"}),
                 dict(source={"git": delivery.delivery_repository(self.pod), "tag": self.version, "commit": "b" * 40})]
        for change in cases:
            with self.subTest(change=change):
                self.raw = json.dumps(dict(self.spec, **change)).encode()
                with self.assertRaises(delivery.SyncError):
                    self.register()
        self.assertFalse(self.target().exists())

    def test_missing_tag_stops_before_json_download(self):
        def absent(pod, version):
            raise delivery.SyncError("Public delivery tag does not exist")
        with self.assertRaisesRegex(delivery.SyncError, "tag does not exist"):
            self.register(tag_reader=absent)
        self.assertEqual(self.requests, [])

    def test_changed_tag_during_download_is_rejected(self):
        shas = iter([self.sha, "b" * 40])
        with self.assertRaisesRegex(delivery.SyncError, "tag changed"):
            self.register(tag_reader=lambda pod, version: next(shas))

    def test_unsafe_identifiers_are_rejected_before_git_or_network(self):
        for pod, version in [("../Demo", self.version), (".github", self.version),
                             ("Demo/Sub", self.version), (self.pod, "../1.0"),
                             (self.pod, "1.0/../../escape"), ("_Hidden", self.version)]:
            with self.subTest(pod=pod, version=version):
                with self.assertRaises(delivery.SyncError):
                    delivery.register_delivery_spec(self.root, pod, version, False,
                                                    self.fetch, self.tag, self.compare)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.tag_requests, [])

    def test_symlinked_pod_directory_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / self.pod).symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(delivery.SyncError, "Symbolic links"):
            self.register()
        self.assertEqual(list(outside.iterdir()), [])

    def test_apply_requires_independent_git_directory(self):
        (self.root / ".git").rmdir()
        (self.root / ".git").write_text("gitdir: /another/checkout")
        with self.assertRaisesRegex(delivery.SyncError, "independent Git clone"):
            self.register(apply=True)

    def test_manifest_change_after_plan_is_not_overwritten(self):
        plan = delivery.make_plan(self.root, self.pod, self.version, self.raw, self.spec,
                                  delivery.delivery_spec_url(self.pod, self.version), self.sha, self.compare)
        updated = self.manifest_path.read_bytes() + b"\n"
        self.manifest_path.write_bytes(updated)
        with self.assertRaisesRegex(delivery.SyncError, "Manifest changed"):
            delivery.apply_plan(self.root, self.raw, plan)
        self.assertEqual(self.manifest_path.read_bytes(), updated)
        self.assertFalse(self.target().parent.exists())

    def test_atomic_manifest_failure_rolls_back_new_version(self):
        original = self.manifest_path.read_bytes()
        def fail_replace(path, destination):
            raise OSError("injected atomic replace failure")
        with patch.object(Path, "replace", fail_replace):
            with self.assertRaisesRegex(OSError, "injected atomic"):
                self.register(apply=True)
        self.assertEqual(self.manifest_path.read_bytes(), original)
        self.assertFalse(self.target().parent.exists())
        self.assertEqual(list(self.root.glob(".specs-manifest-*")), [])

    def test_existing_version_tag_sha_cannot_be_changed(self):
        self.register(apply=True)
        self.sha = "b" * 40
        with self.assertRaisesRegex(delivery.SyncError, "delivery_tag_sha"):
            self.register()

    def test_public_tag_lookup_uses_anonymous_matching_ref_and_peels_annotated_tag(self):
        output = f"{'c' * 40}\trefs/tags/{self.version}\n{self.sha}\trefs/tags/{self.version}^{{}}\n"
        with patch.object(delivery.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output, "")) as run:
            self.assertEqual(delivery.public_tag_sha(self.pod, self.version), self.sha)
        self.assertIn("credential.helper=", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")

    def test_public_tag_lookup_rejects_missing_ref(self):
        with patch.object(delivery.subprocess, "run", return_value=subprocess.CompletedProcess([], 2, "", "")):
            with self.assertRaisesRegex(delivery.SyncError, "tag does not exist"):
                delivery.public_tag_sha(self.pod, self.version)


if __name__ == "__main__":
    unittest.main()
