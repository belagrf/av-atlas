from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from av_atlas import stable_input
from av_atlas.errors import AtlasError, ResourceLimitError
from av_atlas.io import canonical_json, sha256_file, source_id_from_sha256, write_json
from av_atlas.rights import create_rights_manifest
from av_atlas.stable_input import (
    MARKER_NAME,
    SNAPSHOT_NAME,
    StableInputPolicy,
    VerifiedPrivateRoot,
    acquire_authorized_input,
    recover_stale_snapshots,
)


def _rights(source: Path, path: Path) -> Path:
    create_rights_manifest(
        source,
        path,
        "stable-input-test",
        "owned",
        {"analysis", "derivative_artifact_retention"},
    )
    return path


def _fixture_marker(source: Path) -> None:
    digest = sha256_file(source)
    write_json(
        source.with_suffix(".fixture.json"),
        {
            "schema_version": "1.0.0",
            "fixture_id": "STABLE_INPUT_TEST_V1",
            "profile": "m1",
            "generator_version": "1.0.0",
            "source_id": source_id_from_sha256(digest),
            "content_sha256": digest,
            "ffmpeg_version": "fixture-generation-only",
            "parameters": {},
        },
    )


def _children(root: Path) -> list[Path]:
    return list(root.iterdir()) if root.exists() else []


def _open_verified_root(root: Path) -> VerifiedPrivateRoot:
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    descriptor = os.open(
        root,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    value = os.fstat(descriptor)
    return VerifiedPrivateRoot(root, descriptor, value.st_dev, value.st_ino)


def test_snapshot_is_exact_private_path_free_and_cleaned(tmp_path: Path) -> None:
    source = tmp_path / "operator;$(inert).mkv"
    source.write_bytes(b"authorized stable bytes")
    rights = _rights(source, tmp_path / "rights.json")
    private = tmp_path / "private"
    snapshot: Path | None = None
    with acquire_authorized_input(source, rights, "analysis", private_root=private) as stable:
        snapshot = stable.snapshot_path
        assert snapshot != source
        assert snapshot.read_bytes() == source.read_bytes()
        assert stat.S_IMODE(snapshot.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600
        raw = json.dumps(stable.receipt)
        assert str(source) not in raw
        assert str(snapshot) not in raw
        assert stable.receipt["source"]["sha256"] == sha256_file(source)
    assert snapshot is not None and not snapshot.exists()
    assert _children(private) == []
    assert not (tmp_path / "inert").exists()


def test_verified_private_root_uses_retained_fd_and_preserves_legacy_receipt(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"verified private-root bytes")
    rights = _rights(source, tmp_path / "rights.json")
    verified = _open_verified_root(tmp_path / "verified")
    borrowed_snapshot_fd: int | None = None
    try:
        with acquire_authorized_input(
            source,
            rights,
            "analysis",
            verified_private_root=verified,
        ) as stable:
            borrowed_snapshot_fd = stable.snapshot_fd
            assert borrowed_snapshot_fd is not None
            assert os.get_inheritable(borrowed_snapshot_fd) is False
            os.lseek(borrowed_snapshot_fd, 0, os.SEEK_SET)
            assert os.read(borrowed_snapshot_fd, 1024) == source.read_bytes()
            with pytest.raises(OSError):
                os.write(borrowed_snapshot_fd, b"not writable")
            verified_receipt = stable.receipt
            assert os.fstat(verified.descriptor).st_ino == verified.inode
        assert _children(verified.path) == []
        assert borrowed_snapshot_fd is not None
        with pytest.raises(OSError):
            os.fstat(borrowed_snapshot_fd)

        with acquire_authorized_input(
            source,
            rights,
            "analysis",
            private_root=tmp_path / "legacy",
        ) as legacy:
            assert canonical_json(legacy.receipt) == canonical_json(verified_receipt)
        assert _children(tmp_path / "legacy") == []
    finally:
        os.close(verified.descriptor)


def test_verified_private_root_replacement_is_rejected_before_lease(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"root replacement")
    rights = _rights(source, tmp_path / "rights.json")
    verified = _open_verified_root(tmp_path / "verified")
    moved = tmp_path / "moved"
    verified.path.rename(moved)
    verified.path.mkdir(mode=0o700)
    try:
        with (
            pytest.raises(AtlasError, match="private-root identity"),
            acquire_authorized_input(
                source,
                rights,
                "analysis",
                verified_private_root=verified,
            ),
        ):
            pytest.fail("a replaced verified root must not yield a snapshot")
        assert _children(verified.path) == []
        assert _children(moved) == []
    finally:
        os.close(verified.descriptor)


def test_verified_private_root_replacement_before_yield_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"replace after lease allocation")
    rights = _rights(source, tmp_path / "rights.json")
    verified = _open_verified_root(tmp_path / "verified")
    moved = tmp_path / "moved"
    real_copy = stable_input._copy_snapshot

    def replace_root(*args: object, **kwargs: object) -> tuple[str, int]:
        result = real_copy(*args, **kwargs)  # type: ignore[arg-type]
        verified.path.rename(moved)
        verified.path.mkdir(mode=0o700)
        return result

    monkeypatch.setattr(stable_input, "_copy_snapshot", replace_root)
    try:
        with (
            pytest.raises(AtlasError, match="private-root identity"),
            acquire_authorized_input(
                source,
                rights,
                "analysis",
                verified_private_root=verified,
            ),
        ):
            pytest.fail("a replaced root must be rejected before the lease is yielded")
        residues = [item for item in moved.iterdir() if item.is_dir()]
        assert len(residues) == 1
        assert (residues[0] / MARKER_NAME).is_file()
        assert (residues[0] / SNAPSHOT_NAME).is_file()

        verified.path.rmdir()
        moved.rename(verified.path)
        assert recover_stale_snapshots(verified_root=verified) == 1
        assert _children(verified.path) == []
    finally:
        os.close(verified.descriptor)


def test_verified_private_root_mode_drift_blocks_cleanup_then_recovers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"mode drift")
    rights = _rights(source, tmp_path / "rights.json")
    verified = _open_verified_root(tmp_path / "verified")
    try:
        with (
            pytest.raises(AtlasError, match="cleanup failed"),
            acquire_authorized_input(
                source,
                rights,
                "analysis",
                verified_private_root=verified,
            ),
        ):
            verified.path.chmod(0o750)
        residues = [item for item in verified.path.iterdir() if item.is_dir()]
        assert len(residues) == 1
        assert (residues[0] / MARKER_NAME).is_file()
        assert (residues[0] / SNAPSHOT_NAME).is_file()

        verified.path.chmod(0o700)
        assert recover_stale_snapshots(verified_root=verified) == 1
        assert _children(verified.path) == []
    finally:
        verified.path.chmod(0o700)
        os.close(verified.descriptor)


