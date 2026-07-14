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
