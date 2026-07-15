"""Versioned schema loading and JSON validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from av_atlas.errors import AtlasError

SCHEMA_FILES = {
    "config": "config.schema.json",
    "event": "event-ledger.schema.json",
    "provenance": "provenance.schema.json",
    "run_manifest": "run-manifest.schema.json",
    "inventory": "media-inventory.schema.json",
    "evidence_index": "evidence-index.schema.json",
    "entity": "entity.schema.json",
    "quality_report": "quality-report.schema.json",
    "state": "state.schema.json",
    "structured_log": "structured-log.schema.json",
    "observation_sidecar": "observation-sidecar.schema.json",
    "rights_manifest": "rights-manifest.schema.json",
    "fixture_manifest": "fixture-manifest.schema.json",
    "adapter_results": "adapter-results.schema.json",
    "subtitle_tracks": "subtitle-tracks.schema.json",
    "subtitle_cue": "subtitle-cue.schema.json",
    "shot": "shot.schema.json",
    "keyframe": "keyframe.schema.json",
    "component_gold": "component-gold.schema.json",
    "component_evaluation": "component-evaluation.schema.json",
    "dependency_bom": "dependency-bom.schema.json",
    "ocr_observation": "ocr-observation.schema.json",
    "ocr_gold": "ocr-gold.schema.json",
    "ocr_dependency": "ocr-dependency.schema.json",
    "ocr_frame_results": "ocr-frame-results.schema.json",
    "ocr_runtime": "ocr-runtime.schema.json",
    "ocr_evaluation": "ocr-evaluation.schema.json",
    "ocr_benchmark": "ocr-benchmark.schema.json",
    "ocr_text_tracks": "ocr-text-tracks.schema.json",
    "ocr_pilot_manifest": "ocr-pilot-manifest.schema.json",
    "ocr_human_annotation": "ocr-human-annotation.schema.json",
}


def schema_root() -> Path:
    return Path(__file__).resolve().parents[2] / "schemas"


def load_schema(name: str) -> dict[str, Any]:
    path = schema_root() / SCHEMA_FILES[name]
    try:
        value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot load schema {path}: {exc}") from exc
    Draft202012Validator.check_schema(value)
    return value


def validate_instance(name: str, value: Any, label: str) -> None:
    errors = sorted(Draft202012Validator(load_schema(name)).iter_errors(value), key=str)
    if errors:
        details = "; ".join(
            f"{'.'.join(str(item) for item in error.absolute_path)}: {error.message}"
            if error.absolute_path
            else error.message
            for error in errors[:3]
        )
        raise AtlasError(f"schema validation failed for {label}: {details}")
