from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from av_atlas import stable_input
from av_atlas.errors import AtlasError
from av_atlas.io import sha256_file, source_id_from_sha256
from av_atlas.stable_input import verified_stable_input


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _snapshot_directories(root: Path) -> list[Path]:
    return sorted(root.glob(f"{stable_input.SNAPSHOT_DIR_PREFIX}*"))


def test_verified_copy_is_private_identity_bound_and_removed(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    source.write_bytes(b"stable source bytes")
    expected = sha256_file(source)
    snapshot_path: Path | None = None
    snapshot_parent: Path | None = None

    with verified_stable_input(source, expected, temporary_root=tmp_path) as record:
        snapshot_path = record.path
        snapshot_parent = record.path.parent
        assert record.path != source
        assert record.path.read_bytes() == source.read_bytes()
        assert record.source_sha256 == expected
        assert record.source_id == source_id_from_sha256(expected)
        assert record.size_bytes == source.stat().st_size
        assert record.method == "verified-private-copy"
        if os.name != "nt":
            assert stat.S_IMODE(record.path.parent.stat().st_mode) == 0o700
            assert stat.S_IMODE(record.path.stat().st_mode) == 0o600

    assert snapshot_path is not None and not snapshot_path.exists()
    assert snapshot_parent is not None and not snapshot_parent.exists()
    assert _snapshot_directories(tmp_path) == []


def test_body_failure_still_removes_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"body failure")
    with (
        pytest.raises(RuntimeError, match="consumer failed"),
        verified_stable_input(source, sha256_file(source), temporary_root=tmp_path),
    ):
        raise RuntimeError("consumer failed")
    assert _snapshot_directories(tmp_path) == []


def test_hash_mismatch_fails_and_removes_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"hash mismatch")
    with (
        pytest.raises(AtlasError, match="does not match the authorized source hash"),
        verified_stable_input(source, "0" * 64, temporary_root=tmp_path),
    ):
        raise AssertionError("unreachable")
    assert _snapshot_directories(tmp_path) == []


def test_oversize_source_fails_before_snapshot_file_survives(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"12345")
    with (
        pytest.raises(AtlasError, match="exceeds stable snapshot limit"),
        verified_stable_input(
            source,
            sha256_file(source),
            max_snapshot_bytes=4,
            temporary_root=tmp_path,
        ),
    ):
        raise AssertionError("unreachable")
    assert _snapshot_directories(tmp_path) == []


def test_symlink_source_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.bin"
    target.write_bytes(b"target")
    source = tmp_path / "source.bin"
    try:
        source.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")
    with (
        pytest.raises(AtlasError, match="symlinks are not accepted"),
        verified_stable_input(source, sha256_file(target), temporary_root=tmp_path),
    ):
        raise AssertionError("unreachable")
    assert _snapshot_directories(tmp_path) == []


def test_non_directory_or_symlink_temporary_root_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    file_root = tmp_path / "not-a-directory"
    file_root.write_bytes(b"x")
    with (
        pytest.raises(AtlasError, match="must be a real directory"),
        verified_stable_input(source, sha256_file(source), temporary_root=file_root),
    ):
        raise AssertionError("unreachable")

    directory = tmp_path / "directory"
    directory.mkdir()
    link = tmp_path / "directory-link"
    try:
        link.symlink_to(directory, target_is_directory=True)
    except OSError:
        return
    with (
        pytest.raises(AtlasError, match="must be a real directory"),
        verified_stable_input(source, sha256_file(source), temporary_root=link),
    ):
        raise AssertionError("unreachable")


def test_partial_writes_are_completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.bin"
    payload = b"partial writes must be retried"
    source.write_bytes(payload)
    original = stable_input._write_chunk

    def one_byte_at_a_time(file_descriptor: int, value: bytes) -> int:
        return original(file_descriptor, value[:1])

    monkeypatch.setattr(stable_input, "_write_chunk", one_byte_at_a_time)
    with verified_stable_input(source, _digest(payload), temporary_root=tmp_path) as record:
        assert record.path.read_bytes() == payload


def test_zero_progress_write_fails_closed_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"cannot write")
    monkeypatch.setattr(stable_input, "_write_chunk", lambda _descriptor, _value: 0)
    with (
        pytest.raises(AtlasError, match="write made no progress"),
        verified_stable_input(source, sha256_file(source), temporary_root=tmp_path),
    ):
        raise AssertionError("unreachable")
    assert _snapshot_directories(tmp_path) == []


def test_in_place_mutation_during_copy_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    original_payload = b"abcdefgh"
    source.write_bytes(original_payload)
    original_read = stable_input._read_chunk
    calls = 0

    def mutate_after_first_read(file_descriptor: int, size: int) -> bytes:
        nonlocal calls
        chunk = original_read(file_descriptor, size)
        calls += 1
        if calls == 1:
            source.write_bytes(b"changed")
        return chunk

    monkeypatch.setattr(stable_input, "COPY_CHUNK_BYTES", 4)
    monkeypatch.setattr(stable_input, "_read_chunk", mutate_after_first_read)
    with (
        pytest.raises(AtlasError, match="changed during stable copy|authorized source hash"),
        verified_stable_input(source, _digest(original_payload), temporary_root=tmp_path),
    ):
        raise AssertionError("unreachable")
    assert _snapshot_directories(tmp_path) == []


def test_path_replacement_during_copy_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    original_payload = b"abcdefgh"
    source.write_bytes(original_payload)
    original_read = stable_input._read_chunk
    calls = 0

    def replace_after_first_read(file_descriptor: int, size: int) -> bytes:
        nonlocal calls
        chunk = original_read(file_descriptor, size)
        calls += 1
        if calls == 1:
            replacement = tmp_path / "replacement.bin"
            replacement.write_bytes(original_payload)
            replacement.replace(source)
        return chunk

    monkeypatch.setattr(stable_input, "COPY_CHUNK_BYTES", 4)
    monkeypatch.setattr(stable_input, "_read_chunk", replace_after_first_read)
    with (
        pytest.raises(AtlasError, match="path was replaced"),
        verified_stable_input(source, _digest(original_payload), temporary_root=tmp_path),
    ):
        raise AssertionError("unreachable")
    assert _snapshot_directories(tmp_path) == []


@pytest.mark.parametrize("expected", ["", "0" * 63, "z" * 64])
def test_invalid_expected_hash_is_rejected_before_temp_creation(
    tmp_path: Path, expected: str
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    with (
        pytest.raises(AtlasError, match="expected source SHA-256"),
        verified_stable_input(source, expected, temporary_root=tmp_path),
    ):
        raise AssertionError("unreachable")
    assert _snapshot_directories(tmp_path) == []
