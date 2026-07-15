"""Stable-input preparation for the authorized human-annotated OCR pilot."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from av_atlas.errors import AtlasError
from av_atlas.io import sha256_file, write_json
from av_atlas.media import inspect_media
from av_atlas.ocr_pilot import _digest, _empty_output, _extract_frame, _load_json
from av_atlas.rights import validate_rights
from av_atlas.schemas import validate_instance
from av_atlas.stable_input import authorized_stable_input


def prepare_pilot(spec_path: Path, output: Path) -> dict[str, Any]:
    """Authorize stable source copies and extract exactly 20/60 locked frames."""

    spec = _load_json(spec_path)
    expected = {
        "schema_version",
        "pilot_id",
        "selection_method",
        "random_seed",
        "inclusion_criteria",
        "exclusion_criteria",
        "duplicate_frame_policy",
        "sources",
    }
    if set(spec) != expected or spec.get("schema_version") != "1.0.0":
        raise AtlasError("pilot specification has unknown, missing, or unsupported fields")
    sources = spec.get("sources")
    if not isinstance(sources, list) or len(sources) < 3:
        raise AtlasError("pilot requires at least three distinct authorized sources")

    _empty_output(output)
    (output / "frames").mkdir()
    (output / "rights").mkdir()
    source_records: list[dict[str, Any]] = []
    frame_records: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    seen_frames: set[tuple[str, int]] = set()
    try:
        for source in sources:
            if not isinstance(source, dict) or set(source) != {
                "media_path",
                "rights_manifest_path",
                "selections",
            }:
                raise AtlasError(
                    "each source must contain only media_path, rights_manifest_path, selections"
                )
            media = Path(source["media_path"])
            rights_path = Path(source["rights_manifest_path"])
            with authorized_stable_input(media, rights_path, "evaluation") as access:
                authorization = access.authorization
                rights = authorization.rights_declaration
                validate_rights(
                    rights,
                    authorization.source_sha256,
                    authorization.source_id,
                    "annotation",
                )
                inventory = inspect_media(access.stable.path)
                if (
                    inventory["sha256"] != authorization.source_sha256
                    or inventory["source_id"] != authorization.source_id
                ):
                    raise AtlasError(
                        "stable pilot inventory does not match authorized source identity"
                    )
                if inventory["source_id"] in seen_sources:
                    raise AtlasError("pilot sources must be content-distinct")
                seen_sources.add(inventory["source_id"])
                rights_name = f"{inventory['source_id']}.rights.json"
                shutil.copy2(rights_path, output / "rights" / rights_name)
                source_records.append(
                    {
                        "source_id": inventory["source_id"],
                        "source_sha256": inventory["sha256"],
                        "duration_ms": inventory["duration_ms"],
                        "rights_manifest": f"rights/{rights_name}",
                        "rights_manifest_sha256": sha256_file(output / "rights" / rights_name),
                    }
                )
                selections = source["selections"]
                if not isinstance(selections, list):
                    raise AtlasError("source selections must be an array")
                for selection in selections:
                    required = {"timestamp_ms", "split", "categories", "difficulty"}
                    if not isinstance(selection, dict) or set(selection) != required:
                        raise AtlasError("each frame selection has unknown or missing fields")
                    timestamp_ms = selection["timestamp_ms"]
                    if (
                        not isinstance(timestamp_ms, int)
                        or isinstance(timestamp_ms, bool)
                        or not 0 <= timestamp_ms < inventory["duration_ms"]
                    ):
                        raise AtlasError("selected timestamp is outside its source")
                    split = selection["split"]
                    if split not in {"calibration", "evaluation"}:
                        raise AtlasError("frame split must be calibration or evaluation")
                    if not isinstance(selection["categories"], list) or not isinstance(
                        selection["difficulty"], list
                    ):
                        raise AtlasError("frame categories and difficulty must be arrays")
                    key = (inventory["source_id"], timestamp_ms)
                    if key in seen_frames:
                        raise AtlasError("duplicate source/timestamp selection is not permitted")
                    seen_frames.add(key)
                    frame_id = f"FRM_{inventory['sha256'][:12].upper()}_{timestamp_ms:010d}"
                    relative = f"frames/{frame_id}.png"
                    _extract_frame(access.stable.path, timestamp_ms, output / relative)
                    frame_records.append(
                        {
                            "frame_id": frame_id,
                            "source_id": inventory["source_id"],
                            "timestamp_ms": timestamp_ms,
                            "split": split,
                            "categories": selection["categories"],
                            "difficulty": selection["difficulty"],
                            "path": relative,
                            "sha256": sha256_file(output / relative),
                        }
                    )
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise

    calibration = sum(frame["split"] == "calibration" for frame in frame_records)
    evaluation = sum(frame["split"] == "evaluation" for frame in frame_records)
    if (calibration, evaluation) != (20, 60):
        shutil.rmtree(output, ignore_errors=True)
        raise AtlasError(
            "pilot requires exactly 20 calibration and 60 evaluation frames; "
            f"got {calibration}/{evaluation}"
        )
    value: dict[str, Any] = {
        "schema_version": "1.0.0",
        "pilot_id": spec["pilot_id"],
        "state": "prepared_unannotated",
        "selection_protocol": {
            "method": spec["selection_method"],
            "random_seed": spec["random_seed"],
            "inclusion_criteria": spec["inclusion_criteria"],
            "exclusion_criteria": spec["exclusion_criteria"],
            "duplicate_frame_policy": spec["duplicate_frame_policy"],
        },
        "sources": sorted(source_records, key=lambda item: item["source_id"]),
        "frames": sorted(frame_records, key=lambda item: (item["source_id"], item["timestamp_ms"])),
        "counts": {
            "sources": len(source_records),
            "calibration_frames": 20,
            "evaluation_frames": 60,
        },
        "privacy": {
            "source_media_copied": False,
            "source_ids_hash_derived": True,
            "absolute_paths_exported": False,
            "legal_determination": False,
        },
        "manifest_hash": "",
    }
    value["manifest_hash"] = _digest(value)
    validate_instance("ocr_pilot_manifest", value, "pilot manifest")
    write_json(output / "pilot_manifest.json", value)
    return value
