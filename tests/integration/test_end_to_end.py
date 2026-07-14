from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from av_atlas.cli import main
from av_atlas.fixture import make_fixture
from av_atlas.io import sha256_file
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


def test_fixture_is_byte_deterministic(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is unavailable")
    first = make_fixture(tmp_path / "one")
    second = make_fixture(tmp_path / "two")
    assert sha256_file(first) == sha256_file(second)
    assert sha256_file(first.with_suffix(".observations.json")) == sha256_file(
        second.with_suffix(".observations.json")
    )


def test_preserved_m0_run_uses_explicit_legacy_contract(project_root: Path) -> None:
    preserved = project_root / "runs/m0-m1-validation-v3"
    if not preserved.is_dir():
        pytest.skip("preserved local M0 run evidence is intentionally excluded from publication")
    report = validate_run(preserved, write_report=False)
    assert report["valid"] is True
    assert report["checks"]["rights_linkage"] == 0
    assert report["checks"]["artifact_hashes"] == 12
