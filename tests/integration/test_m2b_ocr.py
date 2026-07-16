import json
import shutil
from pathlib import Path

import pytest

from av_atlas.cli import main
from av_atlas.fixture import make_m2b_fixture
from av_atlas.rights import create_rights_manifest


def test_m2b_unavailable_path_is_complete_honest_and_valid(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg is unavailable")
    root = Path(__file__).parents[2]
    media = make_m2b_fixture(tmp_path / "fixture")
    marker = json.loads(media.with_suffix(".fixture.json").read_text())
    assert marker["schema_version"] == "1.1.0"
    assert marker["sidecars"] == []
    run_dir = tmp_path / "run"
    config = json.loads((root / "configs/m2b.yaml").read_text())
    config["ocr"]["executable"] = "definitely-not-an-installed-ocr"
    config_path = tmp_path / "unavailable.json"
    config_path.write_text(json.dumps(config))
    rights = tmp_path / "rights.json"
    create_rights_manifest(
        media,
        rights,
        "controlled-test",
        "synthetic-controlled",
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    args = [
        "run",
        str(media),
        "--config",
        str(config_path),
        "--output",
        str(run_dir),
        "--rights-manifest",
        str(rights),
    ]
    assert main(args) == 0
    gold = root / "tests/gold/m2b-ocr-controlled.gold.json"
    assert main(["evaluate-ocr", str(run_dir), str(gold)]) == 0
    assert main(["benchmark-ocr", str(run_dir), str(gold)]) == 0
    assert main(["validate", str(run_dir)]) == 0
    assert (run_dir / "ocr_observations.jsonl").read_text() == ""
    adapter = json.loads((run_dir / "adapter_results.json").read_text())
    states = {item["adapter"]: item["status"] for item in adapter["results"]}
    assert states["ocr_frame"] == "unavailable_dependency"
    evaluation = json.loads((run_dir / "ocr_evaluation.json").read_text())
    assert evaluation["measured_results"] is None
    benchmark = json.loads((run_dir / "ocr_benchmark.json").read_text())
    assert all(
        item["state"] == "blocked_unavailable_dependency" for item in benchmark["measurements"]
    )
    assert "IGNORE PREVIOUS" not in (run_dir / "run.log.jsonl").read_text()
