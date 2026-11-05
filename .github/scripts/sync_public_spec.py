#!/usr/bin/env python3
"""Preview or import one already-published CocoaPods specification.

Only --apply writes files. It never commits, pushes, modifies the source SDK
repository, or changes CocoaPods configuration. Ruby's Gem::Version provides
the same version ordering used by CocoaPods. Apply uses a lock inside this
independent checkout's .git directory and supports macOS/Linux.
"""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


class SyncError(Exception):
    pass


NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.+-]*\Z")
VERSION_PATTERN = re.compile(r"[0-9][A-Za-z0-9.+-]*\Z")


def validate_identifiers(pod: str, version: str) -> None:
    if not isinstance(pod, str) or not NAME_PATTERN.fullmatch(pod):
        raise SyncError("Invalid Pod name; use one root Pod name without slashes or whitespace")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise SyncError("Invalid version; path separators and whitespace are forbidden")


def compare_versions(left: str, right: str) -> int:
    ruby = shutil.which("ruby")
    if not ruby:
        raise SyncError("Ruby is required to compare versions with Gem::Version")
    program = (
        "require 'rubygems'; begin; "
        "puts(Gem::Version.new(ARGV[0]) <=> Gem::Version.new(ARGV[1])); "
        "rescue ArgumentError => e; warn e.message; exit 2; end"
    )
    try:
        result = subprocess.run(
            [ruby, "-e", program, left, right], check=False,
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SyncError(f"Gem::Version comparison failed: {error}") from error
    if result.returncode or result.stdout.strip() not in {"-1", "0", "1"}:
        raise SyncError("Invalid CocoaPods version: " + result.stderr.strip())
    return int(result.stdout.strip())


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "OSETSpecs-Public-Sync/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise SyncError(f"Unable to download {url}: {error}") from error


def parse_json(raw: bytes, label: str):
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SyncError(f"{label} is not valid UTF-8 JSON") from error


def canonical_url(pod: str, version: str) -> str:
    digest = hashlib.md5(pod.encode("utf-8")).hexdigest()
    return (
        "https://raw.githubusercontent.com/CocoaPods/Specs/master/Specs/"
        f"{digest[0]}/{digest[1]}/{digest[2]}/"
        f"{quote(pod, safe='')}/{quote(version, safe='')}/{quote(pod, safe='')}.podspec.json"
    )


def validate_source(source) -> None:
    if not isinstance(source, dict) or not source:
        raise SyncError("The official specification has no valid source object")
    is_git = "git" in source
    if is_git:
        address = source["git"]
        if not isinstance(address, str) or not address:
            raise SyncError("The Git source URL must be a non-empty string")
        if not any(isinstance(source.get(key), str) and source[key] for key in ("tag", "commit")):
            raise SyncError("The Git source must identify a tag or commit")
        if address.startswith("git@") and ":" in address:
            return
    elif "http" in source:
        address = source["http"]
    else:
        raise SyncError("This sync tool supports Git tag/commit and HTTP artifact sources")
    if not isinstance(address, str):
        raise SyncError("The artifact source URL must be a string")
    parsed = urlparse(address)
    schemes = {"https", "http", "ssh", "git"} if is_git else {"https", "http"}
    if parsed.scheme not in schemes or not parsed.hostname:
        raise SyncError("The specification source URL is not a supported remote URL")
    if parsed.password or (parsed.username and parsed.scheme in {"https", "http"}):
        raise SyncError("Embedded HTTP credentials are not permitted in specification sources")


def obtain_official_spec(pod: str, version: str, fetcher: Callable[[str], bytes]):
    trunk_url = f"https://trunk.cocoapods.org/api/v1/pods/{quote(pod, safe='')}"
    trunk = parse_json(fetcher(trunk_url), "Trunk response")
    if not isinstance(trunk, dict) or not isinstance(trunk.get("versions"), list):
        raise SyncError("Trunk did not return a version list")
    published = {item.get("name") for item in trunk["versions"] if isinstance(item, dict)}
    if version not in published:
        raise SyncError(f"{pod} {version} is not published in official CocoaPods Trunk")
    origin = canonical_url(pod, version)
    raw = fetcher(origin)
    spec = parse_json(raw, "Official Podspec")
    if not isinstance(spec, dict) or spec.get("name") != pod or spec.get("version") != version:
        raise SyncError("Official Podspec name/version does not match the requested Pod/version")
    validate_source(spec.get("source"))
    return raw, spec, origin


def checked_path(root: Path, *components: str) -> Path:
    path = root
    for component in components:
        path = path / component
        if path.is_symlink():
            raise SyncError(f"Symbolic links are not allowed in sync paths: {path}")
    try:
        path.resolve().relative_to(root)
    except ValueError as error:
        raise SyncError("The sync path escapes the repository") from error
    return path


def make_plan(root: Path, pod: str, version: str, raw: bytes, spec: dict,
              origin: str, comparer: Callable[[str, str], int]):
    manifest_path = checked_path(root, "specs-manifest.json")
    if not manifest_path.is_file():
        raise SyncError("specs-manifest.json is required; register the maintained Pod before syncing")
    original_manifest = manifest_path.read_bytes()
    manifest = parse_json(original_manifest, "Manifest")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not isinstance(manifest.get("pods"), list):
        raise SyncError("Unsupported specs-manifest.json schema")
    matches = [entry for entry in manifest["pods"] if isinstance(entry, dict) and entry.get("name") == pod]
    if len(matches) != 1:
        raise SyncError(f"Register exactly one manifest entry for {pod} before syncing")
    entry = matches[0]
    selected = entry.get("selected_version")
    if selected is not None:
        if not isinstance(selected, str):
            raise SyncError("Manifest selected_version must be a string or null")
        if comparer(version, selected) < 0:
            raise SyncError(f"Refusing to downgrade selected_version from {selected} to {version}")
    versions = entry.get("versions")
    if not isinstance(versions, list) or any(not isinstance(item, dict) for item in versions):
        raise SyncError("Manifest versions must be an array of objects")
    existing_entries = [item for item in versions if item.get("version") == version]
    if len(existing_entries) > 1:
        raise SyncError("Manifest contains duplicate entries for this version")
    target = checked_path(root, pod, version, pod + ".podspec.json")
    version_dir = target.parent
    if version_dir.exists():
        if not version_dir.is_dir():
            raise SyncError(f"Version path is not a directory: {version_dir}")
        contents = list(version_dir.iterdir())
        if len(contents) != 1 or contents[0] != target or not target.is_file():
            raise SyncError("Existing version directory is not exactly the expected JSON file; refusing overwrite")
        if target.read_bytes() != raw:
            raise SyncError("Existing version has different bytes; same-version overwrites are forbidden")
        spec_action = "unchanged"
    else:
        spec_action = "create"
    record = {
        "version": version,
        "path": target.relative_to(root).as_posix(),
        "origin_url": origin,
        "sha1": hashlib.sha1(raw).hexdigest(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source": spec["source"],
        "dependencies": spec.get("dependencies", {}),
    }
    if existing_entries:
        existing = existing_entries[0]
        for key in ("sha1", "sha256"):
            if existing.get(key) is not None and existing[key] != record[key]:
                raise SyncError(f"Manifest {key} disagrees with official bytes; refusing same-version change")
    updated = copy.deepcopy(manifest)
    updated_entry = next(item for item in updated["pods"] if isinstance(item, dict) and item.get("name") == pod)
    if existing_entries:
        index = next(index for index, item in enumerate(updated_entry["versions"]) if item.get("version") == version)
        updated_entry["versions"][index].update(record)
    else:
        updated_entry["versions"].append(record)
    updated_entry["selected_version"] = version
    manifest_action = "unchanged" if updated == manifest else "update"
    report = {
        "pod": pod, "version": version, "spec_path": record["path"],
        "spec_action": spec_action, "manifest_action": manifest_action,
        "selected_version_before": selected, "selected_version_after": version,
        "origin_url": origin, "sha1": record["sha1"], "sha256": record["sha256"],
        "source": record["source"], "dependencies": record["dependencies"],
    }
    return report, target, manifest_path, original_manifest, updated


@contextmanager
def checkout_lock(root: Path):
    git_dir = checked_path(root, ".git")
    if not git_dir.is_dir():
        raise SyncError("--apply requires an independent Git clone with its own .git directory")
    try:
        import fcntl
    except ImportError as error:
        raise SyncError("--apply locking currently supports macOS/Linux") from error
    lock_path = checked_path(root, ".git", "oset-specs-sync.lock")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def apply_plan(root: Path, raw: bytes, plan) -> None:
    report, target, manifest_path, original_manifest, updated = plan
    if report["spec_action"] == "unchanged" and report["manifest_action"] == "unchanged":
        return
    manifest_tmp = None
    created = False
    try:
        if report["manifest_action"] == "update":
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".specs-manifest-", dir=root, delete=False) as temporary:
                manifest_tmp = Path(temporary.name)
                temporary.write((json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        if manifest_path.read_bytes() != original_manifest:
            raise SyncError("Manifest changed during sync; retry after the other writer completes")
        if report["spec_action"] == "create":
            target.parent.parent.mkdir(exist_ok=True)
            target.parent.mkdir(exist_ok=False)
            created = True
            with target.open("xb") as destination:
                destination.write(raw)
        if manifest_tmp is not None:
            manifest_tmp.replace(manifest_path)
            manifest_tmp = None
    except BaseException:
        if created:
            if target.is_file() and target.read_bytes() == raw:
                target.unlink()
            if target.parent.exists() and not any(target.parent.iterdir()):
                target.parent.rmdir()
        raise
    finally:
        if manifest_tmp is not None:
            manifest_tmp.unlink(missing_ok=True)


def synchronize(repo_root: Path, pod: str, version: str, apply: bool = False,
                fetcher: Callable[[str], bytes] = fetch_bytes,
                comparer: Callable[[str, str], int] = compare_versions) -> dict:
    validate_identifiers(pod, version)
    comparer(version, version)
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise SyncError("Repository root does not exist")
    raw, spec, origin = obtain_official_spec(pod, version, fetcher)
    if apply:
        with checkout_lock(root):
            plan = make_plan(root, pod, version, raw, spec, origin, comparer)
            apply_plan(root, raw, plan)
    else:
        plan = make_plan(root, pod, version, raw, spec, origin, comparer)
    return dict(plan[0], mode="apply" if apply else "preview", committed=False, pushed=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pod", required=True, help="Root Pod name already registered in specs-manifest.json")
    parser.add_argument("--version", required=True, help="Exact official Trunk version")
    parser.add_argument("--apply", action="store_true", help="Write specification and manifest; default is read-only preview")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    try:
        report = synchronize(args.repo_root, args.pod, args.version, args.apply)
    except (SyncError, OSError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
