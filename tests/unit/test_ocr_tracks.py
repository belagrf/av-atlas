from av_atlas.ocr_tracks import associate_temporal_text


def _record(index: int, timestamp: int, shot: str = "SHOT_0001", x: int = 10) -> dict[str, object]:
    return {
        "observation_id": f"OCR_{index}",
        "source_id": "SRC_000000000000",
        "shot_id": shot,
        "keyframe_id": f"KEY_{index}",
        "timestamp_ms": timestamp,
        "text": "NEWS",
        "normalized_text": "NEWS",
        "bounding_box": [x, 10, x + 50, 30],
        "confidence": 90.0,
        "source_frame_evidence_ref": f"VID:frame:{index}",
    }


def test_repeated_lower_third_associates_and_preserves_every_evidence_member() -> None:
    result = associate_temporal_text([_record(1, 1000), _record(2, 2000)], 1500)
    assert len(result["tracks"]) == 1
    track = result["tracks"][0]
    assert track["member_observation_ids"] == ["OCR_1", "OCR_2"]
    assert track["source_frame_evidence_refs"] == ["VID:frame:1", "VID:frame:2"]
    assert track["first_timestamp_ms"] == 1000
    assert track["last_timestamp_ms"] == 2000


def test_same_text_different_location_or_shot_does_not_associate() -> None:
    location = associate_temporal_text([_record(1, 1000), _record(2, 2000, x=500)], 1500)
    boundary = associate_temporal_text([_record(1, 1000), _record(2, 2000, shot="SHOT_0002")], 1500)
    assert len(location["tracks"]) == 2
    assert len(boundary["tracks"]) == 2
