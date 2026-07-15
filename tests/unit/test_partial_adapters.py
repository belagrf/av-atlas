import json
from pathlib import Path

import pytest

from av_atlas import ocr, subtitles
from av_atlas.adapters import AdapterContext
from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError
from av_atlas.native_media import AUTHORIZED_MATROSKA, NativeInputPolicy
from av_atlas.ocr import TesseractOcrAdapter
from av_atlas.subtitles import extract_subtitles


def _config(tmp_path: Path) -> BaselineConfig:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "chunk_duration_ms": 3000,
                "chunk_overlap_ms": 250,
                "sample_interval_ms": 1000,
                "adapters": ["ocr_frame"],
                "ocr": {"enabled": True, "languages": ["eng"]},
            }
        )
    )
    return BaselineConfig.load(path)


def _dependency(tmp_path: Path) -> dict[str, object]:
    executable = tmp_path / "tesseract"
    executable.write_bytes(b"fake")
    trained = tmp_path / "eng.traineddata"
    trained.write_bytes(b"fake-language")
    return {
        "schema_version": "1.0.0",
        "state": "available",
        "engine": "tesseract",
        "resolved_executable_path": str(executable),
        "executable_sha256": "0" * 64,
        "executable_size_bytes": 4,
        "version": "tesseract test",
        "leptonica_version": "test",
        "reported_build_features": [],
        "version_output": [],
        "executable_package": None,
        "tessdata_prefix": {"environment_value": None, "behavior": "test"},
        "discovered_tessdata_directories": [str(tmp_path)],
        "available_languages": ["eng"],
        "language_data": [
            {
                "language": "eng",
                "path": str(trained),
                "sha256": "1" * 64,
                "size_bytes": 13,
                "package": None,
                "used_by_default_m2b": True,
            }
        ],
        "relevant_environment": {},
        "network_accessed": False,
    }


def _ocr_context(tmp_path: Path) -> AdapterContext:
    keyframes = [
        {
            "keyframe_id": f"KEY_{index:04d}",
            "shot_id": "SHOT_0001",
            "timestamp_ms": index * 1000,
            "evidence_ref": f"VID:frame:{index}",
            "path": f"keyframes/{index}.png",
            "sha256": "0" * 64,
        }
        for index in (1, 2)
    ]
    (tmp_path / "keyframes.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in keyframes)
    )
    return AdapterContext(
        Path("unused"),
        {"source_id": "SRC_000000000000", "duration_ms": 5000},
        tmp_path,
        _config(tmp_path),
    )


@pytest.mark.parametrize(
    ("outcomes", "expected_status", "observations"),
    [
        (["success", "fail"], "partial_success", 1),
        (["fail", "fail"], "decode_failure", 0),
        (["success", "success"], "success", 2),
        (["empty", "empty"], "success_zero", 0),
    ],
)
def test_ocr_unit_outcomes_have_coherent_partial_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[str],
    expected_status: str,
    observations: int,
) -> None:
    dependency = _dependency(tmp_path)
    monkeypatch.setattr(ocr, "inspect_ocr", lambda *args, **kwargs: dependency)

    def process(
        context: AdapterContext,
        dependency_value: dict[str, object],
        temporary: Path,
        frame_number: int,
        keyframe: dict[str, object],
    ) -> tuple[int, list[dict[str, object]], dict[str, object]]:
        outcome = outcomes[frame_number - 1]
        if outcome == "fail":
            raise AtlasError("controlled failure")
        regions = (
            []
            if outcome == "empty"
            else [{"text": "TEXT", "confidence": 90.0, "bbox": [10, 10, 40, 30]}]
        )
        return (
            frame_number,
            regions,
            {
                "keyframe_id": keyframe["keyframe_id"],
                "shot_id": keyframe["shot_id"],
                "timestamp_ms": keyframe["timestamp_ms"],
                "source_frame_evidence_ref": keyframe["evidence_ref"],
                "state": "succeeded",
                "warning": None,
            },
        )

    monkeypatch.setattr(ocr, "_process_frame", process)
    output = TesseractOcrAdapter().run(_ocr_context(tmp_path))
    assert output.result.status == expected_status
    assert len(output.records) == observations
    counts = output.result.as_record()["unit_counts"]
    assert counts["attempted"] == 2
    assert counts["successful"] + counts["failed"] == 2
    assert counts["emitted_observations"] == observations


def _subtitle_inventory() -> dict[str, object]:
    return {
        "source_id": "SRC_000000000000",
        "duration_ms": 5000,
        "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
        "streams": [
            {
                "index": index,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "language": "eng",
                "title": str(index),
                "time_base": "1/1000",
                "disposition": {},
            }
            for index in (1, 2)
        ],
    }


def test_subtitle_one_track_success_and_one_failure_is_partial_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def extract(media: Path, index: int, timeout: int, native_policy: NativeInputPolicy) -> str:
        if index == 2:
            raise AtlasError("controlled track failure")
        return "WEBVTT\n\n00:00.100 --> 00:01.000\nvisible\n"

    monkeypatch.setattr(subtitles, "_extract_track", extract)
    output = extract_subtitles(
        tmp_path / "source.mkv", _subtitle_inventory(), tmp_path / "run", "all", (), 5
    )
    assert output.result.status == "partial_success"
    assert len(output.result.observations) == 1
    assert output.result.successful_units == 1
    assert output.result.failed_units == 1


@pytest.mark.parametrize(
    ("mode", "expected", "observations"),
    [
        ("all_fail", "decode_failure", 0),
        ("all_success", "success", 2),
        ("empty", "success_zero", 0),
    ],
)
def test_subtitle_all_failure_success_and_zero_observation_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected: str,
    observations: int,
) -> None:
    def extract(media: Path, index: int, timeout: int, native_policy: NativeInputPolicy) -> str:
        if mode == "all_fail":
            raise AtlasError("controlled track failure")
        if mode == "empty":
            return "WEBVTT\n\n"
        return f"WEBVTT\n\n00:00.{index}00 --> 00:01.{index}00\ntrack {index}\n"

    monkeypatch.setattr(subtitles, "_extract_track", extract)
    output = extract_subtitles(
        tmp_path / "source.mkv", _subtitle_inventory(), tmp_path / mode, "all", (), 5
    )
    assert output.result.status == expected
    assert len(output.result.observations) == observations