def test_original_mutation_after_acquisition_cannot_change_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"frozen authorized bytes")
    rights = _rights(source, tmp_path / "rights.json")
    with acquire_authorized_input(
        source, rights, "analysis", private_root=tmp_path / "private"
    ) as stable:
        source.write_bytes(b"changed operator bytes!")
        assert stable.snapshot_path.read_bytes() == b"frozen authorized bytes"


@pytest.mark.parametrize(
    "replacement", ["same_size_mutation", "growth", "truncation", "replacement"]
)
def test_hostile_mutation_during_copy_is_rejected_before_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"0123456789")
    rights = _rights(source, tmp_path / "rights.json")
    original = stable_input._copy_snapshot

    def hostile_copy(*args: object, **kwargs: object) -> tuple[str, int]:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        if replacement == "same_size_mutation":
            source.write_bytes(b"abcdefghij")
        elif replacement == "growth":
            source.write_bytes(b"0123456789-grown")
        elif replacement == "truncation":
            source.write_bytes(b"short")
        else:
            alternate = tmp_path / "alternate.bin"
            alternate.write_bytes(b"abcdefghij")
            os.replace(alternate, source)
        return result

    monkeypatch.setattr(stable_input, "_copy_snapshot", hostile_copy)
    with (
        pytest.raises(AtlasError, match="mutated or was replaced"),
        acquire_authorized_input(source, rights, "analysis", private_root=tmp_path / "private"),
    ):
        pytest.fail("an unverified lease must never be yielded")
    assert _children(tmp_path / "private") == []


