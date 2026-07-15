"""Deterministic derived temporal association over immutable OCR observations."""

from __future__ import annotations

from typing import Any

POLICY_VERSION = "ocr-temporal-association/1.0.0"


def spatially_compatible(left: list[int], right: list[int]) -> bool:
    """Apply the spatial-compatibility rule for temporal association policy 1.0.0."""
    lx1, ly1, lx2, ly2 = left
    rx1, ry1, rx2, ry2 = right
    intersection = max(0, min(lx2, rx2) - max(lx1, rx1)) * max(0, min(ly2, ry2) - max(ly1, ry1))
    left_area = max(1, (lx2 - lx1) * (ly2 - ly1))
    right_area = max(1, (rx2 - rx1) * (ry2 - ry1))
    union = left_area + right_area - intersection
    if intersection / union >= 0.1:
        return True
    left_center = ((lx1 + lx2) / 2, (ly1 + ly2) / 2)
    right_center = ((rx1 + rx2) / 2, (ry1 + ry2) / 2)
    scale = max(lx2 - lx1, ly2 - ly1, rx2 - rx1, ry2 - ry1, 1)
    return (
        abs(left_center[0] - right_center[0]) <= scale
        and abs(left_center[1] - right_center[1]) <= scale
    )


def associate_temporal_text(records: list[dict[str, Any]], maximum_gap_ms: int) -> dict[str, Any]:
    """Associate repeated normalized text without deleting or rewriting raw records."""
    tracks: list[dict[str, Any]] = []
    ordered = sorted(
        records,
        key=lambda item: (int(item["timestamp_ms"]), str(item["observation_id"])),
    )
    for record in ordered:
        candidate: dict[str, Any] | None = None
        for track in reversed(tracks):
            if track["source_id"] != record["source_id"]:
                continue
            if track["normalized_text"] != record["normalized_text"]:
                continue
            if track["shot_id"] != record["shot_id"]:
                continue
            if int(record["timestamp_ms"]) - int(track["last_timestamp_ms"]) > maximum_gap_ms:
                continue
            if not spatially_compatible(track["spatial_boxes"][-1], record["bounding_box"]):
                continue
            candidate = track
            break
        if candidate is None:
            candidate = {
                "schema_version": "1.0.0",
                "track_id": f"OCR_TRACK_{len(tracks) + 1:06d}",
                "source_id": record["source_id"],
                "shot_id": record["shot_id"],
                "member_observation_ids": [],
                "source_frame_evidence_refs": [],
                "first_timestamp_ms": record["timestamp_ms"],
                "last_timestamp_ms": record["timestamp_ms"],
                "raw_text_variants": [],
                "normalized_text": record["normalized_text"],
                "spatial_boxes": [],
                "confidence_values": [],
                "confidence_aggregation": "arithmetic_mean",
                "mean_confidence": 0.0,
                "association_policy_version": POLICY_VERSION,
                "maximum_association_gap_ms": maximum_gap_ms,
            }
            tracks.append(candidate)
        candidate["member_observation_ids"].append(record["observation_id"])
        candidate["source_frame_evidence_refs"].append(record["source_frame_evidence_ref"])
        candidate["last_timestamp_ms"] = record["timestamp_ms"]
        if record["text"] not in candidate["raw_text_variants"]:
            candidate["raw_text_variants"].append(record["text"])
        candidate["spatial_boxes"].append(record["bounding_box"])
        candidate["confidence_values"].append(record["confidence"])
        candidate["mean_confidence"] = sum(candidate["confidence_values"]) / len(
            candidate["confidence_values"]
        )
    return {
        "schema_version": "1.0.0",
        "association_policy_version": POLICY_VERSION,
        "maximum_association_gap_ms": maximum_gap_ms,
        "tracks": tracks,
    }
