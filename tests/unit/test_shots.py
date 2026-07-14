from pathlib import Path

from av_atlas.config import BaselineConfig
from av_atlas.fixture import make_m2a_fixture, make_modality_edge_fixtures
from av_atlas.media import inspect_media
from av_atlas.shots import detect_shots


def test_controlled_hard_gradual_flash_and_keyframes(tmp_path: Path) -> None:
    media = make_m2a_fixture(tmp_path / "fixture")
    config = BaselineConfig.load(Path(__file__).parents[2] / "configs/m2a.yaml")
    output = detect_shots(media, inspect_media(media), tmp_path / "run", config)
    assert output.result.status == "success"
    assert [(shot["start_ms"], shot["boundary_type"]) for shot in output.shots] == [
        (0, "source_start"),
        (2000, "hard_cut"),
        (4600, "gradual_transition"),
        (8000, "hard_cut"),
    ]
    assert 6000 not in {shot["start_ms"] for shot in output.shots}
    assert all(
        shot["start_ms"] <= keyframe["timestamp_ms"] < shot["end_ms"]
        for shot, keyframe in zip(output.shots, output.keyframes, strict=True)
    )
    assert all((tmp_path / "run" / item["path"]).is_file() for item in output.keyframes)


def test_missing_video_degrades_without_observations(tmp_path: Path) -> None:
    _, media = make_modality_edge_fixtures(tmp_path / "fixture")
    config = BaselineConfig.load(Path(__file__).parents[2] / "configs/m2a.yaml")
    output = detect_shots(media, inspect_media(media), tmp_path / "run", config)
    assert output.result.status == "unsupported_input"
    assert output.result.observations == ()


def test_corrupt_video_decode_failure_has_no_observations(tmp_path: Path) -> None:
    media = tmp_path / "corrupt.mkv"
    media.write_bytes(b"corrupt")
    config = BaselineConfig.load(Path(__file__).parents[2] / "configs/m2a.yaml")
    inventory = {
        "source_id": "SRC_000000000000",
        "duration_ms": 1000,
        "streams": [{"codec_type": "video"}],
    }
    output = detect_shots(media, inventory, tmp_path / "run", config)
    assert output.result.status == "decode_failure"
    assert output.result.observations == ()
