import json
from pathlib import Path

import pytest

from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError
from av_atlas.ocr import inspect_ocr, parse_tsv
from av_atlas.schemas import validate_instance


def test_tesseract_tsv_preserves_raw_text_confidence_and_geometry() -> None:
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
        "width\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t10\t20\t30\t12\t92.5\tIGNORE\n"
    )
    assert parse_tsv(tsv, 50) == [
        {
            "row_index": 1,
            "text": "IGNORE",
            "confidence": 92.5,
            "bbox": [10, 20, 40, 32],
        }
    ]


def test_invalid_tsv_geometry_fails_without_fabrication() -> None:
    with pytest.raises(AtlasError, match="invalid Tesseract TSV"):
        parse_tsv("left\ttop\twidth\theight\tconf\ttext\n0\t0\t-1\t2\t90\tbad\n", 0)


def test_absent_dependency_is_actionable_and_does_not_install() -> None:
    result = inspect_ocr("definitely-not-an-installed-ocr")
    assert result["state"] == "unavailable"
    assert result["network_accessed"] is False
    assert result["installation_command"] == (
        "sudo apt-get install tesseract-ocr tesseract-ocr-eng"
    )


def test_ocr_config_rejects_unsafe_worker_count(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        '{"schema_version":"1.0.0","chunk_duration_ms":1,"chunk_overlap_ms":0,'
        '"sample_interval_ms":1,"adapters":["ocr_frame"],'
        '"ocr":{"enabled":true,"workers":5}}'
    )
    with pytest.raises(AtlasError, match="workers"):
        BaselineConfig.load(path)


def test_synthetic_ocr_gold_is_not_presented_as_human_annotation() -> None:
    path = Path(__file__).parents[1] / "gold/m2b-ocr-controlled.gold.json"
    value = json.loads(path.read_text())
    validate_instance("ocr_gold", value, path.name)
    assert value["adjudication_state"] == "synthetic-generator-gold"
    assert value["provenance"]["human_annotations"] is False


@pytest.mark.tesseract
def test_real_tesseract_gate_executes_approved_english_data() -> None:
    result = inspect_ocr()
    if result["state"] != "available":
        pytest.skip(result["installation_command"])
    assert "eng" in result["available_languages"]
    english = next(item for item in result["language_data"] if item["language"] == "eng")
    assert len(english["sha256"]) == 64
    assert english["size_bytes"] > 0
