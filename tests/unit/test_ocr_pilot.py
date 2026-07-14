import json
from pathlib import Path

import pytest

from av_atlas.cli import main
from av_atlas.errors import AtlasError
from av_atlas.io import canonical_json
from av_atlas.ocr_pilot import _digest, make_annotation_packages, prepare_pilot
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
