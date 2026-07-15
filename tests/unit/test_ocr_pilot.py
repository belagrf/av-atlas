import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from av_atlas.cli import main
from av_atlas.errors import AtlasError
from av_atlas.io import canonical_json, sha256_file, source_id_from_sha256
from av_atlas.native_media import AUTHORIZED_MATROSKA, NativeInputPolicy
from av_atlas.ocr_pilot import _digest, make_annotation_packages, prepare_pilot
from av_atlas.rights import create_rights_manifest
from av_atlas.schemas import validate_instance


def test_pilot_prepare_rejects_undersized_or_unknown_spec_before_media_access(
    tmp_path: Path,
) -> None:
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "pilot_id": "PILOT_TEST",
                "selection_method": "pre-registered",
                "random_seed": None,
                "inclusion_criteria": ["visible frame"],
                "exclusion_criteria": ["decode failure"],
                "duplicate_frame_policy": "reject exact source/timestamp duplicates",
                "sources": [],
            }
        )
    )
    with pytest.raises(AtlasError, match="at least three"):
        prepare_pilot(spec, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_annotation_packages_are_blank_and_separate(tmp_path: Path) -> None:
    pilot = tmp_path / "pilot"
    (pilot / "frames").mkdir(parents=True)
    frames = []
    for index in range(80):
        frame_id = f"FRM_TEST_{index:04d}"
        path = pilot / "frames" / f"{frame_id}.png"
        path.write_bytes(f"frame-{index}".encode())
        frames.append(
            {
                "frame_id": frame_id,
                "source_id": f"SRC_{index % 3:012X}",
                "timestamp_ms": index * 1000,
                "split": "calibration" if index < 20 else "evaluation",
                "categories": ["test"],
                "difficulty": ["test"],
                "path": f"frames/{frame_id}.png",
                "sha256": "0" * 64,
            }
        )
    manifest = {
        "schema_version": "1.0.0",
        "pilot_id": "PILOT_TEST",
        "state": "prepared_unannotated",
        "selection_protocol": {
            "method": "test",
            "random_seed": None,
            "inclusion_criteria": ["test"],
            "exclusion_criteria": ["none"],
            "duplicate_frame_policy": "reject",
        },
        "sources": [{"source_id": f"SRC_{i:012X}"} for i in range(3)],
        "frames": frames,
        "counts": {"sources": 3, "calibration_frames": 20, "evaluation_frames": 60},
        "privacy": {"source_media_copied": False},
        "manifest_hash": "",
    }
    manifest["manifest_hash"] = _digest(manifest)
    (pilot / "pilot_manifest.json").write_text(json.dumps(manifest))
    make_annotation_packages(pilot)
    first = json.loads((pilot / "annotator_A/annotation.json").read_text())
    second = json.loads((pilot / "annotator_B/annotation.json").read_text())
    validate_instance("ocr_human_annotation", first, "A")
    assert first["frames"][0]["exact_transcription"] is None
    assert first["independence_attestation"] is False
    assert first["annotator_pseudonym"] != second["annotator_pseudonym"]
    assert canonical_json(first["frames"]) == canonical_json(second["frames"])


def test_pilot_cli_reports_fail_closed_error(tmp_path: Path) -> None:
    spec = tmp_path / "bad.json"
    spec.write_text("{}")
    assert main(["pilot-prepare", str(spec), "--output", str(tmp_path / "out")]) == 2


def _pilot_spec(tmp_path: Path, *, deny_last: bool = False) -> Path:
    sources = []
    for source_index in range(3):
        media = tmp_path / f"source-{source_index}.bin"
        media.write_bytes(f"synthetic-pilot-source-{source_index}".encode())
        rights = tmp_path / f"source-{source_index}.rights.json"
        permissions = {
            "analysis",
            "annotation",
            "evaluation",
            "derivative_artifact_retention",
        }
        if deny_last and source_index == 2:
            permissions.remove("analysis")
        create_rights_manifest(
            media,
            rights,
            "pilot-test",
            "synthetic-controlled",
            permissions,
        )
        if source_index == 0:
            splits = ["calibration"] * 20 + ["evaluation"] * 20
        else:
            splits = ["evaluation"] * 20
        selections = [
            {
                "timestamp_ms": index * 1000,
                "split": split,
                "categories": ["synthetic-test"],
                "difficulty": ["controlled"],
            }
            for index, split in enumerate(splits)
        ]
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
                "pilot_id": "PILOT_SYNTHETIC_STABLE_INPUT",
                "selection_method": "pre-registered synthetic",
                "random_seed": None,
                "inclusion_criteria": ["project-authored synthetic source"],
                "exclusion_criteria": ["none"],
                "duplicate_frame_policy": "reject source/timestamp duplicates",
                "sources": sources,
            }
        )
    )
    return spec


