"""Fail-closed local preparation for an authorized, human-annotated OCR pilot."""

from __future__ import annotations

import hashlib
import json
import os
import re
import resource
import shutil
import stat
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from av_atlas.adapters import AdapterContext
from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError
from av_atlas.io import canonical_json, sha256_file, write_jsonl
from av_atlas.media import inspect_media
from av_atlas.native_media import NativeInputPolicy, enforce_path_policy, policy_from_inventory
from av_atlas.native_process import (
    PROFILE_SHA256,
    PROFILE_VERSION,
    BubblewrapNativeRunner,
    NativeInvocation,
    NativeTool,
    ReadOnlyBind,
    WritableDirectory,
    load_bubblewrap_inventory,
    reject_exposed_host_path,
    run_hostile_sandbox_probes,
)
from av_atlas.ocr import TesseractOcrAdapter, inspect_ocr, sanitize_ocr_inventory
from av_atlas.pilot_ocr_output import (
    DEPENDENCY_FILENAME,
    EVIDENCE_FILENAME,
    OBSERVATIONS_FILENAME,
    OUTPUT_MANIFEST_FILENAME,
    RUNTIME_FILENAME,
    build_pilot_ocr_output_binding,
    build_pilot_ocr_output_manifest,
    output_binding_sha256,
    validate_pilot_ocr_output_package,
)
from av_atlas.pilot_security import (
    VerifiedPilotRoot,
    VerifiedRetainedRoot,
    ensure_pilot_security_execution_boundary,
    load_bound_json,
    load_pilot_security_policy,
    make_security_receipt,
    native_limits_from_policy,
    open_retained_output_directory,
    open_verified_pilot_root,
    open_verified_retained_root,
    private_pilot_workspace,
    receipt_capability,
    retained_output_directory,
    source_rights_aggregate,
    validate_security_receipt,
    verified_retained_storage_binding,
    verify_sandbox_policy,
)
from av_atlas.rights import manifest_digest as rights_manifest_digest
from av_atlas.rights import validate_rights
from av_atlas.schemas import validate_instance
from av_atlas.stable_input import (
    StableInputPolicy,
    acquire_authorized_input,
    preflight_authorized_source,
)

REQUIRED_PILOT_OPERATIONS = (
    "analysis",
    "annotation",
    "evaluation",
    "derivative_artifact_retention",
)
_PRIVATE_TEXT_PATTERN = re.compile(
    r"(?:^|\s)(?:/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_. -]+)+|[A-Za-z]:[\\/])"
    r"|(?:ghp_|github_pat_|AKIA)[A-Za-z0-9_+-]{8,}"
    r"|(?:password|api[_-]?key|access[_-]?token|secret)\s*[:=]",
    re.IGNORECASE,
)
_MAX_RETAINED_JSON_BYTES = 64 * 1024 * 1024
_MAX_PRIVATE_PACKAGE_ENTRIES = 16_384
_MAX_PRIVATE_PACKAGE_DEPTH = 12


def _digest(value: dict[str, Any], field: str = "manifest_hash") -> str:
    payload = {key: item for key, item in value.items() if key != field}
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value, _ = load_bound_json(path, maximum_bytes=_MAX_RETAINED_JSON_BYTES)
    return value


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return "".join(canonical_json(record) + "\n" for record in records).encode("utf-8")


def _retained_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _retained_directory_identity(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid)


@dataclass(frozen=True)
class _PinnedDirectoryComponent:
    name: str
    descriptor: int
    identity: tuple[int, ...]