def test_symlink_and_oversize_sources_fail_before_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "target.bin"
    target.write_bytes(b"12345")
    link = tmp_path / "link.bin"
    link.symlink_to(target)
    with (
        pytest.raises(AtlasError, match="regular non-symlink"),
        acquire_authorized_input(link, None, "analysis", private_root=tmp_path / "private"),
    ):
        pass
    _fixture_marker(target)
    with (
        pytest.raises(ResourceLimitError, match="byte ceiling"),
        acquire_authorized_input(
            target,
            None,
            "analysis",
            policy=StableInputPolicy(max_source_bytes=4, max_temporary_bytes=4),
            private_root=tmp_path / "private",
        ),
    ):
        pass
    assert _children(tmp_path / "private") == []


def test_policy_rejects_unbounded_and_asymmetric_temporary_limits(tmp_path: Path) -> None:
    with pytest.raises(AtlasError, match="64 GiB"):
        StableInputPolicy(max_source_bytes=65 * 1024**3).validate()
    source = tmp_path / "source.bin"
    source.write_bytes(b"five!")
    _fixture_marker(source)
    with (
        pytest.raises(ResourceLimitError, match="temporary byte ceiling"),
        acquire_authorized_input(
            source,
            None,
            "analysis",
            policy=StableInputPolicy(max_source_bytes=10, max_temporary_bytes=4),
            private_root=tmp_path / "private",
        ),
    ):
        pass
    assert _children(tmp_path / "private") == []


def test_unsupported_snapshot_platform_fails_closed_before_source_or_private_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"controlled")
    _fixture_marker(source)
    monkeypatch.setattr(stable_input, "fcntl", None)
    with (
        pytest.raises(AtlasError, match="POSIX directory-descriptor"),
        acquire_authorized_input(
            source,
            None,
            "analysis",
            private_root=tmp_path / "private",
        ),
    ):
        pass
    assert not (tmp_path / "private").exists()


def test_partial_writes_are_completed_and_snapshot_hash_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"partial-write-test")
    rights = _rights(source, tmp_path / "rights.json")
    real_write = os.write

    def partial_write(descriptor: int, value: bytes) -> int:
        return real_write(descriptor, value[:2])

    monkeypatch.setattr(os, "write", partial_write)
    with acquire_authorized_input(
        source, rights, "analysis", private_root=tmp_path / "partial"
    ) as stable:
        assert stable.snapshot_path.read_bytes() == source.read_bytes()

    monkeypatch.setattr(
        stable_input,
        "_hash_private_snapshot",
        lambda *args, **kwargs: ("0" * 64, source.stat().st_size),
    )
    with (
        pytest.raises(AtlasError, match="identity verification failed"),
        acquire_authorized_input(source, rights, "analysis", private_root=tmp_path / "mismatch"),
    ):
        pytest.fail("hash-mismatched snapshot must not be yielded")
    assert _children(tmp_path / "mismatch") == []


def test_receipt_is_private_root_independent_and_snapshot_is_not_a_hardlink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"root-independent")
    rights = _rights(source, tmp_path / "rights.json")
    receipts = []
    for name in ("private-a", "private-b"):
        root = tmp_path / name
        with acquire_authorized_input(source, rights, "analysis", private_root=root) as stable:
            receipts.append(stable.receipt)
            assert source.stat().st_ino != stable.snapshot_path.stat().st_ino
            assert str(root) not in canonical_json(stable.receipt)
    assert canonical_json(receipts[0]) == canonical_json(receipts[1])


@pytest.mark.parametrize(
    "failure", [AtlasError("parser failed"), TimeoutError(), KeyboardInterrupt()]
)
def test_ordinary_failure_timeout_and_interruption_clean_snapshot(
    tmp_path: Path, failure: BaseException
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"fixture")
    rights = _rights(source, tmp_path / "rights.json")
    private = tmp_path / "private"
    with (
        pytest.raises(type(failure)),
        acquire_authorized_input(source, rights, "analysis", private_root=private),
    ):
        raise failure
    assert _children(private) == []


