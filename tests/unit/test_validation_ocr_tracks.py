from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from av_atlas.ocr_tracks import POLICY_VERSION, associate_temporal_text
from av_atlas.validation import _validate_ocr_tracks


def _record(index: int, timestamp: int) -> dict[str, Any]:
    return {
        "observation_id": f"OCR_0001_{index:04d}",
        "source_id": "SRC_000000000000",
        "shot_id": "SHOT_0001",
        "timestamp_ms": timestamp,
        "normalized_text": "NEWS",
        "bounding_box": [10, 10, 60, 30],
        "confidence": 90.0 + index,
        "source_frame_evidence_ref": f"VID:SRC_000000000000:frame:{timestamp}",
        "text": "NEWS",
    }


def _case(tmp_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any], set[str]]:
    config = json.loads((Path(__file__).parents[2] / "configs/m2b.yaml").read_text())
    (tmp_path / "config.snapshot.yaml").write_text(json.dumps(config), encoding="utf-8")
    records = [_record(1, 1000), _record(2, 2000)]
    payload = associate_temporal_text(records, 2500)
    refs = {item["source_frame_evidence_ref"] for item in records}
    return records, payload, refs


def _validate(
    tmp_path: Path, records: list[dict[str, Any]], payload: dict[str, Any], refs: set[str]
) -> list[str]:
    (tmp_path / "ocr_text_tracks.json").write_text(json.dumps(payload), encoding="utf-8")
    errors: list[str] = []
    assert _validate_ocr_tracks(tmp_path, records, refs, errors) == len(payload["tracks"])
    return errors


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("evidence_length", "parallel member-array lengths disagree"),
        ("box_length", "parallel member-array lengths disagree"),
        ("confidence_length", "parallel member-array lengths disagree"),
        ("empty_arrays", "parallel member arrays must be nonempty"),
        ("unresolved_member", "member observation is unresolved"),
        ("duplicate_member", "duplicate member observation IDs"),
        ("source", "wrong source ID"),
        ("shot", "crosses a shot boundary"),
        ("text", "different normalized text"),
        ("evidence", "wrong evidence reference"),
        ("box", "wrong spatial box"),
        ("confidence_value", "wrong confidence value"),
        ("first", "first timestamp does not match"),
        ("last", "last timestamp does not match"),
        ("mean", "mean confidence is not the arithmetic mean"),
        ("policy", "unsupported association policy"),
        ("gap", "exceed the configured association gap"),
        ("order", "not deterministically ordered"),
    ],
)
def test_malformed_track_relations_return_actionable_errors(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    records, original, refs = _case(tmp_path)
    payload = copy.deepcopy(original)
    track = payload["tracks"][0]
    if mutation == "evidence_length":
        track["source_frame_evidence_refs"].pop()
    elif mutation == "box_length":
        track["spatial_boxes"].pop()
    elif mutation == "confidence_length":
        track["confidence_values"].pop()
    elif mutation == "empty_arrays":
        for field in (
            "member_observation_ids",
            "source_frame_evidence_refs",
            "spatial_boxes",
            "confidence_values",
        ):
            track[field] = []
    elif mutation == "unresolved_member":
        track["member_observation_ids"][1] = "OCR_9999_9999"
    elif mutation == "duplicate_member":
        track["member_observation_ids"][1] = track["member_observation_ids"][0]
    elif mutation == "source":
        track["source_id"] = "SRC_FFFFFFFFFFFF"
    elif mutation == "shot":
        track["shot_id"] = "SHOT_9999"
    elif mutation == "text":
        track["normalized_text"] = "DIFFERENT"
    elif mutation == "evidence":
        track["source_frame_evidence_refs"][1] = records[0]["source_frame_evidence_ref"]
    elif mutation == "box":
        track["spatial_boxes"][1] = [500, 500, 550, 520]
    elif mutation == "confidence_value":
        track["confidence_values"][1] = 1.0
    elif mutation == "first":
        track["first_timestamp_ms"] = 999
    elif mutation == "last":
        track["last_timestamp_ms"] = 2001
    elif mutation == "mean":
        track["mean_confidence"] = 1.0
    elif mutation == "policy":
        payload["association_policy_version"] = "unsupported/9.9"
        track["association_policy_version"] = "unsupported/9.9"
    elif mutation == "gap":
        records[1]["timestamp_ms"] = 5000
        track["last_timestamp_ms"] = 5000
    elif mutation == "order":
        for field in (
            "member_observation_ids",
            "source_frame_evidence_refs",
            "spatial_boxes",
            "confidence_values",
        ):
            track[field].reverse()
    errors = _validate(tmp_path, records, payload, refs)
    assert any(expected in error for error in errors), errors


def test_generated_track_relations_validate_cleanly(tmp_path: Path) -> None:
    records, payload, refs = _case(tmp_path)
    assert payload["association_policy_version"] == POLICY_VERSION
    assert _validate(tmp_path, records, payload, refs) == []


def test_empty_tracks_are_valid_only_for_empty_raw_observations(tmp_path: Path) -> None:
    records, payload, refs = _case(tmp_path)
    payload["tracks"] = []
    errors = _validate(tmp_path, records, payload, refs)
    assert any("empty while eligible raw observations exist" in error for error in errors)
    assert any("omitted from temporal tracks" in error for error in errors)

    empty = associate_temporal_text([], 2500)
    assert _validate(tmp_path, [], empty, set()) == []


def test_complete_derivation_rejects_omission_duplication_and_fabrication(tmp_path: Path) -> None:
    records, payload, refs = _case(tmp_path)
    omitted = copy.deepcopy(payload)
    track = omitted["tracks"][0]
    for field in (
        "member_observation_ids",
        "source_frame_evidence_refs",
        "spatial_boxes",
        "confidence_values",
    ):
        track[field].pop()
    track["last_timestamp_ms"] = records[0]["timestamp_ms"]
    track["mean_confidence"] = records[0]["confidence"]
    errors = _validate(tmp_path, records, omitted, refs)
    assert any("omitted from temporal tracks" in error for error in errors)
    assert any("does not equal the deterministic derivation" in error for error in errors)

    records[1]["shot_id"] = "SHOT_0002"
    split = associate_temporal_text(records, 2500)
    duplicated = copy.deepcopy(split)
    first = records[0]
    second_track = duplicated["tracks"][1]
    second_track["member_observation_ids"].append(first["observation_id"])
    second_track["source_frame_evidence_refs"].append(first["source_frame_evidence_ref"])
    second_track["spatial_boxes"].append(first["bounding_box"])
    second_track["confidence_values"].append(first["confidence"])
    errors = _validate(tmp_path, records, duplicated, refs)
    assert any("appears in multiple temporal tracks" in error for error in errors)

    fabricated = copy.deepcopy(payload)
    fabricated_track = fabricated["tracks"][0]
    fabricated_track["member_observation_ids"].append("OCR_9999_9999")
    fabricated_track["source_frame_evidence_refs"].append(records[0]["source_frame_evidence_ref"])
    fabricated_track["spatial_boxes"].append(records[0]["bounding_box"])
    fabricated_track["confidence_values"].append(records[0]["confidence"])
    errors = _validate(tmp_path, records, fabricated, refs)
    assert any("fabricated member" in error for error in errors)


def test_complete_derivation_rejects_track_identity_order_variants_and_extra_track(
    tmp_path: Path,
) -> None:
    records, _, refs = _case(tmp_path)
    records[1]["shot_id"] = "SHOT_0002"
    payload = associate_temporal_text(records, 2500)

    duplicate_ids = copy.deepcopy(payload)
    duplicate_ids["tracks"][1]["track_id"] = duplicate_ids["tracks"][0]["track_id"]
    errors = _validate(tmp_path, records, duplicate_ids, refs)
    assert any("track IDs are not unique" in error for error in errors)

    reordered = copy.deepcopy(payload)
    reordered["tracks"].reverse()
    errors = _validate(tmp_path, records, reordered, refs)
    assert any("not globally deterministically ordered" in error for error in errors)

    wrong_variants = copy.deepcopy(payload)
    wrong_variants["tracks"][0]["raw_text_variants"] = ["FABRICATED"]
    errors = _validate(tmp_path, records, wrong_variants, refs)
    assert any("raw text variants do not match" in error for error in errors)

    altered = copy.deepcopy(payload)
    altered["tracks"][0]["track_id"] = "OCR_TRACK_999999"
    errors = _validate(tmp_path, records, altered, refs)
    assert any("does not equal the deterministic derivation" in error for error in errors)

    extra = copy.deepcopy(payload)
    extra_track = copy.deepcopy(extra["tracks"][0])
    extra_track["track_id"] = "OCR_TRACK_999999"
    extra["tracks"].append(extra_track)
    errors = _validate(tmp_path, records, extra, refs)
    assert any("appears in multiple temporal tracks" in error for error in errors)
    assert any("does not equal the deterministic derivation" in error for error in errors)