@dataclass(frozen=True)
class _PinnedRetainedJson:
    """One stably read retained JSON file held by descriptor for an operation."""

    root: VerifiedRetainedRoot
    directories: tuple[_PinnedDirectoryComponent, ...]
    basename: str
    descriptor: int
    identity: tuple[int, ...]
    value: dict[str, Any]
    sha256: str
    size_bytes: int

    @property
    def anchored_path(self) -> Path:
        return Path(f"/proc/self/fd/{self.descriptor}")

    def verify(self) -> None:
        self.root.verify()
        uid = os.geteuid() if hasattr(os, "geteuid") else None
        parent_descriptor = self.root.descriptor
        for component in self.directories:
            try:
                opened = os.fstat(component.descriptor)
                current = os.stat(
                    component.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise AtlasError("retained pilot input directory identity changed") from exc
            if (
                _retained_directory_identity(opened) != component.identity
                or _retained_directory_identity(current) != component.identity
                or not stat.S_ISDIR(opened.st_mode)
                or stat.S_IMODE(opened.st_mode) != 0o700
                or (uid is not None and opened.st_uid != uid)
            ):
                raise AtlasError("retained pilot input directory identity changed")
            parent_descriptor = component.descriptor
        try:
            opened_file = os.fstat(self.descriptor)
            current_file = os.stat(
                self.basename,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise AtlasError("retained pilot JSON input identity changed") from exc
        if (
            _retained_identity(opened_file) != self.identity
            or _retained_identity(current_file) != self.identity
            or not stat.S_ISREG(opened_file.st_mode)
            or stat.S_IMODE(opened_file.st_mode) != 0o600
            or opened_file.st_nlink != 1
            or (uid is not None and opened_file.st_uid != uid)
        ):
            raise AtlasError("retained pilot JSON input identity changed")


@contextmanager
def _open_pinned_retained_json(
    root: VerifiedRetainedRoot,
    path: Path,
    *,
    label: str,
    maximum_bytes: int = _MAX_RETAINED_JSON_BYTES,
) -> Iterator[_PinnedRetainedJson]:
    """Open, stably read, and retain every path component beneath the policy root."""
    reject_exposed_host_path(path, label=label)
    root.verify()
    if not path.is_absolute():
        raise AtlasError(f"{label} must be an absolute retained-artifact path")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise AtlasError(f"{label} is unavailable") from exc
    if path != resolved or not resolved.is_relative_to(root.path):
        raise AtlasError(f"{label} must be canonical and inside policy-bound retained storage")
    relative = resolved.relative_to(root.path)
    if not relative.parts or len(relative.parts) > _MAX_PRIVATE_PACKAGE_DEPTH:
        raise AtlasError(f"{label} has an unsupported retained-artifact depth")
    directory_descriptors: list[int] = []
    components: list[_PinnedDirectoryComponent] = []
    file_descriptor: int | None = None
    parent_descriptor = root.descriptor
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    try:
        for name in relative.parts[:-1]:
            descriptor = os.open(name, directory_flags, dir_fd=parent_descriptor)
            directory_descriptors.append(descriptor)
            opened = os.fstat(descriptor)
            current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            identity = _retained_directory_identity(opened)
            if (
                _retained_directory_identity(current) != identity
                or not stat.S_ISDIR(opened.st_mode)
                or stat.S_IMODE(opened.st_mode) != 0o700
                or (uid is not None and opened.st_uid != uid)
            ):
                raise AtlasError(f"{label} has an unsafe retained directory component")
            components.append(_PinnedDirectoryComponent(name, descriptor, identity))
            parent_descriptor = descriptor
        basename = relative.parts[-1]
        file_descriptor = os.open(basename, file_flags, dir_fd=parent_descriptor)
        opened_file = os.fstat(file_descriptor)
        current_file = os.stat(basename, dir_fd=parent_descriptor, follow_symlinks=False)
        identity = _retained_identity(opened_file)
        if (
            _retained_identity(current_file) != identity
            or not stat.S_ISREG(opened_file.st_mode)
            or stat.S_IMODE(opened_file.st_mode) != 0o600
            or opened_file.st_nlink != 1
            or (uid is not None and opened_file.st_uid != uid)
        ):
            raise AtlasError(f"{label} must be a private regular file with one link")
        if opened_file.st_size <= 0 or opened_file.st_size > maximum_bytes:
            raise AtlasError(f"{label} exceeds its bounded JSON input size")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(file_descriptor, min(1024 * 1024, maximum_bytes - total + 1))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > maximum_bytes:
                raise AtlasError(f"{label} exceeds its bounded JSON input size")
        after = os.fstat(file_descriptor)
        current_after = os.stat(basename, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            _retained_identity(after) != identity
            or _retained_identity(current_after) != identity
            or total != opened_file.st_size
        ):
            raise AtlasError(f"{label} changed during its bounded read")
        raw = b"".join(chunks)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AtlasError(f"{label} is not valid UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise AtlasError(f"{label} must contain a JSON object")
        pinned = _PinnedRetainedJson(
            root=root,
            directories=tuple(components),
            basename=basename,
            descriptor=file_descriptor,
            identity=identity,
            value=value,
            sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=total,
        )
        pinned.verify()
        yield pinned
        pinned.verify()
    except OSError as exc:
        raise AtlasError(f"{label} could not be opened descriptor-relatively") from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor in reversed(directory_descriptors):
            os.close(descriptor)


@dataclass(frozen=True)
class _PinnedPrivateDirectory:
    parent: Any
    name: str
    descriptor: int
    identity: tuple[int, ...]

    @property
    def parent_descriptor(self) -> int:
        return int(self.parent.descriptor)

    @property
    def descriptor_path(self) -> Path:
        return Path(f"/proc/self/fd/{self.descriptor}")

    def verify(self) -> None:
        self.parent.verify()
        try:
            opened = os.fstat(self.descriptor)
            current = os.stat(self.name, dir_fd=self.parent_descriptor, follow_symlinks=False)
        except OSError as exc:
            raise AtlasError("private annotation package identity changed") from exc
        uid = os.geteuid() if hasattr(os, "geteuid") else None
        if (
            _retained_directory_identity(opened) != self.identity
            or _retained_directory_identity(current) != self.identity
            or not stat.S_ISDIR(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o700
            or (uid is not None and opened.st_uid != uid)
        ):
            raise AtlasError("private annotation package identity changed")


def _remove_private_package_tree(
    descriptor: int,
    *,
    depth: int = 0,
    budget: list[int] | None = None,
) -> int:
    if depth > _MAX_PRIVATE_PACKAGE_DEPTH:
        raise AtlasError("private annotation package cleanup exceeded its depth bound")
    if budget is None:
        budget = [0]
    with os.scandir(descriptor) as iterator:
        entries = sorted(iterator, key=lambda item: item.name)
    for entry in entries:
        budget[0] += 1
        if budget[0] > _MAX_PRIVATE_PACKAGE_ENTRIES:
            raise AtlasError("private annotation package cleanup exceeded its entry bound")
        value = os.stat(entry.name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISDIR(value.st_mode):
            child = os.open(
                entry.name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            try:
                _remove_private_package_tree(child, depth=depth + 1, budget=budget)
            finally:
                os.close(child)
            os.rmdir(entry.name, dir_fd=descriptor)
        elif stat.S_ISREG(value.st_mode) or stat.S_ISLNK(value.st_mode):
            os.unlink(entry.name, dir_fd=descriptor)
        else:
            raise AtlasError("private annotation package contains an unsupported special file")
    os.fsync(descriptor)
    return budget[0]


def _find_child_by_identity(parent_descriptor: int, identity: tuple[int, ...]) -> str | None:
    with os.scandir(parent_descriptor) as iterator:
        entries = sorted(iterator, key=lambda item: item.name)
    if len(entries) > _MAX_PRIVATE_PACKAGE_ENTRIES:
        raise AtlasError("private annotation package parent scan exceeded its bound")
    expected = identity[:2]
    for entry in entries:
        value = os.stat(entry.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (value.st_dev, value.st_ino) == expected:
            return entry.name
    return None


@contextmanager
def _create_pinned_private_directory(
    retained_output: Any,
    parent: Any,
    name: str,
) -> Iterator[_PinnedPrivateDirectory]:
    """Create one exact private child under the retained-root transaction."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name):
        raise AtlasError("private annotation package name is invalid")
    parent_descriptor = int(parent.descriptor)
    descriptor: int | None = None
    lease: _PinnedPrivateDirectory | None = None
    directory_created = False
    created_identity: tuple[int, ...] | None = None
    placement_committed = False
    committed = False
    cleanup_succeeded = True
    try:
        with retained_output.serialized_mutation():
            try:
                aggregate_before = retained_output.root.measure_aggregate_bytes()
                parent.verify()
                try:
                    os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise AtlasError(
                        "private annotation package path could not be checked"
                    ) from exc
                else:
                    raise AtlasError(f"annotation package already exists: {name}")
                os.mkdir(name, 0o700, dir_fd=parent_descriptor)
                directory_created = True
                created = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
                created_identity = _retained_directory_identity(created)
                os.fsync(parent_descriptor)
                descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=parent_descriptor,
                )
                opened = os.fstat(descriptor)
                if _retained_directory_identity(opened) != created_identity:
                    raise AtlasError("private annotation package changed while opening")
                lease = _PinnedPrivateDirectory(
                    parent,
                    name,
                    descriptor,
                    created_identity,
                )
                os.fchmod(descriptor, 0o700)
                lease.verify()
                if retained_output.root.measure_aggregate_bytes() != aggregate_before:
                    raise AtlasError("retained bytes appeared during nested directory placement")
                os.fsync(descriptor)
                os.fsync(parent_descriptor)
                retained_output.verify()
                placement_committed = True
            except BaseException as placement_error:
                rollback_succeeded = True
                try:
                    if lease is not None:
                        _remove_private_package_tree(lease.descriptor)
                        actual_name = _find_child_by_identity(parent_descriptor, lease.identity)
                        if actual_name is None:
                            rollback_succeeded = False
                        else:
                            os.rmdir(actual_name, dir_fd=parent_descriptor)
                            os.fsync(parent_descriptor)
                    elif directory_created:
                        current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
                        current_identity = _retained_directory_identity(current)
                        if created_identity is not None and current_identity != created_identity:
                            rollback_succeeded = False
                        else:
                            os.rmdir(name, dir_fd=parent_descriptor)
                            os.fsync(parent_descriptor)
                except (AtlasError, OSError):
                    rollback_succeeded = False
                lease = None
                created_identity = None
                if not rollback_succeeded:
                    raise AtlasError(
                        "private annotation package placement rollback failed"
                    ) from placement_error
                raise
        if lease is None:
            raise AtlasError("private annotation package placement did not produce a lease")
        yield lease
        with retained_output.serialized_mutation():
            lease.verify()
            os.fsync(descriptor)
            os.fsync(parent_descriptor)
        committed = True
    finally:
        if placement_committed and not committed and lease is not None:
            try:
                with retained_output.serialized_mutation():
                    _remove_private_package_tree(lease.descriptor)
                    actual_name = _find_child_by_identity(parent_descriptor, lease.identity)
                    if actual_name is None:
                        cleanup_succeeded = False
                    else:
                        os.rmdir(actual_name, dir_fd=parent_descriptor)
                        os.fsync(parent_descriptor)
            except (AtlasError, OSError):
                cleanup_succeeded = False
        elif placement_committed and not committed and created_identity is not None:
            try:
                with retained_output.serialized_mutation():
                    current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
                    if _retained_directory_identity(current) != created_identity:
                        cleanup_succeeded = False
                    else:
                        os.rmdir(name, dir_fd=parent_descriptor)
                        os.fsync(parent_descriptor)
            except (AtlasError, OSError):
                cleanup_succeeded = False
        if descriptor is not None:
            os.close(descriptor)
        if not committed and not cleanup_succeeded:
            raise AtlasError("private annotation package cleanup failed")


def _write_pinned_package_bytes(
    retained_output: Any,
    package: _PinnedPrivateDirectory,
    *,
    name: str,
    temporary_name: str,
    value: bytes,
) -> None:
    """Place one JSON file directly in a nested transactional destination."""
    del temporary_name
    retained_output.write_bounded_bytes_to(package, name, value)


def _safe_pilot_artifact_path(
    pilot_dir: Path,
    relative_value: str,
    *,
    parent: str,
    basename: str | None = None,
) -> Path:
    """Resolve one schema-bound pilot artifact without accepting links or traversal."""
    if not isinstance(relative_value, str) or "\\" in relative_value or "\x00" in relative_value:
        raise AtlasError("pilot artifact path is malformed")
    relative = PurePosixPath(relative_value)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) != 2
        or relative.parts[0] != parent
        or (basename is not None and relative.parts[1] != basename)
    ):
        raise AtlasError("pilot artifact path escapes its fixed private package directory")
    try:
        descriptor_root = pilot_dir.parent == Path("/proc/self/fd") and pilot_dir.name.isdigit()
        root_stat = os.stat(pilot_dir) if descriptor_root else os.lstat(pilot_dir)
        parent_path = pilot_dir / parent
        parent_stat = os.lstat(parent_path)
        candidate = parent_path / relative.parts[1]
        candidate_stat = os.lstat(candidate)
    except OSError as exc:
        raise AtlasError("pilot artifact path does not resolve to a bounded regular file") from exc
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or not stat.S_ISDIR(parent_stat.st_mode)
        or not stat.S_ISREG(candidate_stat.st_mode)
    ):
        raise AtlasError("pilot artifact path contains a symlink or non-regular component")
    return candidate


def _require_retained_artifact(
    root: VerifiedRetainedRoot,
    path: Path,
    *,
    label: str,
    allow_new_direct_child: bool = False,
) -> None:
    """Reject public-checkout, exposed-runtime, and out-of-policy retained paths."""
    reject_exposed_host_path(path, label=label)
    root.verify()
    try:
        if allow_new_direct_child:
            if path.exists() or path.parent.resolve(strict=True) != root.path:
                raise AtlasError(f"{label} must be a new direct child of retained storage")
        elif not path.resolve(strict=True).is_relative_to(root.path):
            raise AtlasError(f"{label} must be inside policy-bound retained storage")
    except OSError as exc:
        raise AtlasError(f"{label} could not be resolved safely") from exc


def _validate_public_pilot_metadata(value: dict[str, Any], policy: dict[str, Any] | None) -> None:
    selected: list[str] = []
    protocol = value.get("selection_protocol")
    if isinstance(protocol, dict):
        for field in (
            "method",
            "duplicate_frame_policy",
            "inclusion_criteria",
            "exclusion_criteria",
        ):
            item = protocol.get(field)
            if isinstance(item, str):
                selected.append(item)
            elif isinstance(item, list):
                selected.extend(value for value in item if isinstance(value, str))
    for frame in value.get("frames", []):
        if isinstance(frame, dict):
            for field in ("categories", "difficulty"):
                item = frame.get(field)
                if isinstance(item, list):
                    selected.extend(item)
    selected = [item for item in selected if isinstance(item, str)]
    private_values = {str(Path.home())}
    if policy is not None:
        private_values.add(str(policy["private_root"]["path"]))
        if "retained_root" in policy:
            private_values.add(str(policy["retained_root"]["path"]))
    if any(
        _PRIVATE_TEXT_PATTERN.search(item)
        or any(private and private in item for private in private_values)
        for item in selected
    ):
        raise AtlasError("pilot public metadata contains a private path or secret-like value")


def _validate_sandboxed_pilot_manifest(
    pilot_dir: Path,
    value: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> None:
    """Validate schema plus source/frame/path relations for current pilot execution."""
    version = value.get("schema_version")
    if version not in {"1.1.0", "1.2.0"}:
        raise AtlasError("sandboxed pilot validation requires manifest contract 1.1.0 or 1.2.0")
    if policy is not None and version != "1.2.0":
        raise AtlasError("new pilot execution requires pilot manifest contract 1.2.0")
    validate_instance("ocr_pilot_manifest", value, "sandboxed pilot manifest")
    sources = value["sources"]
    frames = value["frames"]
    source_ids = [item["source_id"] for item in sources]
    if len(source_ids) != len(set(source_ids)) or value["counts"]["sources"] != len(sources):
        raise AtlasError("pilot source identities or declared source count are inconsistent")
    durations = {item["source_id"]: item["duration_ms"] for item in sources}
    for source in sources:
        _safe_pilot_artifact_path(
            pilot_dir,
            source["rights_manifest"],
            parent="rights",
            basename=f"{source['source_id']}.rights.json",
        )
    frame_ids = [item["frame_id"] for item in frames]
    if len(frame_ids) != len(set(frame_ids)):
        raise AtlasError("pilot frame identities must be unique")
    for frame in frames:
        source_id = frame["source_id"]
        if source_id not in durations or frame["timestamp_ms"] >= durations[source_id]:
            raise AtlasError("pilot frame source or timestamp relation is invalid")
        _safe_pilot_artifact_path(
            pilot_dir,
            frame["path"],
            parent="frames",
            basename=f"{frame['frame_id']}.png",
        )
    calibration = sum(item["split"] == "calibration" for item in frames)
    evaluation = sum(item["split"] == "evaluation" for item in frames)
    if (calibration, evaluation) != (20, 60):
        raise AtlasError("pilot frame split does not match the declared 20/60 contract")
    _validate_public_pilot_metadata(value, policy)


def _runner_for_policy(
    policy: dict[str, Any],
    root: VerifiedPilotRoot | None = None,
    retained_root: VerifiedRetainedRoot | None = None,
) -> tuple[BubblewrapNativeRunner, dict[str, Any]]:
    if root is not None:
        ensure_pilot_security_execution_boundary(policy, root)
    if retained_root is not None:
        retained_root.verify()
    sandbox = policy["sandbox"]
    if (
        sandbox["provider"] != "bubblewrap"
        or sandbox["profile_contract_version"] != PROFILE_VERSION
        or sandbox["profile_sha256"] != PROFILE_SHA256
    ):
        raise AtlasError("pilot sandbox profile differs from the compiled reviewed contract")
    inventory = load_bubblewrap_inventory(
        expected_executable_sha256=str(sandbox["executable_sha256"]),
        expected_executable_size_bytes=int(sandbox["executable_size_bytes"]),
    )
    if root is not None:
        ensure_pilot_security_execution_boundary(policy, root)
    if retained_root is not None:
        retained_root.verify()
    public_inventory = inventory.as_record()
    verify_sandbox_policy(policy, public_inventory)

    def before_run() -> None:
        if root is not None:
            ensure_pilot_security_execution_boundary(policy, root)
        if retained_root is not None:
            retained_root.verify()

    return (
        BubblewrapNativeRunner(
            inventory,
            native_limits_from_policy(policy),
            before_run=before_run if root is not None or retained_root is not None else None,
        ),
        public_inventory,
    )


def validate_current_pilot_sandbox(policy: dict[str, Any]) -> dict[str, Any]:
    """Recheck the policy-approved executable and capability without pilot media access."""
    _, inventory = _runner_for_policy(policy)
    return inventory


def _source_set_digest(records: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        canonical_json(
            sorted((item["source_id"], item["source_sha256"]) for item in records)
        ).encode()
    ).hexdigest()


def _security_block(
    receipt: dict[str, Any], receipt_sha256: str, source_set_sha256: str
) -> dict[str, Any]:
    sandbox = receipt["sandbox"]
    return {
        "policy_sha256": receipt["policy_sha256"],
        "receipt_path": "pilot_security_receipt.json",
        "receipt_sha256": receipt_sha256,
        "receipt_stage": "prepared",
        "pilot_spec_sha256": receipt["pilot_spec_sha256"],
        "pilot_spec_size_bytes": receipt["pilot_spec_size_bytes"],
        "source_set_sha256": source_set_sha256,
        "source_rights_aggregate_sha256": receipt["source_rights_aggregate_sha256"],
        "root_identity_sha256": receipt["root_identity_sha256"],
        "filesystem_type": receipt["filesystem_type"],
        "storage_decision": receipt["storage"]["decision"],
        "retained_storage": receipt["retained_storage"],
        "sandbox": {
            "provider": "bubblewrap",
            "profile_contract_version": sandbox["profile_contract_version"],
            "profile_sha256": sandbox["profile_sha256"],
            "dependency_identity_sha256": sandbox["dependency_identity_sha256"],
            "capability_smoke_test_passed": sandbox["capability_smoke_test_passed"],
            "exposed_host_subtrees": sandbox["exposed_host_subtrees"],
            "masked_host_subtrees": sandbox["masked_host_subtrees"],
        },
        "resource_limits": receipt["resource_limits"],
        "capability": receipt["capability"],
        "lifecycle": receipt["lifecycle"],
        "privacy": receipt["privacy"],
    }


def _copy_verified_file(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
    expected_size: int | None = None,
) -> int:
    """Copy one immutable regular file without following either final path."""
    source_fd: int | None = None
    destination_fd: int | None = None
    destination_identity: tuple[int, int] | None = None
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)

    def remove_created_destination() -> None:
        if destination_identity is None:
            return
        try:
            current_destination = os.lstat(destination)
            if (current_destination.st_dev, current_destination.st_ino) == destination_identity:
                destination.unlink()
        except OSError:
            pass

    try:
        before = os.lstat(source)
        if not stat.S_ISREG(before.st_mode):
            raise AtlasError("pilot derivative source must be a regular non-symlink file")
        source_fd = os.open(source, flags)
        opened = os.fstat(source_fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise AtlasError("pilot derivative source identity changed while opening")
        if expected_size is not None and opened.st_size != expected_size:
            raise AtlasError("pilot derivative source size differs from its frozen identity")
        destination_fd = os.open(
            destination,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.fchmod(destination_fd, 0o600)
        opened_destination = os.fstat(destination_fd)
        destination_identity = (opened_destination.st_dev, opened_destination.st_ino)
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            total += len(block)
            digest.update(block)
            offset = 0
            while offset < len(block):
                written = os.write(destination_fd, block[offset:])
                if written <= 0:
                    raise AtlasError("pilot derivative copy made no write progress")
                offset += written
        os.fsync(destination_fd)
        after = os.fstat(source_fd)
        current = os.lstat(source)
        identity = {
            (
                value.st_dev,
                value.st_ino,
                value.st_mode,
                value.st_uid,
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
            )
            for value in (before, opened, after, current)
        }
        if len(identity) != 1:
            raise AtlasError("pilot derivative source changed during its bounded copy")
        if digest.hexdigest() != expected_sha256:
            raise AtlasError("pilot derivative source hash differs from its frozen identity")
        if expected_size is not None and total != expected_size:
            raise AtlasError("pilot derivative copy size differs from its frozen identity")
        completed_destination = os.fstat(destination_fd)
        visible_destination = os.lstat(destination)
        if (
            (completed_destination.st_dev, completed_destination.st_ino) != destination_identity
            or (visible_destination.st_dev, visible_destination.st_ino) != destination_identity
            or not stat.S_ISREG(completed_destination.st_mode)
            or stat.S_IMODE(completed_destination.st_mode) != 0o600
            or completed_destination.st_nlink != 1
            or completed_destination.st_size != total
        ):
            raise AtlasError("pilot derivative destination changed during its bounded copy")
        return total
    except OSError as exc:
        remove_created_destination()
        raise AtlasError("pilot derivative could not be copied safely") from exc
    except BaseException:
        remove_created_destination()
        raise
    finally:
        if destination_fd is not None:
            os.close(destination_fd)
        if source_fd is not None:
            os.close(source_fd)


def _extract_frame(
    media: Path,
    timestamp_ms: int,
    output: Path,
    native_policy: NativeInputPolicy,
    *,
    native_runner: BubblewrapNativeRunner | None = None,
    expected_source_sha256: str | None = None,
    expected_source_size: int | None = None,
) -> None:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise AtlasError("ffmpeg is required for pilot frame extraction")
    enforce_path_policy(media, native_policy)
    if native_runner is None:
        raise AtlasError("pilot frame extraction requires the mandatory sandbox runner")
    source_argument = Path("/input/source")
    output_argument = Path("/work") / output.name
    arguments = [
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        *native_policy.arguments(source_argument, seek_ms=timestamp_ms),
        "-frames:v",
        "1",
        "-compression_level",
        "9",
        "-y",
        str(output_argument),
    ]
    try:
        if expected_source_sha256 is None or expected_source_size is None:
            raise AtlasError("sandboxed frame extraction requires exact source identity")
        native_runner.run(
            NativeInvocation(
                NativeTool.FFMPEG,
                tuple(arguments),
                WritableDirectory.measure(output.parent),
                (
                    ReadOnlyBind.measure_file(
                        media,
                        "/input/source",
                        expected_size=expected_source_size,
                        expected_sha256=expected_source_sha256,
                    ),
                ),
                private_paths=(media, output.parent),
            )
        )
    except AtlasError:
        output.unlink(missing_ok=True)
        raise
    except OSError as exc:
        output.unlink(missing_ok=True)
        raise AtlasError("pilot frame extraction could not start safely") from exc
    if not output.is_file() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        raise AtlasError(f"empty extracted frame at {timestamp_ms}ms")
    output.chmod(0o600)


def prepare_pilot(
    spec_path: Path,
    output: Path,
    security_policy_path: Path | None = None,
) -> dict[str, Any]:
    """Authorize, snapshot, sandbox, and extract exactly 20/60 locked frames."""
    reject_exposed_host_path(spec_path, label="pilot specification")
    spec, spec_identity = load_bound_json(spec_path)
    expected = {
        "schema_version",
        "pilot_id",
        "selection_method",
        "random_seed",
        "inclusion_criteria",
        "exclusion_criteria",
        "duplicate_frame_policy",
        "sources",
    }
    if set(spec) != expected or spec.get("schema_version") != "1.0.0":
        raise AtlasError("pilot specification has unknown, missing, or unsupported fields")
    if security_policy_path is None:
        raise AtlasError("pilot preparation requires an explicit private security policy")
    policy = load_pilot_security_policy(
        security_policy_path,
        pilot_id=str(spec.get("pilot_id", "")),
        pilot_spec_identity=spec_identity,
    )
    stable_policy = StableInputPolicy(
        max_source_bytes=int(policy["capacity"]["source_byte_ceiling"]),
        max_temporary_bytes=int(policy["capacity"]["temporary_byte_ceiling"]),
    )
    sources = spec.get("sources")
    if not isinstance(sources, list) or len(sources) < 3:
        raise AtlasError("pilot requires at least three distinct authorized sources")
    # Authorize every source parser-free before any source reaches FFprobe. A
    # denied later source therefore cannot cause earlier media to be parsed.
    preflight_sources: list[tuple[dict[str, Any], str, str, str]] = []
    preflight_ids: set[str] = set()
    split_counts = {"calibration": 0, "evaluation": 0}
    for source in sources:
        if not isinstance(source, dict) or set(source) != {
            "media_path",
            "rights_manifest_path",
            "selections",
        }:
            raise AtlasError(
                "each source must contain only media_path, rights_manifest_path, selections"
            )
        if not isinstance(source["selections"], list):
            raise AtlasError("pilot source selections must be an array")
        reject_exposed_host_path(Path(source["media_path"]), label="pilot source media")
        reject_exposed_host_path(
            Path(source["rights_manifest_path"]), label="pilot source rights declaration"
        )
        seen_source_timestamps: set[int] = set()
        for selection in source["selections"]:
            required = {"timestamp_ms", "split", "categories", "difficulty"}
            if not isinstance(selection, dict) or set(selection) != required:
                raise AtlasError("each frame selection has unknown or missing fields")
            timestamp_ms = selection["timestamp_ms"]
            if (
                not isinstance(timestamp_ms, int)
                or isinstance(timestamp_ms, bool)
                or timestamp_ms < 0
            ):
                raise AtlasError("selected timestamp must be a nonnegative integer")
            split = selection["split"]
            if split not in split_counts:
                raise AtlasError("frame split must be calibration or evaluation")
            if timestamp_ms in seen_source_timestamps:
                raise AtlasError("duplicate timestamp within one pilot source is not permitted")
            seen_source_timestamps.add(timestamp_ms)
            split_counts[split] += 1
        measurement = preflight_authorized_source(
            Path(source["media_path"]),
            Path(source["rights_manifest_path"]),
            "evaluation",
            policy=stable_policy,
            additional_permissions=("annotation",),
        )
        if measurement.source_id in preflight_ids:
            raise AtlasError("pilot sources must be content-distinct")
        preflight_ids.add(measurement.source_id)
        preflight_sources.append(
            (
                source,
                measurement.source_sha256,
                measurement.source_id,
                str(measurement.authorization.rights_declaration["manifest_hash"]),
            )
        )
    if split_counts != {"calibration": 20, "evaluation": 60}:
        raise AtlasError(
            "pilot requires exactly 20 calibration and 60 evaluation frames; "
            f"got {split_counts['calibration']}/{split_counts['evaluation']}"
        )
    source_records: list[dict[str, Any]] = []
    frame_records: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    seen_frames: set[tuple[str, int]] = set()
    resources = ExitStack()
    try:
        root = resources.enter_context(open_verified_pilot_root(policy))
        retained_root = resources.enter_context(open_verified_retained_root(policy))
        output_lease = resources.enter_context(
            retained_output_directory(policy, retained_root, output)
        )
        retained_output = output_lease.descriptor_path
        runner, sandbox_inventory = _runner_for_policy(policy, root, retained_root)
        output_lease.verify()
        retained_root.verify()
        with private_pilot_workspace(policy, root) as probe_workspace:
            hostile = run_hostile_sandbox_probes(
                runner,
                WritableDirectory.measure(probe_workspace.path),
                spec_path,
            )
        capability = receipt_capability(sandbox_inventory, hostile)
        ensure_pilot_security_execution_boundary(policy, root)
        retained_root.verify()
        frames_package = resources.enter_context(
            _create_pinned_private_directory(output_lease, output_lease, "frames")
        )
        rights_package = resources.enter_context(
            _create_pinned_private_directory(output_lease, output_lease, "rights")
        )
        for (
            source,
            expected_hash,
            expected_source_id,
            expected_manifest_hash,
        ) in preflight_sources:
            ensure_pilot_security_execution_boundary(policy, root)
            retained_root.verify()
            media = Path(source["media_path"])
            with (
                acquire_authorized_input(
                    media,
                    Path(source["rights_manifest_path"]),
                    "evaluation",
                    policy=stable_policy,
                    verified_private_root=root.stable_input_binding(),
                    expected_source_sha256=expected_hash,
                    expected_source_id=expected_source_id,
                    expected_manifest_hash=expected_manifest_hash,
                    additional_permissions=("annotation",),
                ) as stable,
                private_pilot_workspace(policy, root) as work,
            ):
                inventory = inspect_media(
                    stable.snapshot_path,
                    native_runner=runner,
                    sandbox_work_directory=work.path,
                    expected_source_sha256=stable.source_sha256,
                    expected_source_size=stable.size_bytes,
                )
                if (
                    inventory["sha256"] != stable.source_sha256
                    or inventory["source_id"] != stable.source_id
                ):
                    raise AtlasError("pilot snapshot inventory identity mismatch")
                if inventory["source_id"] in seen_sources:
                    raise AtlasError("pilot sources must be content-distinct")
                seen_sources.add(inventory["source_id"])
                rights = stable.authorization.rights_declaration
                native_policy = policy_from_inventory(inventory)
                for operation in REQUIRED_PILOT_OPERATIONS:
                    validate_rights(
                        rights,
                        inventory["sha256"],
                        inventory["source_id"],
                        operation,
                    )
                rights_name = f"{inventory['source_id']}.rights.json"
                ensure_pilot_security_execution_boundary(policy, root)
                output_lease.verify()
                rights_bytes = _json_bytes(rights)
                _write_pinned_package_bytes(
                    output_lease,
                    rights_package,
                    name=rights_name,
                    temporary_name=f"{inventory['source_id']}.rights.pending.json",
                    value=rights_bytes,
                )
                source_records.append(
                    {
                        "source_id": inventory["source_id"],
                        "source_sha256": inventory["sha256"],
                        "duration_ms": inventory["duration_ms"],
                        "rights_manifest": f"rights/{rights_name}",
                        "rights_manifest_sha256": hashlib.sha256(rights_bytes).hexdigest(),
                        "rights_manifest_hash": rights["manifest_hash"],
                    }
                )
                for selection in source["selections"]:
                    timestamp_ms = selection["timestamp_ms"]
                    if not 0 <= timestamp_ms < inventory["duration_ms"]:
                        raise AtlasError("selected timestamp is outside its source")
                    split = selection["split"]
                    key = (inventory["source_id"], timestamp_ms)
                    if key in seen_frames:
                        raise AtlasError("duplicate source/timestamp selection is not permitted")
                    seen_frames.add(key)
                    frame_id = f"FRM_{inventory['sha256'][:12].upper()}_{timestamp_ms:010d}"
                    relative = f"frames/{frame_id}.png"
                    private_frame = work.path / f"{frame_id}.png"
                    _extract_frame(
                        stable.snapshot_path,
                        timestamp_ms,
                        private_frame,
                        native_policy,
                        native_runner=runner,
                        expected_source_sha256=stable.source_sha256,
                        expected_source_size=stable.size_bytes,
                    )
                    ensure_pilot_security_execution_boundary(policy, root)
                    output_lease.verify()
                    frame_hash = sha256_file(private_frame)
                    frame_size = private_frame.stat().st_size
                    output_lease.copy_bounded_file_to(
                        frames_package,
                        f"{frame_id}.png",
                        private_frame,
                        expected_sha256=frame_hash,
                        expected_size=frame_size,
                    )
                    frames_package.verify()
                    frame_records.append(
                        {
                            "frame_id": frame_id,
                            "source_id": inventory["source_id"],
                            "timestamp_ms": timestamp_ms,
                            "split": split,
                            "categories": selection["categories"],
                            "difficulty": selection["difficulty"],
                            "path": relative,
                            "sha256": frame_hash,
                            "size_bytes": frame_size,
                        }
                    )
        security_receipt = make_security_receipt(
            policy=policy,
            root=root,
            retained_root=retained_root,
            stage="prepared",
            source_rights_aggregate_sha256=source_rights_aggregate(source_records),
            sandbox_inventory=sandbox_inventory,
            capability=capability,
            cleanup_succeeded=True,
        )
        ensure_pilot_security_execution_boundary(policy, root)
        output_lease.verify()
        security_receipt_bytes = _json_bytes(security_receipt)
        output_lease.write_bounded_bytes(
            "pilot_security_receipt.json",
            security_receipt_bytes,
        )
        calibration = sum(frame["split"] == "calibration" for frame in frame_records)
        evaluation = sum(frame["split"] == "evaluation" for frame in frame_records)
        if (calibration, evaluation) != (20, 60):
            raise AtlasError(
                "pilot requires exactly 20 calibration and 60 evaluation frames; "
                f"got {calibration}/{evaluation}"
            )
        value: dict[str, Any] = {
            "schema_version": "1.2.0",
            "pilot_id": spec["pilot_id"],
            "state": "prepared_unannotated",
            "selection_protocol": {
                "method": spec["selection_method"],
                "random_seed": spec["random_seed"],
                "inclusion_criteria": spec["inclusion_criteria"],
                "exclusion_criteria": spec["exclusion_criteria"],
                "duplicate_frame_policy": spec["duplicate_frame_policy"],
            },
            "sources": sorted(source_records, key=lambda item: item["source_id"]),
            "frames": sorted(
                frame_records, key=lambda item: (item["source_id"], item["timestamp_ms"])
            ),
            "counts": {
                "sources": len(source_records),
                "calibration_frames": 20,
                "evaluation_frames": 60,
            },
            "privacy": {
                "source_media_copied": False,
                "source_ids_hash_derived": True,
                "absolute_paths_exported": False,
                "legal_determination": False,
            },
            "pilot_security": _security_block(
                security_receipt,
                hashlib.sha256(security_receipt_bytes).hexdigest(),
                _source_set_digest(source_records),
            ),
            "manifest_hash": "",
        }
        value["manifest_hash"] = _digest(value)
        _validate_sandboxed_pilot_manifest(retained_output, value, policy)
        ensure_pilot_security_execution_boundary(policy, root)
        output_lease.verify()
        output_lease.write_bounded_bytes("pilot_manifest.json", _json_bytes(value))
        frames_package.verify()
        rights_package.verify()
        output_lease.verify()
        resources.close()
        return value
    except BaseException as exc:
        resources.__exit__(type(exc), exc, exc.__traceback__)
        raise


def _blank_annotation_frame(frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "frame_id": frame["frame_id"],
        "source_id": frame["source_id"],
        "timestamp_ms": frame["timestamp_ms"],
        "exact_transcription": None,
        "normalized_transcription": None,
        "regions": [],
        "ignore_regions": [],
        "language": None,
        "legibility": None,
        "uncertain": None,
        "occluded": None,
        "truncated": None,
        "notes": None,
    }


def _blank_annotation_template(
    manifest: dict[str, Any], label: str, records: list[dict[str, Any]]
) -> dict[str, Any]:
    template = {
        "schema_version": "1.0.0",
        "pilot_id": manifest["pilot_id"],
        "annotator_pseudonym": f"ANNOTATOR_{label}",
        "annotation_timestamp": None,
        "independence_attestation": False,
        "frames": records,
    }
    validate_instance("ocr_human_annotation", template, f"annotator {label} template")
    return template


def make_annotation_packages(pilot_dir: Path, security_policy_path: Path | None = None) -> None:
    if security_policy_path is None:
        raise AtlasError("annotation packages require an explicit private security policy")
    policy = load_pilot_security_policy(security_policy_path)
    resources = ExitStack()
    input_resources = ExitStack()
    package_root = pilot_dir
    try:
        package_lease = None
        retained_root = resources.enter_context(open_verified_retained_root(policy))
        package_lease = resources.enter_context(
            open_retained_output_directory(policy, retained_root, pilot_dir)
        )
        package_root = package_lease.descriptor_path
        pinned_manifest = input_resources.enter_context(
            _open_pinned_retained_json(
                retained_root,
                pilot_dir / "pilot_manifest.json",
                label="prepared pilot manifest",
            )
        )
        manifest = pinned_manifest.value
        if manifest.get("schema_version") != "1.2.0":
            raise AtlasError(
                "new annotation-package execution requires pilot manifest contract 1.2.0"
            )
        _validate_sandboxed_pilot_manifest(package_root, manifest, policy)
        _validate_pilot_security_linkage(
            package_root,
            manifest,
            policy,
            retained_root=retained_root,
        )
        validate_instance("ocr_pilot_manifest", manifest, "pilot manifest")
        if manifest["state"] != "prepared_unannotated" or manifest["manifest_hash"] != _digest(
            manifest
        ):
            raise AtlasError("annotation packages require an intact prepared pilot")
        frames = [frame for frame in manifest["frames"] if frame["split"] == "evaluation"]
        for label in ("A", "B"):
            package = resources.enter_context(
                _create_pinned_private_directory(
                    package_lease,
                    package_lease,
                    f"annotator_{label}",
                )
            )
            frame_package = resources.enter_context(
                _create_pinned_private_directory(package_lease, package, "frames")
            )
            records = []
            for frame in frames:
                frame_source = _safe_pilot_artifact_path(
                    package_root,
                    str(frame["path"]),
                    parent="frames",
                    basename=f"{frame['frame_id']}.png",
                )
                frame_size = int(frame["size_bytes"])
                package_lease.copy_bounded_file_to(
                    frame_package,
                    Path(frame["path"]).name,
                    frame_source,
                    expected_sha256=str(frame["sha256"]),
                    expected_size=frame_size,
                )
                records.append(_blank_annotation_frame(frame))
            template = _blank_annotation_template(manifest, label, records)
            _write_pinned_package_bytes(
                package_lease,
                package,
                name="annotation.json",
                temporary_name=f"annotation-{label}.pending.json",
                value=_json_bytes(template),
            )
            frame_package.verify()
            package.verify()
        package_lease.verify()
        input_resources.close()
        resources.close()
    except BaseException as exc:
        try:
            input_resources.__exit__(type(exc), exc, exc.__traceback__)
        finally:
            resources.__exit__(type(exc), exc, exc.__traceback__)
        raise


def _annotation_comparison_report(
    manifest: dict[str, Any],
    annotations: list[dict[str, Any]],
    annotation_hashes: list[str],
) -> dict[str, Any]:
    for index, value in enumerate(annotations):
        validate_instance("ocr_human_annotation", value, f"annotation {index + 1}")
        if value["pilot_id"] != manifest["pilot_id"] or not value["independence_attestation"]:
            raise AtlasError("annotation is for another pilot or lacks independence attestation")
        if value["annotation_timestamp"] is None or any(
            frame["exact_transcription"] is None or frame["normalized_transcription"] is None
            for frame in value["frames"]
        ):
            raise AtlasError("both human annotation packages must be complete")
    if annotations[0]["annotator_pseudonym"] == annotations[1]["annotator_pseudonym"]:
        raise AtlasError("two distinct annotator pseudonyms are required")
    by_second = {frame["frame_id"]: frame for frame in annotations[1]["frames"]}
    disagreements = []
    char_edits = 0
    char_total = 0
    region_matches = 0
    region_first = 0
    region_second = 0
    for frame in annotations[0]["frames"]:
        other = by_second.get(frame["frame_id"])
        if other is None:
            raise AtlasError("annotation frame sets differ")
        differing = [
            field for field in frame if field != "frame_id" and frame[field] != other[field]
        ]
        if differing:
            disagreements.append({"frame_id": frame["frame_id"], "differing_fields": differing})
        first_text = str(frame["normalized_transcription"])
        second_text = str(other["normalized_transcription"])
        char_edits += _distance(list(first_text), list(second_text))
        char_total += len(first_text)
        first_regions = [_box(region) for region in frame["regions"]]
        second_regions = [_box(region) for region in other["regions"]]
        region_first += len(first_regions)
        region_second += len(second_regions)
        candidates = sorted(
            (
                _iou(left, right),
                left_index,
                right_index,
            )
            for left_index, left in enumerate(first_regions)
            if left is not None
            for right_index, right in enumerate(second_regions)
            if right is not None
        )
        used_left: set[int] = set()
        used_right: set[int] = set()
        for overlap, left_index, right_index in reversed(candidates):
            if overlap < 0.5 or left_index in used_left or right_index in used_right:
                continue
            used_left.add(left_index)
            used_right.add(right_index)
            region_matches += 1
    report = {
        "schema_version": "1.0.0",
        "pilot_id": manifest["pilot_id"],
        "annotation_sha256": annotation_hashes,
        "annotators": [item["annotator_pseudonym"] for item in annotations],
        "agreement_frames": 60 - len(disagreements),
        "disagreement_frames": len(disagreements),
        "disagreements": disagreements,
        "adjudication_required": bool(disagreements),
        "inter_annotator": {
            "exact_frame_agreement": _ratio(60 - len(disagreements), 60),
            "normalized_character_disagreement_rate": _ratio(char_edits, char_total),
            "region_precision_a_to_b": _ratio(region_matches, region_first),
            "region_recall_a_to_b": _ratio(region_matches, region_second),
            "region_matching_threshold_iou": 0.5,
        },
    }
    return report


def compare_annotations(
    pilot_dir: Path,
    first: Path,
    second: Path,
    output: Path | None,
    security_policy_path: Path | None = None,
) -> dict[str, Any]:
    if security_policy_path is None:
        raise AtlasError("annotation comparison requires an explicit private security policy")
    policy = load_pilot_security_policy(security_policy_path)
    resources = ExitStack()
    input_resources = ExitStack()
    try:
        retained_root = resources.enter_context(open_verified_retained_root(policy))
        pilot_lease = resources.enter_context(
            open_retained_output_directory(policy, retained_root, pilot_dir)
        )
        manifest_pin = input_resources.enter_context(
            _open_pinned_retained_json(
                retained_root,
                pilot_dir / "pilot_manifest.json",
                label="prepared pilot manifest",
            )
        )
        first_pin = input_resources.enter_context(
            _open_pinned_retained_json(retained_root, first, label="first human annotation")
        )
        second_pin = input_resources.enter_context(
            _open_pinned_retained_json(retained_root, second, label="second human annotation")
        )
        manifest = manifest_pin.value
        if manifest.get("schema_version") != "1.2.0":
            raise AtlasError(
                "new annotation-comparison execution requires pilot manifest contract 1.2.0"
            )
        _validate_sandboxed_pilot_manifest(pilot_lease.descriptor_path, manifest, policy)
        _validate_pilot_security_linkage(
            pilot_lease.descriptor_path,
            manifest,
            policy,
            retained_root=retained_root,
        )
        report = _annotation_comparison_report(
            manifest,
            [first_pin.value, second_pin.value],
            [first_pin.sha256, second_pin.sha256],
        )
        if output is not None:
            output_lease = resources.enter_context(
                retained_output_directory(policy, retained_root, output)
            )
            output_lease.write_bounded_bytes("disagreement_report.json", _json_bytes(report))
            output_lease.verify()
        input_resources.close()
        resources.close()
        return report
    except BaseException as exc:
        try:
            input_resources.__exit__(type(exc), exc, exc.__traceback__)
        finally:
            resources.__exit__(type(exc), exc, exc.__traceback__)
        raise


def freeze_pilot(
    pilot_dir: Path,
    first: Path,
    second: Path,
    adjudicated: Path,
    output: Path,
    security_policy_path: Path | None = None,
) -> dict[str, Any]:
    if security_policy_path is None:
        raise AtlasError("pilot freeze requires an explicit private security policy")
    policy = load_pilot_security_policy(security_policy_path)
    resources = ExitStack()
    input_resources = ExitStack()
    try:
        retained_root = resources.enter_context(open_verified_retained_root(policy))
        pilot_lease = resources.enter_context(
            open_retained_output_directory(policy, retained_root, pilot_dir)
        )
        manifest_pin = input_resources.enter_context(
            _open_pinned_retained_json(
                retained_root,
                pilot_dir / "pilot_manifest.json",
                label="prepared pilot manifest",
            )
        )
        first_pin = input_resources.enter_context(
            _open_pinned_retained_json(retained_root, first, label="first human annotation")
        )
        second_pin = input_resources.enter_context(
            _open_pinned_retained_json(retained_root, second, label="second human annotation")
        )
        gold_pin = input_resources.enter_context(
            _open_pinned_retained_json(retained_root, adjudicated, label="adjudicated gold")
        )
        manifest = manifest_pin.value
        if manifest.get("schema_version") != "1.2.0":
            raise AtlasError("new pilot-freeze execution requires pilot manifest contract 1.2.0")
        _validate_sandboxed_pilot_manifest(pilot_lease.descriptor_path, manifest, policy)
        _validate_pilot_security_linkage(
            pilot_lease.descriptor_path,
            manifest,
            policy,
            retained_root=retained_root,
        )
        report = _annotation_comparison_report(
            manifest,
            [first_pin.value, second_pin.value],
            [first_pin.sha256, second_pin.sha256],
        )
        gold = gold_pin.value
        validate_instance("ocr_human_annotation", gold, "adjudicated gold")
        if gold["pilot_id"] != manifest["pilot_id"] or gold["annotation_timestamp"] is None:
            raise AtlasError("adjudicated gold is incomplete or belongs to another pilot")
        if any(frame["exact_transcription"] is None for frame in gold["frames"]):
            raise AtlasError("adjudicated gold contains incomplete frames")
        disagreement_bytes = _json_bytes(report)
        frozen = {
            **manifest,
            "state": "adjudicated_frozen",
            "human_annotation_sha256": [first_pin.sha256, second_pin.sha256],
            "adjudicated_gold_sha256": gold_pin.sha256,
            "disagreement_report_sha256": hashlib.sha256(disagreement_bytes).hexdigest(),
            "normalization_rules_sha256": sha256_file(
                Path(__file__).with_name("ocr_evaluation.py")
            ),
            "ocr_configuration_sha256": sha256_file(Path(__file__).parents[2] / "configs/m2b.yaml"),
            "region_matching_rule": "IoU >= 0.5; one-to-one maximum-IoU matching",
            "metric_definition": "AV-Atlas OCR evaluation schema 1.0.0",
            "manifest_hash": "",
            "disagreement_count": report["disagreement_frames"],
        }
        frozen["manifest_hash"] = _digest(frozen)
        _validate_sandboxed_pilot_manifest(pilot_lease.descriptor_path, frozen, policy)
        output_lease = resources.enter_context(
            retained_output_directory(policy, retained_root, output)
        )
        output_lease.write_bounded_bytes("disagreement_report.json", disagreement_bytes)
        output_lease.write_bounded_bytes("frozen_manifest.json", _json_bytes(frozen))
        output_lease.verify()
        input_resources.close()
        resources.close()
        return frozen
    except BaseException as exc:
        try:
            input_resources.__exit__(type(exc), exc, exc.__traceback__)
        finally:
            resources.__exit__(type(exc), exc, exc.__traceback__)
        raise


def _distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for index, item in enumerate(left, 1):
        current = [index]
        for other_index, other in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[other_index] + 1,
                    previous[other_index - 1] + (item != other),
                )
            )
        previous = current
    return previous[-1]


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def _box(region: dict[str, Any]) -> list[float] | None:
    if isinstance(region.get("geometry"), dict):
        region = region["geometry"]
    value = region.get("bounding_box")
    if (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
    ):
        return [float(item) for item in value]
    polygon = region.get("polygon")
    if (
        isinstance(polygon, list)
        and polygon
        and all(isinstance(point, list) and len(point) == 2 for point in polygon)
    ):
        xs = [float(point[0]) for point in polygon]
        ys = [float(point[1]) for point in polygon]
        return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    return None


def _iou(left: list[float], right: list[float]) -> float:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    intersection = max(0.0, min(lx + lw, rx + rw) - max(lx, rx)) * max(
        0.0, min(ly + lh, ry + rh) - max(ly, ry)
    )
    union = lw * lh + rw * rh - intersection
    return intersection / union if union else 0.0


def _evaluate_pilot_with_resources(
    pilot_dir: Path,
    frozen_path: Path,
    adjudicated_path: Path,
    ocr_output_dir: Path,
    output: Path,
    security_policy_path: Path,
    resources: ExitStack,
    input_resources: ExitStack,
) -> dict[str, Any]:
    """Evaluate only a fully authenticated, sandbox-produced pilot OCR package."""
    policy = load_pilot_security_policy(security_policy_path)
    retained_root = resources.enter_context(open_verified_retained_root(policy))
    pilot_lease = resources.enter_context(
        open_retained_output_directory(policy, retained_root, pilot_dir)
    )
    ocr_lease = resources.enter_context(
        open_retained_output_directory(policy, retained_root, ocr_output_dir)
    )
    frozen_pin = input_resources.enter_context(
        _open_pinned_retained_json(
            retained_root,
            frozen_path,
            label="frozen pilot manifest",
        )
    )
    gold_pin = input_resources.enter_context(
        _open_pinned_retained_json(
            retained_root,
            adjudicated_path,
            label="adjudicated pilot gold",
        )
    )
    frozen = frozen_pin.value
    if frozen.get("state") != "adjudicated_frozen" or frozen.get("manifest_hash") != _digest(
        frozen
    ):
        raise AtlasError("pilot evaluation requires an intact adjudicated frozen manifest")
    if gold_pin.sha256 != frozen.get("adjudicated_gold_sha256"):
        raise AtlasError("adjudicated gold differs from the frozen pilot")
    if sha256_file(Path(__file__).parents[2] / "configs/m2b.yaml") != frozen.get(
        "ocr_configuration_sha256"
    ):
        raise AtlasError("OCR configuration differs from the frozen pilot")
    config_path = Path(__file__).parents[2] / "configs/m2b.yaml"
    reject_exposed_host_path(output, label="pilot evaluation output")
    pinned_pilot = pilot_lease.descriptor_path
    _validate_sandboxed_pilot_manifest(pinned_pilot, frozen, policy)
    _, rights_aggregate = _validate_pilot_security_linkage(
        pinned_pilot,
        frozen,
        policy,
        retained_root=retained_root,
    )
    authenticated = validate_pilot_ocr_output_package(
        ocr_lease.descriptor_path,
        frozen_manifest_path=frozen_pin.anchored_path,
        prepared_receipt_path=pinned_pilot / "pilot_security_receipt.json",
        policy_sha256=policy["policy_hash"],
        source_rights_aggregate_sha256=rights_aggregate,
        ocr_configuration_sha256=sha256_file(config_path),
        ocr_configuration_size_bytes=config_path.stat().st_size,
        expected_retained_storage=verified_retained_storage_binding(policy, retained_root),
    )
    observations = list(authenticated.observations)
    runtime = authenticated.runtime
    evidence = authenticated.evidence_index["evidence"]
    gold = gold_pin.value
    validate_instance("ocr_human_annotation", gold, "adjudicated gold")
    by_frame: dict[str, list[dict[str, Any]]] = {}
    for item in observations:
        frame_id = str(item.get("keyframe_id", item.get("frame_id", "")))
        by_frame.setdefault(frame_id, []).append(item)
    expected = {frame["frame_id"]: frame for frame in gold["frames"]}
    predicted_text = {
        frame_id: " ".join(
            str(item.get("normalized_text", "")) for item in by_frame.get(frame_id, [])
        )
        for frame_id in expected
    }
    exact = sum(
        predicted_text[key] == frame["normalized_transcription"] for key, frame in expected.items()
    )
    char_edits = sum(
        _distance(list(predicted_text[key]), list(frame["normalized_transcription"]))
        for key, frame in expected.items()
    )
    characters = sum(len(frame["normalized_transcription"]) for frame in expected.values())
    word_edits = sum(
        _distance(predicted_text[key].split(), frame["normalized_transcription"].split())
        for key, frame in expected.items()
    )
    words = sum(len(frame["normalized_transcription"].split()) for frame in expected.values())
    positive_gold = {key for key, frame in expected.items() if frame["normalized_transcription"]}
    positive_pred = {key for key, text in predicted_text.items() if text}

    def aggregate(frame_ids: list[str]) -> dict[str, Any]:
        subset = [key for key in frame_ids if key in expected]
        subset_exact = sum(
            predicted_text[key] == expected[key]["normalized_transcription"] for key in subset
        )
        subset_char_edits = sum(
            _distance(list(predicted_text[key]), list(expected[key]["normalized_transcription"]))
            for key in subset
        )
        subset_chars = sum(len(expected[key]["normalized_transcription"]) for key in subset)
        subset_word_edits = sum(
            _distance(
                predicted_text[key].split(), expected[key]["normalized_transcription"].split()
            )
            for key in subset
        )
        subset_words = sum(len(expected[key]["normalized_transcription"].split()) for key in subset)
        return {
            "frames": len(subset),
            "exact_match": _ratio(subset_exact, len(subset)),
            "normalized_cer": _ratio(subset_char_edits, subset_chars),
            "normalized_wer": _ratio(subset_word_edits, subset_words),
        }

    metadata = {
        frame["frame_id"]: frame for frame in frozen["frames"] if frame["split"] == "evaluation"
    }
    by_source = {
        source["source_id"]: aggregate(
            [key for key, frame in metadata.items() if frame["source_id"] == source["source_id"]]
        )
        for source in frozen["sources"]
    }
    categories = sorted({item for frame in metadata.values() for item in frame["categories"]})
    difficulties = sorted({item for frame in metadata.values() for item in frame["difficulty"]})
    by_category = {
        category: aggregate(
            [key for key, frame in metadata.items() if category in frame["categories"]]
        )
        for category in categories
    }
    by_difficulty = {
        difficulty: aggregate(
            [key for key, frame in metadata.items() if difficulty in frame["difficulty"]]
        )
        for difficulty in difficulties
    }

    def size_bucket(frame: dict[str, Any]) -> str:
        heights = [box[3] for region in frame["regions"] if (box := _box(region)) is not None]
        if not heights:
            return "no_text_or_unboxed"
        height = max(heights)
        return "small" if height < 24 else "medium" if height < 64 else "large"

    by_text_size = {
        bucket: aggregate([key for key, frame in expected.items() if size_bucket(frame) == bucket])
        for bucket in ("small", "medium", "large", "no_text_or_unboxed")
    }

    def confidence_bucket(frame_id: str) -> str:
        values = [float(item["confidence"]) for item in by_frame.get(frame_id, [])]
        if not values:
            return "no_observation"
        confidence = sum(values) / len(values)
        return (
            "low_0_49" if confidence < 50 else "medium_50_79" if confidence < 80 else "high_80_100"
        )

    by_confidence = {
        bucket: aggregate([key for key in expected if confidence_bucket(key) == bucket])
        for bucket in ("no_observation", "low_0_49", "medium_50_79", "high_80_100")
    }
    tp = len(positive_gold & positive_pred)
    fp = len(positive_pred - positive_gold)
    fn = len(positive_gold - positive_pred)
    presence_precision = _ratio(tp, tp + fp)
    presence_recall = _ratio(tp, tp + fn)
    presence_f1 = (
        2 * presence_precision * presence_recall / (presence_precision + presence_recall)
        if presence_precision is not None
        and presence_recall is not None
        and presence_precision + presence_recall
        else None
    )
    region_tp = 0
    region_fp = 0
    region_fn = 0
    ious: list[float] = []
    exact_region = 0
    reading_correct = 0
    reading_total = 0
    for frame_id, frame in expected.items():
        gold_regions = [(region, _box(region)) for region in frame["regions"]]
        predicted_regions = [(region, _box(region)) for region in by_frame.get(frame_id, [])]
        candidates = sorted(
            (
                (_iou(gbox, pbox), gi, pi)
                for gi, (_, gbox) in enumerate(gold_regions)
                if gbox
                for pi, (_, pbox) in enumerate(predicted_regions)
                if pbox
            ),
            reverse=True,
        )
        used_g: set[int] = set()
        used_p: set[int] = set()
        matched_order: list[tuple[int, int]] = []
        for overlap, gi, pi in candidates:
            if overlap < 0.5 or gi in used_g or pi in used_p:
                continue
            used_g.add(gi)
            used_p.add(pi)
            ious.append(overlap)
            matched_order.append((gi, pi))
            gold_text = str(gold_regions[gi][0].get("normalized_transcription", ""))
            if gold_text == str(predicted_regions[pi][0].get("normalized_text", "")):
                exact_region += 1
        region_tp += len(used_g)
        region_fn += len(gold_regions) - len(used_g)
        region_fp += len(predicted_regions) - len(used_p)
        if len(matched_order) > 1:
            reading_total += 1
            reading_correct += [gi for gi, _ in matched_order] == sorted(
                gi for gi, _ in matched_order
            )
    region_precision = _ratio(region_tp, region_tp + region_fp)
    region_recall = _ratio(region_tp, region_tp + region_fn)
    region_f1 = (
        2 * region_precision * region_recall / (region_precision + region_recall)
        if region_precision is not None
        and region_recall is not None
        and region_precision + region_recall
        else None
    )
    unique = {
        (
            item.get("source_id"),
            item.get("keyframe_id", item.get("frame_id")),
            item.get("normalized_text"),
            tuple(item.get("bounding_box", [])),
        )
        for item in observations
    }
    report = {
        "schema_version": "1.0.0",
        "category": "authorized_real_media_pilot",
        "pilot_id": frozen["pilot_id"],
        "frozen_manifest_sha256": frozen_pin.sha256,
        "ocr_output_manifest_file_sha256": authenticated.manifest_file_sha256,
        "ocr_output_manifest_hash": authenticated.manifest["manifest_hash"],
        "ocr_output_binding_sha256": authenticated.manifest["output_binding_sha256"],
        "source_count": len(frozen["sources"]),
        "frame_count": len(expected),
        "text_region_count": sum(len(frame["regions"]) for frame in expected.values()),
        "no_text_frame_count": len(expected) - len(positive_gold),
        "ocr_observation_count": len(observations),
        "exact_frame_level_match": _ratio(exact, len(expected)),
        "exact_region_level_match": _ratio(
            exact_region, sum(len(frame["regions"]) for frame in expected.values())
        ),
        "normalized_cer": _ratio(char_edits, characters),
        "normalized_wer": _ratio(word_edits, words),
        "text_presence": {
            "precision": presence_precision,
            "recall": presence_recall,
            "f1": presence_f1,
        },
        "region_detection": {
            "precision": region_precision,
            "recall": region_recall,
            "f1": region_f1,
        },
        "mean_region_iou": _ratio(sum(ious), len(ious)),
        "reading_order_accuracy": _ratio(reading_correct, reading_total),
        "duplicate_observation_rate": _ratio(len(observations) - len(unique), len(observations))
        or 0.0,
        "evidence_resolution_failures": sum(
            item.get("evidence_ref") not in evidence
            or item.get("source_frame_evidence_ref") not in evidence
            for item in observations
        ),
        "invalid_timestamps": sum(
            not isinstance(item.get("timestamp_ms"), int) for item in observations
        ),
        "retries": runtime.get("retries"),
        "timeouts": runtime.get("timeouts"),
        "wall_seconds": runtime.get("wall_seconds"),
        "cpu_seconds": runtime.get("cpu_seconds"),
        "peak_rss_kb": runtime.get("peak_rss_kb"),
        "frames_per_second": runtime.get("frames_per_second"),
        "stratified_results": {
            "by_source": by_source,
            "by_text_category": by_category,
            "by_difficulty": by_difficulty,
            "by_text_size": by_text_size,
            "by_confidence": by_confidence,
        },
        "limitations": [
            "Small authorized pilot only; do not generalize to all films, episodes, or livestreams."
        ],
    }
    output_lease = resources.enter_context(retained_output_directory(policy, retained_root, output))
    output_lease.write_bounded_bytes("ocr_evaluation.json", _json_bytes(report))
    output_lease.verify()
    input_resources.close()
    return report


def evaluate_pilot(
    pilot_dir: Path,
    frozen_path: Path,
    adjudicated_path: Path,
    ocr_output_dir: Path,
    output: Path,
    security_policy_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate only a fully authenticated, sandbox-produced pilot OCR package."""
    if security_policy_path is None:
        raise AtlasError("pilot evaluation requires an explicit private security policy")
    resources = ExitStack()
    input_resources = ExitStack()
    try:
        report = _evaluate_pilot_with_resources(
            pilot_dir,
            frozen_path,
            adjudicated_path,
            ocr_output_dir,
            output,
            security_policy_path,
            resources,
            input_resources,
        )
        resources.close()
        return report
    except BaseException as exc:
        try:
            input_resources.__exit__(type(exc), exc, exc.__traceback__)
        finally:
            resources.__exit__(type(exc), exc, exc.__traceback__)
        raise


def _validate_pilot_security_linkage(
    pilot_dir: Path,
    frozen: dict[str, Any],
    policy: dict[str, Any] | None = None,
    *,
    retained_root: VerifiedRetainedRoot | None = None,
) -> tuple[dict[str, Any], str]:
    if frozen.get("schema_version") not in {"1.1.0", "1.2.0"} or not isinstance(
        frozen.get("pilot_security"), dict
    ):
        raise AtlasError("pilot security linkage requires manifest contract 1.1.0 or 1.2.0")
    if policy is not None and frozen.get("schema_version") != "1.2.0":
        raise AtlasError("new pilot execution requires the sandboxed pilot manifest contract 1.2.0")
    security = frozen["pilot_security"]
    receipt_path = pilot_dir / str(security["receipt_path"])
    receipt, receipt_identity = load_bound_json(
        receipt_path,
        maximum_bytes=_MAX_RETAINED_JSON_BYTES,
    )
    validate_security_receipt(
        receipt,
        policy_hash=(policy["policy_hash"] if policy is not None else security["policy_sha256"]),
        pilot_spec_sha256=(
            policy["pilot_spec_sha256"] if policy is not None else security["pilot_spec_sha256"]
        ),
    )
    if (
        receipt_identity["sha256"] != security["receipt_sha256"]
        or receipt["receipt_hash"] != _digest(receipt, "receipt_hash")
        or receipt["policy_sha256"] != security["policy_sha256"]
        or receipt["pilot_spec_sha256"] != security["pilot_spec_sha256"]
        or receipt["pilot_spec_size_bytes"] != security["pilot_spec_size_bytes"]
    ):
        raise AtlasError("pilot security receipt, policy, or specification linkage mismatch")
    if policy is not None and (
        security["policy_sha256"] != policy["policy_hash"]
        or security["pilot_spec_sha256"] != policy["pilot_spec_sha256"]
        or security["pilot_spec_size_bytes"] != policy["pilot_spec_size_bytes"]
    ):
        raise AtlasError("private pilot policy differs from the prepared pilot linkage")
    if frozen.get("schema_version") == "1.2.0":
        retained = security.get("retained_storage")
        if not isinstance(retained, dict) or retained != receipt.get("retained_storage"):
            raise AtlasError("pilot retained-storage receipt differs from its manifest linkage")
        if policy is not None:
            if retained_root is None:
                raise AtlasError(
                    "current pilot linkage validation requires the verified retained root"
                )
            expected_retained = verified_retained_storage_binding(policy, retained_root)
            if any(
                retained.get(field) != expected for field, expected in expected_retained.items()
            ):
                raise AtlasError(
                    "private retained-storage boundary differs from the prepared pilot"
                )
    if _source_set_digest(frozen["sources"]) != security["source_set_sha256"]:
        raise AtlasError("pilot source set differs from its security-bound identity")
    rights_records: list[dict[str, Any]] = []
    for source in frozen["sources"]:
        rights_path = _safe_pilot_artifact_path(
            pilot_dir,
            str(source["rights_manifest"]),
            parent="rights",
            basename=f"{source['source_id']}.rights.json",
        )
        rights, rights_identity = load_bound_json(rights_path, maximum_bytes=1_000_000)
        validate_instance("rights_manifest", rights, "pilot rights manifest")
        if rights_identity["sha256"] != source["rights_manifest_sha256"]:
            raise AtlasError("pilot rights artifact differs from its manifest identity")
        if rights["manifest_hash"] != rights_manifest_digest(rights) or rights[
            "manifest_hash"
        ] != source.get("rights_manifest_hash"):
            raise AtlasError("pilot rights self-hash differs from its prepared linkage")
        for operation in REQUIRED_PILOT_OPERATIONS:
            validate_rights(
                rights,
                source["source_sha256"],
                source["source_id"],
                operation,
            )
        rights_records.append(
            {
                "source_id": source["source_id"],
                "source_sha256": source["source_sha256"],
                "rights_manifest_hash": rights["manifest_hash"],
            }
        )
    aggregate = source_rights_aggregate(rights_records)
    if (
        aggregate != security["source_rights_aggregate_sha256"]
        or aggregate != receipt["source_rights_aggregate_sha256"]
    ):
        raise AtlasError("pilot rights set differs from its security-bound identity")
    return receipt, aggregate


def validate_pilot_security_artifacts(
    pilot_dir: Path,
    manifest_path: Path | None = None,
    security_policy_path: Path | None = None,
) -> dict[str, Any]:
    """Validate public receipt/manifest linkage, optionally against the local policy."""
    selected_manifest = manifest_path or pilot_dir / "pilot_manifest.json"
    manifest = _load_json(selected_manifest)
    if manifest.get("manifest_hash") != _digest(manifest):
        raise AtlasError("pilot manifest checksum mismatch")
    if manifest.get("schema_version") in {"1.1.0", "1.2.0"}:
        _validate_sandboxed_pilot_manifest(pilot_dir, manifest)
    elif manifest.get("state") == "prepared_unannotated":
        validate_instance("ocr_pilot_manifest", manifest, "pilot manifest")
    policy = (
        load_pilot_security_policy(
            security_policy_path,
            pilot_id=str(manifest.get("pilot_id", "")),
        )
        if security_policy_path is not None
        else None
    )
    if policy is None:
        receipt, aggregate = _validate_pilot_security_linkage(pilot_dir, manifest)
    else:
        with (
            open_verified_retained_root(policy) as retained_root,
            open_retained_output_directory(policy, retained_root, pilot_dir) as pilot_lease,
        ):
            if manifest.get("schema_version") == "1.2.0":
                _validate_sandboxed_pilot_manifest(pilot_lease.descriptor_path, manifest, policy)
            receipt, aggregate = _validate_pilot_security_linkage(
                pilot_lease.descriptor_path,
                manifest,
                policy,
                retained_root=retained_root,
            )
    return {
        "schema_version": "1.0.0",
        "state": "valid",
        "pilot_id": manifest["pilot_id"],
        "manifest_schema_version": manifest["schema_version"],
        "manifest_hash": manifest["manifest_hash"],
        "policy_sha256": receipt["policy_sha256"],
        "receipt_hash": receipt["receipt_hash"],
        "source_rights_aggregate_sha256": aggregate,
        "private_paths_exported": False,
        "local_policy_verified": policy is not None,
    }


def run_pilot_ocr(
    pilot_dir: Path,
    frozen_path: Path,
    output: Path,
    security_policy_path: Path | None = None,
) -> dict[str, Any]:
    """Run OCR and finalize one authenticated, policy-retained output package."""
    for path, label in (
        (pilot_dir, "prepared pilot package"),
        (frozen_path, "frozen pilot manifest"),
        (output, "pilot OCR output"),
    ):
        reject_exposed_host_path(path, label=label)
    if security_policy_path is None:
        raise AtlasError("pilot OCR requires an explicit private security policy")
    policy = load_pilot_security_policy(security_policy_path)
    config_path = Path(__file__).parents[2] / "configs/m2b.yaml"
    all_records: list[dict[str, Any]] = []
    evidence: dict[str, dict[str, Any]] = {}
    totals: dict[str, Any] = {
        "wall_seconds": 0.0,
        "cpu_seconds": 0.0,
        "peak_rss_kb": 0,
        "retries": 0,
        "timeouts": 0,
        "frames_processed": 0,
        "failures": 0,
    }
    resources = ExitStack()
    input_resources = ExitStack()
    try:
        root = resources.enter_context(open_verified_pilot_root(policy))
        retained_root = resources.enter_context(open_verified_retained_root(policy))
        pilot_lease = resources.enter_context(
            open_retained_output_directory(policy, retained_root, pilot_dir)
        )
        retained_root.verify()
        frozen_pin = input_resources.enter_context(
            _open_pinned_retained_json(
                retained_root,
                frozen_path,
                label="frozen pilot manifest",
            )
        )
        frozen = frozen_pin.value
        if frozen.get("state") != "adjudicated_frozen" or frozen.get("manifest_hash") != _digest(
            frozen
        ):
            raise AtlasError("pilot OCR requires an intact adjudicated frozen manifest")
        if sha256_file(config_path) != frozen.get("ocr_configuration_sha256"):
            raise AtlasError("OCR configuration differs from the frozen pilot")
        config = BaselineConfig.load(config_path)
        pinned_pilot = pilot_lease.descriptor_path
        _validate_sandboxed_pilot_manifest(pinned_pilot, frozen, policy)
        prepared_receipt, source_rights_hash = _validate_pilot_security_linkage(
            pinned_pilot,
            frozen,
            policy,
            retained_root=retained_root,
        )
        output_lease = resources.enter_context(
            retained_output_directory(policy, retained_root, output)
        )
        retained_output = output_lease.descriptor_path
        runner, sandbox_inventory = _runner_for_policy(policy, root, retained_root)
        with private_pilot_workspace(policy, root) as probe_workspace:
            hostile = run_hostile_sandbox_probes(
                runner,
                WritableDirectory.measure(probe_workspace.path),
                frozen_pin.anchored_path,
            )
        capability = receipt_capability(sandbox_inventory, hostile)
        with private_pilot_workspace(policy, root) as inventory_workspace:
            ocr_dependency = inspect_ocr(
                config.ocr_executable,
                include_private_paths=True,
                native_runner=runner,
                sandbox_work_directory=inventory_workspace.path,
            )
        if ocr_dependency.get("state") != "available":
            raise AtlasError("approved Tesseract dependency is unavailable in the sandbox")
        for source in frozen["sources"]:
            ensure_pilot_security_execution_boundary(policy, root)
            output_lease.verify()
            frames = [
                frame
                for frame in frozen["frames"]
                if frame["source_id"] == source["source_id"] and frame["split"] == "evaluation"
            ]
            with private_pilot_workspace(policy, root) as work:
                workspace = work.path
                (workspace / "keyframes").mkdir(mode=0o700)
                keyframes: list[dict[str, Any]] = []
                frame_map: dict[str, str] = {}
                for index, frame in enumerate(frames, 1):
                    keyframe_id = f"KEY_{index:04d}"
                    shot_id = f"SHOT_{index:04d}"
                    destination = workspace / "keyframes" / f"{keyframe_id}.png"
                    frame_source = _safe_pilot_artifact_path(
                        pinned_pilot,
                        str(frame["path"]),
                        parent="frames",
                        basename=f"{frame['frame_id']}.png",
                    )
                    size = _copy_verified_file(
                        frame_source,
                        destination,
                        expected_sha256=str(frame["sha256"]),
                        expected_size=int(frame["size_bytes"]),
                    )
                    evidence_ref = f"VID:{source['source_id']}:frame:{frame['timestamp_ms']}"
                    keyframes.append(
                        {
                            "schema_version": "1.0.0",
                            "keyframe_id": keyframe_id,
                            "shot_id": shot_id,
                            "source_id": source["source_id"],
                            "timestamp_ms": frame["timestamp_ms"],
                            "frame_index": index,
                            "path": f"keyframes/{keyframe_id}.png",
                            "sha256": frame["sha256"],
                            "size_bytes": size,
                            "evidence_ref": evidence_ref,
                        }
                    )
                    frame_map[keyframe_id] = frame["frame_id"]
                    evidence[evidence_ref] = {
                        "evidence_ref": evidence_ref,
                        "source_id": source["source_id"],
                        "observation_id": frame["frame_id"],
                        "modality": "VID",
                        "start_ms": frame["timestamp_ms"],
                        "end_ms": min(frame["timestamp_ms"] + 1, source["duration_ms"]),
                    }
                write_jsonl(workspace / "keyframes.jsonl", keyframes)
                inventory = {
                    "schema_version": "1.0.0",
                    "source_id": source["source_id"],
                    "sha256": source["source_sha256"],
                    "duration_ms": source["duration_ms"],
                }
                execution = TesseractOcrAdapter().run(
                    AdapterContext(
                        Path("sandbox-input"),
                        inventory,
                        workspace,
                        config,
                        native_execution_mode="pilot_bubblewrap",
                        native_runner=runner,
                        ocr_dependency_private=ocr_dependency,
                    )
                )
                ensure_pilot_security_execution_boundary(policy, root)
                if execution.result.status not in {"success", "success_zero"}:
                    raise AtlasError(
                        f"pilot OCR failed for {source['source_id']}: {execution.result.status}"
                    )
                source_records = [
                    json.loads(line)
                    for line in (workspace / "ocr_observations.jsonl").read_text().splitlines()
                    if line
                ]
                prefix = source["source_id"].removeprefix("SRC_")
                for record in source_records:
                    original = record["observation_id"]
                    record["observation_id"] = f"OCR_{prefix}_{original.removeprefix('OCR_')}"
                    record["keyframe_id"] = frame_map[record["keyframe_id"]]
                    record["evidence_ref"] = f"OCR:{record['observation_id']}"
                    all_records.append(record)
                    evidence[record["evidence_ref"]] = {
                        "evidence_ref": record["evidence_ref"],
                        "source_id": record["source_id"],
                        "observation_id": record["observation_id"],
                        "modality": "OCR",
                        "start_ms": record["timestamp_ms"],
                        "end_ms": min(record["timestamp_ms"] + 1, source["duration_ms"]),
                    }
                runtime = _load_json(workspace / "ocr_runtime.json")
                for field in (
                    "wall_seconds",
                    "cpu_seconds",
                    "retries",
                    "timeouts",
                    "frames_processed",
                    "failures",
                ):
                    totals[field] = float(totals[field]) + float(runtime[field])
                totals["peak_rss_kb"] = max(int(totals["peak_rss_kb"]), int(runtime["peak_rss_kb"]))
        all_records.sort(
            key=lambda item: (
                item["source_id"],
                item["timestamp_ms"],
                item["bounding_box"],
                item["observation_id"],
            )
        )
        output_lease.write_bounded_bytes(
            OBSERVATIONS_FILENAME,
            _jsonl_bytes(all_records),
        )
        output_lease.write_bounded_bytes(
            EVIDENCE_FILENAME,
            _json_bytes({"schema_version": "1.0.0", "evidence": evidence}),
        )
        wall = float(totals["wall_seconds"])
        runtime_record = {
            "schema_version": "1.0.0",
            "workers": config.ocr_workers,
            "frames_processed": int(totals["frames_processed"]),
            "observation_count": len(all_records),
            "wall_seconds": wall,
            "cpu_seconds": float(totals["cpu_seconds"]),
            "peak_rss_kb": int(totals["peak_rss_kb"]),
            "frames_per_second": int(totals["frames_processed"]) / wall if wall else 0.0,
            "failures": int(totals["failures"]),
            "timeouts": int(totals["timeouts"]),
            "retries": int(totals["retries"]),
            "memory_scope": "maximum resident set of parent or one child",
            "thread_limit_per_tesseract_process": 1,
            "temporary_files_retained": False,
        }
        dependency_record = sanitize_ocr_inventory(ocr_dependency)
        output_lease.write_bounded_bytes(RUNTIME_FILENAME, _json_bytes(runtime_record))
        output_lease.write_bounded_bytes(DEPENDENCY_FILENAME, _json_bytes(dependency_record))
        binding_arguments = {
            "frozen_manifest_path": frozen_pin.anchored_path,
            "prepared_receipt_path": pinned_pilot / "pilot_security_receipt.json",
            "policy_sha256": policy["policy_hash"],
            "source_rights_aggregate_sha256": source_rights_hash,
            "ocr_configuration_sha256": sha256_file(config_path),
            "ocr_configuration_size_bytes": config_path.stat().st_size,
        }
        binding = build_pilot_ocr_output_binding(retained_output, **binding_arguments)
        security_receipt = make_security_receipt(
            policy=policy,
            root=root,
            retained_root=retained_root,
            stage="ocr-complete",
            source_rights_aggregate_sha256=source_rights_hash,
            sandbox_inventory=sandbox_inventory,
            capability=capability,
            cleanup_succeeded=True,
            output_binding_sha256=output_binding_sha256(binding),
        )
        if (
            prepared_receipt["retained_storage"]["root_identity_sha256"]
            != security_receipt["retained_storage"]["root_identity_sha256"]
        ):
            raise AtlasError("OCR output retained root differs from the prepared pilot")
        output_lease.write_bounded_bytes(
            "pilot_security_receipt.json",
            _json_bytes(security_receipt),
        )
        manifest = build_pilot_ocr_output_manifest(retained_output, **binding_arguments)
        output_lease.write_bounded_bytes(OUTPUT_MANIFEST_FILENAME, _json_bytes(manifest))
        output_lease.verify()
        input_resources.close()
        resources.close()
        return {
            "observations": len(all_records),
            **runtime_record,
            "output_manifest_hash": manifest["manifest_hash"],
            "output_binding_sha256": manifest["output_binding_sha256"],
        }
    except BaseException as exc:
        try:
            input_resources.__exit__(type(exc), exc, exc.__traceback__)
        finally:
            resources.__exit__(type(exc), exc, exc.__traceback__)
        raise


def run_synthetic_pilot_security_check(
    media: Path,
    rights_manifest: Path,
    pilot_spec: Path,
    security_policy_path: Path,
    output: Path,
) -> dict[str, Any]:
    """Execute the reviewed native stack on one project-authored synthetic fixture."""
    for path, label in (
        (media, "synthetic pilot source media"),
        (rights_manifest, "synthetic pilot rights declaration"),
        (pilot_spec, "synthetic pilot specification"),
    ):
        reject_exposed_host_path(path, label=label)
    spec, spec_identity = load_bound_json(pilot_spec)
    required = {
        "schema_version",
        "pilot_id",
        "source_sha256",
        "source_id",
        "timestamp_ms",
    }
    if set(spec) != required or spec.get("schema_version") != "1.0.0":
        raise AtlasError("synthetic pilot security specification is unknown or unsupported")
    timestamp_ms = spec["timestamp_ms"]
    if not isinstance(timestamp_ms, int) or isinstance(timestamp_ms, bool) or timestamp_ms < 0:
        raise AtlasError("synthetic pilot timestamp must be a nonnegative integer")
    policy = load_pilot_security_policy(
        security_policy_path,
        pilot_id=str(spec["pilot_id"]),
        pilot_spec_identity=spec_identity,
    )
    stable_policy = StableInputPolicy(
        max_source_bytes=int(policy["capacity"]["source_byte_ceiling"]),
        max_temporary_bytes=int(policy["capacity"]["temporary_byte_ceiling"]),
    )
    measurement = preflight_authorized_source(
        media,
        rights_manifest,
        "evaluation",
        policy=stable_policy,
        expected_source_sha256=str(spec["source_sha256"]),
        expected_source_id=str(spec["source_id"]),
    )
    authorization = measurement.authorization
    if (
        authorization.fixture_status != "authorized_controlled_fixture"
        or authorization.fixture_trust_mode != "synthetic-controlled-explicit-rights"
        or authorization.rights_declaration.get("rights_basis") != "synthetic-controlled"
    ):
        raise AtlasError(
            "synthetic sandbox check requires explicit rights and the exact controlled fixture"
        )
    started = time.perf_counter()
    child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    records: list[dict[str, Any]] = []
    dependency: dict[str, Any] = {}
    frame_size = 0
    runtime: dict[str, Any] = {}
    with (
        open_verified_pilot_root(policy) as root,
        open_verified_retained_root(policy) as retained_root,
        retained_output_directory(policy, retained_root, output) as output_lease,
    ):
        ensure_pilot_security_execution_boundary(policy, root)
        retained_root.verify()
        output_lease.verify()
        runner, sandbox_inventory = _runner_for_policy(policy, root, retained_root)
        with private_pilot_workspace(policy, root) as probe_workspace:
            hostile = run_hostile_sandbox_probes(
                runner,
                WritableDirectory.measure(probe_workspace.path),
                pilot_spec,
            )
        capability = receipt_capability(sandbox_inventory, hostile)
        ensure_pilot_security_execution_boundary(policy, root)
        retained_root.verify()
        output_lease.verify()
        with (
            acquire_authorized_input(
                media,
                rights_manifest,
                "evaluation",
                policy=stable_policy,
                verified_private_root=root.stable_input_binding(),
                expected_source_sha256=measurement.source_sha256,
                expected_source_id=measurement.source_id,
                expected_manifest_hash=str(authorization.rights_declaration["manifest_hash"]),
            ) as stable,
            private_pilot_workspace(policy, root) as work,
        ):
            inventory = inspect_media(
                stable.snapshot_path,
                native_runner=runner,
                sandbox_work_directory=work.path,
                expected_source_sha256=stable.source_sha256,
                expected_source_size=stable.size_bytes,
            )
            if timestamp_ms >= inventory["duration_ms"]:
                raise AtlasError("synthetic pilot timestamp is outside the fixture")
            native_policy = policy_from_inventory(inventory)
            frame = work.path / "synthetic-keyframe.png"
            _extract_frame(
                stable.snapshot_path,
                timestamp_ms,
                frame,
                native_policy,
                native_runner=runner,
                expected_source_sha256=stable.source_sha256,
                expected_source_size=stable.size_bytes,
            )
            frame_hash = sha256_file(frame)
            frame_size = frame.stat().st_size
            keyframes = work.path / "keyframes"
            keyframes.mkdir(mode=0o700)
            keyframe_path = keyframes / "KEY_SYNTHETIC_0001.png"
            _copy_verified_file(
                frame,
                keyframe_path,
                expected_sha256=frame_hash,
                expected_size=frame_size,
            )
            evidence_ref = f"VID:{stable.source_id}:frame:{timestamp_ms}"
            write_jsonl(
                work.path / "keyframes.jsonl",
                [
                    {
                        "schema_version": "1.0.0",
                        "keyframe_id": "KEY_SYNTHETIC_0001",
                        "shot_id": "SHOT_SYNTHETIC_0001",
                        "source_id": stable.source_id,
                        "timestamp_ms": timestamp_ms,
                        "frame_index": 1,
                        "path": "keyframes/KEY_SYNTHETIC_0001.png",
                        "sha256": frame_hash,
                        "size_bytes": frame_size,
                        "evidence_ref": evidence_ref,
                    }
                ],
            )
            config = BaselineConfig.load(Path(__file__).parents[2] / "configs/m2b.yaml")
            dependency_private = inspect_ocr(
                config.ocr_executable,
                include_private_paths=True,
                native_runner=runner,
                sandbox_work_directory=work.path,
            )
            execution = TesseractOcrAdapter().run(
                AdapterContext(
                    Path("sandbox-input"),
                    inventory,
                    work.path,
                    config,
                    native_execution_mode="pilot_bubblewrap",
                    native_runner=runner,
                    ocr_dependency_private=dependency_private,
                )
            )
            ensure_pilot_security_execution_boundary(policy, root)
            retained_root.verify()
            output_lease.verify()
            if execution.result.status not in {"success", "success_zero"}:
                raise AtlasError(
                    "synthetic pilot OCR did not complete successfully inside the sandbox"
                )
            records = [
                json.loads(line)
                for line in (work.path / "ocr_observations.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line
            ]
            dependency = _load_json(work.path / "ocr_dependency.json")
            runtime = _load_json(work.path / "ocr_runtime.json")
        ensure_pilot_security_execution_boundary(policy, root)
        retained_root.verify()
        output_lease.verify()
        observations_bytes = _jsonl_bytes(records)
        dependency_bytes = _json_bytes(dependency)
        output_lease.write_bounded_bytes("ocr_observations.jsonl", observations_bytes)
        output_lease.write_bounded_bytes("ocr_dependency.json", dependency_bytes)
        receipt = make_security_receipt(
            policy=policy,
            root=root,
            retained_root=retained_root,
            stage="synthetic-smoke-complete",
            source_rights_aggregate_sha256=source_rights_aggregate(
                [
                    {
                        "source_id": measurement.source_id,
                        "source_sha256": measurement.source_sha256,
                        "rights_manifest_hash": authorization.rights_declaration["manifest_hash"],
                    }
                ]
            ),
            sandbox_inventory=sandbox_inventory,
            capability=capability,
            cleanup_succeeded=True,
        )
        receipt_bytes = _json_bytes(receipt)
        output_lease.write_bounded_bytes("pilot_security_receipt.json", receipt_bytes)
        child_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu_seconds = (
            child_after.ru_utime
            + child_after.ru_stime
            - child_before.ru_utime
            - child_before.ru_stime
        )
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        report: dict[str, Any] = {
            "schema_version": "1.1.0",
            "contract_version": "av-atlas-m2b3-synthetic-pilot/1.1.0",
            "state": "succeeded",
            "pilot_id": spec["pilot_id"],
            "source_id": measurement.source_id,
            "source_sha256": measurement.source_sha256,
            "policy_sha256": policy["policy_hash"],
            "security_receipt_sha256": receipt_sha,
            "tools": {
                "ffprobe_sandboxed": True,
                "ffmpeg_sandboxed": True,
                "tesseract_sandboxed": True,
            },
            "measurements": {
                "wall_seconds": time.perf_counter() - started,
                "cpu_seconds": max(0.0, cpu_seconds),
                "peak_rss_kb": max(0, int(child_after.ru_maxrss)),
                "source_size_bytes": measurement.size_bytes,
                "frame_size_bytes": frame_size,
                "ocr_observation_count": len(records),
                "ocr_frames_processed": int(runtime["frames_processed"]),
                "ocr_timeouts": int(runtime["timeouts"]),
                "ocr_retries": int(runtime["retries"]),
            },
            "resource_limits": policy["resource_limits"],
            "capability": capability,
            "privacy": {
                "real_media_processed": False,
                "private_paths_exported": False,
                "source_media_exported": False,
                "frame_derivative_exported": False,
            },
            "artifact_hashes": {
                "ocr_observations": hashlib.sha256(observations_bytes).hexdigest(),
                "ocr_dependency": hashlib.sha256(dependency_bytes).hexdigest(),
                "security_receipt": receipt_sha,
            },
            "report_hash": "",
        }
        report["report_hash"] = _digest(report, "report_hash")
        validate_instance(
            "pilot_security_synthetic_report",
            report,
            "synthetic pilot security report",
        )
        ensure_pilot_security_execution_boundary(policy, root)
        retained_root.verify()
        output_lease.write_bounded_bytes(
            "synthetic_pilot_security_report.json",
            _json_bytes(report),
        )
        output_lease.verify()
        return report
