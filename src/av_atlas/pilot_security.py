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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from av_atlas.native_process import NativeResourceLimits
    from av_atlas.stable_input import VerifiedPrivateRoot as StableInputPrivateRoot

try:  # pragma: no cover - exercised on the supported Linux pilot host
    import fcntl
except ImportError:  # pragma: no cover - fail-closed non-POSIX fallback
    fcntl = None  # type: ignore[assignment]

from av_atlas.errors import AtlasError, ResourceLimitError
from av_atlas.io import canonical_json, write_json_new
from av_atlas.schemas import validate_instance

POLICY_SCHEMA_VERSION = "1.0.0"
POLICY_CONTRACT_VERSION = "av-atlas-pilot-security-policy/1.0.0"
RECEIPT_SCHEMA_VERSION = "1.0.0"
RECEIPT_CONTRACT_VERSION = "av-atlas-pilot-security-receipt/1.0.0"
SANDBOX_PROFILE_VERSION = "av-atlas-bubblewrap-pilot/1.0.0"
MAX_POLICY_BYTES = 1_000_000
DEFAULT_MAX_SOURCE_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_MAX_TEMPORARY_BYTES = 8 * 1024 * 1024 * 1024
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


def _filesystem_record(path: Path, device: int) -> dict[str, str]:
    """Classify a Linux mount without starting a helper subprocess."""
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AtlasError("pilot private-root filesystem could not be classified") from exc
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
        raise AtlasError("pilot private-root mount is unknown and therefore unsupported")
    _, filesystem_type, identity, measured_device = max(candidates)
    if filesystem_type in REMOTE_FILESYSTEMS:
        raise AtlasError("pilot private root must not use a network or remote filesystem")
    if filesystem_type not in LOCAL_FILESYSTEMS:
        raise AtlasError(f"pilot private-root filesystem is unsupported: {filesystem_type}")
    return {
        "filesystem_type": filesystem_type,
        "mount_identity_sha256": identity,
        "device_class": measured_device,
    }


def _root_measurement(path: Path) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise AtlasError("pilot private root is unavailable") from exc
    if not path.is_absolute() or path != resolved:
        raise AtlasError("pilot private root must be an absolute, canonical, non-symlink path")
    repository_root = Path(__file__).parents[2].resolve()
    if resolved.is_relative_to(repository_root):
        raise AtlasError("pilot private root must be outside the tracked repository checkout")
    before = os.lstat(path)
    if not stat.S_ISDIR(before.st_mode):
        raise AtlasError("pilot private root must be a pre-created directory")
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    if uid is not None and before.st_uid != uid:
        raise AtlasError("pilot private root must be owned by the current operating-system user")
    if stat.S_IMODE(before.st_mode) != PRIVATE_ROOT_MODE:
        raise AtlasError("pilot private root must have exact mode 0700")
    filesystem = _filesystem_record(path, before.st_dev)
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


def _validate_storage_limits(source_bytes: int, temporary_bytes: int, reserve_bytes: int) -> None:
    values = (source_bytes, temporary_bytes, reserve_bytes)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
        raise AtlasError("pilot storage limits must be nonnegative integers")
    if source_bytes == 0 or temporary_bytes == 0:
        raise AtlasError("pilot source and temporary byte ceilings must be positive")
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


def create_pilot_security_policy(
    *,
    root: Path,
    pilot_id: str,
    pilot_spec: Path,
    output: Path,
    expires_at: str,
    storage_decision: str,
    bubblewrap_inventory: dict[str, Any],
    resource_limits: dict[str, int],
    reviewer_pseudonym: str | None = None,
    review_record: str | None = None,
    review_expires_at: str | None = None,
    compensating_controls: tuple[str, ...] = (),
    deletion_plan: str | None = None,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
    max_temporary_bytes: int = DEFAULT_MAX_TEMPORARY_BYTES,
    reserve_bytes: int = DEFAULT_RESERVE_BYTES,
) -> dict[str, Any]:
    """Create one no-overwrite, mode-0600 local policy bound to a pilot spec."""
    validate_private_policy_output_path(output)
    if _parse_timestamp(expires_at, "pilot security policy expiry") <= _utc_now():
        raise AtlasError("pilot security policy expiry must be in the future")
    root_value = preflight_pilot_security_root(
        root,
        storage_decision,
        max_source_bytes,
        max_temporary_bytes,
        reserve_bytes,
    )
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
        "storage": {
            "decision": storage_decision,
            "expected_filesystem_type": root_value["filesystem_type"],
            **review,
            "tmpfs_swap_warning_acknowledged": storage_decision == "verified-tmpfs",
            "secure_erasure_claimed": False,
        },
        "capacity": {
            "source_byte_ceiling": max_source_bytes,
            "temporary_byte_ceiling": max_temporary_bytes,
            "reserve_bytes": reserve_bytes,
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


def ensure_pilot_security_policy_current(value: dict[str, Any]) -> None:
    """Recheck expiry and review scope at bounded native-processing unit boundaries."""
    if _parse_timestamp(value.get("expires_at"), "pilot security policy expiry") <= _utc_now():
        raise AtlasError("private pilot security policy has expired")
    storage = value["storage"]
    if (
        storage["independently_reviewed"]
        and _parse_timestamp(storage["review_expires_at"], "storage review expiry") <= _utc_now()
    ):
        raise AtlasError("pilot storage review has expired")
    if storage["independently_reviewed"] and storage["review_scope"] != value["pilot_id"]:
        raise AtlasError("pilot storage review scope does not match the policy pilot")


def ensure_pilot_security_execution_boundary(
    policy: dict[str, Any], root: VerifiedPilotRoot
) -> None:
    """Recheck time-bounded authority and the retained private-root identity."""
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


def _write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = os.write(descriptor, value[offset:])
        if written <= 0:
            raise AtlasError("pilot private work marker write made no progress")
        offset += written


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


@contextmanager
def open_verified_pilot_root(policy: dict[str, Any]) -> Iterator[VerifiedPilotRoot]:
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
    }
    if set(hostile_probes) != required_probes or not all(hostile_probes.values()):
        raise AtlasError("mandatory hostile sandbox probe did not prove every isolation property")
    return {
        "namespace_smoke_test_passed": bool(smoke.get("passed")),
        "network_denied": bool(
            hostile_probes["loopback_network_denied"] and hostile_probes["external_network_denied"]
        ),
        "external_sentinel_denied": hostile_probes["outside_sentinel_denied"],
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
    stage: str,
    source_rights_aggregate_sha256: str,
    sandbox_inventory: dict[str, Any],
    capability: dict[str, bool],
    cleanup_succeeded: bool,
) -> dict[str, Any]:
    """Create a path-free receipt; the private policy itself is never exported."""
    ensure_pilot_security_execution_boundary(policy, root)
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
