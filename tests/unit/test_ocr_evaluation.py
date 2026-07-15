import json
from pathlib import Path

from av_atlas.ocr_evaluation import _quality_metrics
from av_atlas.ocr_tracks import associate_temporal_text


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value))


def _record(frame: str, timestamp: int, observation: str) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "observation_id": observation,
        "source_id": "SRC_000000000000",
        "shot_id": "SHOT_0001",
        "keyframe_id": frame,
        "timestamp_ms": timestamp,
        "text": "TEXT",
        "normalized_text": "TEXT",
        "bounding_box": [10, 10, 40, 30],
        "confidence": 90.0,
        "language": "eng",
        "engine": "tesseract",
        "engine_version": "test",
        "language_data_identity": "eng:test",
        "preprocessing": {},
        "source_frame_evidence_ref": f"VID:{frame}",
        "adapter_state": "succeeded",
        "warnings": [],
        "evidence_ref": f"OCR:{observation}",
    }


def _gold() -> dict[str, object]:
    return {
        "frames": [
            {
                "keyframe_id": "KEY_GOLD_TEXT",
                "timestamp_ms": 1000,
                "normalized_transcription": "TEXT",
                "difficulty": ["text"],
            },
            {
                "keyframe_id": "KEY_NO_TEXT",
                "timestamp_ms": 2000,
                "normalized_transcription": "",
                "difficulty": ["no-text"],
            },
            {
                "keyframe_id": "KEY_GOLD_ONLY",
                "timestamp_ms": 3000,
                "normalized_transcription": "MISSING",
                "difficulty": ["text"],
            },
        ]
    }


def _runtime() -> dict[str, object]:
    return {
        "timeouts": 0,
        "retries": 0,
        "wall_seconds": 1.0,
        "cpu_seconds": 1.0,
        "peak_rss_kb": 1,
        "frames_per_second": 1.0,
    }


def test_prediction_only_gold_only_and_no_text_frames_affect_presence_metrics(
    tmp_path: Path,
) -> None:
    records = [_record("KEY_GOLD_TEXT", 1000, "OCR_1"), _record("KEY_PRED_ONLY", 4000, "OCR_2")]
    (tmp_path / "ocr_observations.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in records)
    )
    evidence = {}
    for item in records:
        evidence[item["evidence_ref"]] = {}
        evidence[item["source_frame_evidence_ref"]] = {}
    _write_json(tmp_path / "evidence_index.json", {"evidence": evidence})
    _write_json(tmp_path / "ocr_runtime.json", _runtime())
    _write_json(tmp_path / "ocr_frame_results.json", {"adapter_state": "succeeded", "frames": []})
    _write_json(
        tmp_path / "adapter_results.json",
        {"results": [{"adapter": "ocr_frame", "status": "success"}]},
    )
    _write_json(tmp_path / "ocr_text_tracks.json", associate_temporal_text(records, 2500))
    metrics = _quality_metrics(tmp_path, _gold())
    assert metrics["frame_text_presence_precision"] == 0.5
    assert metrics["frame_text_presence_recall"] == 0.5
    assert metrics["prediction_only_keyframe_count"] == 1
    assert metrics["gold_only_keyframe_count"] == 1
    assert metrics["invalid_timestamp_count"] == 0


def test_zero_observation_state_correctness_is_explicit_not_vacuous(tmp_path: Path) -> None:
    (tmp_path / "ocr_observations.jsonl").write_text("")
    _write_json(tmp_path / "evidence_index.json", {"evidence": {}})
    _write_json(tmp_path / "ocr_runtime.json", _runtime())
    _write_json(tmp_path / "ocr_frame_results.json", {"adapter_state": "succeeded", "frames": []})
    _write_json(tmp_path / "ocr_text_tracks.json", associate_temporal_text([], 2500))
    _write_json(
        tmp_path / "adapter_results.json",
        {"results": [{"adapter": "ocr_frame", "status": "success_zero"}]},
    )
    assert _quality_metrics(tmp_path, _gold())["adapter_state_correctness"] is True
    _write_json(
        tmp_path / "adapter_results.json",
        {"results": [{"adapter": "ocr_frame", "status": "success"}]},
    )
    assert _quality_metrics(tmp_path, _gold())["adapter_state_correctness"] is False
