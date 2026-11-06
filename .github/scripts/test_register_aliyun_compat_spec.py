import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import register_aliyun_compat_spec as compat
import validate_specs


UPSTREAM_RAW = b'''{
  "name": "AliyunLogProducer",
  "version": "4.3.3",
  "summary": "aliyun log service ios producer.",
  "description": "log service ios producer.\\nhttps://help.aliyun.com/document_detail/29063.html\\nhttps://help.aliyun.com/product/28958.html",
  "homepage": "https://github.com/aliyun/aliyun-log-ios-sdk",
  "license": {
    "type": "MIT",
    "file": "LICENSE"
  },
  "authors": {
    "aliyun-log": "yulong.gyl@alibaba-inc.com"
  },
  "source": {
    "git": "https://gitee.com/aliyun-sls/aliyun-log-ios-sdk.git",
    "tag": "4.3.3"
  },
  "social_media_url": "http://t.cn/AiRpol8C",
  "platforms": {
    "ios": "10.0",
    "tvos": "10.0",
    "osx": "10.12"
  },
  "requires_arc": true,
  "libraries": "z",
  "swift_versions": "5.0",
  "pod_target_xcconfig": {
    "EXCLUDED_ARCHS[sdk=iphonesimulator*]": "arm64 i386"
  },
  "user_target_xcconfig": {
    "EXCLUDED_ARCHS[sdk=iphonesimulator*]": "arm64 i386"
  },
  "source_files": [
    "Sources/Producer/**/*.{h,m}",
    "Sources/aliyun-log-c-sdk/**/*.{c,h}"
  ],
  "public_header_files": [
    "Sources/Producer/include/*.h",
    "Sources/aliyun-log-c-sdk/include/*.h"
  ],
  "resource_bundles": {
    "AliyunLogProducer": [
      "Sources/Producer/PrivacyInfo.xcprivacy"
    ]
  },
  "swift_version": "5.0"
}
'''


class AliyunCompatibilitySpecTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="oset-aliyun-compat-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / ".git").mkdir()
        self.base = json.loads(UPSTREAM_RAW)
        self.base_path = self.root / compat.POD / compat.BASE_VERSION / (compat.POD + ".podspec.json")
        self.base_path.parent.mkdir(parents=True)
        self.base_path.write_bytes(UPSTREAM_RAW)
        self.manifest = {"schema_version": 1, "notes": ["keep top note"], "pods": [{
            "name": compat.POD, "order": 53, "modified_at": "2026-11-06T14:00:00+08:00",
            "selected_version": compat.BASE_VERSION, "notes": {"keep": True}, "versions": [{
                "version": compat.BASE_VERSION, "path": self.base_path.relative_to(self.root).as_posix(),
                "origin_url": compat.BASE_URL, **compat.hashes(UPSTREAM_RAW),
                "source": self.base["source"], "dependencies": {}, "notes": ["keep base note"],
            }]}]}
        self.manifest_path = self.root / "specs-manifest.json"
        self.save_manifest()
        self.calls = []

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def fetch(self, url):
        self.calls.append(url)
        self.assertEqual(url, compat.BASE_URL)
        return UPSTREAM_RAW

    @staticmethod
    def compare(left, right):
        a, b = tuple(map(int, left.split("."))), tuple(map(int, right.split(".")))
        return (a > b) - (a < b)

    def register(self, apply=False, fetcher=None):
        return compat.register_compat_spec(self.root, apply, fetcher or self.fetch, self.compare)

    def target(self):
        return self.root / compat.POD / compat.COMPAT_VERSION / (compat.POD + ".podspec.json")

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_pinned_fixture_and_exact_candidate_bytes(self):
        self.assertEqual(hashlib.sha1(UPSTREAM_RAW).hexdigest(), compat.BASE_SHA1)
        self.assertEqual(hashlib.sha256(UPSTREAM_RAW).hexdigest(), compat.BASE_SHA256)
        raw, spec = compat.derive_spec(UPSTREAM_RAW)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "45d556112cf6c80a3d4e624596f424724c168d5f91a6dc95de718eaecae1f972")
        expected = copy.deepcopy(self.base)
        expected["version"] = compat.COMPAT_VERSION
        for key in ("pod_target_xcconfig", "user_target_xcconfig"):
            expected[key][compat.ARCH_KEY] = "i386"
        self.assertEqual(spec, expected)
        self.assertEqual(spec["source"], self.base["source"])
        self.assertTrue(raw.endswith(b"}\n"))

    def test_preview_does_not_write(self):
        before = self.snapshot()
        result = self.register()
        self.assertEqual(result["mode"], "preview")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.calls, [compat.BASE_URL])
        self.assertFalse(self.target().parent.exists())

    def test_apply_preserves_base_and_notes_and_records_derived_provenance(self):
        original_base_record = copy.deepcopy(self.manifest["pods"][0]["versions"][0])
        self.register(apply=True)
        saved = json.loads(self.manifest_path.read_bytes())
        entry = saved["pods"][0]
        self.assertEqual(self.base_path.read_bytes(), UPSTREAM_RAW)
        self.assertEqual(entry["versions"][0], original_base_record)
        self.assertEqual(saved["notes"], self.manifest["notes"])
        self.assertEqual(entry["notes"], {"keep": True})
        self.assertEqual(entry["selected_version"], compat.COMPAT_VERSION)
        record = entry["versions"][1]
        self.assertEqual(record["publication_origin"], "oset_compatibility")
        self.assertEqual(record["origin_url_role"], "upstream_base_spec")
        self.assertEqual(record["upstream"]["sha256"], compat.BASE_SHA256)
        self.assertEqual(record["transform"]["changes"], compat.TRANSFORM["changes"])
        self.assertNotEqual(record["sha256"], record["upstream"]["sha256"])
        self.assertEqual(validate_specs.validate_repository(self.root)["specs"], 2)

    def test_apply_and_check_are_idempotent_and_check_is_offline(self):
        self.register(apply=True)
        before = self.snapshot()
        self.assertEqual(self.register(apply=True)["manifest_action"], "unchanged")
        with patch.object(compat, "fetch_bytes", side_effect=AssertionError("network forbidden")), \
                patch.object(compat, "compare_versions", side_effect=AssertionError("Ruby forbidden")):
            result = compat.check_repository(self.root)
        self.assertTrue(result["offline"])
        self.assertEqual(self.snapshot(), before)

    def test_changed_upstream_bytes_stop_before_any_apply(self):
        before = self.snapshot()
        with self.assertRaisesRegex(compat.SyncError, "pinned 4.3.3"):
            self.register(apply=True, fetcher=lambda url: UPSTREAM_RAW + b"\n")
        self.assertFalse(self.target().exists())
        self.assertEqual(self.manifest_path.read_bytes(), before["specs-manifest.json"])

    def test_local_base_cannot_differ_from_official_bytes(self):
        self.base_path.write_bytes(UPSTREAM_RAW + b"\n")
        with self.assertRaisesRegex(compat.SyncError, "different bytes"):
            self.register()

    def test_base_must_be_imported_and_correctly_recorded_first(self):
        self.manifest["pods"][0]["versions"][0]["sha256"] = "0" * 64
        self.save_manifest()
        with self.assertRaisesRegex(compat.SyncError, "base provenance"):
            self.register()

    def test_existing_compatibility_bytes_cannot_be_overwritten(self):
        self.register(apply=True)
        self.target().write_bytes(self.target().read_bytes() + b"\n")
        with self.assertRaisesRegex(compat.SyncError, "different bytes"):
            self.register()
        with self.assertRaisesRegex(compat.SyncError, "different bytes"):
            compat.check_repository(self.root)

    def test_extension_bypass_is_rejected(self):
        self.target().parent.mkdir(parents=True)
        self.target().with_suffix("").write_text("Pod::Spec.new {}")
        with self.assertRaisesRegex(compat.SyncError, "Existing version directory"):
            self.register()

    def test_compatibility_provenance_cannot_claim_original_upstream_bytes(self):
        self.register(apply=True)
        saved = json.loads(self.manifest_path.read_bytes())
        saved["pods"][0]["versions"][1]["publication_origin"] = "public_trunk"
        self.manifest_path.write_text(json.dumps(saved))
        with self.assertRaisesRegex(compat.SyncError, "provenance"):
            compat.check_repository(self.root)
        with self.assertRaisesRegex(compat.SyncError, "publication_origin"):
            self.register()

    def test_offline_check_rejects_extra_semantic_change_even_with_updated_hash(self):
        self.register(apply=True)
        spec = json.loads(self.target().read_bytes())
        spec["source"]["tag"] = "4.3.4"
        raw = json.dumps(spec).encode()
        self.target().write_bytes(raw)
        saved = json.loads(self.manifest_path.read_bytes())
        saved["pods"][0]["versions"][1].update(compat.hashes(raw))
        self.manifest_path.write_text(json.dumps(saved))
        with self.assertRaisesRegex(compat.SyncError, "different bytes"):
            compat.check_repository(self.root)

    def test_downgrade_is_rejected(self):
        self.manifest["pods"][0]["selected_version"] = "4.4.0"
        self.save_manifest()
        with self.assertRaisesRegex(compat.SyncError, "downgrade"):
            self.register()

    def test_symlink_version_directory_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.target().parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(compat.SyncError, "Symbolic links"):
            self.register()
        self.assertEqual(list(outside.iterdir()), [])

    def test_manifest_race_is_rejected_without_replacing_another_writer(self):
        raw, plan = compat.make_plan(self.root, UPSTREAM_RAW, self.compare)
        changed = self.manifest_path.read_bytes() + b"\n"
        self.manifest_path.write_bytes(changed)
        with self.assertRaisesRegex(compat.SyncError, "Manifest changed"):
            compat.apply_plan(self.root, raw, plan)
        self.assertEqual(self.manifest_path.read_bytes(), changed)
        self.assertFalse(self.target().parent.exists())

    def test_atomic_replace_failure_rolls_back_new_version(self):
        before = self.manifest_path.read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("injected replace failure")):
            with self.assertRaisesRegex(OSError, "injected replace"):
                self.register(apply=True)
        self.assertEqual(self.manifest_path.read_bytes(), before)
        self.assertFalse(self.target().parent.exists())
        self.assertEqual(list(self.root.glob(".specs-manifest-*")), [])


if __name__ == "__main__":
    unittest.main()
