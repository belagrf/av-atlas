from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from av_atlas.cli import main
from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError
from av_atlas.fixture import make_m2a_fixture, make_modality_edge_fixtures
from av_atlas.io import sha256_file
from av_atlas.media import inspect_media
from av_atlas.rights import create_rights_manifest, manifest_digest
from av_atlas.subtitles import extract_subtitles
from av_atlas.validation import validate_run


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(__file__).parents[2]


@pytest.fixture(scope="module")
def controlled_media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg is unavailable")
    media = make_m2a_fixture(tmp_path_factory.mktemp("m2a_fixture"))
    _rights(
        media,
        media.with_suffix(".rights.json"),
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    return media


def _rights(
    media: Path,
    path: Path,
    allowed: set[str],
    basis: str = "synthetic-controlled",
) -> Path:
    create_rights_manifest(
        media,
        path,
        "test-operator",
        basis,
        allowed,
    )
    return path


def _controlled_rights(media: Path) -> Path:
    return media.with_suffix(".rights.json")


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
        basis="owned",
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
                "--rights-manifest",
                str(_controlled_rights(controlled_media)),
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
        main(
            [
                "run",
                str(controlled_media),
                "--config",
                str(config),
                "--output",
                str(second),
                "--rights-manifest",
                str(_controlled_rights(controlled_media)),
            ]
        )
        == 0
    )
    for name in ("shots.jsonl", "keyframes.jsonl", "subtitles.jsonl", "subtitle_tracks.json"):
        assert sha256_file(interrupted / name) == sha256_file(second / name)


def test_missing_subtitles_is_observed_absence(tmp_path: Path, project_root: Path) -> None:
    no_subtitles, no_video = make_modality_edge_fixtures(tmp_path / "edges")
    for fixture in (no_subtitles, no_video):
        marker = json.loads(fixture.with_suffix(".fixture.json").read_text())
        assert marker["schema_version"] == "1.1.0"
        assert marker["sidecars"] == []
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


def test_fresh_m2a_fixture_has_current_empty_sidecar_contract(
    controlled_media: Path,
) -> None:
    marker = json.loads(controlled_media.with_suffix(".fixture.json").read_text())
    assert marker["schema_version"] == "1.1.0"
    assert marker["sidecars"] == []


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


