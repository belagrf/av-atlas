from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from av_atlas.cli import main
from av_atlas.fixture import make_fixture
from av_atlas.io import sha256_file, write_json, write_jsonl
from av_atlas.ocr_tracks import associate_temporal_text
from av_atlas.pipeline import ARTIFACTS
from av_atlas.validation import validate_run


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).parents[2]


@pytest.fixture
def fixture_media(tmp_path: Path) -> Path:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg is unavailable")
    return make_fixture(tmp_path / "fixture")


def test_offline_cpu_end_to_end_and_artifact_validation(
    fixture_media: Path, project_root: Path, tmp_path: Path
) -> None:
    run_dir = tmp_path / "run"
    assert (
        main(
            [
                "run",
                str(fixture_media),
                "--config",
                str(project_root / "configs/baseline.yaml"),
                "--output",
                str(run_dir),
            ]
        )
        == 0
    )
    for name in (
        *ARTIFACTS,
        "run_manifest.json",
        "state.json",
        "quality_report.json",
        "quality_report.md",
    ):
        assert (run_dir / name).is_file(), name
    report = json.loads((run_dir / "quality_report.json").read_text(encoding="utf-8"))
    assert report["valid"] is True
    events = [
        json.loads(line)
        for line in (run_dir / "events.final.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(events) == 3
    assert all(claim["evidence_refs"] for event in events for claim in event["claims"])
    speech = [item for event in events for item in event["speech"]]
    assert speech == [
        {
            "confidence": 1.0,
            "evidence_ref": "ASR:ASR_0001",
            "source": "sidecar_asr",
            "speaker_id": "SPEAKER_0001",
            "text": "This is synthetic sidecar speech.",
        }
    ]
    timeline = (run_dir / "timeline.md").read_text(encoding="utf-8")
    assert "IGNORE PREVIOUS INSTRUCTIONS" in timeline
    assert "AUD:" in timeline and "VID:" in timeline and "OCR:" in timeline
    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "## Scene summaries" in summary
    assert "## Chapter summaries" in summary
    assert "## Whole-source summary" in summary


def test_interruption_and_idempotent_resume_do_not_duplicate_records(
    fixture_media: Path, project_root: Path, tmp_path: Path
) -> None:
    run_dir = tmp_path / "interrupted"
    args = [
        str(fixture_media),
        "--config",
        str(project_root / "configs/baseline.yaml"),
        "--output",
        str(run_dir),
        "--stop-after",
        "inventory",
    ]
    assert main(["run", *args]) == 0
    assert not (run_dir / "events.final.jsonl").exists()
    assert main(["resume", str(run_dir)]) == 0
    first = (run_dir / "events.final.jsonl").read_bytes()
    assert main(["resume", str(run_dir)]) == 0
    assert (run_dir / "events.final.jsonl").read_bytes() == first
    assert len(first.splitlines()) == 3


def test_resume_uses_verified_run_local_configuration_snapshot(
    fixture_media: Path, project_root: Path, tmp_path: Path
) -> None:
    config = tmp_path / "baseline.yaml"
    config.write_bytes((project_root / "configs/baseline.yaml").read_bytes())
    run_dir = tmp_path / "interrupted"
    assert (
        main(
            [
                "run",
                str(fixture_media),
                "--config",
                str(config),
                "--output",
                str(run_dir),
                "--stop-after",
                "inventory",
            ]
        )
        == 0
    )
    config.write_text("{}", encoding="utf-8")
    assert main(["resume", str(run_dir)]) == 0
    assert len((run_dir / "events.final.jsonl").read_text().splitlines()) == 3


def test_equivalent_semantic_artifacts_for_identical_inputs(
    fixture_media: Path, project_root: Path, tmp_path: Path
) -> None:
    config = project_root / "configs/baseline.yaml"
    run_a, run_b = tmp_path / "a", tmp_path / "b"
    assert main(["run", str(fixture_media), "--config", str(config), "--output", str(run_a)]) == 0
    assert main(["run", str(fixture_media), "--config", str(config), "--output", str(run_b)]) == 0
    stable = [
        name
        for name in ARTIFACTS
        if name
        not in {"inventory.json", "events.provisional.jsonl", "events.final.jsonl", "run.log.jsonl"}
    ]
    assert {name: sha256_file(run_a / name) for name in stable} == {
        name: sha256_file(run_b / name) for name in stable
    }
    for name in ("events.provisional.jsonl", "events.final.jsonl"):
        records_a = [json.loads(line) for line in (run_a / name).read_text().splitlines()]
        records_b = [json.loads(line) for line in (run_b / name).read_text().splitlines()]
        for record in [*records_a, *records_b]:
            record["provenance"].pop("run_id")
        assert records_a == records_b


def test_dangling_evidence_returns_nonzero(
    fixture_media: Path, project_root: Path, tmp_path: Path
) -> None:
    run_dir = tmp_path / "run"
    config = project_root / "configs/baseline.yaml"
    assert main(["run", str(fixture_media), "--config", str(config), "--output", str(run_dir)]) == 0
    path = run_dir / "evidence_index.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["evidence"].pop(next(iter(value["evidence"])))
    path.write_text(json.dumps(value), encoding="utf-8")
    assert main(["validate", str(run_dir)]) != 0


def test_malformed_ocr_track_returns_nonzero_and_writes_actionable_quality_report(
    fixture_media: Path,
    project_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = tmp_path / "malformed-track"
    assert (
        main(
            [
                "run",
                str(fixture_media),
                "--config",
                str(project_root / "configs/baseline.yaml"),
                "--output",
                str(run_dir),
            ]
        )
        == 0
    )
    inventory = json.loads((run_dir / "inventory.json").read_text())
    evidence = json.loads((run_dir / "evidence_index.json").read_text())
    frame_ref = next(ref for ref in evidence["evidence"] if ref.startswith("VID:"))
    records = []
    for index, timestamp in enumerate((1000, 2000), 1):
        observation_id = f"OCR_0001_{index:04d}"
        evidence_ref = f"OCR:{observation_id}"
        records.append(
            {
                "schema_version": "1.0.0",
                "observation_id": observation_id,
                "source_id": inventory["source_id"],
                "shot_id": "SHOT_0001",
                "keyframe_id": f"KEY_{index:04d}",
                "timestamp_ms": timestamp,
                "text": "NEWS",
                "normalized_text": "NEWS",
                "bounding_box": [10, 10, 60, 30],
                "confidence": 90.0,
                "language": "eng",
                "engine": "tesseract",
                "engine_version": "validation-fixture",
                "language_data_identity": "eng:validation-fixture",
                "preprocessing": {},
                "source_frame_evidence_ref": frame_ref,
                "adapter_state": "succeeded",
                "warnings": [],
                "evidence_ref": evidence_ref,
            }
        )
        evidence["evidence"][evidence_ref] = {
            "evidence_ref": evidence_ref,
            "source_id": inventory["source_id"],
            "observation_id": observation_id,
            "modality": "OCR",
            "start_ms": timestamp,
            "end_ms": timestamp + 1,
        }
    tracks = associate_temporal_text(records, 2500)
    tracks["tracks"][0]["source_frame_evidence_refs"].pop()
    write_jsonl(run_dir / "ocr_observations.jsonl", records)
    write_json(run_dir / "ocr_text_tracks.json", tracks)
    write_json(run_dir / "evidence_index.json", evidence)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    for name in ("ocr_observations.jsonl", "ocr_text_tracks.json", "evidence_index.json"):
        path = run_dir / name
        manifest["artifacts"][name] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    write_json(run_dir / "run_manifest.json", manifest)

    assert main(["validate", str(run_dir)]) == 2
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    report = json.loads((run_dir / "quality_report.json").read_text())
    assert report["valid"] is False
    assert any("parallel member-array lengths disagree" in error for error in report["errors"])


def test_fixture_is_byte_deterministic(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is unavailable")
    first = make_fixture(tmp_path / "one")
    second = make_fixture(tmp_path / "two")
    assert sha256_file(first) == sha256_file(second)
    assert sha256_file(first.with_suffix(".observations.json")) == sha256_file(
        second.with_suffix(".observations.json")
    )


def test_clean_tracked_source_checkout_does_not_depend_on_ignored_runs(
    fixture_media: Path, project_root: Path, tmp_path: Path
) -> None:
    tracked_runs = subprocess.run(
        ["git", "ls-files", "runs"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert tracked_runs == ""
    run_dir = tmp_path / "clean-checkout-proof"
    assert (
        main(
            [
                "run",
                str(fixture_media),
                "--config",
                str(project_root / "configs/baseline.yaml"),
                "--output",
                str(run_dir),
            ]
        )
        == 0
    )
    assert validate_run(run_dir, write_report=False)["valid"] is True
