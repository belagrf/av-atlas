from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from av_atlas import pipeline
from av_atlas.io import sha256_file, source_id_from_sha256, write_json


def _fixture_marker(media: Path) -> None:
    digest = sha256_file(media)
    write_json(
        media.with_suffix(".fixture.json"),
        {
            "schema_version": "1.0.0",
            "fixture_id": "PIPELINE_STABLE_INPUT_V1",
            "profile": "m1",
            "generator_version": "1.0.0",
            "source_id": source_id_from_sha256(digest),
            "content_sha256": digest,
            "ffmpeg_version": "fixture-generation-only",
            "parameters": {},
        },
    )


def _inventory(path: Path) -> dict[str, Any]:
    digest = sha256_file(path)
    return {
        "schema_version": "1.0.0",
        "source_id": source_id_from_sha256(digest),
        "sha256": digest,
        "size_bytes": path.stat().st_size,
        "duration_ms": 1000,
        "format_names": ["test"],
        "streams": [],
        "chapters": [],
    }


def test_initial_completion_receives_snapshot_and_original_sidecar_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "controlled.bin"
    media.write_bytes(b"controlled bytes")
    _fixture_marker(media)
    run_dir = tmp_path / "run"
    captured: dict[str, Path] = {}

    def inspect(path: Path) -> dict[str, Any]:
        assert path != media
        return _inventory(path)

    def complete(
        received_run_dir: Path,
        parser_media: Path,
        config: object,
        *,
        source_media: Path | None = None,
    ) -> None:
        assert received_run_dir == run_dir
        assert parser_media != media
        assert parser_media.is_file()
        assert parser_media.read_bytes() == media.read_bytes()
        assert source_media == media
        captured["snapshot"] = parser_media

    monkeypatch.setattr(pipeline, "inspect_media", inspect)
    monkeypatch.setattr(pipeline, "tool_version", lambda name: None)
    monkeypatch.setattr(pipeline, "_complete", complete)
    pipeline.initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
    )
    assert not captured["snapshot"].exists()


def test_resume_reauthorizes_and_reacquires_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "controlled.bin"
    media.write_bytes(b"controlled bytes")
    _fixture_marker(media)
    run_dir = tmp_path / "run"
    first_snapshot: Path | None = None

    def inspect(path: Path) -> dict[str, Any]:
        nonlocal first_snapshot
        first_snapshot = path
        return _inventory(path)

    monkeypatch.setattr(pipeline, "inspect_media", inspect)
    monkeypatch.setattr(pipeline, "tool_version", lambda name: None)
    pipeline.initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
        stop_after="inventory",
    )
    assert first_snapshot is not None and not first_snapshot.exists()

    captured: dict[str, Path] = {}

    def complete(
        received_run_dir: Path,
        parser_media: Path,
        config: object,
        *,
        source_media: Path | None = None,
    ) -> None:
        assert received_run_dir == run_dir
        assert parser_media != media
        assert parser_media != first_snapshot
        assert parser_media.read_bytes() == media.read_bytes()
        assert source_media == media
        captured["snapshot"] = parser_media

    monkeypatch.setattr(pipeline, "_complete", complete)
    pipeline.resume_run(run_dir)
    assert not captured["snapshot"].exists()


def test_complete_run_resume_does_not_reacquire_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "controlled.bin"
    media.write_bytes(b"controlled bytes")
    _fixture_marker(media)
    run_dir = tmp_path / "run"

    monkeypatch.setattr(pipeline, "inspect_media", _inventory)
    monkeypatch.setattr(pipeline, "tool_version", lambda name: None)

    def complete(
        received_run_dir: Path,
        parser_media: Path,
        config: object,
        *,
        source_media: Path | None = None,
    ) -> None:
        manifest = pipeline._read_json(received_run_dir / "run_manifest.json")
        manifest["status"] = "complete"
        write_json(received_run_dir / "run_manifest.json", manifest)

    monkeypatch.setattr(pipeline, "_complete", complete)
    pipeline.initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("complete-run resume must not create another stable snapshot")

    monkeypatch.setattr(pipeline, "authorized_stable_input", forbidden)
    pipeline.resume_run(run_dir)
