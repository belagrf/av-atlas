"""Fail-closed local preparation for an authorized, human-annotated OCR pilot."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from av_atlas.adapters import AdapterContext
from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError
from av_atlas.io import canonical_json, sha256_file, write_json, write_jsonl
from av_atlas.media import inspect_media
from av_atlas.ocr import TesseractOcrAdapter
from av_atlas.rights import load_rights_manifest, validate_rights
from av_atlas.schemas import validate_instance

REQUIRED_PILOT_OPERATIONS = (
    "analysis",
    "annotation",
    "evaluation",
    "derivative_artifact_retention",
)


def _digest(value: dict[str, Any], field: str = "manifest_hash") -> str:
    payload = {key: item for key, item in value.items() if key != field}
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"invalid JSON file {path.name}: {exc}") from exc


def _empty_output(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise AtlasError(f"pilot output must be a new empty directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _extract_frame(media: Path, timestamp_ms: int, output: Path) -> None:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise AtlasError("ffmpeg is required for pilot frame extraction")
    try:
        subprocess.run(
            [
                executable,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{timestamp_ms / 1000:.3f}",
                "-i",
                str(media),
                "-frames:v",
                "1",
                "-compression_level",
                "9",
                "-y",
                str(output),
            ],
            check=True,
            shell=False,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        output.unlink(missing_ok=True)
        raise AtlasError(f"failed to extract pre-registered frame at {timestamp_ms}ms") from exc
    if not output.is_file() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        raise AtlasError(f"empty extracted frame at {timestamp_ms}ms")


def prepare_pilot(spec_path: Path, output: Path) -> dict[str, Any]:
    """Inventory authorized local sources and extract exactly 20/60 locked frames."""
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
            if set(source) != {"media_path", "rights_manifest_path", "selections"}:
                raise AtlasError(
                    "each source must contain only media_path, rights_manifest_path, selections"
                )
            media = Path(source["media_path"])
            inventory = inspect_media(media)
            if inventory["source_id"] in seen_sources:
                raise AtlasError("pilot sources must be content-distinct")
            seen_sources.add(inventory["source_id"])
            rights = load_rights_manifest(Path(source["rights_manifest_path"]))
            for operation in REQUIRED_PILOT_OPERATIONS:
                validate_rights(rights, inventory["sha256"], inventory["source_id"], operation)
            rights_name = f"{inventory['source_id']}.rights.json"
            shutil.copy2(source["rights_manifest_path"], output / "rights" / rights_name)
            source_records.append(
                {
                    "source_id": inventory["source_id"],
                    "source_sha256": inventory["sha256"],
                    "duration_ms": inventory["duration_ms"],
                    "rights_manifest": f"rights/{rights_name}",
                    "rights_manifest_sha256": sha256_file(output / "rights" / rights_name),
                }
            )
            for selection in source["selections"]:
                required = {"timestamp_ms", "split", "categories", "difficulty"}
                if set(selection) != required:
                    raise AtlasError("each frame selection has unknown or missing fields")
                timestamp_ms = selection["timestamp_ms"]
                if (
                    not isinstance(timestamp_ms, int)
                    or not 0 <= timestamp_ms < inventory["duration_ms"]
                ):
                    raise AtlasError("selected timestamp is outside its source")
                split = selection["split"]
                if split not in {"calibration", "evaluation"}:
                    raise AtlasError("frame split must be calibration or evaluation")
                key = (inventory["source_id"], timestamp_ms)
                if key in seen_frames:
                    raise AtlasError("duplicate source/timestamp selection is not permitted")
                seen_frames.add(key)
                frame_id = f"FRM_{inventory['sha256'][:12].upper()}_{timestamp_ms:010d}"
                relative = f"frames/{frame_id}.png"
                _extract_frame(media, timestamp_ms, output / relative)
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


def make_annotation_packages(pilot_dir: Path) -> None:
    manifest = _load_json(pilot_dir / "pilot_manifest.json")
    validate_instance("ocr_pilot_manifest", manifest, "pilot manifest")
    if manifest["state"] != "prepared_unannotated" or manifest["manifest_hash"] != _digest(
        manifest
    ):
        raise AtlasError("annotation packages require an intact prepared pilot")
    frames = [frame for frame in manifest["frames"] if frame["split"] == "evaluation"]
    for label in ("A", "B"):
        package = pilot_dir / f"annotator_{label}"
        if package.exists():
            raise AtlasError(f"annotation package already exists: annotator_{label}")
        (package / "frames").mkdir(parents=True)
        records = []
        for frame in frames:
            shutil.copy2(pilot_dir / frame["path"], package / "frames" / Path(frame["path"]).name)
            records.append(
                {
                    "frame_id": frame["frame_id"],
                    "source_id": frame["source_id"],
                    "timestamp_ms": frame["timestamp_ms"],
                    "exact_transcription": None,
                    "normalized_transcription": None,
                    "regions": [],
                    "ignore_regions": [],
                    "language": None,
                    "legibility": None,
                    "uncertain": None,
                    "occluded": None,
                    "truncated": None,
                    "notes": None,
                }
            )
        template = {
            "schema_version": "1.0.0",
            "pilot_id": manifest["pilot_id"],
            "annotator_pseudonym": f"ANNOTATOR_{label}",
            "annotation_timestamp": None,
            "independence_attestation": False,
            "frames": records,
        }
        validate_instance("ocr_human_annotation", template, f"annotator {label} template")
        write_json(package / "annotation.json", template)


def compare_annotations(pilot_dir: Path, first: Path, second: Path, output: Path) -> dict[str, Any]:
    manifest = _load_json(pilot_dir / "pilot_manifest.json")
    annotations = [_load_json(first), _load_json(second)]
    for index, value in enumerate(annotations):
        validate_instance("ocr_human_annotation", value, f"annotation {index + 1}")
        if value["pilot_id"] != manifest["pilot_id"] or not value["independence_attestation"]:
            raise AtlasError("annotation is for another pilot or lacks independence attestation")
        if value["annotation_timestamp"] is None or any(
            frame["exact_transcription"] is None or frame["normalized_transcription"] is None
            for frame in value["frames"]
        ):
            raise AtlasError("both human annotation packages must be complete")
    if annotations[0]["annotator_pseudonym"] == annotations[1]["annotator_pseudonym"]:
        raise AtlasError("two distinct annotator pseudonyms are required")
    by_second = {frame["frame_id"]: frame for frame in annotations[1]["frames"]}
    disagreements = []
    char_edits = 0
    char_total = 0
    region_matches = 0
    region_first = 0
    region_second = 0
    for frame in annotations[0]["frames"]:
        other = by_second.get(frame["frame_id"])
        if other is None:
            raise AtlasError("annotation frame sets differ")
        differing = [
            field for field in frame if field != "frame_id" and frame[field] != other[field]
        ]
        if differing:
            disagreements.append({"frame_id": frame["frame_id"], "differing_fields": differing})
        first_text = str(frame["normalized_transcription"])
        second_text = str(other["normalized_transcription"])
        char_edits += _distance(list(first_text), list(second_text))
        char_total += len(first_text)
        first_regions = [_box(region) for region in frame["regions"]]
        second_regions = [_box(region) for region in other["regions"]]
        region_first += len(first_regions)
        region_second += len(second_regions)
        candidates = sorted(
            (
                _iou(left, right),
                left_index,
                right_index,
            )
            for left_index, left in enumerate(first_regions)
            if left is not None
            for right_index, right in enumerate(second_regions)
            if right is not None
        )
        used_left: set[int] = set()
        used_right: set[int] = set()
        for overlap, left_index, right_index in reversed(candidates):
            if overlap < 0.5 or left_index in used_left or right_index in used_right:
                continue
            used_left.add(left_index)
            used_right.add(right_index)
            region_matches += 1
    report = {
        "schema_version": "1.0.0",
        "pilot_id": manifest["pilot_id"],
        "annotation_sha256": [sha256_file(first), sha256_file(second)],
        "annotators": [item["annotator_pseudonym"] for item in annotations],
        "agreement_frames": 60 - len(disagreements),
        "disagreement_frames": len(disagreements),
        "disagreements": disagreements,
        "adjudication_required": bool(disagreements),
        "inter_annotator": {
            "exact_frame_agreement": _ratio(60 - len(disagreements), 60),
            "normalized_character_disagreement_rate": _ratio(char_edits, char_total),
            "region_precision_a_to_b": _ratio(region_matches, region_first),
            "region_recall_a_to_b": _ratio(region_matches, region_second),
            "region_matching_threshold_iou": 0.5,
        },
    }
    write_json(output, report)
    return report


def freeze_pilot(
    pilot_dir: Path, first: Path, second: Path, adjudicated: Path, output: Path
) -> dict[str, Any]:
    report = compare_annotations(
        pilot_dir, first, second, output.with_suffix(".disagreements.json")
    )
    manifest = _load_json(pilot_dir / "pilot_manifest.json")
    gold = _load_json(adjudicated)
    validate_instance("ocr_human_annotation", gold, "adjudicated gold")
    if gold["pilot_id"] != manifest["pilot_id"] or gold["annotation_timestamp"] is None:
        raise AtlasError("adjudicated gold is incomplete or belongs to another pilot")
    if any(frame["exact_transcription"] is None for frame in gold["frames"]):
        raise AtlasError("adjudicated gold contains incomplete frames")
    frozen = {
        **manifest,
        "state": "adjudicated_frozen",
        "human_annotation_sha256": [sha256_file(first), sha256_file(second)],
        "adjudicated_gold_sha256": sha256_file(adjudicated),
        "disagreement_report_sha256": sha256_file(output.with_suffix(".disagreements.json")),
        "normalization_rules_sha256": sha256_file(Path(__file__).with_name("ocr_evaluation.py")),
        "ocr_configuration_sha256": sha256_file(Path(__file__).parents[2] / "configs/m2b.yaml"),
        "region_matching_rule": "IoU >= 0.5; one-to-one maximum-IoU matching",
        "metric_definition": "AV-Atlas OCR evaluation schema 1.0.0",
        "manifest_hash": "",
        "disagreement_count": report["disagreement_frames"],
    }
    # The frozen manifest intentionally has a richer shape and is hash-protected rather than
    # validated as the pre-freeze intake manifest.
    frozen["manifest_hash"] = _digest(frozen)
    write_json(output, frozen)
    return frozen


def _distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for index, item in enumerate(left, 1):
        current = [index]
        for other_index, other in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[other_index] + 1,
                    previous[other_index - 1] + (item != other),
                )
            )
        previous = current
    return previous[-1]


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def _box(region: dict[str, Any]) -> list[float] | None:
    if isinstance(region.get("geometry"), dict):
        region = region["geometry"]
    value = region.get("bounding_box")
    if (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
    ):
        return [float(item) for item in value]
    polygon = region.get("polygon")
    if (
        isinstance(polygon, list)
        and polygon
        and all(isinstance(point, list) and len(point) == 2 for point in polygon)
    ):
        xs = [float(point[0]) for point in polygon]
        ys = [float(point[1]) for point in polygon]
        return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    return None


def _iou(left: list[float], right: list[float]) -> float:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    intersection = max(0.0, min(lx + lw, rx + rw) - max(lx, rx)) * max(
        0.0, min(ly + lh, ry + rh) - max(ly, ry)
    )
    union = lw * lh + rw * rh - intersection
    return intersection / union if union else 0.0


def evaluate_pilot(
    pilot_dir: Path,
    frozen_path: Path,
    adjudicated_path: Path,
    observations_path: Path,
    runtime_path: Path,
    output: Path,
) -> dict[str, Any]:
    """Evaluate unchanged-adapter JSONL only after a hash-locked human adjudication."""
    frozen = _load_json(frozen_path)
    if frozen.get("state") != "adjudicated_frozen" or frozen.get("manifest_hash") != _digest(
        frozen
    ):
        raise AtlasError("pilot evaluation requires an intact adjudicated frozen manifest")
    if sha256_file(adjudicated_path) != frozen.get("adjudicated_gold_sha256"):
        raise AtlasError("adjudicated gold differs from the frozen pilot")
    if sha256_file(Path(__file__).parents[2] / "configs/m2b.yaml") != frozen.get(
        "ocr_configuration_sha256"
    ):
        raise AtlasError("OCR configuration differs from the frozen pilot")
    for source in frozen["sources"]:
        rights = load_rights_manifest(pilot_dir / source["rights_manifest"])
        validate_rights(rights, source["source_sha256"], source["source_id"], "evaluation")
        validate_rights(
            rights, source["source_sha256"], source["source_id"], "derivative_artifact_retention"
        )
    gold = _load_json(adjudicated_path)
    validate_instance("ocr_human_annotation", gold, "adjudicated gold")
    try:
        observations = [
            json.loads(line)
            for line in observations_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"invalid pilot OCR observations: {exc}") from exc
    runtime = _load_json(runtime_path)
    by_frame: dict[str, list[dict[str, Any]]] = {}
    for item in observations:
        frame_id = str(item.get("keyframe_id", item.get("frame_id", "")))
        by_frame.setdefault(frame_id, []).append(item)
    expected = {frame["frame_id"]: frame for frame in gold["frames"]}
    predicted_text = {
        frame_id: " ".join(
            str(item.get("normalized_text", "")) for item in by_frame.get(frame_id, [])
        )
        for frame_id in expected
    }
    exact = sum(
        predicted_text[key] == frame["normalized_transcription"] for key, frame in expected.items()
    )
    char_edits = sum(
        _distance(list(predicted_text[key]), list(frame["normalized_transcription"]))
        for key, frame in expected.items()
    )
    characters = sum(len(frame["normalized_transcription"]) for frame in expected.values())
    word_edits = sum(
        _distance(predicted_text[key].split(), frame["normalized_transcription"].split())
        for key, frame in expected.items()
    )
    words = sum(len(frame["normalized_transcription"].split()) for frame in expected.values())
    positive_gold = {key for key, frame in expected.items() if frame["normalized_transcription"]}
    positive_pred = {key for key, text in predicted_text.items() if text}

    def aggregate(frame_ids: list[str]) -> dict[str, Any]:
        subset = [key for key in frame_ids if key in expected]
        subset_exact = sum(
            predicted_text[key] == expected[key]["normalized_transcription"] for key in subset
        )
        subset_char_edits = sum(
            _distance(list(predicted_text[key]), list(expected[key]["normalized_transcription"]))
            for key in subset
        )
        subset_chars = sum(len(expected[key]["normalized_transcription"]) for key in subset)
        subset_word_edits = sum(
            _distance(
                predicted_text[key].split(), expected[key]["normalized_transcription"].split()
            )
            for key in subset
        )
        subset_words = sum(len(expected[key]["normalized_transcription"].split()) for key in subset)
        return {
            "frames": len(subset),
            "exact_match": _ratio(subset_exact, len(subset)),
            "normalized_cer": _ratio(subset_char_edits, subset_chars),
            "normalized_wer": _ratio(subset_word_edits, subset_words),
        }

    metadata = {
        frame["frame_id"]: frame for frame in frozen["frames"] if frame["split"] == "evaluation"
    }
    by_source = {
        source["source_id"]: aggregate(
            [key for key, frame in metadata.items() if frame["source_id"] == source["source_id"]]
        )
        for source in frozen["sources"]
    }
    categories = sorted({item for frame in metadata.values() for item in frame["categories"]})
    difficulties = sorted({item for frame in metadata.values() for item in frame["difficulty"]})
    by_category = {
        category: aggregate(
            [key for key, frame in metadata.items() if category in frame["categories"]]
        )
        for category in categories
    }
    by_difficulty = {
        difficulty: aggregate(
            [key for key, frame in metadata.items() if difficulty in frame["difficulty"]]
        )
        for difficulty in difficulties
    }

    def size_bucket(frame: dict[str, Any]) -> str:
        heights = [box[3] for region in frame["regions"] if (box := _box(region)) is not None]
        if not heights:
            return "no_text_or_unboxed"
        height = max(heights)
        return "small" if height < 24 else "medium" if height < 64 else "large"

    by_text_size = {
        bucket: aggregate([key for key, frame in expected.items() if size_bucket(frame) == bucket])
        for bucket in ("small", "medium", "large", "no_text_or_unboxed")
    }

    def confidence_bucket(frame_id: str) -> str:
        values = [float(item["confidence"]) for item in by_frame.get(frame_id, [])]
        if not values:
            return "no_observation"
        confidence = sum(values) / len(values)
        return (
            "low_0_49" if confidence < 50 else "medium_50_79" if confidence < 80 else "high_80_100"
        )

    by_confidence = {
        bucket: aggregate([key for key in expected if confidence_bucket(key) == bucket])
        for bucket in ("no_observation", "low_0_49", "medium_50_79", "high_80_100")
    }
    tp = len(positive_gold & positive_pred)
    fp = len(positive_pred - positive_gold)
    fn = len(positive_gold - positive_pred)
    presence_precision = _ratio(tp, tp + fp)
    presence_recall = _ratio(tp, tp + fn)
    presence_f1 = (
        2 * presence_precision * presence_recall / (presence_precision + presence_recall)
        if presence_precision is not None
        and presence_recall is not None
        and presence_precision + presence_recall
        else None
    )
    region_tp = 0
    region_fp = 0
    region_fn = 0
    ious: list[float] = []
    exact_region = 0
    reading_correct = 0
    reading_total = 0
    for frame_id, frame in expected.items():
        gold_regions = [(region, _box(region)) for region in frame["regions"]]
        predicted_regions = [(region, _box(region)) for region in by_frame.get(frame_id, [])]
        candidates = sorted(
            (
                (_iou(gbox, pbox), gi, pi)
                for gi, (_, gbox) in enumerate(gold_regions)
                if gbox
                for pi, (_, pbox) in enumerate(predicted_regions)
                if pbox
            ),
            reverse=True,
        )
        used_g: set[int] = set()
        used_p: set[int] = set()
        matched_order: list[tuple[int, int]] = []
        for overlap, gi, pi in candidates:
            if overlap < 0.5 or gi in used_g or pi in used_p:
                continue
            used_g.add(gi)
            used_p.add(pi)
            ious.append(overlap)
            matched_order.append((gi, pi))
            gold_text = str(gold_regions[gi][0].get("normalized_transcription", ""))
            if gold_text == str(predicted_regions[pi][0].get("normalized_text", "")):
                exact_region += 1
        region_tp += len(used_g)
        region_fn += len(gold_regions) - len(used_g)
        region_fp += len(predicted_regions) - len(used_p)
        if len(matched_order) > 1:
            reading_total += 1
            reading_correct += [gi for gi, _ in matched_order] == sorted(
                gi for gi, _ in matched_order
            )
    region_precision = _ratio(region_tp, region_tp + region_fp)
    region_recall = _ratio(region_tp, region_tp + region_fn)
    region_f1 = (
        2 * region_precision * region_recall / (region_precision + region_recall)
        if region_precision is not None
        and region_recall is not None
        and region_precision + region_recall
        else None
    )
    unique = {
        (
            item.get("source_id"),
            item.get("keyframe_id", item.get("frame_id")),
            item.get("normalized_text"),
            tuple(item.get("bounding_box", [])),
        )
        for item in observations
    }
    evidence_path = observations_path.parent / "evidence_index.json"
    evidence = _load_json(evidence_path).get("evidence", {}) if evidence_path.is_file() else {}
    report = {
        "schema_version": "1.0.0",
        "category": "authorized_real_media_pilot",
        "pilot_id": frozen["pilot_id"],
        "frozen_manifest_sha256": sha256_file(frozen_path),
        "source_count": len(frozen["sources"]),
        "frame_count": len(expected),
        "text_region_count": sum(len(frame["regions"]) for frame in expected.values()),
        "no_text_frame_count": len(expected) - len(positive_gold),
        "ocr_observation_count": len(observations),
        "exact_frame_level_match": _ratio(exact, len(expected)),
        "exact_region_level_match": _ratio(
            exact_region, sum(len(frame["regions"]) for frame in expected.values())
        ),
        "normalized_cer": _ratio(char_edits, characters),
        "normalized_wer": _ratio(word_edits, words),
        "text_presence": {
            "precision": presence_precision,
            "recall": presence_recall,
            "f1": presence_f1,
        },
        "region_detection": {
            "precision": region_precision,
            "recall": region_recall,
            "f1": region_f1,
        },
        "mean_region_iou": _ratio(sum(ious), len(ious)),
        "reading_order_accuracy": _ratio(reading_correct, reading_total),
        "duplicate_observation_rate": _ratio(len(observations) - len(unique), len(observations))
        or 0.0,
        "evidence_resolution_failures": sum(
            item.get("evidence_ref") not in evidence
            or item.get("source_frame_evidence_ref") not in evidence
            for item in observations
        ),
        "invalid_timestamps": sum(
            not isinstance(item.get("timestamp_ms"), int) for item in observations
        ),
        "retries": runtime.get("retries"),
        "timeouts": runtime.get("timeouts"),
        "wall_seconds": runtime.get("wall_seconds"),
        "cpu_seconds": runtime.get("cpu_seconds"),
        "peak_rss_kb": runtime.get("peak_rss_kb"),
        "frames_per_second": runtime.get("frames_per_second"),
        "stratified_results": {
            "by_source": by_source,
            "by_text_category": by_category,
            "by_difficulty": by_difficulty,
            "by_text_size": by_text_size,
            "by_confidence": by_confidence,
        },
        "limitations": [
            "Small authorized pilot only; do not generalize to all films, episodes, or livestreams."
        ],
    }
    write_json(output, report)
    return report


def run_pilot_ocr(pilot_dir: Path, frozen_path: Path, output: Path) -> dict[str, Any]:
    """Run the unchanged frozen M2B adapter over the locked evaluation frames."""
    frozen = _load_json(frozen_path)
    if frozen.get("state") != "adjudicated_frozen" or frozen.get("manifest_hash") != _digest(
        frozen
    ):
        raise AtlasError("pilot OCR requires an intact adjudicated frozen manifest")
    config_path = Path(__file__).parents[2] / "configs/m2b.yaml"
    if sha256_file(config_path) != frozen.get("ocr_configuration_sha256"):
        raise AtlasError("OCR configuration differs from the frozen pilot")
    config = BaselineConfig.load(config_path)
    _empty_output(output)
    all_records: list[dict[str, Any]] = []
    evidence: dict[str, dict[str, Any]] = {}
    totals: dict[str, Any] = {
        "wall_seconds": 0.0,
        "cpu_seconds": 0.0,
        "peak_rss_kb": 0,
        "retries": 0,
        "timeouts": 0,
        "frames_processed": 0,
    }
    try:
        for source in frozen["sources"]:
            rights = load_rights_manifest(pilot_dir / source["rights_manifest"])
            for operation in ("analysis", "evaluation", "derivative_artifact_retention"):
                validate_rights(rights, source["source_sha256"], source["source_id"], operation)
            frames = [
                frame
                for frame in frozen["frames"]
                if frame["source_id"] == source["source_id"] and frame["split"] == "evaluation"
            ]
            workspace = output / source["source_id"]
            (workspace / "keyframes").mkdir(parents=True)
            keyframes = []
            frame_map: dict[str, str] = {}
            for index, frame in enumerate(frames, 1):
                keyframe_id = f"KEY_{index:04d}"
                shot_id = f"SHOT_{index:04d}"
                destination = workspace / "keyframes" / f"{keyframe_id}.png"
                shutil.copy2(pilot_dir / frame["path"], destination)
                if sha256_file(destination) != frame["sha256"]:
                    raise AtlasError("selected frame differs from frozen pilot hash")
                evidence_ref = f"VID:{source['source_id']}:frame:{frame['timestamp_ms']}"
                keyframes.append(
                    {
                        "schema_version": "1.0.0",
                        "keyframe_id": keyframe_id,
                        "shot_id": shot_id,
                        "source_id": source["source_id"],
                        "timestamp_ms": frame["timestamp_ms"],
                        "frame_index": index,
                        "path": f"keyframes/{keyframe_id}.png",
                        "sha256": frame["sha256"],
                        "size_bytes": destination.stat().st_size,
                        "evidence_ref": evidence_ref,
                    }
                )
                frame_map[keyframe_id] = frame["frame_id"]
                evidence[evidence_ref] = {
                    "evidence_ref": evidence_ref,
                    "source_id": source["source_id"],
                    "observation_id": frame["frame_id"],
                    "modality": "VID",
                    "start_ms": frame["timestamp_ms"],
                    "end_ms": min(frame["timestamp_ms"] + 1, source["duration_ms"]),
                }
            write_jsonl(workspace / "keyframes.jsonl", keyframes)
            inventory = {
                "schema_version": "1.0.0",
                "source_id": source["source_id"],
                "sha256": source["source_sha256"],
                "duration_ms": source["duration_ms"],
            }
            execution = TesseractOcrAdapter().run(
                AdapterContext(Path("authorized-local-source"), inventory, workspace, config)
            )
            if execution.result.status not in {"success", "success_zero"}:
                raise AtlasError(
                    f"pilot OCR failed for {source['source_id']}: {execution.result.status}"
                )
            source_records = [
                json.loads(line)
                for line in (workspace / "ocr_observations.jsonl").read_text().splitlines()
                if line
            ]
            prefix = source["source_id"].removeprefix("SRC_")
            for record in source_records:
                original = record["observation_id"]
                record["observation_id"] = f"OCR_{prefix}_{original.removeprefix('OCR_')}"
                record["keyframe_id"] = frame_map[record["keyframe_id"]]
                record["evidence_ref"] = f"OCR:{record['observation_id']}"
                all_records.append(record)
                evidence[record["evidence_ref"]] = {
                    "evidence_ref": record["evidence_ref"],
                    "source_id": record["source_id"],
                    "observation_id": record["observation_id"],
                    "modality": "OCR",
                    "start_ms": record["timestamp_ms"],
                    "end_ms": min(record["timestamp_ms"] + 1, source["duration_ms"]),
                }
            runtime = _load_json(workspace / "ocr_runtime.json")
            for field in ("wall_seconds", "cpu_seconds", "retries", "timeouts", "frames_processed"):
                totals[field] = float(totals[field]) + float(runtime[field])
            totals["peak_rss_kb"] = max(int(totals["peak_rss_kb"]), int(runtime["peak_rss_kb"]))
        all_records.sort(
            key=lambda item: (
                item["source_id"],
                item["timestamp_ms"],
                item["bounding_box"],
                item["observation_id"],
            )
        )
        write_jsonl(output / "ocr_observations.jsonl", all_records)
        write_json(
            output / "evidence_index.json", {"schema_version": "1.0.0", "evidence": evidence}
        )
        wall = float(totals["wall_seconds"])
        totals["frames_per_second"] = int(totals["frames_processed"]) / wall if wall else None
        totals["observation_count"] = len(all_records)
        totals["configuration_sha256"] = sha256_file(config_path)
        totals["output_semantic_sha256"] = sha256_file(output / "ocr_observations.jsonl")
        write_json(output / "ocr_runtime.json", totals)
        return {"observations": len(all_records), **totals}
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise
