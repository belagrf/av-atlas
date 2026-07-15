"""Rights-gated, parser-free acquisition of a verified private media snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised on supported Unix hosts
    import fcntl
except ImportError:  # pragma: no cover - conservative non-Unix fallback
    fcntl = None  # type: ignore[assignment]

from av_atlas.errors import AtlasError, ResourceLimitError
from av_atlas.io import source_id_from_sha256
from av_atlas.rights import AuthorizationPreflight, authorize_source_identity
from av_atlas.schemas import validate_instance

CONTRACT_VERSION = "av-atlas-stable-input/1.0.0"
SCHEMA_VERSION = "1.0.0"
DEFAULT_MAX_SOURCE_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_MAX_TEMPORARY_BYTES = 8 * 1024 * 1024 * 1024
MAX_POLICY_BYTES = 64 * 1024 * 1024 * 1024
COPY_BLOCK_BYTES = 1024 * 1024
MAX_STALE_SCAN = 64
MAX_STALE_REMOVALS = 16
MARKER_NAME = ".av-atlas-stable-input.json"
SNAPSHOT_NAME = "source.snapshot"
DIRECTORY_PATTERN = re.compile(r"^snapshot-[0-9a-f]{32}$")
MARKER_MAGIC = "av-atlas-private-stable-input"
_DIR_FD_PLATFORM_SUPPORTED = (
    all(
        function in os.supports_dir_fd
        for function in (os.open, os.mkdir, os.stat, os.unlink, os.rmdir)
    )
    and os.scandir in os.supports_fd
    and os.stat in os.supports_follow_symlinks
)


@dataclass(frozen=True)
class StableInputPolicy:
    """Bounded local resource policy for one transient snapshot."""

    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES
    max_temporary_bytes: int = DEFAULT_MAX_TEMPORARY_BYTES

    def validate(self) -> None:
        values = (self.max_source_bytes, self.max_temporary_bytes)
        if (
            any(not isinstance(value, int) or isinstance(value, bool) for value in values)
            or min(values) <= 0
        ):
            raise AtlasError("stable-input resource limits must be positive integers")
        if max(values) > MAX_POLICY_BYTES:
            raise AtlasError("stable-input byte limits may not exceed 64 GiB")


@dataclass(frozen=True)
class SourceMeasurement:
    """Parser-free identity and authorization result, without a copied derivative."""

    source_sha256: str
    source_id: str
    size_bytes: int
    authorization: AuthorizationPreflight


@dataclass(frozen=True)
class StableInput:
    """A verified private snapshot leased only for the active context."""

    snapshot_path: Path
    source_sha256: str
    source_id: str
    size_bytes: int
    authorization: AuthorizationPreflight
    receipt: dict[str, Any]


@dataclass(frozen=True)
class _SourceMetadata:
    device: int
    inode: int
    mode: int
    links: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class _PrivateLease:
    root: Path
    directory: Path
    root_fd: int
    directory_fd: int
    marker_fd: int


def _metadata(value: os.stat_result) -> _SourceMetadata:
    return _SourceMetadata(
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _current_uid() -> int | None:
    return os.geteuid() if hasattr(os, "geteuid") else None


def _require_snapshot_platform() -> None:
    if fcntl is None or not _DIR_FD_PLATFORM_SUPPORTED:
        raise AtlasError(
            "stable-input snapshots require POSIX directory-descriptor and advisory-lock support"
        )


def _open_source(source: Path, policy: StableInputPolicy) -> tuple[int, _SourceMetadata]:
    """Open a regular source without following a final symlink."""
    policy.validate()
    try:
        before_path = os.lstat(source)
    except OSError as exc:
        raise AtlasError("stable input source is unavailable") from exc
    if not stat.S_ISREG(before_path.st_mode):
        raise AtlasError("stable input source must be a regular non-symlink file")
    if (
        before_path.st_size > policy.max_source_bytes
        or before_path.st_size > policy.max_temporary_bytes
    ):
        raise ResourceLimitError(
            "source exceeds a configured stable-input source or temporary byte ceiling"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise AtlasError("stable input source could not be opened without following links") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (
            opened.st_dev,
            opened.st_ino,
        ) != (before_path.st_dev, before_path.st_ino):
            raise AtlasError("stable input source identity changed while it was opened")
        return descriptor, _metadata(opened)
    except BaseException:
        os.close(descriptor)
        raise


def _hash_descriptor(
    descriptor: int,
    policy: StableInputPolicy,
    expected_size: int,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        block = os.read(descriptor, COPY_BLOCK_BYTES)
        if not block:
            break
        total += len(block)
        if total > policy.max_source_bytes or total > expected_size:
            raise ResourceLimitError("source grew beyond its authorized stable-input boundary")
        digest.update(block)
    if total != expected_size:
        raise AtlasError("source was truncated during stable-input identity measurement")
    return digest.hexdigest(), total


def _path_metadata(source: Path) -> _SourceMetadata:
    try:
        value = os.lstat(source)
    except OSError as exc:
        raise AtlasError("stable input source path changed during acquisition") from exc
    if not stat.S_ISREG(value.st_mode):
        raise AtlasError("stable input source path became non-regular during acquisition")
    return _metadata(value)


def _verify_source_unchanged(
    descriptor: int,
    source: Path,
    expected: _SourceMetadata,
) -> None:
    try:
        descriptor_metadata = _metadata(os.fstat(descriptor))
    except OSError as exc:
        raise AtlasError("stable input source descriptor became unavailable") from exc
    if descriptor_metadata != expected or _path_metadata(source) != expected:
        raise AtlasError("source mutated or was replaced during stable-input acquisition")


def preflight_authorized_source(
    source: Path,
    rights_manifest: Path | None,
    run_mode: str,
    *,
    policy: StableInputPolicy | None = None,
    expected_source_sha256: str | None = None,
    expected_source_id: str | None = None,
    expected_manifest_hash: str | None = None,
    additional_permissions: tuple[str, ...] = (),
) -> SourceMeasurement:
    """Measure and authorize a source without creating a snapshot or invoking a parser."""
    active_policy = policy or StableInputPolicy()
    descriptor, metadata = _open_source(source, active_policy)
    try:
        source_hash, size = _hash_descriptor(descriptor, active_policy, metadata.size)
        _verify_source_unchanged(descriptor, source, metadata)
        source_id = source_id_from_sha256(source_hash)
        if expected_source_sha256 is not None and source_hash != expected_source_sha256:
            raise AtlasError("stable input does not match the run source hash")
        if expected_source_id is not None and source_id != expected_source_id:
            raise AtlasError("stable input does not match the run source ID")
        authorization = authorize_source_identity(
            source,
            source_hash,
            source_id,
            rights_manifest,
            run_mode,
            expected_manifest_hash=expected_manifest_hash,
            additional_permissions=additional_permissions,
        )
        return SourceMeasurement(source_hash, source_id, size, authorization)
    except AtlasError:
        raise
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        raise AtlasError("stable-input parser-free preflight failed safely") from exc
    finally:
        os.close(descriptor)


def _private_root(root: Path | None = None) -> Path:
    uid = _current_uid()
    selected = root or Path(tempfile.gettempdir()) / f"av-atlas-stable-input-{uid or 0}"
    try:
        selected.mkdir(mode=0o700, parents=True, exist_ok=True)
        value = os.lstat(selected)
        if not stat.S_ISDIR(value.st_mode):
            raise AtlasError("stable-input private root is not a directory")
        if uid is not None and value.st_uid != uid:
            raise AtlasError("stable-input private root has the wrong owner")
        os.chmod(selected, 0o700)
        if stat.S_IMODE(os.lstat(selected).st_mode) != 0o700:
            raise AtlasError("stable-input private root permissions are not private")
    except AtlasError:
        raise
    except OSError as exc:
        raise AtlasError("stable-input private root cannot be secured") from exc
    return selected


def _read_marker(descriptor: int) -> dict[str, Any] | None:
    try:
        size = os.fstat(descriptor).st_size
        if size <= 0 or size > 16_384:
            return None
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = os.read(descriptor, 16_385)
        if len(raw) != size:
            return None
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _valid_marker(value: dict[str, Any] | None, directory_name: str) -> bool:
    if value is None:
        return False
    return value == {
        "contract_version": CONTRACT_VERSION,
        "created_unix": value.get("created_unix"),
        "directory_name": directory_name,
        "magic": MARKER_MAGIC,
        "owner_uid": _current_uid(),
    } and isinstance(value.get("created_unix"), (int, float))


def _stat_is_private_regular(value: os.stat_result) -> bool:
    uid = _current_uid()
    return (
        stat.S_ISREG(value.st_mode)
        and stat.S_IMODE(value.st_mode) == 0o600
        and (uid is None or value.st_uid == uid)
    )


def _entry_is_private_regular(path: Path) -> bool:
    try:
        return _stat_is_private_regular(os.lstat(path))
    except OSError:
        return False


def _try_lock(descriptor: int) -> bool:
    if fcntl is None:
        return True
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        return False
    return True


def _recover_one(
    root_fd: int,
    directory_name: str,
    remaining_recovery_bytes: int,
) -> tuple[bool, int]:
    """Remove one recognized inactive stale lease without recursive traversal."""
    if fcntl is None:
        return False, 0
    directory_fd: int | None = None
    marker_fd: int | None = None
    try:
        directory_stat = os.stat(directory_name, dir_fd=root_fd, follow_symlinks=False)
        if (
            not stat.S_ISDIR(directory_stat.st_mode)
            or stat.S_IMODE(directory_stat.st_mode) != 0o700
            or (_current_uid() is not None and directory_stat.st_uid != _current_uid())
        ):
            return False, 0
        directory_fd = os.open(
            directory_name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_fd,
        )
        opened_directory = os.fstat(directory_fd)
        if (opened_directory.st_dev, opened_directory.st_ino) != (
            directory_stat.st_dev,
            directory_stat.st_ino,
        ):
            return False, 0
        with os.scandir(directory_fd) as iterator:
            entries = list(islice(iterator, 4))
        names = sorted(item.name for item in entries)
        if len(entries) > 2:
            return False, 0
        if not set(names).issubset({MARKER_NAME, SNAPSHOT_NAME}) or MARKER_NAME not in names:
            return False, 0
        marker_stat = os.stat(MARKER_NAME, dir_fd=directory_fd, follow_symlinks=False)
        if not _stat_is_private_regular(marker_stat):
            return False, 0
        marker_fd = os.open(
            MARKER_NAME,
            os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        if not _try_lock(marker_fd):
            return False, 0
        marker = _read_marker(marker_fd)
        if marker is None or not _valid_marker(marker, directory_name):
            return False, 0
        snapshot_size = 0
        if SNAPSHOT_NAME in names:
            snapshot_stat = os.stat(SNAPSHOT_NAME, dir_fd=directory_fd, follow_symlinks=False)
            if not _stat_is_private_regular(snapshot_stat):
                return False, 0
            snapshot_size = snapshot_stat.st_size
            if snapshot_size > remaining_recovery_bytes:
                return False, 0
            os.unlink(SNAPSHOT_NAME, dir_fd=directory_fd)
            os.fsync(directory_fd)
        os.unlink(MARKER_NAME, dir_fd=directory_fd)
        os.fsync(directory_fd)
        os.rmdir(directory_name, dir_fd=root_fd)
        os.fsync(root_fd)
        return True, snapshot_size
    except (OSError, KeyError, TypeError, ValueError, OverflowError):
        return False, 0
    finally:
        if marker_fd is not None:
            os.close(marker_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def recover_stale_snapshots(
    policy: StableInputPolicy | None = None,
    *,
    root: Path | None = None,
) -> int:
    """Boundedly remove only marker-recognized, inactive stale snapshot directories."""
    active_policy = policy or StableInputPolicy()
    active_policy.validate()
    _require_snapshot_platform()
    private_root = _private_root(root)
    root_fd: int | None = None
    try:
        root_fd = os.open(
            private_root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.scandir(root_fd) as iterator:
            entries = list(islice(iterator, MAX_STALE_SCAN))
        entries.sort(key=lambda item: item.name)
    except OSError as exc:
        if root_fd is not None:
            os.close(root_fd)
        raise AtlasError("stable-input stale recovery could not inspect its private root") from exc
    removed = 0
    reclaimed = 0
    try:
        for entry in entries:
            if removed >= MAX_STALE_REMOVALS or reclaimed >= MAX_POLICY_BYTES:
                break
            if not DIRECTORY_PATTERN.fullmatch(entry.name) or not entry.is_dir(
                follow_symlinks=False
            ):
                continue
            assert root_fd is not None
            did_remove, size = _recover_one(
                root_fd,
                entry.name,
                MAX_POLICY_BYTES - reclaimed,
            )
            if did_remove:
                reclaimed += size
                removed += 1
    finally:
        if root_fd is not None:
            os.close(root_fd)
    return removed


def _new_private_directory(root: Path) -> _PrivateLease:
    directory_name: str | None = None
    root_fd: int | None = None
    directory_fd: int | None = None
    marker_fd: int | None = None
    try:
        root_fd = os.open(
            root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        for _ in range(8):
            candidate = f"snapshot-{secrets.token_hex(16)}"
            try:
                os.mkdir(candidate, mode=0o700, dir_fd=root_fd)
            except FileExistsError:
                continue
            directory_name = candidate
            break
        if directory_name is None:
            raise AtlasError("stable-input unique private directory allocation failed")
        directory_fd = os.open(
            directory_name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_fd,
        )
        os.fchmod(directory_fd, 0o700)
        marker_fd = os.open(
            MARKER_NAME,
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
            raise AtlasError("stable-input lease lock could not be acquired")
        marker = {
            "contract_version": CONTRACT_VERSION,
            "created_unix": time.time(),
            "directory_name": directory_name,
            "magic": MARKER_MAGIC,
            "owner_uid": _current_uid(),
        }
        encoded = (json.dumps(marker, sort_keys=True) + "\n").encode("utf-8")
        offset = 0
        while offset < len(encoded):
            written = os.write(marker_fd, encoded[offset:])
            if written <= 0:
                raise AtlasError("stable-input ownership marker write was incomplete")
            offset += written
        os.fsync(marker_fd)
        os.fsync(directory_fd)
        os.fsync(root_fd)
        return _PrivateLease(
            root,
            root / directory_name,
            root_fd,
            directory_fd,
            marker_fd,
        )
    except BaseException as exc:
        if marker_fd is not None:
            os.close(marker_fd)
        if directory_fd is not None:
            with suppress(OSError):
                os.unlink(MARKER_NAME, dir_fd=directory_fd)
            os.close(directory_fd)
        if root_fd is not None:
            if directory_name is not None:
                with suppress(OSError):
                    os.rmdir(directory_name, dir_fd=root_fd)
            os.close(root_fd)
        if isinstance(exc, (AtlasError, KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(exc, OSError):
            raise AtlasError(
                "stable-input private snapshot directory could not be created"
            ) from exc
        raise


def _copy_snapshot(
    source_fd: int,
    directory_fd: int,
    policy: StableInputPolicy,
    expected_size: int,
) -> tuple[str, int]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        output_fd = os.open(SNAPSHOT_NAME, flags, 0o600, dir_fd=directory_fd)
    except OSError as exc:
        raise AtlasError("stable-input snapshot file could not be created") from exc
    digest = hashlib.sha256()
    total = 0
    try:
        os.fchmod(output_fd, 0o600)
        os.lseek(source_fd, 0, os.SEEK_SET)
        while True:
            block = os.read(source_fd, COPY_BLOCK_BYTES)
            if not block:
                break
            total += len(block)
            if (
                total > expected_size
                or total > policy.max_source_bytes
                or total > policy.max_temporary_bytes
            ):
                raise ResourceLimitError(
                    "stable-input copy exceeded a configured source or temporary byte ceiling"
                )
            digest.update(block)
            offset = 0
            while offset < len(block):
                written = os.write(output_fd, block[offset:])
                if written <= 0:
                    raise AtlasError("stable-input snapshot copy made no write progress")
                offset += written
        if total != expected_size:
            raise AtlasError("stable-input snapshot copy was incomplete")
        os.fsync(output_fd)
    finally:
        os.close(output_fd)
    return digest.hexdigest(), total


def _hash_private_snapshot(
    directory_fd: int,
    policy: StableInputPolicy,
    expected_size: int,
) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(SNAPSHOT_NAME, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise AtlasError("stable-input snapshot could not be independently verified") from exc
    try:
        value = os.fstat(descriptor)
        if not stat.S_ISREG(value.st_mode) or stat.S_IMODE(value.st_mode) != 0o600:
            raise AtlasError("stable-input snapshot permissions or type are invalid")
        if (
            value.st_size != expected_size
            or value.st_size > policy.max_source_bytes
            or value.st_size > policy.max_temporary_bytes
        ):
            raise AtlasError("stable-input snapshot size does not match authorized input")
        return _hash_descriptor(descriptor, policy, expected_size)
    finally:
        os.close(descriptor)


def _verify_lease_path(lease: _PrivateLease) -> None:
    directory_stat = os.fstat(lease.directory_fd)
    path_directory_stat = os.stat(
        lease.directory.name,
        dir_fd=lease.root_fd,
        follow_symlinks=False,
    )
    uid = _current_uid()
    if (
        not stat.S_ISDIR(directory_stat.st_mode)
        or stat.S_IMODE(directory_stat.st_mode) != 0o700
        or (uid is not None and directory_stat.st_uid != uid)
        or (directory_stat.st_dev, directory_stat.st_ino)
        != (path_directory_stat.st_dev, path_directory_stat.st_ino)
    ):
        raise AtlasError("stable-input private directory identity changed")
    descriptor_snapshot = os.stat(
        SNAPSHOT_NAME,
        dir_fd=lease.directory_fd,
        follow_symlinks=False,
    )
    path_snapshot = os.lstat(lease.directory / SNAPSHOT_NAME)
    if (
        not _stat_is_private_regular(descriptor_snapshot)
        or not _stat_is_private_regular(path_snapshot)
        or (
            descriptor_snapshot.st_dev,
            descriptor_snapshot.st_ino,
            descriptor_snapshot.st_size,
            descriptor_snapshot.st_nlink,
        )
        != (
            path_snapshot.st_dev,
            path_snapshot.st_ino,
            path_snapshot.st_size,
            path_snapshot.st_nlink,
        )
        or descriptor_snapshot.st_nlink != 1
    ):
        raise AtlasError("stable-input private snapshot identity changed")


def _cleanup_lease(lease: _PrivateLease | None) -> bool:
    if lease is None:
        return True
    cleaned = False
    try:
        directory_stat = os.fstat(lease.directory_fd)
        path_directory_stat = os.stat(
            lease.directory.name,
            dir_fd=lease.root_fd,
            follow_symlinks=False,
        )
        path_identity_matches = (directory_stat.st_dev, directory_stat.st_ino) == (
            path_directory_stat.st_dev,
            path_directory_stat.st_ino,
        )
        with os.scandir(lease.directory_fd) as iterator:
            entries = list(islice(iterator, 4))
        names = {entry.name for entry in entries}
        if len(entries) > 2 or not names.issubset({MARKER_NAME, SNAPSHOT_NAME}):
            return False
        marker_stat = os.stat(
            MARKER_NAME,
            dir_fd=lease.directory_fd,
            follow_symlinks=False,
        )
        open_marker_stat = os.fstat(lease.marker_fd)
        if not _stat_is_private_regular(marker_stat) or (
            marker_stat.st_dev,
            marker_stat.st_ino,
        ) != (open_marker_stat.st_dev, open_marker_stat.st_ino):
            return False
        if SNAPSHOT_NAME in names:
            snapshot_stat = os.stat(
                SNAPSHOT_NAME,
                dir_fd=lease.directory_fd,
                follow_symlinks=False,
            )
            if not _stat_is_private_regular(snapshot_stat):
                return False
            os.unlink(SNAPSHOT_NAME, dir_fd=lease.directory_fd)
            os.fsync(lease.directory_fd)
        if not path_identity_matches:
            return False
        os.unlink(MARKER_NAME, dir_fd=lease.directory_fd)
        os.fsync(lease.directory_fd)
        os.rmdir(lease.directory.name, dir_fd=lease.root_fd)
        os.fsync(lease.root_fd)
        cleaned = True
    except (OSError, ValueError, TypeError, OverflowError):
        # A replaced or unexpected entry is deliberately left for bounded,
        # marker-aware operator inspection rather than recursively deleted.
        pass
    finally:
        os.close(lease.marker_fd)
        os.close(lease.directory_fd)
        os.close(lease.root_fd)
    return cleaned


def _receipt(
    measurement: SourceMeasurement,
    policy: StableInputPolicy,
    nofollow_supported: bool,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "source": {
            "source_id": measurement.source_id,
            "sha256": measurement.source_sha256,
            "size_bytes": measurement.size_bytes,
        },
        "authorization": {
            "run_mode": measurement.authorization.requested_run_mode,
            "fixture_status": measurement.authorization.fixture_status,
            "rights_manifest_hash": measurement.authorization.rights_declaration["manifest_hash"],
        },
        "acquisition": {
            "method": "private-file-descriptor-copy",
            "bytes_copied": measurement.size_bytes,
            "source_byte_ceiling": policy.max_source_bytes,
            "temporary_storage_byte_ceiling": policy.max_temporary_bytes,
            "nofollow_strategy": (
                "o_nofollow-plus-identity-checks"
                if nofollow_supported
                else "lstat-open-fstat-identity-checks"
            ),
            "source_identity_stable": True,
            "snapshot_hash_verified": True,
            "snapshot_source_id_verified": True,
            "fsync_completed": True,
            "private_directory_mode": "0700",
            "private_file_mode": "0600",
        },
        "lifecycle": {
            "snapshot_is_canonical_artifact": False,
            "snapshot_retained": False,
            "cleanup": "context-finally-and-bounded-marker-recovery",
            "resume_reacquires_fresh_snapshot": True,
        },
        "privacy": {
            "original_path_exported": False,
            "snapshot_path_exported": False,
        },
    }
    validate_instance("stable_input", value, "stable_input.json")
    return value


@contextmanager
def acquire_authorized_input(
    source: Path,
    rights_manifest: Path | None,
    run_mode: str,
    *,
    policy: StableInputPolicy | None = None,
    expected_source_sha256: str | None = None,
    expected_source_id: str | None = None,
    expected_manifest_hash: str | None = None,
    additional_permissions: tuple[str, ...] = (),
    private_root: Path | None = None,
    recover_stale: bool = True,
) -> Iterator[StableInput]:
    """Authorize, acquire, verify, lease, and always clean a private snapshot."""
    active_policy = policy or StableInputPolicy()
    active_policy.validate()
    _require_snapshot_platform()
    root = _private_root(private_root)
    if recover_stale:
        recover_stale_snapshots(active_policy, root=root)
    descriptor, metadata = _open_source(source, active_policy)
    private_lease: _PrivateLease | None = None
    lease_ready = False
    try:
        source_hash, size = _hash_descriptor(descriptor, active_policy, metadata.size)
        _verify_source_unchanged(descriptor, source, metadata)
        source_id = source_id_from_sha256(source_hash)
        if expected_source_sha256 is not None and source_hash != expected_source_sha256:
            raise AtlasError("stable input does not match the run source hash")
        if expected_source_id is not None and source_id != expected_source_id:
            raise AtlasError("stable input does not match the run source ID")
        authorization = authorize_source_identity(
            source,
            source_hash,
            source_id,
            rights_manifest,
            run_mode,
            expected_manifest_hash=expected_manifest_hash,
            additional_permissions=additional_permissions,
        )
        measurement = SourceMeasurement(source_hash, source_id, size, authorization)
        private_lease = _new_private_directory(root)
        snapshot_path = private_lease.directory / SNAPSHOT_NAME
        copied_hash, copied_size = _copy_snapshot(
            descriptor, private_lease.directory_fd, active_policy, metadata.size
        )
        _verify_source_unchanged(descriptor, source, metadata)
        verified_hash, verified_size = _hash_private_snapshot(
            private_lease.directory_fd,
            active_policy,
            size,
        )
        if (
            copied_size != size
            or verified_size != size
            or copied_hash != source_hash
            or verified_hash != source_hash
            or source_id_from_sha256(verified_hash) != source_id
        ):
            raise AtlasError("stable-input snapshot identity verification failed")
        _verify_lease_path(private_lease)
        os.fsync(private_lease.directory_fd)
        receipt = _receipt(measurement, active_policy, hasattr(os, "O_NOFOLLOW"))
        lease_ready = True
        yield StableInput(
            snapshot_path,
            source_hash,
            source_id,
            size,
            authorization,
            receipt,
        )
    except (AtlasError, ResourceLimitError):
        raise
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        if lease_ready:
            raise
        raise AtlasError("stable-input acquisition failed safely") from exc
    finally:
        cleanup_succeeded = _cleanup_lease(private_lease)
        os.close(descriptor)
        if not cleanup_succeeded and sys.exc_info()[0] is None:
            raise AtlasError(
                "stable-input snapshot cleanup failed; marked residue requires safe recovery"
            )