def test_bounded_stale_recovery_removes_only_recognized_inactive_lease(
    tmp_path: Path,
) -> None:
    root = stable_input._private_root(tmp_path / "private")
    lease = stable_input._new_private_directory(root)
    directory = lease.directory
    os.close(lease.marker_fd)
    os.close(lease.directory_fd)
    os.close(lease.root_fd)
    marker_path = directory / MARKER_NAME
    marker = json.loads(marker_path.read_text())
    marker["created_unix"] = 0
    marker_path.write_text(json.dumps(marker) + "\n")
    marker_path.chmod(0o600)
    snapshot = directory / SNAPSHOT_NAME
    snapshot.write_bytes(b"stale")
    snapshot.chmod(0o600)

    unknown = root / ("snapshot-" + "a" * 32)
    unknown.mkdir(mode=0o700)
    (unknown / "unexpected").write_text("do not delete")
    outside = tmp_path / "outside"
    outside.mkdir()
    escape = root / ("snapshot-" + "b" * 32)
    escape.symlink_to(outside, target_is_directory=True)

    removed = recover_stale_snapshots(StableInputPolicy(), root=root)
    assert removed == 1
    assert not directory.exists()
    assert (unknown / "unexpected").is_file()
    assert outside.is_dir()
    assert escape.is_symlink()


def test_stale_recovery_accepts_known_legacy_lease_marker_version(tmp_path: Path) -> None:
    root = stable_input._private_root(tmp_path / "private")
    lease = stable_input._new_private_directory(root)
    directory = lease.directory
    os.close(lease.marker_fd)
    os.close(lease.directory_fd)
    os.close(lease.root_fd)
    marker_path = directory / MARKER_NAME
    marker = json.loads(marker_path.read_text())
    marker["contract_version"] = "av-atlas-stable-input/1.0.0"
    marker["created_unix"] = 0
    marker_path.write_text(json.dumps(marker) + "\n")
    marker_path.chmod(0o600)
    snapshot = directory / SNAPSHOT_NAME
    snapshot.write_bytes(b"legacy stale")
    snapshot.chmod(0o600)

    assert recover_stale_snapshots(StableInputPolicy(), root=root) == 1
    assert not directory.exists()


def test_stale_recovery_does_not_remove_live_locked_lease(tmp_path: Path) -> None:
    root = stable_input._private_root(tmp_path / "private")
    lease = stable_input._new_private_directory(root)
    directory = lease.directory
    try:
        marker = json.loads((directory / MARKER_NAME).read_text())
        marker["created_unix"] = 0
        encoded = (json.dumps(marker, sort_keys=True) + "\n").encode()
        os.ftruncate(lease.marker_fd, 0)
        os.lseek(lease.marker_fd, 0, os.SEEK_SET)
        os.write(lease.marker_fd, encoded)
        os.fsync(lease.marker_fd)
        assert recover_stale_snapshots(StableInputPolicy(), root=root) == 0
        assert directory.is_dir()
    finally:
        assert stable_input._cleanup_lease(lease) is True


def test_stale_recovery_removal_count_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = stable_input._private_root(tmp_path / "private")
    for _ in range(3):
        lease = stable_input._new_private_directory(root)
        os.close(lease.marker_fd)
        os.close(lease.directory_fd)
        os.close(lease.root_fd)
    monkeypatch.setattr(stable_input, "MAX_STALE_REMOVALS", 2)
    assert recover_stale_snapshots(root=root) == 2
    assert len([path for path in root.iterdir() if path.is_dir()]) == 1
    assert recover_stale_snapshots(root=root) == 1


def test_stale_recovery_scan_count_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = stable_input._private_root(tmp_path / "private")
    for _ in range(3):
        lease = stable_input._new_private_directory(root)
        os.close(lease.marker_fd)
        os.close(lease.directory_fd)
        os.close(lease.root_fd)
    monkeypatch.setattr(stable_input, "MAX_STALE_SCAN", 2)
    monkeypatch.setattr(stable_input, "MAX_STALE_REMOVALS", 16)
    assert recover_stale_snapshots(root=root) == 2
    assert len([path for path in root.iterdir() if path.is_dir()]) == 1


