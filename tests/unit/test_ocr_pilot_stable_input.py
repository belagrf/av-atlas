from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from av_atlas.errors import AtlasError
from av_atlas.io import sha256_file, source_id_from_sha256
from av_atlas.ocr_pilot_intake import prepare_pilot
from av_atlas.rights import create_rights_manifest


def _inventory(path: Path, duration_ms: int = 120_000) -> dict[str, Any]:
    digest = sha256_file(path)
    return {
        "schema_version": "1.0.0",
        "source_id": source_id_from_sha256(digest),
        "sha256": digest,
        "size_bytes": path.stat().st_size,
        "duration_ms": duration_ms,
        "format_names": ["test"],
        "streams": [],
        "chapters": [],
    }


def _spec(tmp_path: Path, permissions: set[str]) -> tuple[Path, list[Path]]:
    source_paths: list[Path] = []
    sources: list[dict[str, Any]] = []
    calibration_remaining = 20
    evaluation_remaining = 60
    for source_index in range(3):
        media = tmp_path / f"source-{source_index}.bin"
        media.write_bytes(f"authorized source {source_index}".encode())
        source_paths.append(media)
        rights = tmp_path / f"source-{source_index}.rights.json"
        create_rights_manifest(media, rights, "operator", "owned", permissions)
        selections: list[dict[str, Any]] = []
        calibration_count = 7 if source_index < 2 else calibration_remaining
        evaluation_count = 20 if source_index < 2 else evaluation_remaining
        calibration_remaining -= calibration_count
        evaluation_remaining -= evaluation_count
        timestamp = 1000
        for _ in range(calibration_count):
            selections.append(
                {
                    "timestamp_ms": timestamp,
                    "split": "calibration",
                    "categories": ["test"],
                    "difficulty": ["controlled"],
                }
            )
            timestamp += 1000
        for _ in range(evaluation_count):
            selections.append(
                {
                    "timestamp_ms": timestamp,
                    "split": "evaluation",
                    "categories": ["test"],
                    "difficulty": ["controlled"],
                }
            )
            timestamp += 1000
        sources.append(
            {
                "media_path": str(media),
                "rights_manifest_path": str(rights),
                "selections": selections,
            }
        )
    spec = tmp_path / "pilot-spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "pilot_id": "PILOT_STABLE_INPUT_TEST",
                "selection_method": "pre-registered",
                "random_seed": None,
                "inclusion_criteria": ["visible frame"],
                "exclusion_criteria": ["decode failure"],
                "duplicate_frame_policy": "reject exact source/timestamp duplicates",
                "sources": sources,
            }
        ),
        encoding="utf-8",
    )
    return spec, source_paths


def test_pilot_inventory_and_frame_extraction_use_snapshots_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, original_sources = _spec(
        tmp_path,
        {"analysis", "annotation", "evaluation", "derivative_artifact_retention"},
    )
    inspected: list[Path] = []
    extracted: list[Path] = []
    snapshot_parents: set[Path] = set()

    def inspect(path: Path) -> dict[str, Any]:
        assert path not in original_sources
        assert path.is_file()
        inspected.append(path)
        snapshot_parents.add(path.parent)
        return _inventory(path)

    def extract(path: Path, timestamp_ms: int, output: Path) -> None:
        assert path not in original_sources
        assert path.is_file()
        extracted.append(path)
        snapshot_parents.add(path.parent)
        output.write_bytes(f"frame-{timestamp_ms}".encode())

    monkeypatch.setattr("av_atlas.ocr_pilot_intake.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.ocr_pilot_intake._extract_frame", extract)
    output = tmp_path / "pilot"
    manifest = prepare_pilot(spec, output)

    assert len(inspected) == 3
    assert len(extracted) == 80
    assert manifest["counts"] == {
        "sources": 3,
        "calibration_frames": 20,
        "evaluation_frames": 60,
    }
    assert all(not path.exists() for path in inspected)
    assert all(not parent.exists() for parent in snapshot_parents)
    raw = (output / "pilot_manifest.json").read_text(encoding="utf-8")
    assert all(str(source) not in raw for source in original_sources)
    assert all(str(path) not in raw for path in inspected)


def test_pilot_missing_annotation_permission_fails_before_parser_and_cleans_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, _ = _spec(
        tmp_path,
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    calls: list[Path] = []

    def forbidden(path: Path) -> dict[str, Any]:
        calls.append(path)
        raise AssertionError("pilot parser must not run without annotation permission")

    monkeypatch.setattr("av_atlas.ocr_pilot_intake.inspect_media", forbidden)
    output = tmp_path / "pilot"
    with pytest.raises(AtlasError, match="annotation"):
        prepare_pilot(spec, output)
    assert calls == []
    assert not output.exists()


def test_pilot_insufficient_evaluation_closure_fails_before_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, _ = _spec(
        tmp_path,
        {"analysis", "annotation", "derivative_artifact_retention"},
    )
    calls: list[Path] = []

    def forbidden(path: Path) -> dict[str, Any]:
        calls.append(path)
        raise AssertionError("pilot parser must not run without evaluation permission")

    monkeypatch.setattr("av_atlas.ocr_pilot_intake.inspect_media", forbidden)
    output = tmp_path / "pilot"
    with pytest.raises(AtlasError, match="evaluation"):
        prepare_pilot(spec, output)
    assert calls == []
    assert not output.exists()
