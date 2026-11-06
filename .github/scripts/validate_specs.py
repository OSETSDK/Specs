#!/usr/bin/env python3
"""Validate the Specs working tree without downloads or CocoaPods.

--base-ref compares existing spec blobs in a Git commit with files currently on
disk. It works before a local commit, and against the checked-out PR merge tree
or push commit in CI. New version directories may be added; published bytes may
not be changed or removed, even if the manifest checksums are updated as well.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import urlsplit


class ValidationError(Exception):
    """A repository invariant was violated."""


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def safe_component(value, label):
    require(isinstance(value, str) and
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+\-]*", value) is not None,
            f"Unsafe {label}: {value!r}")
    return value


def safe_path(root, relative):
    require(isinstance(relative, str) and relative and "\\" not in relative,
            f"Unsafe relative path: {relative!r}")
    parts = PurePosixPath(relative)
    require(not parts.is_absolute() and
            all(part not in {".", ".."} for part in relative.split("/")) and
            str(parts) == relative,
            f"Unsafe relative path: {relative!r}")
    path = root
    for part in parts.parts:
        path = path / part
        require(not path.is_symlink(), f"Symlink is not allowed: {relative}")
    require(path.resolve().is_relative_to(root),
            f"Path escapes repository: {relative}")
    return path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValidationError(f"Invalid JSON constant: {value}")


def read_json(raw, label):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"Invalid JSON in {label}: {error}") from error


def git_output(root, *arguments):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(["git", "-C", str(root), *arguments],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=environment, check=False)
    require(result.returncode == 0,
            "Git baseline unavailable: " + result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def is_spec_file(path):
    return path.endswith(".podspec.json") or path.endswith(".podspec")


def check_immutable(root, base_ref):
    require(isinstance(base_ref, str) and
            re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", base_ref),
            "--base-ref must be a full Git commit SHA")
    git_output(root, "cat-file", "-e", base_ref + "^{commit}")
    count = 0
    for entry in git_output(root, "ls-tree", "-r", "-z", base_ref).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        relative = raw_path.decode("utf-8")
        if not is_spec_file(relative):
            continue
        mode, kind, object_id = metadata.decode("ascii").split()
        require(kind == "blob" and mode in {"100644", "100755"},
                f"Invalid baseline spec type: {relative}")
        path = safe_path(root, relative)
        require(path.is_file(), f"Published spec was deleted: {relative}")
        raw = path.read_bytes()
        algorithm = hashlib.sha1 if len(object_id) == 40 else hashlib.sha256
        digest = algorithm(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        require(digest == object_id,
                f"Published spec was changed: {relative}; add a new version instead")
        count += 1
    return count


def disk_specs(root):
    result = set()
    for directory, subdirectories, files in os.walk(root, followlinks=False):
        if Path(directory) == root:
            subdirectories[:] = [name for name in subdirectories if name != ".git"]
        for name in subdirectories:
            path = Path(directory) / name
            require(not path.is_symlink(),
                    f"Symlink directory is not allowed: {path.relative_to(root)}")
        for name in files:
            if is_spec_file(name):
                relative = (Path(directory) / name).relative_to(root).as_posix()
                require(not name.endswith(".podspec"),
                        f"Ruby podspec is not allowed: {relative}")
                safe_path(root, relative)
                result.add(relative)
    return result


def validate_repository(root, manifest_name="specs-manifest.json", base_ref=None):
    root = Path(root).resolve()
    manifest_path = safe_path(root, manifest_name)
    require(manifest_path.is_file(), f"Manifest is missing: {manifest_name}")
    manifest = read_json(manifest_path.read_bytes(), manifest_name)
    require(isinstance(manifest, dict), "Manifest must be a JSON object")
    require(type(manifest.get("schema_version")) is int and
            manifest["schema_version"] == 1, "Unsupported manifest schema_version")
    pods = manifest.get("pods")
    require(isinstance(pods, list), "Manifest pods must be a list")
    declared_paths = set()
    names = set()
    previous_order = 0
    for pod in pods:
        require(isinstance(pod, dict), "Each Pod entry must be an object")
        name = safe_component(pod.get("name"), "Pod name")
        require(name.casefold() not in names, f"Duplicate Pod name: {name}")
        names.add(name.casefold())
        order = pod.get("order")
        require(type(order) is int and order > previous_order,
                f"Pod order must be strictly increasing: {name}")
        previous_order = order
        versions = pod.get("versions")
        require(isinstance(versions, list) and versions,
                f"Pod versions must be a nonempty list: {name}")
        seen_versions = set()
        for record in versions:
            require(isinstance(record, dict), f"Invalid version entry: {name}")
            version = safe_component(record.get("version"), "version")
            require(version not in seen_versions, f"Duplicate version: {name} {version}")
            seen_versions.add(version)
            expected_path = f"{name}/{version}/{name}.podspec.json"
            relative = record.get("path")
            path = safe_path(root, relative)
            require(relative == expected_path,
                    f"Noncanonical spec path: {relative!r}; expected {expected_path}")
            require(relative not in declared_paths, f"Duplicate spec path: {relative}")
            declared_paths.add(relative)
            require(path.is_file(), f"Manifest spec is missing: {relative}")
            raw = path.read_bytes()
            for algorithm in ("sha1", "sha256"):
                digest = hashlib.new(algorithm, raw).hexdigest()
                require(record.get(algorithm) == digest,
                        f"{algorithm} mismatch: {relative}; preserve original bytes")
            spec = read_json(raw, relative)
            require(isinstance(spec, dict), f"Spec must be an object: {relative}")
            for key, expected in (("name", name), ("version", version)):
                require(spec.get(key) == expected,
                        f"Spec {key} mismatch: {relative}")
            require(isinstance(record.get("source"), dict) and record["source"] and
                    spec.get("source") == record["source"],
                    f"Spec source mismatch: {relative}")
            require(isinstance(record.get("dependencies"), dict) and
                    spec.get("dependencies", {}) == record["dependencies"],
                    f"Spec dependencies mismatch: {relative}")
            origin = record.get("origin_url")
            require(isinstance(origin, str), f"Missing origin_url: {relative}")
            parsed_origin = urlsplit(origin)
            require(parsed_origin.scheme == "https" and parsed_origin.netloc and
                    parsed_origin.username is None and parsed_origin.password is None,
                    f"origin_url must be HTTPS without credentials: {relative}")
        require(pod.get("selected_version") in seen_versions,
                f"selected_version is not recorded: {name}")
    actual_paths = disk_specs(root)
    require(actual_paths == declared_paths,
            "Spec inventory differs from manifest; unrecorded=" +
            repr(sorted(actual_paths - declared_paths)) + "; missing=" +
            repr(sorted(declared_paths - actual_paths)))
    immutable_count = check_immutable(root, base_ref) if base_ref else 0
    return {"pods": len(pods), "specs": len(declared_paths),
            "immutable_specs": immutable_count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", default="specs-manifest.json")
    parser.add_argument("--base-ref", help="Full Git SHA whose existing spec bytes must stay unchanged")
    options = parser.parse_args()
    try:
        result = validate_repository(options.root, options.manifest, options.base_ref)
    except (ValidationError, OSError, UnicodeDecodeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Validated {pods} Pods, {specs} checksummed JSON specs, "
          "{immutable_specs} immutable baseline specs.".format(**result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