def test_pilot_denied_later_source_invokes_no_parser_or_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _pilot_spec(tmp_path, deny_last=True)
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("pilot parser must not run before every source is authorized")

    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(AtlasError, match="requested operation: analysis"):
        prepare_pilot(spec, tmp_path / "pilot")
    assert calls == 0
    assert not (tmp_path / "pilot").exists()


def test_pilot_rehashed_rights_after_all_source_preflight_invokes_no_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import ocr_pilot
    from av_atlas.rights import manifest_digest

    spec = _pilot_spec(tmp_path)
    sources = json.loads(spec.read_text())["sources"]
    rights_path = Path(sources[0]["rights_manifest_path"])
    original_preflight = ocr_pilot.preflight_authorized_source
    preflight_calls = 0
    parser_calls = 0

    def preflight(*args: object, **kwargs: object) -> object:
        nonlocal preflight_calls
        result = original_preflight(*args, **kwargs)  # type: ignore[arg-type]
        preflight_calls += 1
        if preflight_calls == 3:
            rights = json.loads(rights_path.read_text())
            rights["notes"] = "validly rehashed after all-source authorization"
            rights["manifest_hash"] = manifest_digest(rights)
            rights_path.write_text(json.dumps(rights))
        return result

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal parser_calls
        parser_calls += 1
        raise AssertionError("changed pilot rights must fail before parsing")

    monkeypatch.setattr(ocr_pilot, "preflight_authorized_source", preflight)
    monkeypatch.setattr(ocr_pilot, "inspect_media", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    output = tmp_path / "pilot"
    with pytest.raises(AtlasError, match="expected rights manifest hash"):
        prepare_pilot(spec, output)
    assert preflight_calls == 3
    assert parser_calls == 0
    assert not output.exists()


def test_synthetic_pilot_preparation_parses_and_extracts_only_from_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _pilot_spec(tmp_path)
    original_paths = {
        Path(source["media_path"]) for source in json.loads(spec.read_text())["sources"]
    }
    parser_paths: list[Path] = []
    extraction_paths: list[Path] = []

    def inspect(path: Path) -> dict[str, Any]:
        parser_paths.append(path)
        digest = sha256_file(path)
        return {
            "schema_version": "1.1.0",
            "source_id": source_id_from_sha256(digest),
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "duration_ms": 100_000,
            "format_names": ["matroska", "webm"],
            "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
            "streams": [],
            "chapters": [],
        }

    def extract(
        path: Path,
        timestamp_ms: int,
        output: Path,
        native_policy: NativeInputPolicy,
    ) -> None:
        assert native_policy == AUTHORIZED_MATROSKA
        extraction_paths.append(path)
        output.write_bytes(f"synthetic-frame-{timestamp_ms}".encode())

    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.ocr_pilot._extract_frame", extract)
    manifest = prepare_pilot(spec, tmp_path / "pilot")
    assert manifest["counts"] == {
        "sources": 3,
        "calibration_frames": 20,
        "evaluation_frames": 60,
    }
    assert len(parser_paths) == 3
    assert len(extraction_paths) == 80
    assert not ({*parser_paths, *extraction_paths} & original_paths)
    assert all(path.name == "source.snapshot" for path in parser_paths + extraction_paths)
    assert all(not path.exists() for path in parser_paths)


def test_controlled_release_manifest_is_private_and_claim_bounded() -> None:
    root = Path(__file__).parents[2]
    raw = (root / "docs/releases/M2B_CONTROLLED_BASELINE_V1.json").read_text()
    value = json.loads(raw)
    assert "/home/" not in raw
    assert value["scope"] == "four-frame project-authored synthetic controlled fixture only"
    assert value["claims"] == {
        "real_media_accuracy": False,
        "semantic_visual_understanding": False,
        "full_m2_complete": False,
    }
    assert (
        value["frozen_hashes"]["observations_semantic"]
        == "f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060"
    )
