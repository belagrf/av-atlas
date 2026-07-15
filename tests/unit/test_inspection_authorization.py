from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from av_atlas import cli
from av_atlas.io import sha256_file, source_id_from_sha256, write_json
from av_atlas.rights import create_rights_manifest


def _inventory(path: Path, *, subtitle: bool = False) -> dict[str, Any]:
    digest = sha256_file(path)
    streams: list[dict[str, Any]] = []
    if subtitle:
        streams.append(
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "width": None,
                "height": None,
                "sample_rate": None,
                "channels": None,
                "tags": {"language": "eng"},
                "disposition": {},
            }
        )
    return {
        "schema_version": "1.0.0",
        "source_id": source_id_from_sha256(digest),
        "sha256": digest,
        "size_bytes": path.stat().st_size,
        "duration_ms": 1000,
        "format_names": ["test"],
        "streams": streams,
        "chapters": [],
    }


def _fixture_marker(media: Path) -> None:
    digest = sha256_file(media)
    write_json(
        media.with_suffix(".fixture.json"),
        {
            "schema_version": "1.0.0",
            "fixture_id": "INSPECTION_AUTH_TEST_V1",
            "profile": "m1",
            "generator_version": "1.0.0",
            "source_id": source_id_from_sha256(digest),
            "content_sha256": digest,
            "ffmpeg_version": "fixture-generation-only",
            "parameters": {},
        },
    )


def test_non_fixture_inspect_without_rights_fails_before_ffprobe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "operator.bin"
    media.write_bytes(b"not authorized")
    calls: list[Path] = []

    def forbidden(path: Path) -> dict[str, Any]:
        calls.append(path)
        raise AssertionError("FFprobe must not run before inspection authorization")

    monkeypatch.setattr(cli, "inspect_media", forbidden)
    assert cli.main(["inspect", str(media)]) == 2
    assert calls == []


def test_invalid_inspection_rights_fail_before_ffprobe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "operator.bin"
    media.write_bytes(b"operator source")
    rights = tmp_path / "rights.json"
    create_rights_manifest(media, rights, "operator", "owned", {"analysis"})
    calls: list[Path] = []

    def forbidden(path: Path) -> dict[str, Any]:
        calls.append(path)
        raise AssertionError("FFprobe must not run when retention permission is absent")

    monkeypatch.setattr(cli, "inspect_media", forbidden)
    assert cli.main(["inspect", str(media), "--rights-manifest", str(rights)]) == 2
    assert calls == []


def test_authorized_inspect_uses_snapshot_and_removes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "operator.bin"
    media.write_bytes(b"authorized operator source")
    rights = tmp_path / "rights.json"
    create_rights_manifest(
        media,
        rights,
        "operator",
        "owned",
        {"analysis", "derivative_artifact_retention"},
    )
    output = tmp_path / "inventory.json"
    snapshot: Path | None = None

    def inspect(path: Path) -> dict[str, Any]:
        nonlocal snapshot
        snapshot = path
        assert path != media
        assert path.read_bytes() == media.read_bytes()
        return _inventory(path)

    monkeypatch.setattr(cli, "inspect_media", inspect)
    assert (
        cli.main(
            [
                "inspect",
                str(media),
                "--rights-manifest",
                str(rights),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert snapshot is not None and not snapshot.exists()
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["sha256"] == sha256_file(media)
    assert str(media) not in output.read_text(encoding="utf-8")
    assert str(snapshot) not in output.read_text(encoding="utf-8")


def test_controlled_fixture_inspect_uses_snapshot_without_explicit_rights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "controlled.bin"
    media.write_bytes(b"controlled fixture")
    _fixture_marker(media)
    snapshot: Path | None = None

    def inspect(path: Path) -> dict[str, Any]:
        nonlocal snapshot
        snapshot = path
        assert path != media
        return _inventory(path)

    monkeypatch.setattr(cli, "inspect_media", inspect)
    assert cli.main(["inspect", str(media)]) == 0
    assert snapshot is not None and not snapshot.exists()


def test_inspect_subtitles_uses_same_authorized_snapshot_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    media = tmp_path / "operator.bin"
    media.write_bytes(b"authorized subtitles")
    rights = tmp_path / "rights.json"
    create_rights_manifest(
        media,
        rights,
        "operator",
        "owned",
        {"analysis", "derivative_artifact_retention"},
    )
    snapshot: Path | None = None

    def inspect(path: Path) -> dict[str, Any]:
        nonlocal snapshot
        snapshot = path
        assert path != media
        return _inventory(path, subtitle=True)

    monkeypatch.setattr(cli, "inspect_media", inspect)
    assert (
        cli.main(
            [
                "inspect-subtitles",
                str(media),
                "--rights-manifest",
                str(rights),
            ]
        )
        == 0
    )
    assert snapshot is not None and not snapshot.exists()
    output = capsys.readouterr().out
    value = json.loads(output)
    assert value["source_id"] == source_id_from_sha256(sha256_file(media))
    assert len(value["tracks"]) == 1
    assert str(media) not in output
    assert str(snapshot) not in output
