from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from av_atlas.cli import main
from av_atlas.config import BaselineConfig
from av_atlas.fixture import make_m2a_fixture, make_modality_edge_fixtures
from av_atlas.io import sha256_file
from av_atlas.media import inspect_media
from av_atlas.rights import create_rights_manifest
from av_atlas.subtitles import extract_subtitles


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(__file__).parents[2]


@pytest.fixture(scope="module")
def controlled_media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg is unavailable")
    return make_m2a_fixture(tmp_path_factory.mktemp("m2a_fixture"))


def _rights(media: Path, path: Path, allowed: set[str]) -> Path:
    create_rights_manifest(
        media,
        path,
        "test-operator",
        "synthetic-controlled",
        allowed,
    )
    return path


def test_non_fixture_refusal_mismatch_permission_and_valid_acceptance(
    controlled_media: Path, project_root: Path, tmp_path: Path
) -> None:
    media = tmp_path / "operator_media.mkv"
    media.write_bytes(controlled_media.read_bytes())
    config = project_root / "configs/m2a.yaml"
    assert (
        main(["run", str(media), "--config", str(config), "--output", str(tmp_path / "refused")])
        != 0
    )

    other = tmp_path / "other.bin"
    other.write_bytes(b"different source")
    mismatch = _rights(
        other,
        tmp_path / "mismatch.json",
        {"analysis", "derivative_artifact_retention"},
    )
    assert (
        main(
            [
                "run",
                str(media),
                "--config",
                str(config),
                "--rights-manifest",
                str(mismatch),
                "--output",
                str(tmp_path / "mismatch-run"),
            ]
        )
        != 0
    )

    no_analysis = _rights(
        media,
        tmp_path / "no-analysis.json",
        {"evaluation", "derivative_artifact_retention"},
    )
    assert (
        main(
            [
                "run",
                str(media),
                "--config",
                str(config),
                "--rights-manifest",
                str(no_analysis),
                "--output",
                str(tmp_path / "no-analysis-run"),
            ]
        )
        != 0
    )

    valid = _rights(
        media,
        tmp_path / "valid.json",
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    run_dir = tmp_path / "accepted"
    assert (
        main(
            [
                "run",
                str(media),
                "--config",
                str(config),
                "--rights-manifest",
                str(valid),
                "--output",
                str(run_dir),
            ]
        )
        == 0
    )
    assert json.loads((run_dir / "run_manifest.json").read_text())["operation"] == "analysis"
    assert "/home/" not in (run_dir / "state.json").read_text()


def test_complete_m2a_run_evaluation_and_prompt_injection_is_inert(
    controlled_media: Path, project_root: Path, tmp_path: Path
) -> None:
    rights = _rights(
        controlled_media,
        tmp_path / "rights.json",
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    run_dir = tmp_path / "run"
    assert (
        main(
            [
                "run",
                str(controlled_media),
                "--config",
                str(project_root / "configs/m2a.yaml"),
                "--rights-manifest",
                str(rights),
                "--output",
                str(run_dir),
            ]
        )
        == 0
    )
    tracks = json.loads((run_dir / "subtitle_tracks.json").read_text())["tracks"]
    assert [
        (item["language"], item["disposition"]["default"], item["disposition"]["forced"])
        for item in tracks
    ] == [
        ("eng", True, False),
        ("deu", False, True),
    ]
    cues = [json.loads(line) for line in (run_dir / "subtitles.jsonl").read_text().splitlines()]
    assert len(cues) == 4
    assert any("IGNORE PREVIOUS INSTRUCTIONS" in item["text"] for item in cues)
    assert (
        json.loads((run_dir / "run_manifest.json").read_text())["configuration"]["path"]
        == "config.snapshot.yaml"
    )
    assert (
        main(["evaluate", str(run_dir), str(project_root / "tests/gold/m2a-controlled.gold.json")])
        == 0
    )
    assert main(["validate", str(run_dir)]) == 0
    evaluation = json.loads((run_dir / "evaluation.json").read_text())
    measured = evaluation["measured_fixture_results"]
    assert measured["shot_boundaries"]["f1"] == 1.0
    assert measured["subtitle_cues"]["text_exact_match_rate"] == 1.0
    assert measured["keyframes"]["missing_count"] == 0
    assert "statistical significance" in evaluation["unmeasured_targets"]


def test_m2a_interruption_repeated_resume_and_semantic_determinism(
    controlled_media: Path, project_root: Path, tmp_path: Path
) -> None:
    config = project_root / "configs/m2a.yaml"
    interrupted = tmp_path / "interrupted"
    assert (
        main(
            [
                "run",
                str(controlled_media),
                "--config",
                str(config),
                "--output",
                str(interrupted),
                "--stop-after",
                "inventory",
            ]
        )
        == 0
    )
    assert main(["resume", str(interrupted), "--media", str(controlled_media)]) == 0
    first = (interrupted / "events.final.jsonl").read_bytes()
    assert main(["resume", str(interrupted), "--media", str(controlled_media)]) == 0
    assert (interrupted / "events.final.jsonl").read_bytes() == first

    second = tmp_path / "second"
    assert (
        main(["run", str(controlled_media), "--config", str(config), "--output", str(second)]) == 0
    )
    for name in ("shots.jsonl", "keyframes.jsonl", "subtitles.jsonl", "subtitle_tracks.json"):
        assert sha256_file(interrupted / name) == sha256_file(second / name)


def test_missing_subtitles_is_observed_absence(tmp_path: Path, project_root: Path) -> None:
    no_subtitles, _ = make_modality_edge_fixtures(tmp_path / "edges")
    config = BaselineConfig.load(project_root / "configs/m2a.yaml")
    output = extract_subtitles(
        no_subtitles,
        inspect_media(no_subtitles),
        tmp_path / "subtitle-run",
        "all",
        (),
        config.subprocess_timeout_seconds,
    )
    assert output.result.status == "success_zero"
    assert output.result.observations == ()
    assert output.tracks["tracks"] == []


def test_explicit_subtitle_track_selection(
    controlled_media: Path, project_root: Path, tmp_path: Path
) -> None:
    config = BaselineConfig.load(project_root / "configs/m2a.yaml")
    output = extract_subtitles(
        controlled_media,
        inspect_media(controlled_media),
        tmp_path / "selected",
        "selected",
        (3,),
        config.subprocess_timeout_seconds,
    )
    assert [cue["track_id"] for cue in output.cues] == ["TRACK_0003", "TRACK_0003"]
    statuses = {track["track_id"]: track["status"] for track in output.tracks["tracks"]}
    assert statuses == {"TRACK_0002": "not_selected", "TRACK_0003": "extracted"}
