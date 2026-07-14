import json
from pathlib import Path

import pytest

from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError


def _config(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1.0.0",
        "chunk_duration_ms": 2000,
        "chunk_overlap_ms": 250,
        "sample_interval_ms": 1000,
        "adapters": ["ocr_frame"],
        "ocr": {"enabled": True, "retain_raw_frames": False},
    }
    value.update(changes)
    return value


@pytest.mark.parametrize(
    ("section", "expected"),
    [
        ({"ocr": {"enabled": "false"}}, "enabled"),
        ({"ocr": {"enabled": True, "workers": True}}, "workers"),
        ({"ocr": {"enabled": True, "preprocessing": {"threshold": "100"}}}, "threshold"),
        ({"ocr": {"enabled": True, "languages": "eng"}}, "languages"),
        ({"ocr": {"enabled": True, "preprocessing": {"mystery": True}}}, "mystery"),
        ({"subtitle": {"mode": "all", "mystery": 1}}, "mystery"),
        ({"shot": {"enabled": True, "mystery": 1}}, "mystery"),
        ({"resources": {"mystery": 1}}, "mystery"),
        ({"ocr": {"enabled": True, "mystery": 1}}, "mystery"),
    ],
)
def test_configuration_rejects_wrong_types_and_unknown_nested_keys(
    tmp_path: Path, section: dict[str, object], expected: str
) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_config(**section)))
    with pytest.raises(AtlasError, match=expected):
        BaselineConfig.load(path)


def test_raw_frame_retention_true_is_explicitly_unsupported(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_config(ocr={"enabled": True, "retain_raw_frames": True})))
    with pytest.raises(AtlasError, match="retain_raw_frames"):
        BaselineConfig.load(path)
