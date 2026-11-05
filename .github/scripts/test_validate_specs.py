"""Regression checks for manifest provenance and released-version immutability."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import validate_specs


class ValidateSpecsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="oset-spec-validation-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = {"schema_version": 1, "pods": []}
        self.add_spec("DemoPod", "1.0.0", 1)

    def add_spec(self, name, version, order):
        spec = {"name": name, "version": version,
                "source": {"git": "https://github.com/example/DemoPod.git", "tag": version},
                "dependencies": {"Dependency": [">= 1.0"]}}
        raw = (json.dumps(spec, indent=2) + "\n").encode()
        relative = f"{name}/{version}/{name}.podspec.json"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        record = {"version": version, "path": relative,
                  "origin_url": f"https://example.com/{relative}",
                  "sha1": hashlib.sha1(raw).hexdigest(),
                  "sha256": hashlib.sha256(raw).hexdigest(),
                  "source": spec["source"], "dependencies": spec["dependencies"]}
        pod = next((p for p in self.manifest["pods"] if p["name"] == name), None)
        if pod is None:
            pod = {"name": name, "order": order, "modified_at": "2026-11-05T10:00:00+08:00",
                   "selected_version": version, "versions": []}
            self.manifest["pods"].append(pod)
        pod["versions"].append(record)
        self.save_manifest()
        return record

    def save_manifest(self):
        (self.root / "specs-manifest.json").write_text(json.dumps(self.manifest))

    def record(self):
        return self.manifest["pods"][0]["versions"][0]

    def rewrite_spec(self, transform):
        record = self.record()
        path = self.root / record["path"]
        updated = transform(path.read_bytes())
        path.write_bytes(updated)
        record["sha1"] = hashlib.sha1(updated).hexdigest()
        record["sha256"] = hashlib.sha256(updated).hexdigest()
        self.save_manifest()

    def reject(self, message, **arguments):
        with self.assertRaisesRegex(validate_specs.ValidationError, message):
            validate_specs.validate_repository(self.root, **arguments)

    def git(self, *arguments):
        environment = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                           GIT_OPTIONAL_LOCKS="0")
        return subprocess.check_output(["git", "-C", str(self.root), *arguments],
                                       env=environment, stderr=subprocess.PIPE).decode().strip()

    def baseline(self):
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "initial")
        return self.git("rev-parse", "HEAD")

    def test_valid_inventory_accepts_gaps_in_sort_order(self):
        self.add_spec("OtherPod", "2.0.0", 5)
        result = validate_specs.validate_repository(self.root)
        self.assertEqual(result, {"pods": 2, "specs": 2, "immutable_specs": 0})

    def test_formatting_only_change_is_detected_by_original_byte_checksum(self):
        path = self.root / self.record()["path"]
        path.write_bytes(path.read_bytes() + b"\n")
        self.reject("sha1 mismatch")

    def test_sha256_is_checked_independently(self):
        self.record()["sha256"] = "0" * 64
        self.save_manifest()
        self.reject("sha256 mismatch")

    def test_json_identity_cannot_be_changed_by_updating_checksums(self):
        self.rewrite_spec(lambda raw: raw.replace(b'"name": "DemoPod"', b'"name": "OtherPod"'))
        self.reject("Spec name mismatch")

    def test_source_must_match_provenance_record(self):
        self.record()["source"] = {"http": "https://example.com/other.zip"}
        self.save_manifest()
        self.reject("Spec source mismatch")

    def test_dependencies_must_match_provenance_record(self):
        self.record()["dependencies"] = {}
        self.save_manifest()
        self.reject("Spec dependencies mismatch")

    def test_manifest_cannot_omit_existing_spec(self):
        self.manifest["pods"] = []
        self.save_manifest()
        self.reject("unrecorded=")

    def test_missing_file_is_reported(self):
        (self.root / self.record()["path"]).unlink()
        self.reject("Manifest spec is missing")

    def test_ruby_spec_is_rejected_even_without_manifest_entry(self):
        (self.root / "Unreviewed.podspec").write_text("Pod::Spec.new")
        self.reject("Ruby podspec is not allowed")

    def test_duplicate_versions_are_rejected(self):
        self.manifest["pods"][0]["versions"].append(copy.deepcopy(self.record()))
        self.save_manifest()
        self.reject("Duplicate version")

    def test_selected_version_must_be_present(self):
        self.manifest["pods"][0]["selected_version"] = "9.9.9"
        self.save_manifest()
        self.reject("selected_version is not recorded")

    def test_order_must_be_strictly_increasing(self):
        self.add_spec("OtherPod", "2.0.0", 1)
        self.reject("strictly increasing")

    def test_boolean_is_not_accepted_as_order(self):
        self.manifest["pods"][0]["order"] = True
        self.save_manifest()
        self.reject("strictly increasing")

    def test_noncanonical_path_is_rejected(self):
        original = self.root / self.record()["path"]
        moved = self.root / "DemoPod" / "1.0.0" / "renamed.podspec.json"
        original.rename(moved)
        self.record()["path"] = moved.relative_to(self.root).as_posix()
        self.save_manifest()
        self.reject("Noncanonical spec path")

    def test_traversal_absolute_and_windows_paths_are_rejected(self):
        for path in ["../outside.podspec.json", "/tmp/outside.podspec.json",
                     "DemoPod/../DemoPod/1.0.0/DemoPod.podspec.json",
                     "DemoPod\\1.0.0\\DemoPod.podspec.json"]:
            with self.subTest(path=path):
                self.record()["path"] = path
                self.save_manifest()
                self.reject("Unsafe relative path")

    def test_symlink_to_spec_is_rejected(self):
        path = self.root / self.record()["path"]
        target = path.with_suffix(".data")
        path.rename(target)
        path.symlink_to(target.name)
        self.reject("Symlink is not allowed")

    def test_duplicate_json_keys_are_rejected(self):
        self.rewrite_spec(lambda raw: raw.replace(b'"name": "DemoPod",',
                          b'"name": "DemoPod", "name": "OtherPod",'))
        self.reject("Duplicate JSON key")

    def test_baseline_accepts_unchanged_specs_and_new_versions(self):
        baseline = self.baseline()
        self.add_spec("DemoPod", "1.1.0", 1)
        self.manifest["pods"][0]["selected_version"] = "1.1.0"
        self.save_manifest()
        result = validate_specs.validate_repository(self.root, base_ref=baseline)
        self.assertEqual(result["specs"], 2)
        self.assertEqual(result["immutable_specs"], 1)

    def test_baseline_rejects_mutation_even_with_updated_manifest_hashes(self):
        baseline = self.baseline()
        self.rewrite_spec(lambda raw: raw + b"\n")
        self.reject("Published spec was changed", base_ref=baseline)

    def test_baseline_rejects_deletion_even_with_removed_manifest_record(self):
        baseline = self.baseline()
        (self.root / self.record()["path"]).unlink()
        self.manifest["pods"] = []
        self.save_manifest()
        self.reject("Published spec was deleted", base_ref=baseline)

    def test_baseline_requires_existing_full_commit_sha(self):
        self.baseline()
        self.reject("full Git commit SHA", base_ref="HEAD")
        self.reject("Git baseline unavailable", base_ref="0" * 40)


if __name__ == "__main__":
    unittest.main()