def test_malformed_stale_entries_do_not_leak_file_descriptors(tmp_path: Path) -> None:
    descriptors = Path("/proc/self/fd")
    if not descriptors.is_dir():
        pytest.skip("file-descriptor accounting requires procfs")
    root = stable_input._private_root(tmp_path / "private")
    lease = stable_input._new_private_directory(root)
    directory = lease.directory
    os.close(lease.marker_fd)
    os.close(lease.directory_fd)
    os.close(lease.root_fd)
    unexpected = directory / "unexpected"
    unexpected.write_text("must remain")
    before = len(list(descriptors.iterdir()))
    for _ in range(20):
        assert recover_stale_snapshots(root=root) == 0
    after = len(list(descriptors.iterdir()))
    assert after <= before + 1
    assert unexpected.is_file()


def test_stale_recovery_fsyncs_deletions_before_removing_marker_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = stable_input._private_root(tmp_path / "private")
    lease = stable_input._new_private_directory(root)
    snapshot = lease.directory / SNAPSHOT_NAME
    snapshot.write_bytes(b"stale private bytes")
    snapshot.chmod(0o600)
    os.close(lease.marker_fd)
    os.close(lease.directory_fd)
    os.close(lease.root_fd)
    events: list[str] = []
    real_unlink = os.unlink
    real_rmdir = os.rmdir
    real_fsync = os.fsync

    def record_unlink(path: str, *args: object, **kwargs: object) -> None:
        events.append(f"unlink:{path}")
        real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    def record_rmdir(path: str, *args: object, **kwargs: object) -> None:
        events.append(f"rmdir:{path}")
        real_rmdir(path, *args, **kwargs)  # type: ignore[arg-type]

    def record_fsync(descriptor: int) -> None:
        events.append("fsync")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "unlink", record_unlink)
    monkeypatch.setattr(os, "rmdir", record_rmdir)
    monkeypatch.setattr(os, "fsync", record_fsync)
    assert recover_stale_snapshots(root=root) == 1
    assert events == [
        f"unlink:{SNAPSHOT_NAME}",
        "fsync",
        f"unlink:{MARKER_NAME}",
        "fsync",
        f"rmdir:{lease.directory.name}",
        "fsync",
    ]


def test_cleanup_parent_replacement_cannot_escape_private_root(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"cleanup-sensitive-bytes")
    rights = _rights(source, tmp_path / "rights.json")
    root = tmp_path / "private"
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_marker = outside / MARKER_NAME
    outside_snapshot = outside / SNAPSHOT_NAME
    outside_marker.write_text("outside marker")
    outside_snapshot.write_text("outside snapshot")
    outside_marker.chmod(0o600)
    outside_snapshot.chmod(0o600)
    moved: Path | None = None
    with (
        pytest.raises(AtlasError, match="cleanup failed"),
        acquire_authorized_input(source, rights, "analysis", private_root=root) as stable,
    ):
        moved = root / "renamed-active-lease"
        stable.snapshot_path.parent.rename(moved)
        stable.snapshot_path.parent.symlink_to(outside, target_is_directory=True)
    assert outside_marker.read_text() == "outside marker"
    assert outside_snapshot.read_text() == "outside snapshot"
    assert moved is not None
    assert not (moved / SNAPSHOT_NAME).exists()
    assert (moved / MARKER_NAME).is_file()
    (root / stable.snapshot_path.parent.name).unlink()
    (moved / MARKER_NAME).unlink()
    moved.rmdir()


def test_cleanup_failure_is_reported_and_marker_preserved_for_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"cleanup-failure")
    rights = _rights(source, tmp_path / "rights.json")
    root = tmp_path / "private"
    real_unlink = os.unlink
    with monkeypatch.context() as active:

        def fail_snapshot_unlink(path: str, *args: object, **kwargs: object) -> None:
            if path == SNAPSHOT_NAME:
                raise OSError("injected cleanup failure")
            real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

        active.setattr(os, "unlink", fail_snapshot_unlink)
        with (
            pytest.raises(AtlasError, match="cleanup failed"),
            acquire_authorized_input(source, rights, "analysis", private_root=root),
        ):
            pass
    residues = [path for path in root.iterdir() if path.is_dir()]
    assert len(residues) == 1
    assert (residues[0] / MARKER_NAME).is_file()
    assert (residues[0] / SNAPSHOT_NAME).is_file()
    assert recover_stale_snapshots(root=root) == 1
