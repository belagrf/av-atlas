"""Verified private transient copies for stable native-media parser input."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from av_atlas.errors import AtlasError
from av_atlas.io import source_id_from_sha256
from av_atlas.rights import AuthorizationPreflight, authorize_media_preflight

DEFAULT_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024
SNAPSHOT_DIR_PREFIX = "av-atlas-stable-"


@dataclass(frozen=True)
class StableInputRecord:
    """Private runtime record for one verified transient source copy.

    ``path`` is intentionally runtime-only and must never be serialized into ordinary run
    artifacts, logs, or public reports.
    """

    path: Path
    source_sha256: str
    source_id: str
    size_bytes: int
    method: str = "verified-private-copy"


@dataclass(frozen=True)
class AuthorizedStableInput:
    """Rights authorization paired with its private verified parser input."""

    authorization: AuthorizationPreflight
    stable: StableInputRecord


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_size),
        int(value.st_mtime_ns),
        int(value.st_ctime_ns),
    )


def _path_identity(value: os.stat_result) -> tuple[int, int]:
    return int(value.st_dev), int(value.st_ino)


def _read_chunk(file_descriptor: int, size: int) -> bytes:
    return os.read(file_descriptor, size)


def _write_chunk(file_descriptor: int, value: bytes) -> int:
    return os.write(file_descriptor, value)


def _write_all(file_descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = _write_chunk(file_descriptor, value[offset:])
        if written <= 0:
            raise AtlasError("stable snapshot write made no progress")
        offset += written


def validate_stable_source_path(source: Path) -> os.stat_result:
    """Reject symlink and non-regular source paths without invoking a native parser."""
    try:
        value = source.lstat()
    except OSError as exc:
        raise AtlasError(f"cannot inspect media source before stable copy: {exc}") from exc
    if stat.S_ISLNK(value.st_mode):
        raise AtlasError("media source symlinks are not accepted for stable input")
    if not stat.S_ISREG(value.st_mode):
        raise AtlasError(f"media source is not a regular file: {source}")
    return value


def _open_regular_source(source: Path) -> tuple[int, os.stat_result]:
    before = validate_stable_source_path(source)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(source, flags)
    except OSError as exc:
        raise AtlasError(f"cannot open media source for stable copy: {exc}") from exc
    try:
        opened = os.fstat(file_descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise AtlasError("opened media source is not a regular file")
        if _path_identity(before) != _path_identity(opened):
            raise AtlasError("media source changed while it was being opened")
        return file_descriptor, opened
    except BaseException:
        os.close(file_descriptor)
        raise


def _validate_expected_sha256(value: str) -> None:
    if len(value) != 64:
        raise AtlasError("expected source SHA-256 must contain 64 hexadecimal characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise AtlasError("expected source SHA-256 must be hexadecimal") from exc


def _validate_temporary_root(temporary_root: Path | None) -> Path | None:
    if temporary_root is None:
        return None
    try:
        value = temporary_root.lstat()
    except OSError as exc:
        raise AtlasError(f"stable-input temporary root is unavailable: {exc}") from exc
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
        raise AtlasError("stable-input temporary root must be a real directory, not a symlink")
    return temporary_root


def _copy_verified(
    source: Path,
    source_descriptor: int,
    initial_source_stat: os.stat_result,
    destination: Path,
    expected_sha256: str,
    max_snapshot_bytes: int,
) -> StableInputRecord:
    if max_snapshot_bytes <= 0:
        raise AtlasError("stable snapshot byte limit must be positive")
    if int(initial_source_stat.st_size) > max_snapshot_bytes:
        raise AtlasError(
            f"media source size {initial_source_stat.st_size} exceeds stable snapshot limit "
            f"{max_snapshot_bytes}"
        )

    destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    try:
        destination_descriptor = os.open(destination, destination_flags, 0o600)
    except OSError as exc:
        raise AtlasError(f"cannot create private stable snapshot: {exc}") from exc

    digest = hashlib.sha256()
    copied = 0
    try:
        while True:
            chunk = _read_chunk(source_descriptor, COPY_CHUNK_BYTES)
            if not chunk:
                break
            copied += len(chunk)
            if copied > max_snapshot_bytes:
                raise AtlasError(
                    "media source exceeded stable snapshot limit "
                    f"{max_snapshot_bytes} while copying"
                )
            digest.update(chunk)
            _write_all(destination_descriptor, chunk)
        os.fsync(destination_descriptor)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        os.close(destination_descriptor)

    final_source_stat = os.fstat(source_descriptor)
    try:
        final_path_stat = source.lstat()
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise AtlasError(f"media source disappeared during stable copy: {exc}") from exc

    actual_sha256 = digest.hexdigest()
    if copied != int(initial_source_stat.st_size):
        destination.unlink(missing_ok=True)
        raise AtlasError("media source size changed during stable copy")
    if _stat_identity(initial_source_stat) != _stat_identity(final_source_stat):
        destination.unlink(missing_ok=True)
        raise AtlasError("media source metadata changed during stable copy")
    if _path_identity(initial_source_stat) != _path_identity(final_path_stat):
        destination.unlink(missing_ok=True)
        raise AtlasError("media source path was replaced during stable copy")
    if actual_sha256 != expected_sha256:
        destination.unlink(missing_ok=True)
        raise AtlasError("stable snapshot hash does not match the authorized source hash")
    try:
        snapshot_size = destination.stat().st_size
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise AtlasError(f"cannot verify stable snapshot: {exc}") from exc
    if snapshot_size != copied:
        destination.unlink(missing_ok=True)
        raise AtlasError("stable snapshot size does not match copied byte count")
    try:
        os.chmod(destination, 0o600)
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise AtlasError(f"cannot restrict stable snapshot permissions: {exc}") from exc

    return StableInputRecord(
        path=destination,
        source_sha256=actual_sha256,
        source_id=source_id_from_sha256(actual_sha256),
        size_bytes=copied,
    )


@contextmanager
def verified_stable_input(
    source: Path,
    expected_sha256: str,
    *,
    max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
    temporary_root: Path | None = None,
) -> Iterator[StableInputRecord]:
    """Yield a private hash-verified copy and remove it after use.

    This lower-level primitive does not grant rights. Callers must complete parser-free rights
    authorization before invoking it and must keep the returned path out of exported records.
    """

    _validate_expected_sha256(expected_sha256)
    root = _validate_temporary_root(temporary_root)
    try:
        temporary_directory = Path(
            tempfile.mkdtemp(prefix=SNAPSHOT_DIR_PREFIX, dir=str(root) if root else None)
        )
        os.chmod(temporary_directory, 0o700)
    except OSError as exc:
        raise AtlasError(f"cannot create private stable-input directory: {exc}") from exc

    snapshot = temporary_directory / "source.media"
    source_descriptor: int | None = None
    try:
        source_descriptor, initial_source_stat = _open_regular_source(source)
        record = _copy_verified(
            source,
            source_descriptor,
            initial_source_stat,
            snapshot,
            expected_sha256,
            max_snapshot_bytes,
        )
        yield record
    finally:
        if source_descriptor is not None:
            os.close(source_descriptor)
        active_exception = sys.exc_info()[1]
        try:
            shutil.rmtree(temporary_directory)
        except OSError as exc:
            if active_exception is not None:
                active_exception.add_note(f"stable snapshot cleanup also failed: {exc}")
            else:
                raise AtlasError(f"cannot remove private stable snapshot: {exc}") from exc


@contextmanager
def authorized_stable_input(
    source: Path,
    rights_manifest: Path | None,
    run_mode: str,
    *,
    expected_manifest_hash: str | None = None,
    max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
    temporary_root: Path | None = None,
) -> Iterator[AuthorizedStableInput]:
    """Authorize exact bytes, yield their verified private parser input, then remove it."""

    validate_stable_source_path(source)
    authorization = authorize_media_preflight(
        source,
        rights_manifest,
        run_mode,
        expected_manifest_hash=expected_manifest_hash,
    )
    with verified_stable_input(
        source,
        authorization.source_sha256,
        max_snapshot_bytes=max_snapshot_bytes,
        temporary_root=temporary_root,
    ) as stable:
        if (
            stable.source_sha256 != authorization.source_sha256
            or stable.source_id != authorization.source_id
        ):
            raise AtlasError("stable snapshot identity does not match parser-free authorization")
        yield AuthorizedStableInput(authorization=authorization, stable=stable)
