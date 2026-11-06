#!/usr/bin/env python3
"""Preview or register a specification published directly in an OSET delivery tag.

Reads OSETSDK/POD's VERSION tag and POD.podspec.json only; never queries Trunk.
Only --apply writes the independent Specs clone. It does not commit or push.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable
from urllib.parse import quote

from sync_public_spec import (
    SyncError, apply_plan, checked_path, checkout_lock, compare_versions,
    fetch_bytes, validate_identifiers, validate_source,
)
from validate_specs import ValidationError, read_json, safe_component


def delivery_repository(pod: str) -> str:
    return f"https://github.com/OSETSDK/{pod}.git"


def delivery_spec_url(pod: str, version: str) -> str:
    return (f"https://raw.githubusercontent.com/OSETSDK/{quote(pod, safe='')}/"
            f"{quote(version, safe='')}/{quote(pod, safe='')}.podspec.json")


def public_tag_sha(pod: str, version: str) -> str:
    reference = f"refs/tags/{version}"
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        result = subprocess.run(
            ["git", "-c", "credential.helper=", "ls-remote", "--exit-code", "--tags",
             delivery_repository(pod), reference, reference + "^{}"],
            capture_output=True, text=True, check=False, timeout=30, env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SyncError(f"Public delivery tag lookup failed: {error}") from error
    if result.returncode == 2:
        raise SyncError(f"Public delivery tag does not exist: {pod} {version}")
    if result.returncode:
        raise SyncError("Public delivery tag lookup failed: " + result.stderr.strip())
    refs = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) == 2:
            refs[fields[1]] = fields[0]
    if reference not in refs:
        raise SyncError(f"Public delivery tag does not exist: {pod} {version}")
    sha = refs.get(reference + "^{}", refs[reference])
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", sha):
        raise SyncError("Public delivery tag returned an invalid Git SHA")
    return sha


def parse_document(raw: bytes, label: str):
    try:
        return read_json(raw, label)
    except ValidationError as error:
        raise SyncError(str(error)) from error


def obtain_delivery_spec(pod, version, fetcher, tag_reader):
    tag_sha = tag_reader(pod, version)
    if not isinstance(tag_sha, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", tag_sha):
        raise SyncError("Public delivery tag returned an invalid Git SHA")
    origin = delivery_spec_url(pod, version)
    raw = fetcher(origin)
    spec = parse_document(raw, "Delivery Podspec")
    if not isinstance(spec, dict) or spec.get("name") != pod or spec.get("version") != version:
        raise SyncError("Delivery Podspec name/version does not match the requested Pod/version")
    source = spec.get("source")
    validate_source(source)
    if source.get("git") != delivery_repository(pod) or source.get("tag") != version:
        raise SyncError("Delivery source must use the matching OSETSDK repository and version tag")
    if any(key in source for key in ("branch", "commit", "http")):
        raise SyncError("Delivery source cannot include a conflicting branch, commit, or HTTP source")
    if not isinstance(spec.get("dependencies", {}), dict):
        raise SyncError("Delivery Podspec dependencies must be an object")
    if tag_reader(pod, version) != tag_sha:
        raise SyncError("Delivery tag changed while its Podspec was downloaded; retry after release settles")
    return raw, spec, origin, tag_sha


def make_plan(root, pod, version, raw, spec, origin, tag_sha, comparer):
    manifest_path = checked_path(root, "specs-manifest.json")
    if not manifest_path.is_file():
        raise SyncError("specs-manifest.json is required")
    original_manifest = manifest_path.read_bytes()
    manifest = parse_document(original_manifest, "Manifest")
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or
            manifest["schema_version"] != 1 or not isinstance(manifest.get("pods"), list)):
        raise SyncError("Unsupported specs-manifest.json schema")
    previous_order = 0
    seen = set()
    for entry in manifest["pods"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise SyncError("Manifest contains an invalid Pod entry")
        order = entry.get("order")
        if type(order) is not int or order <= previous_order or entry["name"].casefold() in seen:
            raise SyncError("Manifest Pod names must be unique and orders strictly increasing")
        seen.add(entry["name"].casefold())
        previous_order = order
    updated = copy.deepcopy(manifest)
    matches = [entry for entry in updated["pods"] if entry["name"].casefold() == pod.casefold()]
    new_pod = not matches
    if matches and matches[0]["name"] != pod:
        raise SyncError("Requested Pod spelling differs from the registered name")
    if new_pod:
        entry = {"name": pod, "order": previous_order + 1,
                 "modified_at": datetime.now(timezone.utc).isoformat(),
                 "selected_version": None, "publication_origin": "direct_delivery", "versions": []}
        updated["pods"].append(entry)
    else:
        entry = matches[0]
    selected = entry.get("selected_version")
    if selected is not None and (not isinstance(selected, str) or comparer(version, selected) < 0):
        raise SyncError(f"Refusing to downgrade selected_version from {selected} to {version}")
    versions = entry.get("versions")
    if not isinstance(versions, list) or any(not isinstance(item, dict) for item in versions):
        raise SyncError("Manifest versions must be an array of objects")
    existing = [item for item in versions if item.get("version") == version]
    if len(existing) > 1:
        raise SyncError("Manifest contains duplicate entries for this version")
    target = checked_path(root, pod, version, pod + ".podspec.json")
    if target.parent.exists():
        if (not target.parent.is_dir() or list(target.parent.iterdir()) != [target] or
                not target.is_file()):
            raise SyncError("Existing version directory must contain only the expected JSON file")
        if target.read_bytes() != raw:
            raise SyncError("Existing version has different bytes; same-version overwrites are forbidden")
        spec_action = "unchanged"
    else:
        spec_action = "create"
    record = {"version": version, "path": target.relative_to(root).as_posix(),
              "origin_url": origin, "sha1": hashlib.sha1(raw).hexdigest(),
              "sha256": hashlib.sha256(raw).hexdigest(), "source": spec["source"],
              "dependencies": spec.get("dependencies", {}), "delivery_tag_sha": tag_sha}
    if existing:
        saved = existing[0]
        for key in ("path", "sha1", "sha256", "source", "dependencies", "delivery_tag_sha"):
            if key in saved and saved[key] != record[key]:
                raise SyncError(f"Manifest {key} disagrees with delivery; refusing same-version change")
        # Preserve the original provenance and all user metadata for an existing version.
        for key, value in record.items():
            saved.setdefault(key, value)
    else:
        record["publication_origin"] = "direct_delivery"
        versions.append(record)
    entry["selected_version"] = version
    report = {"pod": pod, "version": version, "new_pod": new_pod,
              "spec_path": record["path"], "spec_action": spec_action,
              "manifest_action": "unchanged" if updated == manifest else "update",
              "selected_version_before": selected, "selected_version_after": version,
              "delivery_spec_url": origin, "delivery_tag_sha": tag_sha,
              "sha1": record["sha1"], "sha256": record["sha256"]}
    return report, target, manifest_path, original_manifest, updated


def register_delivery_spec(repo_root: Path, pod: str, version: str, apply: bool = False,
                           fetcher: Callable = fetch_bytes, tag_reader: Callable = public_tag_sha,
                           comparer: Callable = compare_versions):
    validate_identifiers(pod, version)
    try:
        safe_component(pod, "Pod name")
        safe_component(version, "version")
    except ValidationError as error:
        raise SyncError(str(error)) from error
    comparer(version, version)
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise SyncError("Repository root does not exist")
    raw, spec, origin, tag_sha = obtain_delivery_spec(pod, version, fetcher, tag_reader)
    if apply:
        with checkout_lock(root):
            plan = make_plan(root, pod, version, raw, spec, origin, tag_sha, comparer)
            apply_plan(root, raw, plan)
    else:
        plan = make_plan(root, pod, version, raw, spec, origin, tag_sha, comparer)
    return dict(plan[0], mode="apply" if apply else "preview", committed=False, pushed=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pod", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--apply", action="store_true", help="Write JSON and manifest; default is preview")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    options = parser.parse_args(argv)
    try:
        report = register_delivery_spec(options.repo_root, options.pod, options.version, options.apply)
    except (SyncError, OSError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
