import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from av_atlas.adapters import AdapterContext
from av_atlas.cli import main
from av_atlas.config import BaselineConfig
from av_atlas.fixture import make_m2b_fixture
from av_atlas.io import sha256_file
from av_atlas.ocr import TesseractOcrAdapter, inspect_ocr
from av_atlas.rights import create_rights_manifest


def _approved_engine() -> None:
    result = inspect_ocr()
    if result["state"] != "available" or "eng" not in result["available_languages"]:
        pytest.skip(result.get("installation_command", "Tesseract English data unavailable"))


def _run_frozen(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = Path(__file__).parents[2]
    media = make_m2b_fixture(tmp_path / "fixture")
    rights = tmp_path / "rights.json"
    create_rights_manifest(
        media,
        rights,
        "controlled-test",
        "synthetic-controlled",
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    run_dir = tmp_path / "run"
    assert (
        main(
            [
                "run",
                str(media),
                "--config",
                str(root / "configs/m2b.yaml"),
                "--output",
                str(run_dir),
                "--rights-manifest",
                str(rights),
            ]
        )
        == 0
    )
    return root, media, run_dir


@pytest.mark.tesseract
def test_actual_frozen_ocr_prompt_is_inert_and_resume_is_idempotent(tmp_path: Path) -> None:
    _approved_engine()
    root, media, run_dir = _run_frozen(tmp_path)
    gold = root / "tests/gold/m2b-ocr-controlled.gold.json"
    assert main(["evaluate-ocr", str(run_dir), str(gold)]) == 0
    observations = (run_dir / "ocr_observations.jsonl").read_text(encoding="utf-8")
    assert "IGNORE" in observations and "PREVIOUS" in observations
    assert "IGNORE PREVIOUS" not in (run_dir / "run.log.jsonl").read_text(encoding="utf-8")
    tracked = json.loads((run_dir / "run_manifest.json").read_text())["artifacts"]
    before = {name: sha256_file(run_dir / name) for name in tracked}
    assert main(["resume", str(run_dir), "--media", str(media)]) == 0
    assert main(["resume", str(run_dir), "--media", str(media)]) == 0
    after = {name: sha256_file(run_dir / name) for name in tracked}
    assert after == before


@pytest.mark.tesseract
def test_ocr_failure_paths_are_structured_and_cleanup_is_bounded(tmp_path: Path) -> None:
    _approved_engine()
    _, _, base = _run_frozen(tmp_path)
    inventory = json.loads((base / "inventory.json").read_text())
    config = BaselineConfig.load(base / "config.snapshot.yaml")

    unsupported = TesseractOcrAdapter().run(
        AdapterContext(Path("unused"), inventory, base, replace(config, ocr_languages=("zzz",)))
    )
    assert unsupported.result.status == "invalid_configuration"
    assert unsupported.records == ()

    corrupt = tmp_path / "corrupt"
    shutil.copytree(base, corrupt)
    keyframe = json.loads((corrupt / "keyframes.jsonl").read_text().splitlines()[0])
    image = corrupt / keyframe["path"]
    image.write_bytes(b"not an image")
    keyframe["sha256"] = sha256_file(image)
    (corrupt / "keyframes.jsonl").write_text(json.dumps(keyframe) + "\n")
    malformed = TesseractOcrAdapter().run(
        AdapterContext(Path("unused"), inventory, corrupt, config)
    )
    assert malformed.result.status == "decode_failure"
    assert malformed.records == ()

    oversized = tmp_path / "oversized"
    shutil.copytree(base, oversized)
    keyframe = json.loads((oversized / "keyframes.jsonl").read_text().splitlines()[0])
    image = oversized / keyframe["path"]
    image.write_bytes(b"0" * 8_000_001)
    (oversized / "keyframes.jsonl").write_text(json.dumps(keyframe) + "\n")
    too_large = TesseractOcrAdapter().run(
        AdapterContext(Path("unused"), inventory, oversized, config)
    )
    assert too_large.result.status == "decode_failure"
    assert not list(oversized.glob("av-atlas-ocr-*"))

    symlinked = tmp_path / "symlinked"
    shutil.copytree(base, symlinked)
    keyframe = json.loads((symlinked / "keyframes.jsonl").read_text().splitlines()[0])
    original = symlinked / keyframe["path"]
    outside = tmp_path / "outside.png"
    shutil.copy2(original, outside)
    original.unlink()
    original.symlink_to(outside)
    (symlinked / "keyframes.jsonl").write_text(json.dumps(keyframe) + "\n")
    unsafe = TesseractOcrAdapter().run(AdapterContext(Path("unused"), inventory, symlinked, config))
    assert unsafe.result.status == "decode_failure"
    assert unsafe.records == ()


@pytest.mark.tesseract
def test_no_text_metacharacter_path_and_timeout_are_safe(tmp_path: Path) -> None:
    _approved_engine()
    _, _, base = _run_frozen(tmp_path)
    inventory = json.loads((base / "inventory.json").read_text())
    config = BaselineConfig.load(base / "config.snapshot.yaml")

    no_text = tmp_path / "safe;touch-NOT-CREATED"
    shutil.copytree(base, no_text)
    keyframe = json.loads((no_text / "keyframes.jsonl").read_text().splitlines()[0])
    image = no_text / keyframe["path"]
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=640x360",
            "-frames:v",
            "1",
            "-y",
            str(image),
        ],
        check=True,
        shell=False,
    )
    keyframe["sha256"] = sha256_file(image)
    (no_text / "keyframes.jsonl").write_text(json.dumps(keyframe) + "\n")
    empty = TesseractOcrAdapter().run(AdapterContext(Path("unused"), inventory, no_text, config))
    assert empty.result.status == "success_zero"
    assert empty.records == ()
    assert not (tmp_path / "touch-NOT-CREATED").exists()

    fake_root = tmp_path / "fake"
    tessdata = fake_root / "tessdata"
    tessdata.mkdir(parents=True)
    (tessdata / "eng.traineddata").write_bytes(b"approved-test-language-data")
    executable = fake_root / "tesseract"
    executable.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo \'tesseract 5.test\'; '
        "echo 'leptonica-1.test'; exit 0; fi\n"
        'if [ "$1" = "--list-langs" ]; then echo \'List of available languages in "'
        + str(tessdata)
        + "/\" (1):'; echo eng; exit 0; fi\n"
        "sleep 2\n"
    )
    os.chmod(executable, 0o700)
    timed = TesseractOcrAdapter().run(
        AdapterContext(
            Path("unused"),
            inventory,
            no_text,
            replace(config, ocr_executable=str(executable), ocr_timeout_seconds=1),
        )
    )
    assert timed.result.status == "resource_limit_failure"
    runtime = json.loads((no_text / "ocr_runtime.json").read_text())
    assert runtime["timeouts"] == 1
    assert not list(no_text.glob("av-atlas-ocr-*"))
