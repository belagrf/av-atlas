"""Private pilot-storage policy and sanitized public security receipts.

The local policy is an operator-controlled authorization input.  It may contain
the private temporary-root path and therefore must never be copied into a run,
report, release, or annotation package.  Public artifacts receive only the
hash-linked receipt produced by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from av_atlas.native_process import NativeResourceLimits
    from av_atlas.stable_input import VerifiedPrivateRoot as StableInputPrivateRoot

try:  # pragma: no cover - exercised on the supported Linux pilot host
    import fcntl
except ImportError:  # pragma: no cover - fail-closed non-POSIX fallback
    fcntl = None  # type: ignore[assignment]

from av_atlas.errors import AtlasError, ResourceLimitError
from av_atlas.io import canonical_json, write_json_new
from av_atlas.native_process import (
    PROFILE_VERSION as SANDBOX_PROFILE_VERSION,
)
from av_atlas.native_process import (
    reject_exposed_host_path,
)
from av_atlas.schemas import validate_instance

POLICY_SCHEMA_VERSION = "1.1.0"
POLICY_CONTRACT_VERSION = "av-atlas-pilot-security-policy/1.1.0"
LEGACY_POLICY_CONTRACT_VERSION = "av-atlas-pilot-security-policy/1.0.0"
RECEIPT_SCHEMA_VERSION = "1.1.0"
RECEIPT_CONTRACT_VERSION = "av-atlas-pilot-security-receipt/1.1.0"
LEGACY_RECEIPT_CONTRACT_VERSION = "av-atlas-pilot-security-receipt/1.0.0"
MAX_POLICY_BYTES = 1_000_000
DEFAULT_MAX_SOURCE_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_MAX_TEMPORARY_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_MAX_RETAINED_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_RESERVE_BYTES = 1024 * 1024 * 1024
MAX_STORAGE_BYTES = 64 * 1024 * 1024 * 1024
PRIVATE_POLICY_MODE = 0o600
PRIVATE_ROOT_MODE = 0o700
WORK_DIRECTORY_PATTERN = re.compile(r"^pilot-work-[0-9a-f]{32}$")
WORK_MARKER_NAME = ".av-atlas-pilot-work.json"
WORK_MARKER_MAGIC = "av-atlas-private-pilot-work"
MAX_WORK_ENTRIES = 4096
MAX_WORK_DEPTH = 8
MAX_STALE_SCAN = 64
MAX_STALE_REMOVALS = 16
RETAINED_OUTPUT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_RETAINED_ENTRIES = 16_384
MAX_RETAINED_DEPTH = 12
REMOTE_FILESYSTEMS = frozenset(
    {
        "9p",
        "afs",
        "ceph",
        "cifs",
        "davfs",
        "fuse.rclone",
        "fuse.sshfs",
        "glusterfs",
        "lustre",
        "nfs",
        "nfs4",
        "smb3",
    }
)
LOCAL_FILESYSTEMS = frozenset(
    {
        "btrfs",
        "ecryptfs",
        "ext2",
        "ext3",
        "ext4",
        "f2fs",
        "overlay",
        "tmpfs",
        "xfs",
        "zfs",
    }
)


def _digest(value: dict[str, Any], field: str) -> str:
    return hashlib.sha256(
        canonical_json({key: item for key, item in value.items() if key != field}).encode()
    ).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise AtlasError(f"{label} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AtlasError(f"{label} is not a valid RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise AtlasError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _stable_read(path: Path, *, maximum_bytes: int, required_mode: int | None) -> bytes:
    """Read one regular file once without following its final path component."""
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise AtlasError(f"private {path.name} is unavailable") from exc
    if not stat.S_ISREG(before.st_mode):
        raise AtlasError(f"private {path.name} must be a regular non-symlink file")
    if before.st_size <= 0 or before.st_size > maximum_bytes:
        raise ResourceLimitError(f"private {path.name} exceeds its bounded input size")
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    if uid is not None and before.st_uid != uid:
        raise AtlasError(f"private {path.name} has the wrong owner")
    if required_mode is not None and stat.S_IMODE(before.st_mode) != required_mode:
        raise AtlasError(f"private {path.name} must have mode {required_mode:04o}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AtlasError(
            f"private {path.name} could not be opened without following links"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise AtlasError(f"private {path.name} identity changed while opening")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > maximum_bytes:
                raise ResourceLimitError(f"private {path.name} exceeds its bounded input size")
        after = os.fstat(descriptor)
        final = os.lstat(path)
        identities = {
            (
                item.st_dev,
                item.st_ino,
                item.st_mode,
                item.st_uid,
                item.st_size,
                item.st_mtime_ns,
                item.st_ctime_ns,
            )
            for item in (before, opened, after, final)
        }
        if len(identities) != 1 or total != before.st_size:
            raise AtlasError(f"private {path.name} changed during its bounded read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def stable_file_identity(path: Path, *, maximum_bytes: int = MAX_POLICY_BYTES) -> dict[str, Any]:
    """Return a path-free digest and size after a stable, no-follow read."""
    raw = _stable_read(path, maximum_bytes=maximum_bytes, required_mode=None)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def load_bound_json(
    path: Path, *, maximum_bytes: int = MAX_POLICY_BYTES
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Stably read one JSON object and return it with the exact byte identity."""
    raw = _stable_read(path, maximum_bytes=maximum_bytes, required_mode=None)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AtlasError(f"invalid JSON file {path.name}") from exc
    if not isinstance(value, dict):
        raise AtlasError(f"JSON file {path.name} must contain an object")
    return value, {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def _mount_unescape(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _filesystem_record(
    path: Path, device: int, *, label: str = "pilot private root"
) -> dict[str, str]:
    """Classify a Linux mount without starting a helper subprocess."""
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AtlasError(f"{label} filesystem could not be classified") from exc
    device_id = f"{os.major(device)}:{os.minor(device)}"
    resolved = str(path)
    candidates: list[tuple[int, str, str, str]] = []
    for line in lines:
        fields = line.split()
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        if len(fields) <= separator + 2 or fields[2] != device_id:
            continue
        mountpoint = _mount_unescape(fields[4])
        if resolved != mountpoint and not resolved.startswith(mountpoint.rstrip("/") + "/"):
            continue
        filesystem_type = fields[separator + 1]
        source = _mount_unescape(fields[separator + 2])
        identity = hashlib.sha256(
            canonical_json(
                {
                    "device": device_id,
                    "filesystem_type": filesystem_type,
                    "mountpoint": mountpoint,
                    "source": source,
                }
            ).encode()
        ).hexdigest()
        candidates.append((len(mountpoint), filesystem_type, identity, device_id))
    if not candidates:
        raise AtlasError(f"{label} mount is unknown and therefore unsupported")
    _, filesystem_type, identity, measured_device = max(candidates)
    if filesystem_type in REMOTE_FILESYSTEMS:
        raise AtlasError(f"{label} must not use a network or remote filesystem")
    if filesystem_type not in LOCAL_FILESYSTEMS:
        raise AtlasError(f"{label} filesystem is unsupported: {filesystem_type}")
    return {
        "filesystem_type": filesystem_type,
        "mount_identity_sha256": identity,
        "device_class": measured_device,
    }


def _root_measurement(path: Path, *, label: str = "pilot private root") -> dict[str, Any]:
    reject_exposed_host_path(path, label=label)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise AtlasError(f"{label} is unavailable") from exc
    if not path.is_absolute() or path != resolved:
        raise AtlasError(f"{label} must be an absolute, canonical, non-symlink path")
    repository_root = Path(__file__).parents[2].resolve()
    if resolved.is_relative_to(repository_root):
        raise AtlasError(f"{label} must be outside the tracked repository checkout")
    before = os.lstat(path)
    if not stat.S_ISDIR(before.st_mode):
        raise AtlasError(f"{label} must be a pre-created directory")
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    if uid is not None and before.st_uid != uid:
        raise AtlasError(f"{label} must be owned by the current operating-system user")
    if stat.S_IMODE(before.st_mode) != PRIVATE_ROOT_MODE:
        raise AtlasError(f"{label} must have exact mode 0700")
    filesystem = _filesystem_record(path, before.st_dev, label=label)
    capacity = os.statvfs(path)
    available_bytes = capacity.f_bavail * capacity.f_frsize
    return {
        "device": before.st_dev,
        "inode": before.st_ino,
        "owner_uid": before.st_uid,
        "mode": "0700",
        **filesystem,
        "available_bytes": available_bytes,
    }


def _validate_storage_limits(
    source_bytes: int,
    temporary_bytes: int,
    reserve_bytes: int,
    retained_bytes: int = DEFAULT_MAX_RETAINED_BYTES,
    retained_reserve_bytes: int = DEFAULT_RESERVE_BYTES,
) -> None:
    values = (
        source_bytes,
        temporary_bytes,
        reserve_bytes,
        retained_bytes,
        retained_reserve_bytes,
    )
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
        raise AtlasError("pilot storage limits must be nonnegative integers")
    if source_bytes == 0 or temporary_bytes == 0 or retained_bytes == 0:
        raise AtlasError("pilot source, temporary, and retained byte ceilings must be positive")
    if max(values) > MAX_STORAGE_BYTES:
        raise AtlasError("pilot storage limits may not exceed 64 GiB each")


def _review_record(
    *,
    pilot_id: str,
    storage_decision: str,
    reviewer_pseudonym: str | None,
    review_record: str | None,
    review_expires_at: str | None,
    compensating_controls: tuple[str, ...],
    deletion_plan: str | None,
) -> dict[str, Any]:
    reviewed = storage_decision != "verified-tmpfs"
    if reviewed and (
        not reviewer_pseudonym
        or not reviewer_pseudonym.strip()
        or not review_record
        or not review_expires_at
        or _parse_timestamp(review_expires_at, "storage review expiry") <= _utc_now()
    ):
        raise AtlasError(
            "reviewed pilot storage requires a pseudonymous reviewer, record, and future expiry"
        )
    if storage_decision == "reviewed-remanence-acceptance" and (
        not compensating_controls or not deletion_plan
    ):
        raise AtlasError("remanence acceptance requires compensating controls and a deletion plan")
    return {
        "independently_reviewed": reviewed,
        "reviewer_pseudonym": reviewer_pseudonym if reviewed else None,
        "review_record": review_record if reviewed else None,
        "review_scope": pilot_id if reviewed else None,
        "review_expires_at": review_expires_at if reviewed else None,
        "compensating_controls": list(compensating_controls),
        "deletion_plan": deletion_plan,
    }


def validate_private_policy_output_path(output: Path) -> None:
    """Require the repository-wide ignored suffix for host-private policies."""
    required_name = "pilot-security-policy.local.json"
    if output.name != required_name and not output.name.endswith(f".{required_name}"):
        raise AtlasError(
            "private pilot security policy output must use the ignored "
            "pilot-security-policy.local.json name or *.pilot-security-policy.local.json suffix"
        )


def preflight_pilot_security_root(
    root: Path,
    storage_decision: str,
    max_source_bytes: int,
    max_temporary_bytes: int,
    reserve_bytes: int,
) -> dict[str, Any]:
    """Validate storage identity and capacity before any sandbox executable runs."""
    if storage_decision not in {
        "verified-tmpfs",
        "reviewed-encrypted-volume",
        "reviewed-remanence-acceptance",
    }:
        raise AtlasError("unsupported pilot storage decision")
    _validate_storage_limits(max_source_bytes, max_temporary_bytes, reserve_bytes)
    root_value = _root_measurement(root)
    if storage_decision == "verified-tmpfs" and root_value["filesystem_type"] != "tmpfs":
        raise AtlasError("verified-tmpfs requires a root measured on tmpfs")
    required = max_source_bytes + max_temporary_bytes + reserve_bytes
    if root_value["available_bytes"] < required:
        raise ResourceLimitError("pilot private root lacks the policy-required free capacity")
    return root_value


def preflight_pilot_security_roots(
    transient_root: Path,
    retained_root: Path,
    transient_storage_decision: str,
    retained_storage_decision: str,
    max_source_bytes: int,
    max_temporary_bytes: int,
    max_retained_bytes: int,
    reserve_bytes: int,
    retained_reserve_bytes: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the distinct transient and retained roots before dependency execution."""
    _validate_storage_limits(
        max_source_bytes,
        max_temporary_bytes,
        reserve_bytes,
        max_retained_bytes,
        retained_reserve_bytes,
    )
    transient = preflight_pilot_security_root(
        transient_root,
        transient_storage_decision,
        max_source_bytes,
        max_temporary_bytes,
        reserve_bytes,
    )
    if retained_storage_decision not in {
        "verified-tmpfs",
        "reviewed-encrypted-volume",
        "reviewed-remanence-acceptance",
    }:
        raise AtlasError("unsupported retained pilot storage decision")
    retained = _root_measurement(retained_root, label="pilot retained root")
    if retained_storage_decision == "verified-tmpfs" and retained["filesystem_type"] != "tmpfs":
        raise AtlasError("verified-tmpfs retained storage requires a root measured on tmpfs")
    if (transient["device"], transient["inode"]) == (
        retained["device"],
        retained["inode"],
    ):
        raise AtlasError("pilot transient and retained roots must be distinct directories")
    if retained_root.is_relative_to(transient_root) or transient_root.is_relative_to(retained_root):
        raise AtlasError("pilot transient and retained roots must not overlap")
    retained_required = max_retained_bytes + retained_reserve_bytes
    if retained["available_bytes"] < retained_required:
        raise ResourceLimitError("pilot retained root lacks the policy-required free capacity")
    if transient["mount_identity_sha256"] == retained["mount_identity_sha256"]:
        shared_required = (
            max_source_bytes
            + max_temporary_bytes
            + reserve_bytes
            + max_retained_bytes
            + retained_reserve_bytes
        )
        if min(transient["available_bytes"], retained["available_bytes"]) < shared_required:
            raise ResourceLimitError(
                "shared pilot storage lacks combined transient and retained capacity"
            )
    return transient, retained


def create_pilot_security_policy(
    *,
    root: Path,
    retained_root: Path,
    pilot_id: str,
    pilot_spec: Path,
    output: Path,
    expires_at: str,
    storage_decision: str,
    retained_storage_decision: str,
    bubblewrap_inventory: dict[str, Any],
    resource_limits: dict[str, int],
    reviewer_pseudonym: str | None = None,
    review_record: str | None = None,
    review_expires_at: str | None = None,
    compensating_controls: tuple[str, ...] = (),
    deletion_plan: str | None = None,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
    max_temporary_bytes: int = DEFAULT_MAX_TEMPORARY_BYTES,
    max_retained_bytes: int = DEFAULT_MAX_RETAINED_BYTES,
    reserve_bytes: int = DEFAULT_RESERVE_BYTES,
    retained_reserve_bytes: int = DEFAULT_RESERVE_BYTES,
) -> dict[str, Any]:
    """Create one no-overwrite, mode-0600 local policy bound to a pilot spec."""
    reject_exposed_host_path(pilot_spec, label="pilot specification")
    reject_exposed_host_path(output, label="private pilot policy output")
    validate_private_policy_output_path(output)
    if _parse_timestamp(expires_at, "pilot security policy expiry") <= _utc_now():
        raise AtlasError("pilot security policy expiry must be in the future")
    root_value, retained_root_value = preflight_pilot_security_roots(
        root,
        retained_root,
        storage_decision,
        retained_storage_decision,
        max_source_bytes,
        max_temporary_bytes,
        max_retained_bytes,
        reserve_bytes,
        retained_reserve_bytes,
    )
    try:
        with os.scandir(retained_root) as entries:
            if next(entries, None) is not None:
                raise AtlasError("pilot retained root must be empty when its policy is created")
    except OSError as exc:
        raise AtlasError("pilot retained root could not be inspected safely") from exc
    for private_root in (root, retained_root):
        try:
            if output.resolve(strict=False).is_relative_to(private_root):
                raise AtlasError("private pilot policy must be stored outside its storage roots")
        except OSError as exc:
            raise AtlasError("private pilot policy output could not be resolved safely") from exc
    spec = stable_file_identity(pilot_spec)
    review = _review_record(
        pilot_id=pilot_id,
        storage_decision=storage_decision,
        reviewer_pseudonym=reviewer_pseudonym,
        review_record=review_record,
        review_expires_at=review_expires_at,
        compensating_controls=compensating_controls,
        deletion_plan=deletion_plan,
    )
    retained_review = _review_record(
        pilot_id=pilot_id,
        storage_decision=retained_storage_decision,
        reviewer_pseudonym=reviewer_pseudonym,
        review_record=review_record,
        review_expires_at=review_expires_at,
        compensating_controls=compensating_controls,
        deletion_plan=deletion_plan,
    )
    smoke = bubblewrap_inventory.get("capability_smoke")
    dependency_identity = bubblewrap_inventory.get("dependency_identity_sha256")
    if (
        bubblewrap_inventory.get("state") != "available"
        or bubblewrap_inventory.get("profile_version") != SANDBOX_PROFILE_VERSION
        or not isinstance(smoke, dict)
        or smoke.get("passed") is not True
        or not isinstance(dependency_identity, str)
        or not re.fullmatch(r"[a-f0-9]{64}", dependency_identity)
    ):
        raise AtlasError("Bubblewrap is unavailable; pilot security policy creation fails closed")
    executable = bubblewrap_inventory.get("executable")
    if not isinstance(executable, dict):
        raise AtlasError("Bubblewrap inventory lacks a measured executable identity")
    value: dict[str, Any] = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "contract_version": POLICY_CONTRACT_VERSION,
        "pilot_id": pilot_id,
        "pilot_spec_sha256": spec["sha256"],
        "pilot_spec_size_bytes": spec["size_bytes"],
        "created_at": _utc_now().isoformat(),
        "expires_at": expires_at,
        "private_root": {
            "path": str(root),
            "expected_device": root_value["device"],
            "expected_inode": root_value["inode"],
            "expected_uid": root_value["owner_uid"],
            "expected_mode": "0700",
            "mount_identity_sha256": root_value["mount_identity_sha256"],
        },
        "retained_root": {
            "path": str(retained_root),
            "expected_device": retained_root_value["device"],
            "expected_inode": retained_root_value["inode"],
            "expected_uid": retained_root_value["owner_uid"],
            "expected_mode": "0700",
            "mount_identity_sha256": retained_root_value["mount_identity_sha256"],
        },
        "storage": {
            "decision": storage_decision,
            "expected_filesystem_type": root_value["filesystem_type"],
            **review,
            "tmpfs_swap_warning_acknowledged": storage_decision == "verified-tmpfs",
            "secure_erasure_claimed": False,
        },
        "retained_storage": {
            "decision": retained_storage_decision,
            "expected_filesystem_type": retained_root_value["filesystem_type"],
            **retained_review,
            "tmpfs_swap_warning_acknowledged": retained_storage_decision == "verified-tmpfs",
            "secure_erasure_claimed": False,
        },
        "capacity": {
            "source_byte_ceiling": max_source_bytes,
            "temporary_byte_ceiling": max_temporary_bytes,
            "retained_byte_ceiling": max_retained_bytes,
            "reserve_bytes": reserve_bytes,
            "retained_reserve_bytes": retained_reserve_bytes,
        },
        "sandbox": {
            "provider": "bubblewrap",
            "profile_contract_version": SANDBOX_PROFILE_VERSION,
            "profile_sha256": bubblewrap_inventory["profile_sha256"],
            "executable_basename": executable["basename"],
            "executable_sha256": executable["sha256"],
            "executable_size_bytes": executable["size_bytes"],
            "dependency_identity_sha256": dependency_identity,
            "version": bubblewrap_inventory["version"],
            "capability_state": "passed",
        },
        "resource_limits": resource_limits,
        "policy_hash": "",
    }
    value["policy_hash"] = _digest(value, "policy_hash")
    validate_instance("pilot_security_policy", value, "private pilot security policy")
    try:
        write_json_new(output, value)
        os.chmod(output, PRIVATE_POLICY_MODE)
    except OSError as exc:
        raise AtlasError("private pilot security policy could not be created safely") from exc
    return value


def load_pilot_security_policy(
    path: Path,
    *,
    pilot_id: str | None = None,
    pilot_spec: Path | None = None,
    pilot_spec_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reject_exposed_host_path(path, label="private pilot policy")
    if pilot_spec is not None:
        reject_exposed_host_path(pilot_spec, label="pilot specification")
    try:
        raw = _stable_read(path, maximum_bytes=MAX_POLICY_BYTES, required_mode=PRIVATE_POLICY_MODE)
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AtlasError("private pilot security policy contains invalid JSON") from exc
    if not isinstance(value, dict):
        raise AtlasError("private pilot security policy must be a JSON object")
    validate_instance("pilot_security_policy", value, "private pilot security policy")
    if value.get("policy_hash") != _digest(value, "policy_hash"):
        raise AtlasError("private pilot security policy checksum mismatch")
    ensure_pilot_security_policy_current(value)
    if pilot_id is not None and value.get("pilot_id") != pilot_id:
        raise AtlasError("private pilot security policy belongs to another pilot")
    if pilot_spec is not None and pilot_spec_identity is not None:
        raise AtlasError("pilot specification identity was supplied twice")
    if pilot_spec is not None or pilot_spec_identity is not None:
        if pilot_spec_identity is not None:
            identity = pilot_spec_identity
        else:
            assert pilot_spec is not None
            identity = stable_file_identity(pilot_spec)
        if (
            value.get("pilot_spec_sha256") != identity["sha256"]
            or value.get("pilot_spec_size_bytes") != identity["size_bytes"]
        ):
            raise AtlasError("private pilot security policy does not match the pilot specification")
    return value


def require_current_pilot_security_policy(value: dict[str, Any]) -> None:
    """Reject legacy private policies for new pilot execution while retaining read validation."""
    if (
        value.get("schema_version") != POLICY_SCHEMA_VERSION
        or value.get("contract_version") != POLICY_CONTRACT_VERSION
    ):
        raise AtlasError(
            "legacy pilot security policies are read-only and cannot authorize execution"
        )


def ensure_pilot_security_policy_current(value: dict[str, Any]) -> None:
    """Recheck expiry and review scope at bounded native-processing unit boundaries."""
    if _parse_timestamp(value.get("expires_at"), "pilot security policy expiry") <= _utc_now():
        raise AtlasError("private pilot security policy has expired")
    storage_records = [("storage", value["storage"])]
    if value.get("contract_version") == POLICY_CONTRACT_VERSION:
        storage_records.append(("retained storage", value["retained_storage"]))
    for label, storage in storage_records:
        if storage["independently_reviewed"]:
            if value.get("contract_version") == POLICY_CONTRACT_VERSION and (
                not isinstance(storage.get("reviewer_pseudonym"), str)
                or not storage["reviewer_pseudonym"].strip()
            ):
                raise AtlasError(f"pilot {label} review lacks its reviewer pseudonym")
            if (
                _parse_timestamp(storage["review_expires_at"], f"{label} review expiry")
                <= _utc_now()
            ):
                raise AtlasError(f"pilot {label} review has expired")
            if storage["review_scope"] != value["pilot_id"]:
                raise AtlasError(f"pilot {label} review scope does not match the policy pilot")


def ensure_pilot_security_execution_boundary(
    policy: dict[str, Any], root: VerifiedPilotRoot
) -> None:
    """Recheck time-bounded authority and the retained private-root identity."""
    require_current_pilot_security_policy(policy)
    ensure_pilot_security_policy_current(policy)
    root.verify()


@dataclass
class VerifiedPilotRoot:
    """An exact private root held open for the complete pilot operation."""

    path: Path
    descriptor: int
    device: int
    inode: int
    owner_uid: int
    filesystem_type: str
    mount_identity_sha256: str
    available_bytes: int
    required_free_bytes: int

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(
            canonical_json(
                {
                    "device": self.device,
                    "inode": self.inode,
                    "filesystem_type": self.filesystem_type,
                    "mount_identity_sha256": self.mount_identity_sha256,
                }
            ).encode()
        ).hexdigest()

    def stable_input_binding(self) -> StableInputPrivateRoot:
        """Return the additive stable-input root binding without a module cycle."""
        from av_atlas.stable_input import VerifiedPrivateRoot

        self.verify()
        return VerifiedPrivateRoot(self.path, self.descriptor, self.device, self.inode)

    def verify(self, *, require_capacity: bool = True) -> None:
        try:
            opened = os.fstat(self.descriptor)
            current = os.lstat(self.path)
        except OSError as exc:
            raise AtlasError("pilot private root became unavailable") from exc
        uid = os.geteuid() if hasattr(os, "geteuid") else None
        identity = (opened.st_dev, opened.st_ino)
        if (
            identity != (self.device, self.inode)
            or identity != (current.st_dev, current.st_ino)
            or not stat.S_ISDIR(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != PRIVATE_ROOT_MODE
            or stat.S_IMODE(current.st_mode) != PRIVATE_ROOT_MODE
            or (uid is not None and (opened.st_uid != uid or current.st_uid != uid))
        ):
            raise AtlasError("pilot private root identity, owner, or permissions changed")
        filesystem = _filesystem_record(self.path, opened.st_dev)
        if (
            filesystem["filesystem_type"] != self.filesystem_type
            or filesystem["mount_identity_sha256"] != self.mount_identity_sha256
        ):
            raise AtlasError("pilot private-root filesystem identity changed")
        capacity = os.fstatvfs(self.descriptor)
        available = capacity.f_bavail * capacity.f_frsize
        if require_capacity and available < self.required_free_bytes:
            raise ResourceLimitError("pilot private root no longer has required free capacity")
        self.available_bytes = available


@dataclass
class VerifiedRetainedRoot:
    """An exact private retained-artifact root held through an open descriptor."""

    path: Path
    descriptor: int
    device: int
    inode: int
    owner_uid: int
    filesystem_type: str
    mount_identity_sha256: str
    available_bytes: int
    byte_ceiling: int
    reserve_bytes: int
    shared_capacity_ceiling: int | None = None
    shared_reserve_bytes: int = 0

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(
            canonical_json(
                {
                    "device": self.device,
                    "inode": self.inode,
                    "filesystem_type": self.filesystem_type,
                    "mount_identity_sha256": self.mount_identity_sha256,
                }
            ).encode()
        ).hexdigest()

    def measure_aggregate_bytes(self) -> int:
        budget = _RetainedTreeBudget(entries=0, bytes_seen=0)
        _measure_retained_tree(self.descriptor, budget)
        if budget.bytes_seen > self.byte_ceiling:
            raise ResourceLimitError("pilot retained artifacts exceed their aggregate byte ceiling")
        return budget.bytes_seen

    def verify(self, *, require_capacity: bool = True) -> int:
        try:
            opened = os.fstat(self.descriptor)
            current = os.lstat(self.path)
        except OSError as exc:
            raise AtlasError("pilot retained root became unavailable") from exc
        uid = os.geteuid() if hasattr(os, "geteuid") else None
        identity = (opened.st_dev, opened.st_ino)
        if (
            identity != (self.device, self.inode)
            or identity != (current.st_dev, current.st_ino)
            or not stat.S_ISDIR(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != PRIVATE_ROOT_MODE
            or stat.S_IMODE(current.st_mode) != PRIVATE_ROOT_MODE
            or (uid is not None and (opened.st_uid != uid or current.st_uid != uid))
        ):
            raise AtlasError("pilot retained root identity, owner, or permissions changed")
        filesystem = _filesystem_record(self.path, opened.st_dev, label="pilot retained root")
        if (
            filesystem["filesystem_type"] != self.filesystem_type
            or filesystem["mount_identity_sha256"] != self.mount_identity_sha256
        ):
            raise AtlasError("pilot retained-root filesystem identity changed")
        aggregate = self.measure_aggregate_bytes()
        capacity = os.fstatvfs(self.descriptor)
        available = capacity.f_bavail * capacity.f_frsize
        if require_capacity:
            required = max(0, self.byte_ceiling - aggregate) + self.reserve_bytes
            if self.shared_capacity_ceiling is not None:
                required = max(
                    required,
                    max(0, self.shared_capacity_ceiling - aggregate) + self.shared_reserve_bytes,
                )
            if available < required:
                raise ResourceLimitError("pilot retained root no longer has required free capacity")
        self.available_bytes = available
        return aggregate


def verified_retained_storage_binding(
    policy: dict[str, Any], root: VerifiedRetainedRoot
) -> dict[str, Any]:
    """Return the current policy/root semantics that a retained receipt must bind."""
    require_current_pilot_security_policy(policy)
    ensure_pilot_security_policy_current(policy)
    root.verify()
    expected_filesystem = policy["retained_storage"]["expected_filesystem_type"]
    expected_ceiling = int(policy["capacity"]["retained_byte_ceiling"])
    expected_reserve = int(policy["capacity"]["retained_reserve_bytes"])
    if (
        root.filesystem_type != expected_filesystem
        or root.byte_ceiling != expected_ceiling
        or root.reserve_bytes != expected_reserve
    ):
        raise AtlasError("verified retained root differs from its current policy semantics")
    return {
        "decision": policy["retained_storage"]["decision"],
        "root_identity_sha256": root.identity_sha256,
        "filesystem_type": root.filesystem_type,
        "byte_ceiling": root.byte_ceiling,
        "reserve_bytes": root.reserve_bytes,
    }


@dataclass
class _RetainedTreeBudget:
    entries: int
    bytes_seen: int


def _measure_retained_tree(descriptor: int, budget: _RetainedTreeBudget, depth: int = 0) -> None:
    if depth > MAX_RETAINED_DEPTH:
        raise ResourceLimitError("pilot retained-artifact scan exceeded its depth bound")
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    with os.scandir(descriptor) as iterator:
        entries = sorted(iterator, key=lambda item: item.name)
    for entry in entries:
        budget.entries += 1
        if budget.entries > MAX_RETAINED_ENTRIES:
            raise ResourceLimitError("pilot retained-artifact scan exceeded its entry bound")
        value = os.stat(entry.name, dir_fd=descriptor, follow_symlinks=False)
        if uid is not None and value.st_uid != uid:
            raise AtlasError("pilot retained artifact has the wrong owner")
        if stat.S_ISDIR(value.st_mode):
            if stat.S_IMODE(value.st_mode) != 0o700:
                raise AtlasError("pilot retained artifact directory must have exact mode 0700")
            child = os.open(
                entry.name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            try:
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != (value.st_dev, value.st_ino):
                    raise AtlasError("pilot retained artifact changed while opening")
                _measure_retained_tree(child, budget, depth + 1)
            finally:
                os.close(child)
        elif stat.S_ISREG(value.st_mode):
            if stat.S_IMODE(value.st_mode) != 0o600 or value.st_nlink != 1:
                raise AtlasError(
                    "pilot retained artifact files must have mode 0600 and one hard link"
                )
            budget.bytes_seen += value.st_size
            if budget.bytes_seen > MAX_STORAGE_BYTES:
                raise ResourceLimitError("pilot retained-artifact scan exceeded its safety bound")
        else:
            raise AtlasError("pilot retained storage contains a symlink or special file")


@dataclass(frozen=True)
class PilotWorkLease:
    """One marker-owned private work directory under the retained pilot root."""

    path: Path
    descriptor: int


@dataclass
class _RemovalBudget:
    entries: int
    bytes_seen: int
    maximum_bytes: int


class RetainedWriteDestination(Protocol):
    """A descriptor-pinned retained directory accepted by the write transaction."""

    @property
    def descriptor(self) -> int:
        """Return the pinned destination directory descriptor."""

    def verify(self) -> None:
        """Verify the destination and its complete pinned ancestor chain."""


@contextmanager
def _retained_root_transaction(
    root: VerifiedRetainedRoot, *, verify_identity: bool = True
) -> Iterator[None]:
    """Serialize one cooperating retained-root mutation under the sole root lock."""
    if fcntl is None:
        raise AtlasError("retained aggregate locking is unavailable on this platform")
    fcntl.flock(root.descriptor, fcntl.LOCK_EX)
    try:
        if verify_identity:
            root.verify()
        yield
    finally:
        fcntl.flock(root.descriptor, fcntl.LOCK_UN)


def _write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = os.write(descriptor, value[offset:])
        if written <= 0:
            raise AtlasError("pilot private work marker write made no progress")
        offset += written


def _sha256_descriptor(descriptor: int) -> str:
    """Hash a regular file descriptor without changing its shared offset."""
    digest = hashlib.sha256()
    offset = 0
    while block := os.pread(descriptor, 1024 * 1024, offset):
        digest.update(block)
        offset += len(block)
    return digest.hexdigest()


def _try_lock(descriptor: int) -> bool:
    if fcntl is None:
        raise AtlasError("pilot private workspaces require POSIX advisory locks")
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        return False
    return True


def _work_marker(policy: dict[str, Any], name: str, root: VerifiedPilotRoot) -> dict[str, Any]:
    return {
        "contract_version": POLICY_CONTRACT_VERSION,
        "directory_name": name,
        "magic": WORK_MARKER_MAGIC,
        "owner_uid": os.geteuid() if hasattr(os, "geteuid") else None,
        "policy_hash": policy["policy_hash"],
        "root_identity_sha256": root.identity_sha256,
    }


def _read_work_marker(descriptor: int) -> dict[str, Any] | None:
    try:
        size = os.fstat(descriptor).st_size
        if size <= 0 or size > 16_384:
            return None
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = os.read(descriptor, 16_385)
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return value if isinstance(value, dict) and len(raw) == size else None


def _remove_private_tree(descriptor: int, budget: _RemovalBudget, depth: int = 0) -> None:
    if depth > MAX_WORK_DEPTH:
        raise ResourceLimitError("pilot private-work cleanup exceeded its depth bound")
    entries: list[os.DirEntry[str]] = []
    with os.scandir(descriptor) as iterator:
        for entry in iterator:
            entries.append(entry)
            permitted = MAX_WORK_ENTRIES - budget.entries
            if depth == 0:
                permitted += 1  # The root marker is authenticated and removed separately.
            if len(entries) > permitted:
                raise ResourceLimitError("pilot private-work cleanup exceeded its entry bound")
    for entry in sorted(entries, key=lambda item: item.name):
        if entry.name == WORK_MARKER_NAME and depth == 0:
            continue
        budget.entries += 1
        if budget.entries > MAX_WORK_ENTRIES:
            raise ResourceLimitError("pilot private-work cleanup exceeded its entry bound")
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
                _remove_private_tree(child, budget, depth + 1)
                os.fsync(child)
            finally:
                os.close(child)
            os.rmdir(entry.name, dir_fd=descriptor)
        elif stat.S_ISREG(value.st_mode) or stat.S_ISLNK(value.st_mode):
            if stat.S_ISREG(value.st_mode):
                budget.bytes_seen += value.st_size
                if budget.bytes_seen > budget.maximum_bytes:
                    raise ResourceLimitError("pilot private-work cleanup exceeded its byte bound")
            os.unlink(entry.name, dir_fd=descriptor)
        else:
            raise AtlasError("pilot private work contains an unsupported special file")
        os.fsync(descriptor)


def _cleanup_work_lease(
    root: VerifiedPilotRoot,
    name: str,
    directory_fd: int,
    marker_fd: int,
    maximum_bytes: int,
) -> bool:
    try:
        root.verify(require_capacity=False)
        opened = os.fstat(directory_fd)
        current = os.stat(name, dir_fd=root.descriptor, follow_symlinks=False)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o700
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
        ):
            return False
        _remove_private_tree(directory_fd, _RemovalBudget(0, 0, maximum_bytes))
        marker_stat = os.stat(WORK_MARKER_NAME, dir_fd=directory_fd, follow_symlinks=False)
        opened_marker = os.fstat(marker_fd)
        if (
            not stat.S_ISREG(marker_stat.st_mode)
            or stat.S_IMODE(marker_stat.st_mode) != 0o600
            or (marker_stat.st_dev, marker_stat.st_ino)
            != (opened_marker.st_dev, opened_marker.st_ino)
        ):
            return False
        os.unlink(WORK_MARKER_NAME, dir_fd=directory_fd)
        os.fsync(directory_fd)
        os.rmdir(name, dir_fd=root.descriptor)
        os.fsync(root.descriptor)
        root.verify(require_capacity=False)
        return True
    except (AtlasError, OSError, ResourceLimitError, TypeError, ValueError, OverflowError):
        return False


def recover_stale_pilot_workspaces(policy: dict[str, Any], root: VerifiedPilotRoot) -> int:
    """Boundedly remove only inactive, marker-authenticated workspaces for this policy."""
    root.verify(require_capacity=False)
    maximum_bytes = int(policy["capacity"]["temporary_byte_ceiling"])
    candidates: list[str] = []
    with os.scandir(root.descriptor) as iterator:
        for scanned, entry in enumerate(iterator, 1):
            if scanned > MAX_STALE_SCAN:
                break
            if WORK_DIRECTORY_PATTERN.fullmatch(entry.name):
                candidates.append(entry.name)
    candidates.sort()
    removed = 0
    for name in candidates:
        if removed >= MAX_STALE_REMOVALS:
            break
        directory_fd: int | None = None
        marker_fd: int | None = None
        try:
            directory_fd = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root.descriptor,
            )
            marker_fd = os.open(
                WORK_MARKER_NAME,
                os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            if not _try_lock(marker_fd):
                continue
            marker = _read_work_marker(marker_fd)
            if marker != _work_marker(policy, name, root):
                continue
            if _cleanup_work_lease(root, name, directory_fd, marker_fd, maximum_bytes):
                removed += 1
        except (AtlasError, OSError, ResourceLimitError, TypeError, ValueError, OverflowError):
            continue
        finally:
            if marker_fd is not None:
                os.close(marker_fd)
            if directory_fd is not None:
                os.close(directory_fd)
    return removed


@contextmanager
def private_pilot_workspace(
    policy: dict[str, Any], root: VerifiedPilotRoot
) -> Iterator[PilotWorkLease]:
    """Create, retain, and safely clean one policy-bound private work directory."""
    root.verify()
    recover_stale_pilot_workspaces(policy, root)
    name: str | None = None
    directory_fd: int | None = None
    marker_fd: int | None = None
    try:
        for _ in range(8):
            candidate = f"pilot-work-{secrets.token_hex(16)}"
            try:
                os.mkdir(candidate, 0o700, dir_fd=root.descriptor)
            except FileExistsError:
                continue
            name = candidate
            break
        if name is None:
            raise AtlasError("pilot private workspace allocation failed")
        directory_fd = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root.descriptor,
        )
        os.fchmod(directory_fd, 0o700)
        marker_fd = os.open(
            WORK_MARKER_NAME,
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        os.fchmod(marker_fd, 0o600)
        if not _try_lock(marker_fd):
            raise AtlasError("pilot private workspace lock could not be acquired")
        _write_all(
            marker_fd,
            (json.dumps(_work_marker(policy, name, root), sort_keys=True) + "\n").encode(),
        )
        os.fsync(marker_fd)
        os.fsync(directory_fd)
        os.fsync(root.descriptor)
        root.verify()
        yield PilotWorkLease(root.path / name, directory_fd)
    finally:
        succeeded = False
        if name is not None and directory_fd is not None and marker_fd is not None:
            succeeded = _cleanup_work_lease(
                root,
                name,
                directory_fd,
                marker_fd,
                int(policy["capacity"]["temporary_byte_ceiling"]),
            )
        if marker_fd is not None:
            os.close(marker_fd)
        if directory_fd is not None:
            os.close(directory_fd)
        if not succeeded and name is not None and sys.exc_info()[0] is None:
            raise AtlasError(
                "pilot private workspace cleanup failed; marker-aware recovery is required"
            )


@dataclass(frozen=True)
class RetainedOutputLease:
    """One no-replace retained output pinned beneath the policy-bound root."""

    path: Path
    descriptor: int
    root: VerifiedRetainedRoot
    name: str
    device: int
    inode: int

    @property
    def descriptor_path(self) -> Path:
        """Return an internal descriptor path immune to same-name replacement."""
        return Path(f"/proc/self/fd/{self.descriptor}")

    def verify(self) -> None:
        self.root.verify()
        try:
            opened = os.fstat(self.descriptor)
            retained_child = os.stat(self.name, dir_fd=self.root.descriptor, follow_symlinks=False)
            visible = os.lstat(self.path)
        except OSError as exc:
            raise AtlasError("pilot retained output identity changed") from exc
        uid = os.geteuid() if hasattr(os, "geteuid") else None
        expected = (self.device, self.inode)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o700
            or stat.S_IMODE(retained_child.st_mode) != 0o700
            or stat.S_IMODE(visible.st_mode) != 0o700
            or (opened.st_dev, opened.st_ino) != expected
            or (retained_child.st_dev, retained_child.st_ino) != expected
            or (visible.st_dev, visible.st_ino) != expected
            or (
                uid is not None
                and any(item.st_uid != uid for item in (opened, retained_child, visible))
            )
        ):
            raise AtlasError("pilot retained output identity, owner, or permissions changed")

    def _ensure_additional_capacity_locked(self, byte_count: int, aggregate: int) -> None:
        """Check one write while the caller holds the sole retained-root lock."""
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
            raise AtlasError("retained write size must be a nonnegative integer")
        if byte_count > self.root.byte_ceiling - aggregate:
            raise ResourceLimitError("pilot retained write would exceed its aggregate byte ceiling")
        capacity = os.fstatvfs(self.root.descriptor)
        available = capacity.f_bavail * capacity.f_frsize
        if available < byte_count + self.root.reserve_bytes:
            raise ResourceLimitError("pilot retained write lacks policy-required free capacity")

    def write_bounded_bytes(self, name: str, value: bytes) -> None:
        """Create one direct private file in a complete retained-root transaction."""
        self.write_bounded_bytes_to(self, name, value)

    def write_bounded_bytes_to(
        self,
        destination: RetainedWriteDestination,
        name: str,
        value: bytes,
    ) -> None:
        """Create one direct or nested file while capacity and placement stay locked."""
        if not isinstance(name, str) or not RETAINED_OUTPUT_PATTERN.fullmatch(name):
            raise AtlasError("retained artifact name is invalid")
        if not isinstance(value, bytes):
            raise AtlasError("retained artifact payload must be bytes")
        descriptor: int | None = None
        identity: tuple[int, int] | None = None
        created = False
        with _retained_root_transaction(self.root):
            self.verify()
            destination.verify()
            aggregate_before = self.root.measure_aggregate_bytes()
            self._ensure_additional_capacity_locked(len(value), aggregate_before)
            try:
                flags = (
                    os.O_RDWR
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                descriptor = os.open(name, flags, 0o600, dir_fd=destination.descriptor)
                created = True
                opened = os.fstat(descriptor)
                identity = (opened.st_dev, opened.st_ino)
                visible_created = os.stat(
                    name, dir_fd=destination.descriptor, follow_symlinks=False
                )
                if (visible_created.st_dev, visible_created.st_ino) != identity:
                    raise AtlasError("retained artifact changed while opening")
                os.fchmod(descriptor, 0o600)
                _write_all(descriptor, value)
                os.fsync(descriptor)
                written = os.fstat(descriptor)
                visible = os.stat(name, dir_fd=destination.descriptor, follow_symlinks=False)
                if (
                    (visible.st_dev, visible.st_ino) != identity
                    or not stat.S_ISREG(written.st_mode)
                    or stat.S_IMODE(written.st_mode) != 0o600
                    or written.st_nlink != 1
                    or written.st_size != len(value)
                    or hashlib.sha256(value).hexdigest() != _sha256_descriptor(descriptor)
                ):
                    raise AtlasError("retained artifact changed during its bounded write")
                destination.verify()
                self.verify()
                aggregate_after = self.root.measure_aggregate_bytes()
                if aggregate_after != aggregate_before + len(value):
                    raise AtlasError("retained aggregate changed during its bounded write")
                os.fsync(destination.descriptor)
                os.fsync(self.descriptor)
                os.fsync(self.root.descriptor)
            except BaseException:
                if created:
                    if identity is None:
                        self._rollback_preidentity_created_file_locked(destination, name)
                    else:
                        self._rollback_created_file_locked(destination, name, identity)
                if descriptor is not None:
                    os.close(descriptor)
                    descriptor = None
                raise
            finally:
                if descriptor is not None:
                    os.close(descriptor)

    def copy_bounded_file_to(
        self,
        destination: RetainedWriteDestination,
        name: str,
        source: Path,
        *,
        expected_sha256: str,
        expected_size: int,
    ) -> int:
        """Copy one immutable file into retained storage under the root transaction."""
        if not isinstance(name, str) or not RETAINED_OUTPUT_PATTERN.fullmatch(name):
            raise AtlasError("retained artifact name is invalid")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
        ):
            raise AtlasError("retained copy size must be a nonnegative integer")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise AtlasError("retained copy SHA-256 is invalid")
        source_descriptor: int | None = None
        destination_descriptor: int | None = None
        destination_identity: tuple[int, int] | None = None
        created = False
        source_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        with _retained_root_transaction(self.root):
            self.verify()
            destination.verify()
            aggregate_before = self.root.measure_aggregate_bytes()
            self._ensure_additional_capacity_locked(expected_size, aggregate_before)
            try:
                source_before = os.lstat(source)
                if not stat.S_ISREG(source_before.st_mode):
                    raise AtlasError("pilot derivative source must be a regular non-symlink file")
                source_descriptor = os.open(source, source_flags)
                source_opened = os.fstat(source_descriptor)
                if (source_opened.st_dev, source_opened.st_ino) != (
                    source_before.st_dev,
                    source_before.st_ino,
                ) or source_opened.st_size != expected_size:
                    raise AtlasError("pilot derivative source differs from its frozen identity")
                destination_descriptor = os.open(
                    name,
                    os.O_RDWR
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=destination.descriptor,
                )
                created = True
                destination_opened = os.fstat(destination_descriptor)
                destination_identity = (
                    destination_opened.st_dev,
                    destination_opened.st_ino,
                )
                visible_created = os.stat(
                    name, dir_fd=destination.descriptor, follow_symlinks=False
                )
                if (
                    visible_created.st_dev,
                    visible_created.st_ino,
                ) != destination_identity:
                    raise AtlasError("pilot derivative destination changed while opening")
                os.fchmod(destination_descriptor, 0o600)
                digest = hashlib.sha256()
                total = 0
                while block := os.read(source_descriptor, 1024 * 1024):
                    total += len(block)
                    if total > expected_size:
                        raise ResourceLimitError(
                            "pilot derivative source exceeded its bounded size"
                        )
                    digest.update(block)
                    _write_all(destination_descriptor, block)
                os.fsync(destination_descriptor)
                source_after = os.fstat(source_descriptor)
                source_current = os.lstat(source)
                source_identities = {
                    (
                        value.st_dev,
                        value.st_ino,
                        value.st_mode,
                        value.st_uid,
                        value.st_size,
                        value.st_mtime_ns,
                        value.st_ctime_ns,
                    )
                    for value in (source_before, source_opened, source_after, source_current)
                }
                completed = os.fstat(destination_descriptor)
                visible = os.stat(name, dir_fd=destination.descriptor, follow_symlinks=False)
                if (
                    len(source_identities) != 1
                    or total != expected_size
                    or digest.hexdigest() != expected_sha256
                    or (completed.st_dev, completed.st_ino) != destination_identity
                    or (visible.st_dev, visible.st_ino) != destination_identity
                    or not stat.S_ISREG(completed.st_mode)
                    or stat.S_IMODE(completed.st_mode) != 0o600
                    or completed.st_nlink != 1
                    or completed.st_size != expected_size
                    or _sha256_descriptor(destination_descriptor) != expected_sha256
                ):
                    raise AtlasError("pilot derivative changed during its retained transaction")
                destination.verify()
                self.verify()
                aggregate_after = self.root.measure_aggregate_bytes()
                if aggregate_after != aggregate_before + expected_size:
                    raise AtlasError("retained aggregate changed during its bounded copy")
                os.fsync(destination.descriptor)
                os.fsync(self.descriptor)
                os.fsync(self.root.descriptor)
                return total
            except OSError as exc:
                if created:
                    if destination_identity is None:
                        self._rollback_preidentity_created_file_locked(destination, name)
                    else:
                        self._rollback_created_file_locked(destination, name, destination_identity)
                if destination_descriptor is not None:
                    os.close(destination_descriptor)
                    destination_descriptor = None
                if source_descriptor is not None:
                    os.close(source_descriptor)
                    source_descriptor = None
                raise AtlasError("pilot derivative could not be copied safely") from exc
            except BaseException:
                if created:
                    if destination_identity is None:
                        self._rollback_preidentity_created_file_locked(destination, name)
                    else:
                        self._rollback_created_file_locked(destination, name, destination_identity)
                if destination_descriptor is not None:
                    os.close(destination_descriptor)
                    destination_descriptor = None
                if source_descriptor is not None:
                    os.close(source_descriptor)
                    source_descriptor = None
                raise
            finally:
                if destination_descriptor is not None:
                    os.close(destination_descriptor)
                if source_descriptor is not None:
                    os.close(source_descriptor)

    def _rollback_created_file_locked(
        self,
        destination: RetainedWriteDestination,
        name: str,
        identity: tuple[int, int],
    ) -> None:
        """Remove only the inode created by the current still-locked transaction."""
        try:
            current = os.stat(name, dir_fd=destination.descriptor, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != identity:
                raise AtlasError("retained transaction rollback found a replaced inode")
            os.unlink(name, dir_fd=destination.descriptor)
            os.fsync(destination.descriptor)
            self.root.measure_aggregate_bytes()
        except OSError as exc:
            raise AtlasError("retained transaction rollback failed") from exc

    def _rollback_preidentity_created_file_locked(
        self,
        destination: RetainedWriteDestination,
        name: str,
    ) -> None:
        """Remove the private empty file created after O_EXCL but before fstat."""
        try:
            current = os.stat(name, dir_fd=destination.descriptor, follow_symlinks=False)
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) & 0o077
                or current.st_nlink != 1
                or current.st_size != 0
            ):
                raise AtlasError("retained pre-identity rollback found an unsafe replacement")
            os.unlink(name, dir_fd=destination.descriptor)
            os.fsync(destination.descriptor)
            self.root.measure_aggregate_bytes()
        except OSError as exc:
            raise AtlasError("retained pre-identity transaction rollback failed") from exc

    @contextmanager
    def serialized_mutation(self) -> Iterator[None]:
        """Hold the sole retained-root lock for a caller-verified directory mutation."""
        with _retained_root_transaction(self.root):
            self.verify()
            yield


def _remove_retained_contents(descriptor: int, budget: _RemovalBudget, depth: int = 0) -> None:
    if depth > MAX_RETAINED_DEPTH:
        raise ResourceLimitError("pilot retained-output cleanup exceeded its depth bound")
    with os.scandir(descriptor) as iterator:
        entries = sorted(iterator, key=lambda item: item.name)
    for entry in entries:
        budget.entries += 1
        if budget.entries > MAX_RETAINED_ENTRIES:
            raise ResourceLimitError("pilot retained-output cleanup exceeded its entry bound")
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
                _remove_retained_contents(child, budget, depth + 1)
                os.fsync(child)
            finally:
                os.close(child)
            os.rmdir(entry.name, dir_fd=descriptor)
        elif stat.S_ISREG(value.st_mode) or stat.S_ISLNK(value.st_mode):
            if stat.S_ISREG(value.st_mode):
                budget.bytes_seen += value.st_size
                if budget.bytes_seen > budget.maximum_bytes:
                    raise ResourceLimitError(
                        "pilot retained-output cleanup exceeded its byte bound"
                    )
            os.unlink(entry.name, dir_fd=descriptor)
        else:
            raise AtlasError("pilot retained output contains an unsupported special file")
        os.fsync(descriptor)


def _find_retained_child_name(root_descriptor: int, device: int, inode: int) -> str | None:
    with os.scandir(root_descriptor) as iterator:
        entries = sorted(iterator, key=lambda item: item.name)
    if len(entries) > MAX_RETAINED_ENTRIES:
        raise ResourceLimitError("pilot retained-root recovery exceeded its entry bound")
    for entry in entries:
        value = os.stat(entry.name, dir_fd=root_descriptor, follow_symlinks=False)
        if (value.st_dev, value.st_ino) == (device, inode):
            return entry.name
    return None


def _cleanup_retained_output(lease: RetainedOutputLease, maximum_bytes: int) -> bool:
    try:
        opened_root = os.fstat(lease.root.descriptor)
        if (opened_root.st_dev, opened_root.st_ino) != (
            lease.root.device,
            lease.root.inode,
        ):
            return False
        _remove_retained_contents(
            lease.descriptor,
            _RemovalBudget(entries=0, bytes_seen=0, maximum_bytes=maximum_bytes),
        )
        actual_name = _find_retained_child_name(lease.root.descriptor, lease.device, lease.inode)
        if actual_name is None:
            return False
        os.rmdir(actual_name, dir_fd=lease.root.descriptor)
        os.fsync(lease.root.descriptor)
        return True
    except (AtlasError, OSError, ResourceLimitError, TypeError, ValueError, OverflowError):
        return False


def _validate_retained_output_path(root: VerifiedRetainedRoot, output: Path) -> None:
    if not output.is_absolute() or not RETAINED_OUTPUT_PATTERN.fullmatch(output.name):
        raise AtlasError("pilot retained output must be an absolute direct-child path")
    try:
        if output.parent != root.path or output.parent.resolve(strict=True) != root.path:
            raise AtlasError("pilot retained output must be a direct child of its policy root")
    except OSError as exc:
        raise AtlasError("pilot retained output parent is unavailable") from exc


@contextmanager
def retained_output_directory(
    policy: dict[str, Any], root: VerifiedRetainedRoot, output: Path
) -> Iterator[RetainedOutputLease]:
    """Create one policy-bound retained directory without path replacement."""
    require_current_pilot_security_policy(policy)
    ensure_pilot_security_policy_current(policy)
    root.verify()
    _validate_retained_output_path(root, output)
    descriptor: int | None = None
    lease: RetainedOutputLease | None = None
    directory_created = False
    created_identity: tuple[int, int] | None = None
    placement_committed = False
    committed = False
    try:
        with _retained_root_transaction(root):
            try:
                aggregate_before = root.measure_aggregate_bytes()
                try:
                    os.stat(output.name, dir_fd=root.descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise AtlasError("pilot retained output could not be checked safely") from exc
                else:
                    raise AtlasError("pilot retained output must not already exist")
                os.mkdir(output.name, 0o700, dir_fd=root.descriptor)
                directory_created = True
                created = os.stat(output.name, dir_fd=root.descriptor, follow_symlinks=False)
                created_identity = (created.st_dev, created.st_ino)
                os.fsync(root.descriptor)
                descriptor = os.open(
                    output.name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=root.descriptor,
                )
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != created_identity:
                    raise AtlasError("pilot retained output changed while opening")
                lease = RetainedOutputLease(
                    path=output,
                    descriptor=descriptor,
                    root=root,
                    name=output.name,
                    device=opened.st_dev,
                    inode=opened.st_ino,
                )
                os.fchmod(descriptor, 0o700)
                lease.verify()
                if root.measure_aggregate_bytes() != aggregate_before:
                    raise AtlasError("retained bytes appeared during output placement")
                os.fsync(descriptor)
                os.fsync(root.descriptor)
                placement_committed = True
            except BaseException as placement_error:
                rollback_succeeded = True
                if lease is not None:
                    rollback_succeeded = _cleanup_retained_output(
                        lease, int(policy["capacity"]["retained_byte_ceiling"])
                    )
                elif directory_created:
                    try:
                        current = os.stat(
                            output.name,
                            dir_fd=root.descriptor,
                            follow_symlinks=False,
                        )
                        current_identity = (current.st_dev, current.st_ino)
                        if created_identity is not None and current_identity != created_identity:
                            rollback_succeeded = False
                        else:
                            os.rmdir(output.name, dir_fd=root.descriptor)
                            os.fsync(root.descriptor)
                    except OSError:
                        rollback_succeeded = False
                lease = None
                created_identity = None
                if not rollback_succeeded:
                    raise AtlasError(
                        "pilot retained-output placement rollback failed"
                    ) from placement_error
                raise
        if lease is None:
            raise AtlasError("pilot retained-output placement did not produce a lease")
        yield lease
        with _retained_root_transaction(root):
            lease.verify()
            os.fsync(descriptor)
        committed = True
    finally:
        cleaned = True
        if placement_committed and not committed and lease is not None:
            try:
                with _retained_root_transaction(root, verify_identity=False):
                    cleaned = _cleanup_retained_output(
                        lease, int(policy["capacity"]["retained_byte_ceiling"])
                    )
            except (AtlasError, OSError, ResourceLimitError):
                cleaned = False
        elif placement_committed and not committed and created_identity is not None:
            try:
                with _retained_root_transaction(root, verify_identity=False):
                    current = os.stat(
                        output.name,
                        dir_fd=root.descriptor,
                        follow_symlinks=False,
                    )
                    if (current.st_dev, current.st_ino) != created_identity:
                        cleaned = False
                    else:
                        os.rmdir(output.name, dir_fd=root.descriptor)
                        os.fsync(root.descriptor)
            except OSError:
                cleaned = False
        if descriptor is not None:
            os.close(descriptor)
        if not committed and not cleaned and sys.exc_info()[0] is None:
            raise AtlasError("pilot retained-output cleanup failed")


@contextmanager
def open_retained_output_directory(
    policy: dict[str, Any], root: VerifiedRetainedRoot, output: Path
) -> Iterator[RetainedOutputLease]:
    """Pin one existing policy-bound retained package for a complete operation."""
    require_current_pilot_security_policy(policy)
    ensure_pilot_security_policy_current(policy)
    root.verify()
    _validate_retained_output_path(root, output)
    with _retained_root_transaction(root):
        try:
            descriptor = os.open(
                output.name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root.descriptor,
            )
        except OSError as exc:
            raise AtlasError("pilot retained package could not be opened safely") from exc
        opened = os.fstat(descriptor)
        lease = RetainedOutputLease(
            path=output,
            descriptor=descriptor,
            root=root,
            name=output.name,
            device=opened.st_dev,
            inode=opened.st_ino,
        )
        lease.verify()
    try:
        yield lease
        with _retained_root_transaction(root):
            lease.verify()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def open_verified_pilot_root(policy: dict[str, Any]) -> Iterator[VerifiedPilotRoot]:
    require_current_pilot_security_policy(policy)
    root_record = policy["private_root"]
    path = Path(root_record["path"])
    measured = _root_measurement(path)
    if (
        measured["device"] != root_record["expected_device"]
        or measured["inode"] != root_record["expected_inode"]
        or measured["owner_uid"] != root_record["expected_uid"]
        or measured["mode"] != root_record["expected_mode"]
        or measured["filesystem_type"] != policy["storage"]["expected_filesystem_type"]
        or measured["mount_identity_sha256"] != root_record["mount_identity_sha256"]
    ):
        raise AtlasError("pilot private root no longer matches its policy-bound identity")
    required = sum(
        int(policy["capacity"][field])
        for field in ("source_byte_ceiling", "temporary_byte_ceiling", "reserve_bytes")
    )
    if (
        policy["private_root"]["mount_identity_sha256"]
        == policy["retained_root"]["mount_identity_sha256"]
    ):
        required += int(policy["capacity"]["retained_byte_ceiling"]) + int(
            policy["capacity"]["retained_reserve_bytes"]
        )
    if measured["available_bytes"] < required:
        raise ResourceLimitError("pilot private root lacks the policy-required free capacity")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AtlasError("pilot private root could not be opened without following links") from exc
    handle = VerifiedPilotRoot(
        path=path,
        descriptor=descriptor,
        device=measured["device"],
        inode=measured["inode"],
        owner_uid=measured["owner_uid"],
        filesystem_type=measured["filesystem_type"],
        mount_identity_sha256=measured["mount_identity_sha256"],
        available_bytes=measured["available_bytes"],
        required_free_bytes=required,
    )
    try:
        handle.verify()
        yield handle
        handle.verify()
    finally:
        os.close(descriptor)


@contextmanager
def open_verified_retained_root(
    policy: dict[str, Any],
) -> Iterator[VerifiedRetainedRoot]:
    """Open and retain the exact policy-bound private retained-artifact root."""
    require_current_pilot_security_policy(policy)
    ensure_pilot_security_policy_current(policy)
    root_record = policy["retained_root"]
    path = Path(root_record["path"])
    measured = _root_measurement(path, label="pilot retained root")
    if (
        measured["device"] != root_record["expected_device"]
        or measured["inode"] != root_record["expected_inode"]
        or measured["owner_uid"] != root_record["expected_uid"]
        or measured["mode"] != root_record["expected_mode"]
        or measured["filesystem_type"] != policy["retained_storage"]["expected_filesystem_type"]
        or measured["mount_identity_sha256"] != root_record["mount_identity_sha256"]
    ):
        raise AtlasError("pilot retained root no longer matches its policy-bound identity")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AtlasError("pilot retained root could not be opened without following links") from exc
    shared_ceiling: int | None = None
    shared_reserve = 0
    if (
        policy["private_root"]["mount_identity_sha256"]
        == policy["retained_root"]["mount_identity_sha256"]
    ):
        shared_ceiling = sum(
            int(policy["capacity"][field])
            for field in (
                "source_byte_ceiling",
                "temporary_byte_ceiling",
                "retained_byte_ceiling",
            )
        )
        shared_reserve = int(policy["capacity"]["reserve_bytes"]) + int(
            policy["capacity"]["retained_reserve_bytes"]
        )
    handle = VerifiedRetainedRoot(
        path=path,
        descriptor=descriptor,
        device=measured["device"],
        inode=measured["inode"],
        owner_uid=measured["owner_uid"],
        filesystem_type=measured["filesystem_type"],
        mount_identity_sha256=measured["mount_identity_sha256"],
        available_bytes=measured["available_bytes"],
        byte_ceiling=int(policy["capacity"]["retained_byte_ceiling"]),
        reserve_bytes=int(policy["capacity"]["retained_reserve_bytes"]),
        shared_capacity_ceiling=shared_ceiling,
        shared_reserve_bytes=shared_reserve,
    )
    try:
        handle.verify()
        yield handle
        handle.verify()
    finally:
        os.close(descriptor)


def source_rights_aggregate(records: list[dict[str, Any]]) -> str:
    normalized = sorted(
        (
            str(item["source_id"]),
            str(item["source_sha256"]),
            str(item["rights_manifest_hash"]),
        )
        for item in records
    )
    return hashlib.sha256(canonical_json(normalized).encode()).hexdigest()


def policy_resource_limits(value: NativeResourceLimits) -> dict[str, int]:
    """Convert the typed native limits to the stable policy vocabulary."""
    return {
        "wall_timeout_seconds": int(value.wall_seconds),
        "cpu_time_seconds": int(value.cpu_seconds),
        "address_space_bytes": int(value.address_space_bytes),
        "output_file_size_bytes": int(value.file_size_bytes),
        "open_files": int(value.open_files),
        "process_count": int(value.process_count),
        "core_dump_bytes": 0,
        "capture_bytes": int(max(value.stdout_bytes, value.stderr_bytes)),
        "cleanup_timeout_seconds": max(1, int(value.termination_grace_seconds)),
    }


def native_limits_from_policy(policy: dict[str, Any]) -> NativeResourceLimits:
    """Build the centralized runner's immutable limits from a validated policy."""
    from av_atlas.native_process import NativeResourceLimits

    value = policy["resource_limits"]
    capture = int(value["capture_bytes"])
    return NativeResourceLimits(
        wall_seconds=float(value["wall_timeout_seconds"]),
        cpu_seconds=int(value["cpu_time_seconds"]),
        address_space_bytes=int(value["address_space_bytes"]),
        file_size_bytes=int(value["output_file_size_bytes"]),
        open_files=int(value["open_files"]),
        process_count=int(value["process_count"]),
        stdout_bytes=capture,
        stderr_bytes=capture,
        termination_grace_seconds=float(value["cleanup_timeout_seconds"]),
    )


def verify_sandbox_policy(policy: dict[str, Any], inventory: dict[str, Any]) -> None:
    """Require the current host to match the exact policy-approved Bubblewrap identity."""
    expected = policy["sandbox"]
    executable = inventory.get("executable")
    smoke = inventory.get("capability_smoke")
    if (
        inventory.get("state") != "available"
        or not isinstance(executable, dict)
        or inventory.get("profile_version") != expected["profile_contract_version"]
        or inventory.get("profile_sha256") != expected["profile_sha256"]
        or executable.get("basename") != expected["executable_basename"]
        or executable.get("sha256") != expected["executable_sha256"]
        or executable.get("size_bytes") != expected["executable_size_bytes"]
        or inventory.get("dependency_identity_sha256") != expected["dependency_identity_sha256"]
        or inventory.get("version") != expected["version"]
        or not isinstance(smoke, dict)
        or not smoke.get("passed")
    ):
        raise AtlasError("current Bubblewrap identity or capability differs from pilot policy")


def receipt_capability(
    inventory: dict[str, Any], hostile_probes: dict[str, bool]
) -> dict[str, bool]:
    smoke = inventory.get("capability_smoke")
    if not isinstance(smoke, dict):
        raise AtlasError("Bubblewrap capability smoke is missing")
    required_probes = {
        "outside_sentinel_denied",
        "outside_host_write_denied",
        "outside_root_write_denied",
        "device_directory_write_denied",
        "work_write_allowed",
        "tmp_write_allowed",
        "loopback_network_denied",
        "external_network_denied",
        "home_directory_denied",
        "inherited_environment_denied",
        "hostname_sanitized",
        "outside_write_positive_control",
        "masked_runtime_sentinel_denied",
    }
    if set(hostile_probes) != required_probes or not all(hostile_probes.values()):
        raise AtlasError("mandatory hostile sandbox probe did not prove every isolation property")
    return {
        "namespace_smoke_test_passed": bool(smoke.get("passed")),
        "network_denied": bool(
            hostile_probes["loopback_network_denied"] and hostile_probes["external_network_denied"]
        ),
        "external_sentinel_denied": hostile_probes["outside_sentinel_denied"],
        "mutable_runtime_subtree_denied": hostile_probes["masked_runtime_sentinel_denied"],
        "outside_write_denied": bool(
            hostile_probes["outside_write_positive_control"]
            and hostile_probes["outside_host_write_denied"]
            and hostile_probes["outside_root_write_denied"]
            and hostile_probes["device_directory_write_denied"]
        ),
    }


def make_security_receipt(
    *,
    policy: dict[str, Any],
    root: VerifiedPilotRoot,
    retained_root: VerifiedRetainedRoot,
    stage: str,
    source_rights_aggregate_sha256: str,
    sandbox_inventory: dict[str, Any],
    capability: dict[str, bool],
    cleanup_succeeded: bool,
    output_binding_sha256: str | None = None,
) -> dict[str, Any]:
    """Create a path-free receipt; the private policy itself is never exported."""
    ensure_pilot_security_execution_boundary(policy, root)
    retained_aggregate_bytes = retained_root.verify()
    if stage == "ocr-complete":
        if not isinstance(output_binding_sha256, str) or not re.fullmatch(
            r"[a-f0-9]{64}", output_binding_sha256
        ):
            raise AtlasError("OCR-complete receipt requires its exact output binding")
    elif output_binding_sha256 is not None:
        raise AtlasError("output binding is only supported for an OCR-complete receipt")
    executable = sandbox_inventory["executable"]
    package = sandbox_inventory.get("package")
    if not isinstance(package, dict):
        package = {}
    package_identity = (
        f"{package.get('package')}:{package.get('architecture')} {package.get('version')}"
        if package
        else None
    )
    source_identity = (
        f"{package.get('source_package')} {package.get('source_version')}" if package else None
    )
    license_verification = (
        "installed-package-metadata-read"
        if package.get("license_verification") == "read installed package copyright metadata"
        else "unverified"
    )
    exposed_host_subtrees = sandbox_inventory.get("exposed_host_subtrees")
    masked_host_subtrees = sandbox_inventory.get("masked_host_subtrees")
    if (
        not isinstance(exposed_host_subtrees, list)
        or not exposed_host_subtrees
        or not all(isinstance(item, str) for item in exposed_host_subtrees)
        or not isinstance(masked_host_subtrees, list)
        or not masked_host_subtrees
        or not all(isinstance(item, str) for item in masked_host_subtrees)
    ):
        raise AtlasError("Bubblewrap inventory lacks its sanitized runtime mount policy")
    value: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "contract_version": RECEIPT_CONTRACT_VERSION,
        "stage": stage,
        "measured_at": _utc_now().isoformat(),
        "pilot_id": policy["pilot_id"],
        "policy_sha256": policy["policy_hash"],
        "pilot_spec_sha256": policy["pilot_spec_sha256"],
        "pilot_spec_size_bytes": policy["pilot_spec_size_bytes"],
        "source_rights_aggregate_sha256": source_rights_aggregate_sha256,
        "output_binding_sha256": output_binding_sha256,
        "root_identity_sha256": root.identity_sha256,
        "filesystem_type": root.filesystem_type,
        "storage": {
            "decision": policy["storage"]["decision"],
            "available_bytes": root.available_bytes,
            "required_bytes": root.required_free_bytes,
            "reserve_bytes": policy["capacity"]["reserve_bytes"],
            "root_identity_verified": True,
            "owner_verified": True,
            "mode_verified": True,
            "local_filesystem_verified": True,
            "capacity_verified": root.available_bytes >= root.required_free_bytes,
        },
        "retained_storage": {
            "decision": policy["retained_storage"]["decision"],
            "root_identity_sha256": retained_root.identity_sha256,
            "filesystem_type": retained_root.filesystem_type,
            "available_bytes": retained_root.available_bytes,
            "aggregate_bytes": retained_aggregate_bytes,
            "byte_ceiling": retained_root.byte_ceiling,
            "reserve_bytes": retained_root.reserve_bytes,
            "root_identity_verified": True,
            "owner_verified": True,
            "mode_verified": True,
            "local_filesystem_verified": True,
            "capacity_verified": True,
            "private_path_exported": False,
        },
        "sandbox": {
            "provider": "bubblewrap",
            "profile_contract_version": policy["sandbox"]["profile_contract_version"],
            "profile_sha256": policy["sandbox"]["profile_sha256"],
            "dependency_identity_sha256": sandbox_inventory["dependency_identity_sha256"],
            "executable_basename": executable["basename"],
            "executable_sha256": executable["sha256"],
            "executable_size_bytes": executable["size_bytes"],
            "version": sandbox_inventory["version"],
            "package_identity": package_identity,
            "source_identity": source_identity,
            "license_id": package.get("license_id", "unknown-not-verified"),
            "license_verification": license_verification,
            "capability_smoke_test_passed": True,
            "namespaces": {
                "network": True,
                "user": True,
                "pid": True,
                "ipc": True,
                "uts": True,
                "mount": True,
            },
            "capabilities_dropped": True,
            "environment_cleared": True,
            "home_exposed": False,
            "whole_root_bound": False,
            "input_read_only": True,
            "output_only_writable": True,
            "private_tmp": True,
            "exposed_host_subtrees": list(exposed_host_subtrees),
            "masked_host_subtrees": list(masked_host_subtrees),
        },
        "resource_limits": policy["resource_limits"],
        "capability": capability,
        "lifecycle": {
            "cleanup_method": "logical-unlink-and-directory-removal",
            "cleanup_outcome": (
                "logical-deletion-complete" if cleanup_succeeded else "marker-recovery-required"
            ),
            "logical_deletion": True,
            "secure_erasure_claimed": False,
            "bounded_stale_recovery": True,
        },
        "privacy": {
            "private_paths_exported": False,
            "original_path_exported": False,
            "snapshot_path_exported": False,
            "user_identity_exported": False,
            "hostname_exported": False,
            "raw_environment_exported": False,
        },
        "receipt_hash": "",
    }
    value["receipt_hash"] = _digest(value, "receipt_hash")
    validate_instance("pilot_security_receipt", value, "pilot security receipt")
    return value


def validate_security_receipt(
    value: dict[str, Any],
    *,
    policy_hash: str | None = None,
    pilot_spec_sha256: str | None = None,
) -> None:
    validate_instance("pilot_security_receipt", value, "pilot security receipt")
    if value.get("receipt_hash") != _digest(value, "receipt_hash"):
        raise AtlasError("pilot security receipt checksum mismatch")
    if policy_hash is not None and value.get("policy_sha256") != policy_hash:
        raise AtlasError("pilot security receipt is linked to another policy")
    if pilot_spec_sha256 is not None and value.get("pilot_spec_sha256") != pilot_spec_sha256:
        raise AtlasError("pilot security receipt is linked to another pilot specification")
    if any(not value["capability"].get(field, False) for field in value["capability"]):
        raise AtlasError("pilot security receipt does not prove the mandatory sandbox capability")
