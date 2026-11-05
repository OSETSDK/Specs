import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import sync_public_spec as sync


class PublicSpecSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="oset-spec-sync-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        self.pod = "DemoPod"
        self.version = "1.2.3.4"
        self.spec = {
            "name": self.pod, "version": self.version,
            "source": {"git": "https://github.com/example/DemoPod.git", "tag": self.version},
            "dependencies": {"OtherPod": [">= 1.0"]},
        }
        self.raw = ("  " + json.dumps(self.spec, indent=4) + "\n\n").encode()
        self.manifest = {"schema_version": 1, "pods": [{
            "name": self.pod, "order": 2, "modified_at": "2026-11-05T10:00:00+08:00",
            "local_version": "1.2.3.0", "selected_version": "1.2.3.0", "versions": [],
        }]}
        self.manifest_path = self.root / "specs-manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.requests = []

    def fetch(self, url):
        self.requests.append(url)
        if url.startswith("https://trunk.cocoapods.org/"):
            return json.dumps({"versions": [{"name": self.version}]}).encode()
        self.assertEqual(url, sync.canonical_url(self.pod, self.version))
        return self.raw

    @staticmethod
    def compare(left, right):
        a, b = tuple(map(int, left.split("."))), tuple(map(int, right.split(".")))
        return (a > b) - (a < b)

    def run_sync(self, apply=False):
        return sync.synchronize(self.root, self.pod, self.version, apply, self.fetch, self.compare)

    def target(self):
        return self.root / self.pod / self.version / (self.pod + ".podspec.json")

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def test_preview_reports_changes_without_writing_any_files(self):
        before = self.snapshot()
        report = self.run_sync()
        self.assertEqual(report["mode"], "preview")
        self.assertEqual(report["spec_action"], "create")
        self.assertEqual(report["manifest_action"], "update")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / self.pod).exists())

    def test_apply_preserves_original_bytes_and_updates_manifest(self):
        report = self.run_sync(apply=True)
        self.assertEqual(self.target().read_bytes(), self.raw)
        entry = json.loads(self.manifest_path.read_bytes())["pods"][0]
        self.assertEqual(entry["selected_version"], self.version)
        self.assertEqual(entry["local_version"], "1.2.3.0")
        record = entry["versions"][0]
        self.assertEqual(record["sha1"], hashlib.sha1(self.raw).hexdigest())
        self.assertEqual(record["sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(record["source"], self.spec["source"])
        self.assertFalse(report["committed"])
        self.assertFalse(report["pushed"])

    def test_identical_version_is_idempotent(self):
        self.run_sync(apply=True)
        before = self.snapshot()
        report = self.run_sync(apply=True)
        self.assertEqual(report["spec_action"], "unchanged")
        self.assertEqual(report["manifest_action"], "unchanged")
        self.assertEqual(self.snapshot(), before)

    def test_same_version_different_bytes_is_rejected_even_if_json_equivalent(self):
        self.target().parent.mkdir(parents=True)
        self.target().write_bytes(json.dumps(self.spec).encode())
        before = self.snapshot()
        with self.assertRaisesRegex(sync.SyncError, "different bytes"):
            self.run_sync(apply=True)
        self.assertEqual(self.snapshot(), before | {".git/oset-specs-sync.lock": b""})

    def test_ruby_extension_cannot_bypass_json_immutability(self):
        self.target().parent.mkdir(parents=True)
        alternate = self.target().with_suffix("")
        alternate.write_text("Pod::Spec.new {}")
        with self.assertRaisesRegex(sync.SyncError, "Existing version directory"):
            self.run_sync()
        self.assertFalse(self.target().exists())

    def test_mixed_extensions_are_rejected_even_with_identical_json(self):
        self.target().parent.mkdir(parents=True)
        self.target().write_bytes(self.raw)
        self.target().with_suffix("").write_text("Pod::Spec.new {}")
        with self.assertRaisesRegex(sync.SyncError, "Existing version directory"):
            self.run_sync()

    def test_path_traversal_and_subspec_names_are_rejected_before_network(self):
        cases = [("../DemoPod", self.version), ("DemoPod/Sub", self.version),
                 ("DemoPod\\Sub", self.version), (self.pod, "../1.0"),
                 (".github", self.version), (self.pod, "1.0/../../escape")]
        for pod, version in cases:
            with self.subTest(pod=pod, version=version):
                with self.assertRaises(sync.SyncError):
                    sync.synchronize(self.root, pod, version, False, self.fetch, self.compare)
        self.assertEqual(self.requests, [])

    def test_symlinked_pod_directory_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / self.pod).symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(sync.SyncError, "Symbolic links"):
            self.run_sync()
        self.assertEqual(list(outside.iterdir()), [])

    def test_unpublished_version_stops_before_raw_spec_download(self):
        calls = []
        def unpublished(url):
            calls.append(url)
            return b'{"versions": [{"name": "1.0"}]}'
        with self.assertRaisesRegex(sync.SyncError, "not published"):
            sync.synchronize(self.root, self.pod, self.version, False, unpublished, self.compare)
        self.assertEqual(len(calls), 1)

    def test_wrong_official_identity_is_rejected(self):
        self.spec["name"] = "AnotherPod"
        self.raw = json.dumps(self.spec).encode()
        with self.assertRaisesRegex(sync.SyncError, "name/version"):
            self.run_sync()

    def test_source_without_immutable_git_reference_is_rejected(self):
        self.spec["source"] = {"git": "https://github.com/example/DemoPod.git", "branch": "main"}
        self.raw = json.dumps(self.spec).encode()
        with self.assertRaisesRegex(sync.SyncError, "tag or commit"):
            self.run_sync()

    def test_http_source_rejects_non_http_url(self):
        self.spec["source"] = {"http": "ssh://example.com/artifact.zip"}
        self.raw = json.dumps(self.spec).encode()
        with self.assertRaisesRegex(sync.SyncError, "supported remote URL"):
            self.run_sync()

    def test_selected_version_cannot_be_downgraded(self):
        self.manifest["pods"][0]["selected_version"] = "2.0.0"
        self.manifest_path.write_text(json.dumps(self.manifest))
        before = self.snapshot()
        with self.assertRaisesRegex(sync.SyncError, "downgrade"):
            self.run_sync()
        self.assertEqual(self.snapshot(), before)

    def test_manifest_checksum_disagreement_is_not_silently_repaired(self):
        self.manifest["pods"][0]["versions"] = [{"version": self.version, "sha1": "bad"}]
        self.manifest_path.write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(sync.SyncError, "Manifest sha1"):
            self.run_sync()

    def test_manifest_does_not_require_local_version_metadata(self):
        del self.manifest["pods"][0]["local_version"]
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.run_sync(apply=True)
        entry = json.loads(self.manifest_path.read_bytes())["pods"][0]
        self.assertNotIn("local_version", entry)
        self.assertEqual(entry["selected_version"], self.version)

    @unittest.skipUnless(shutil.which("ruby"), "Ruby is not installed")
    def test_gem_version_order_handles_four_components_and_prereleases(self):
        self.assertGreater(sync.compare_versions("7.0.10.0", "7.0.3.5"), 0)
        self.assertLess(sync.compare_versions("7.0.3.beta1", "7.0.3"), 0)

    def test_existing_exact_bytes_can_add_missing_manifest_record(self):
        self.target().parent.mkdir(parents=True)
        self.target().write_bytes(self.raw)
        report = self.run_sync(apply=True)
        self.assertEqual(report["spec_action"], "unchanged")
        self.assertEqual(report["manifest_action"], "update")
        self.assertEqual(self.target().read_bytes(), self.raw)


if __name__ == "__main__":
    unittest.main()
