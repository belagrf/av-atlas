from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from av_atlas.errors import AtlasError
from av_atlas.schemas import validate_instance

SHA256 = "a" * 64


def _artifact(path: str) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": SHA256,
        "size_bytes": 128,
        "schema_version": "1.0.0",
    }


def _manifest() -> dict[str, Any]:
    binding = {
        "contract_version": "av-atlas-pilot-ocr-output-binding/1.0.0",
        "pilot_id": "PILOT_OUTPUT_SCHEMA",
        "pilot_spec_sha256": SHA256,
        "pilot_spec_size_bytes": 1024,
        "frozen_manifest": {
            "sha256": SHA256,
            "size_bytes": 4096,
            "embedded_manifest_hash": SHA256,
        },
        "policy_sha256": SHA256,
        "prepared_receipt": {
            "path": "pilot_security_receipt.json",
            "sha256": SHA256,
            "size_bytes": 2048,
            "embedded_receipt_hash": SHA256,
            "stage": "prepared",
        },
        "source_set_sha256": SHA256,
        "source_rights_aggregate_sha256": SHA256,
        "ocr_configuration_sha256": SHA256,
        "ocr_configuration_size_bytes": 2048,
        "retained_storage": {
            "decision": "reviewed-remanence-acceptance",
            "root_identity_sha256": SHA256,
            "filesystem_type": "ext4",
            "byte_ceiling": 1073741824,
            "reserve_bytes": 1048576,
        },
        "ocr_dependency_identity_sha256": SHA256,
        "artifacts": {
            "dependency": _artifact("ocr_dependency.json"),
            "observations": _artifact("ocr_observations.jsonl"),
            "evidence_index": _artifact("evidence_index.json"),
            "runtime": _artifact("ocr_runtime.json"),
        },
        "counts": {
            "frames": 60,
            "observations": 13,
            "evidence_entries": 73,
            "source_frame_evidence_entries": 60,
            "ocr_evidence_entries": 13,
        },
        "semantic_output_sha256": SHA256,
    }
    return {
        "schema_version": "1.0.0",
        "contract_version": "av-atlas-pilot-ocr-output/1.0.0",
        "state": "complete",
        "pilot_id": "PILOT_OUTPUT_SCHEMA",
        "output_binding": binding,
        "output_binding_sha256": SHA256,
        "completion_receipt": {
            "path": "pilot_security_receipt.json",
            "sha256": SHA256,
            "size_bytes": 2048,
            "embedded_receipt_hash": SHA256,
            "stage": "ocr-complete",
            "output_binding_sha256": SHA256,
        },
        "manifest_hash": SHA256,
    }


def _observation() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_id": "OCR_ABCDEF012345_0001_0001",
        "source_id": "SRC_ABCDEF012345",
        "shot_id": "SHOT_0001",
        "keyframe_id": "FRM_ABCDEF012345_0000001000",
        "timestamp_ms": 1000,
        "text": "Synthetic text",
        "normalized_text": "synthetic text",
        "bounding_box": [10, 20, 200, 60],
        "confidence": 95.0,
        "language": "eng",
        "engine": "tesseract",
        "engine_version": "tesseract 5.3.0",
        "language_data_identity": "eng:sha256:" + SHA256,
        "preprocessing": {},
        "source_frame_evidence_ref": "VID:SRC_ABCDEF012345:frame:1000",
        "adapter_state": "succeeded",
        "warnings": [],
        "evidence_ref": "OCR:OCR_ABCDEF012345_0001_0001",
    }


def test_pilot_ocr_output_manifest_schema_accepts_complete_contract() -> None:
    validate_instance("pilot_ocr_output_manifest", _manifest(), "pilot OCR output manifest")


@pytest.mark.parametrize(
    ("section", "field"),
    (
        ("output_binding", "prepared_receipt"),
        ("output_binding", "ocr_configuration_size_bytes"),
        ("output_binding", "semantic_output_sha256"),
        ("root", "completion_receipt"),
    ),
)
def test_pilot_ocr_output_manifest_schema_rejects_missing_integrity_fields(
    section: str, field: str
) -> None:
    value = deepcopy(_manifest())
    if section == "root":
        value.pop(field)
    else:
        value[section].pop(field)
    with pytest.raises(AtlasError, match="schema validation failed"):
        validate_instance("pilot_ocr_output_manifest", value, "pilot OCR output manifest")


def test_pilot_ocr_observation_schema_accepts_source_scoped_identity() -> None:
    validate_instance("pilot_ocr_observation", _observation(), "pilot OCR observation")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("observation_id", "OCR_0001_0001"),
        ("keyframe_id", "KEY_0001"),
        ("adapter_state", "partial"),
        ("source_frame_evidence_ref", "VID:wrong"),
    ),
)
def test_pilot_ocr_observation_schema_rejects_non_pilot_identity(field: str, value: str) -> None:
    record = _observation()
    record[field] = value
    with pytest.raises(AtlasError, match="schema validation failed"):
        validate_instance("pilot_ocr_observation", record, "pilot OCR observation")