def test_run_native_parser_arguments_never_contain_original_media_path(
    controlled_media: Path,
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_run = subprocess.run
    argument_lists: list[list[str]] = []

    def capture(
        arguments: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
        argument_lists.append([str(item) for item in arguments])
        return real_run(arguments, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", capture)
    run_dir = tmp_path / "snapshot-only"
    assert (
        main(
            [
                "run",
                str(controlled_media),
                "--config",
                str(project_root / "configs/m2a.yaml"),
                "--output",
                str(run_dir),
                "--rights-manifest",
                str(_controlled_rights(controlled_media)),
            ]
        )
        == 0
    )
    original = str(controlled_media)
    assert all(original not in arguments for arguments in argument_lists)
    media_parser_calls = [
        arguments
        for arguments in argument_lists
        if Path(arguments[0]).name in {"ffprobe", "ffmpeg"}
        and any(Path(argument).name == "source.snapshot" for argument in arguments)
    ]
    assert media_parser_calls
    expected_policy_prefix = [
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        "matroska",
        "-f",
        "matroska",
    ]
    for arguments in media_parser_calls:
        assert arguments.count("-i") == 1
        input_index = arguments.index("-i")
        policy_index = arguments.index("-protocol_whitelist")
        assert arguments[policy_index : policy_index + 6] == expected_policy_prefix
        assert policy_index < input_index
        assert Path(arguments[input_index + 1]).name == "source.snapshot"
        assert not any(
            value in arguments for value in ("hls", "dash", "concat", "concatf", "image2", "bluray")
        )
    snapshot_arguments = [
        argument
        for arguments in media_parser_calls
        for argument in arguments
        if Path(argument).name == "source.snapshot"
    ]
    assert all(not Path(argument).exists() for argument in snapshot_arguments)


def test_authorized_nonfixture_run_uses_only_snapshot_and_exports_no_input_paths(
    controlled_media: Path,
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "operator;$(inert).mkv"
    media.write_bytes(controlled_media.read_bytes())
    rights = _rights(
        media,
        tmp_path / "rights.json",
        {"analysis", "derivative_artifact_retention"},
        basis="owned",
    )
    real_run = subprocess.run
    argument_lists: list[list[str]] = []

    def capture(
        arguments: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
        argument_lists.append([str(item) for item in arguments])
        return real_run(arguments, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", capture)
    run_dir = tmp_path / "authorized-nonfixture"
    assert (
        main(
            [
                "run",
                str(media),
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
    parser_calls = [
        arguments
        for arguments in argument_lists
        if Path(arguments[0]).name in {"ffprobe", "ffmpeg", "tesseract"}
    ]
    assert parser_calls
    original = str(media).encode()
    snapshots = {
        argument
        for arguments in parser_calls
        for argument in arguments
        if Path(argument).name == "source.snapshot"
    }
    assert snapshots
    assert all(str(media) not in arguments for arguments in parser_calls)
    assert all(not Path(snapshot).exists() for snapshot in snapshots)
    private_values = [original, *(snapshot.encode() for snapshot in snapshots)]
    for artifact in run_dir.rglob("*"):
        if artifact.is_file():
            content = artifact.read_bytes()
            assert all(value not in content for value in private_values), artifact
    assert not (tmp_path / "inert").exists()


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("retention", "derivative_artifact_retention"),
        ("expired", "expired"),
        ("source", "exact source"),
        ("operation", "requested operation"),
    ],
)
def test_resume_rights_mutations_fail_before_adapter_execution(
    controlled_media: Path,
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected: str,
) -> None:
    rights = _rights(
        controlled_media,
        tmp_path / "rights.json",
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    run_dir = tmp_path / "interrupted"
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
                "--stop-after",
                "inventory",
            ]
        )
        == 0
    )
    rights_value = json.loads((run_dir / "rights_manifest.json").read_text())
    if mutation == "retention":
        rights_value["permissions"]["derivative_artifact_retention"] = False
    elif mutation == "expired":
        rights_value["expires_at"] = "2000-01-01T00:00:00+00:00"
    elif mutation == "source":
        rights_value["source_id"] = "SRC_000000000000"
    else:
        rights_value["permissions"]["analysis"] = False
    rights_value["manifest_hash"] = manifest_digest(rights_value)
    (run_dir / "rights_manifest.json").write_text(json.dumps(rights_value))
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    manifest["rights"]["manifest_hash"] = rights_value["manifest_hash"]
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest))

    invoked = False

    def forbidden_complete(*args: object, **kwargs: object) -> None:
        nonlocal invoked
        invoked = True
        raise AssertionError("adapter processing must not start")

    monkeypatch.setattr("av_atlas.pipeline._complete", forbidden_complete)
    assert main(["resume", str(run_dir), "--media", str(controlled_media)]) == 2
    assert invoked is False
    assert not (run_dir / "shots.jsonl").exists()


def test_validate_recomputes_rights_manifest_digest(
    controlled_media: Path, project_root: Path, tmp_path: Path
) -> None:
    run_dir = tmp_path / "run"
    assert (
        main(
            [
                "run",
                str(controlled_media),
                "--config",
                str(project_root / "configs/m2a.yaml"),
                "--output",
                str(run_dir),
                "--rights-manifest",
                str(_controlled_rights(controlled_media)),
            ]
        )
        == 0
    )
    path = run_dir / "rights_manifest.json"
    value = json.loads(path.read_text())
    value["permissions"]["analysis"] = False
    path.write_text(json.dumps(value))
    with pytest.raises(AtlasError, match="rights manifest hash is invalid"):
        validate_run(run_dir, write_report=False)


def test_resume_rehashed_rights_with_stale_run_linkage_invokes_no_processing(
    controlled_media: Path,
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "interrupted-linkage"
    assert (
        main(
            [
                "run",
                str(controlled_media),
                "--config",
                str(project_root / "configs/m2a.yaml"),
                "--output",
                str(run_dir),
                "--stop-after",
                "inventory",
                "--rights-manifest",
                str(_controlled_rights(controlled_media)),
            ]
        )
        == 0
    )
    rights_path = run_dir / "rights_manifest.json"
    rights = json.loads(rights_path.read_text())
    rights["notes"] = "changed and rehashed after run linkage was accepted"
    rights["manifest_hash"] = manifest_digest(rights)
    rights_path.write_text(json.dumps(rights), encoding="utf-8")
    invoked: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        invoked.append("processing")
        raise AssertionError("resume processing must not start with stale rights linkage")

    monkeypatch.setattr("av_atlas.pipeline._complete", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert main(["resume", str(run_dir), "--media", str(controlled_media)]) == 2
    assert invoked == []
    assert not (run_dir / "shots.jsonl").exists()


def test_evaluation_permission_closure_is_enforced_on_resume_and_validation(
    controlled_media: Path,
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rights_path = _rights(
        controlled_media,
        tmp_path / "evaluation-rights.json",
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    run_dir = tmp_path / "evaluation-interrupted"
    assert (
        main(
            [
                "run",
                str(controlled_media),
                "--config",
                str(project_root / "configs/m2a.yaml"),
                "--rights-manifest",
                str(rights_path),
                "--operation",
                "evaluation",
                "--output",
                str(run_dir),
                "--stop-after",
                "inventory",
            ]
        )
        == 0
    )
    persisted = run_dir / "rights_manifest.json"
    rights = json.loads(persisted.read_text())
    rights["permissions"]["analysis"] = False
    rights["manifest_hash"] = manifest_digest(rights)
    persisted.write_text(json.dumps(rights), encoding="utf-8")
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["rights"]["manifest_hash"] = rights["manifest_hash"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    invoked: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        invoked.append("processing")
        raise AssertionError("processing must not start without analysis permission")

    monkeypatch.setattr("av_atlas.pipeline._complete", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert main(["resume", str(run_dir), "--media", str(controlled_media)]) == 2
    assert invoked == []
    with pytest.raises(AtlasError, match="requested operation: analysis"):
        validate_run(run_dir, write_report=False)
