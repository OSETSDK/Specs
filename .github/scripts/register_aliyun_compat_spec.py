#!/usr/bin/env python3
"""Register one OSET-maintained Aliyun 4.3.3 arm64-simulator metadata revision.

Default: read-only preview. --apply adds version 4.3.3.1 in this Specs clone.
--check is offline and checks the original base, exact derived bytes and ledger
provenance. Neither mode changes upstream source, existing versions or Git refs.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

from sync_public_spec import (
    SyncError, apply_plan, checked_path, checkout_lock, compare_versions, fetch_bytes,
)
from validate_specs import ValidationError, read_json


POD = "AliyunLogProducer"
BASE_VERSION = "4.3.3"
COMPAT_VERSION = "4.3.3.1"
BASE_URL = ("https://raw.githubusercontent.com/CocoaPods/Specs/master/Specs/b/b/4/"
            "AliyunLogProducer/4.3.3/AliyunLogProducer.podspec.json")
BASE_SHA1 = "889e71ee9e0fd0e49c03097dd806196549f8a873"
BASE_SHA256 = "5f8213a56e124d2d8a289ac42609bdd02b823ac4c3b88137d259adfed4e1b269"
SOURCE_TAG_SHA = "9f12d40a8bda23d0775963401e29d6a2954c7e51"
ARCH_KEY = "EXCLUDED_ARCHS[sdk=iphonesimulator*]"
TRANSFORM = {
    "id": "aliyun-4.3.3-arm64-simulator-v1",
    "changes": [
        {"path": ["version"], "from": BASE_VERSION, "to": COMPAT_VERSION},
        {"path": ["pod_target_xcconfig", ARCH_KEY], "from": "arm64 i386", "to": "i386"},
        {"path": ["user_target_xcconfig", ARCH_KEY], "from": "arm64 i386", "to": "i386"},
    ],
}


def document(raw, label):
    try:
        return read_json(raw, label)
    except ValidationError as error:
        raise SyncError(str(error)) from error


def hashes(raw):
    return {"sha1": hashlib.sha1(raw).hexdigest(), "sha256": hashlib.sha256(raw).hexdigest()}


def spec_path(root, version):
    return checked_path(root, POD, version, POD + ".podspec.json")


def check_version_directory(path, expected, required):
    if not path.parent.exists():
        if required:
            raise SyncError(f"Required specification is missing: {path}")
        return "create"
    if not path.parent.is_dir() or list(path.parent.iterdir()) != [path] or not path.is_file():
        raise SyncError("Existing version directory must contain only its expected JSON file")
    if path.read_bytes() != expected:
        raise SyncError(f"Existing version has different bytes; refusing overwrite: {path}")
    return "unchanged"


def derive_spec(base_raw):
    if hashes(base_raw) != {"sha1": BASE_SHA1, "sha256": BASE_SHA256}:
        raise SyncError("Upstream base bytes do not match the pinned 4.3.3 SHA1/SHA256")
    old_version = b'"version": "4.3.3"'
    old_arch = b'"EXCLUDED_ARCHS[sdk=iphonesimulator*]": "arm64 i386"'
    if base_raw.count(old_version) != 1 or base_raw.count(old_arch) != 2:
        raise SyncError("Pinned base does not have the expected three replacement fields")
    raw = base_raw.replace(old_version, b'"version": "4.3.3.1"', 1)
    raw = raw.replace(old_arch, b'"EXCLUDED_ARCHS[sdk=iphonesimulator*]": "i386"')
    base = document(base_raw, "Upstream base")
    derived = document(raw, "Derived specification")
    allowed = copy.deepcopy(base)
    for change in TRANSFORM["changes"]:
        container = allowed
        for key in change["path"][:-1]:
            container = container[key]
        leaf = change["path"][-1]
        if container[leaf] != change["from"]:
            raise SyncError("Upstream base differs from the limited transform contract")
        container[leaf] = change["to"]
    if derived != allowed or derived.get("name") != POD or derived.get("version") != COMPAT_VERSION:
        raise SyncError("Derived specification contains changes outside the three allowed fields")
    return raw, derived


def expected_record(raw, spec):
    return {
        "version": COMPAT_VERSION,
        "path": f"{POD}/{COMPAT_VERSION}/{POD}.podspec.json",
        "origin_url": BASE_URL,
        "origin_url_role": "upstream_base_spec",
        "publication_origin": "oset_compatibility",
        **hashes(raw),
        "source": spec["source"],
        "dependencies": spec.get("dependencies", {}),
        "upstream": {"name": POD, "version": BASE_VERSION, "origin_url": BASE_URL,
                     "sha1": BASE_SHA1, "sha256": BASE_SHA256,
                     "source_tag_sha": SOURCE_TAG_SHA},
        "transform": copy.deepcopy(TRANSFORM),
    }


def ledger(root, base_raw):
    path = checked_path(root, "specs-manifest.json")
    if not path.is_file():
        raise SyncError("specs-manifest.json is required")
    original = path.read_bytes()
    manifest = document(original, "Manifest")
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or
            manifest["schema_version"] != 1 or not isinstance(manifest.get("pods"), list)):
        raise SyncError("Unsupported specs-manifest.json schema")
    matches = [entry for entry in manifest["pods"] if isinstance(entry, dict) and entry.get("name") == POD]
    if len(matches) != 1:
        raise SyncError("Import and register the official AliyunLogProducer 4.3.3 base first")
    entry = matches[0]
    versions = entry.get("versions")
    if not isinstance(versions, list) or any(not isinstance(item, dict) for item in versions):
        raise SyncError("Manifest versions must be an array of objects")
    bases = [item for item in versions if item.get("version") == BASE_VERSION]
    base_spec = document(base_raw, "Upstream base")
    base_expected = {"version": BASE_VERSION, "path": f"{POD}/{BASE_VERSION}/{POD}.podspec.json",
                     "origin_url": BASE_URL, "sha1": BASE_SHA1, "sha256": BASE_SHA256,
                     "source": base_spec["source"], "dependencies": base_spec.get("dependencies", {})}
    if len(bases) != 1 or any(bases[0].get(key) != value for key, value in base_expected.items()):
        raise SyncError("Official base provenance is missing or does not match the pinned original")
    return path, original, manifest, entry


def make_plan(root, base_raw, comparer=compare_versions):
    raw, spec = derive_spec(base_raw)
    check_version_directory(spec_path(root, BASE_VERSION), base_raw, required=True)
    path, original, manifest, entry = ledger(root, base_raw)
    selected = entry.get("selected_version")
    if not isinstance(selected, str) or comparer(COMPAT_VERSION, selected) < 0:
        raise SyncError(f"Refusing to downgrade selected_version from {selected} to {COMPAT_VERSION}")
    target = spec_path(root, COMPAT_VERSION)
    action = check_version_directory(target, raw, required=False)
    updated = copy.deepcopy(manifest)
    new_entry = next(item for item in updated["pods"] if item.get("name") == POD)
    matches = [item for item in new_entry["versions"] if item.get("version") == COMPAT_VERSION]
    if len(matches) > 1:
        raise SyncError("Manifest contains duplicate compatibility version entries")
    record = expected_record(raw, spec)
    if matches:
        saved = matches[0]
        for key, value in record.items():
            if key in saved and saved[key] != value:
                raise SyncError(f"Compatibility provenance disagrees at {key}; refusing same-version change")
            saved.setdefault(key, value)
    else:
        new_entry["versions"].append(record)
    new_entry["selected_version"] = COMPAT_VERSION
    report = {"pod": POD, "version": COMPAT_VERSION, "spec_path": record["path"],
              "spec_action": action, "manifest_action": "unchanged" if updated == manifest else "update",
              "publication_origin": "oset_compatibility", "origin_url": BASE_URL,
              "origin_url_role": "upstream_base_spec", **hashes(raw)}
    return raw, (report, target, path, original, updated)


def check_repository(repo_root):
    root = Path(repo_root).resolve()
    base_path = spec_path(root, BASE_VERSION)
    if not base_path.is_file():
        raise SyncError("Official base JSON must be present for offline --check")
    base_raw = base_path.read_bytes()
    raw, spec = derive_spec(base_raw)
    check_version_directory(base_path, base_raw, required=True)
    check_version_directory(spec_path(root, COMPAT_VERSION), raw, required=True)
    _path, _original, _manifest, entry = ledger(root, base_raw)
    records = [item for item in entry["versions"] if item.get("version") == COMPAT_VERSION]
    if len(records) != 1 or any(records[0].get(key) != value for key, value in expected_record(raw, spec).items()):
        raise SyncError("Compatibility manifest provenance does not match the fixed upstream transform")
    if entry.get("selected_version") not in {item.get("version") for item in entry["versions"]}:
        raise SyncError("Manifest selected_version is not recorded")
    return {"mode": "check", "pod": POD, "version": COMPAT_VERSION,
            "publication_origin": "oset_compatibility", "origin_url_role": "upstream_base_spec",
            "offline": True, **hashes(raw), "committed": False, "pushed": False}


def register_compat_spec(repo_root, apply=False, fetcher=fetch_bytes, comparer=compare_versions):
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise SyncError("Repository root does not exist")
    base_raw = fetcher(BASE_URL)
    if apply:
        with checkout_lock(root):
            raw, plan = make_plan(root, base_raw, comparer)
            apply_plan(root, raw, plan)
    else:
        _raw, plan = make_plan(root, base_raw, comparer)
    return dict(plan[0], mode="apply" if apply else "preview", committed=False, pushed=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--check", action="store_true", help="Offline byte/provenance validation; no downloads")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    options = parser.parse_args(argv)
    try:
        report = check_repository(options.repo_root) if options.check else register_compat_spec(options.repo_root, options.apply)
    except (SyncError, OSError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
