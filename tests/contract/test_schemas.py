import json
from pathlib import Path

from jsonschema import Draft202012Validator

from av_atlas.schemas import validate_instance


def test_every_committed_schema_is_valid_draft_2020_12() -> None:
    root = Path(__file__).parents[2] / "schemas"
    schemas = sorted(root.glob("*.schema.json"))
    assert schemas
    for path in schemas:
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_versioned_gold_and_dependency_bom_records_validate() -> None:
    root = Path(__file__).parents[2]
    for path in sorted((root / "tests/gold").glob("*.json")):
        schema = "ocr_gold" if "m2b-ocr" in path.name else "component_gold"
        validate_instance(schema, json.loads(path.read_text()), path.name)
    bom = root / "docs/dependency-bom.json"
    validate_instance("dependency_bom", json.loads(bom.read_text()), bom.name)


def test_adapter_result_v1_backward_compatibility_and_v1_1_partial_success() -> None:
    validate_instance(
        "adapter_results",
        {
            "schema_version": "1.0.0",
            "results": [
                {
                    "adapter": "ocr_frame",
                    "status": "success",
                    "observation_count": 1,
                    "detail": "legacy",
                    "retryable": False,
                }
            ],
        },
        "legacy adapter results",
    )
    validate_instance(
        "adapter_results",
        {
            "schema_version": "1.1.0",
            "results": [
                {
                    "adapter": "ocr_frame",
                    "status": "partial_success",
                    "observation_count": 1,
                    "detail": "one of two frames succeeded",
                    "retryable": False,
                    "unit_counts": {
                        "attempted": 2,
                        "successful": 1,
                        "failed": 1,
                        "timed_out": 0,
                        "unsupported": 0,
                        "emitted_observations": 1,
                    },
                }
            ],
        },
        "current adapter results",
    )
