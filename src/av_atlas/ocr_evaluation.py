"""Reproducible controlled-fixture OCR evaluation and worker benchmarks."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from av_atlas.adapters import AdapterContext
from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError
from av_atlas.io import sha256_file, write_json
from av_atlas.ocr import TesseractOcrAdapter
from av_atlas.rights import load_and_validate_rights
from av_atlas.schemas import validate_instance


def _read(path: Path) -> dict[str, Any]:
    try:
        value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"invalid OCR evaluation input {path.name}: {exc}") from exc


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"invalid OCR evaluation input {path.name}: {exc}") from exc


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


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _quality_metrics(run_dir: Path, gold: dict[str, Any]) -> dict[str, Any]:
    records = _jsonl(run_dir / "ocr_observations.jsonl")
    evidence = _read(run_dir / "evidence_index.json").get("evidence", {})
    runtime = _read(run_dir / "ocr_runtime.json")
    frame_results = _read(run_dir / "ocr_frame_results.json")
    if (run_dir / "adapter_results.json").is_file():
        adapter_results = _read(run_dir / "adapter_results.json")
        adapter_status = next(
            (
                item["status"]
                for item in adapter_results["results"]
                if item["adapter"] == "ocr_frame"
            ),
            "missing",
        )
    else:
        adapter_status = {
            "succeeded": "success" if records else "success_zero",
            "partial_success": "partial_success",
            "partial": "partial_success",
            "failed": "decode_failure",
        }.get(str(frame_results.get("adapter_state")), "missing")
    tracks = (
        _read(run_dir / "ocr_text_tracks.json")
        if (run_dir / "ocr_text_tracks.json").is_file()
        else {"tracks": []}
    )
    gold_by_frame = {item["keyframe_id"]: item for item in gold["frames"]}
    records_by_frame: dict[str, list[dict[str, Any]]] = {key: [] for key in gold_by_frame}
    for record in records:
        records_by_frame.setdefault(str(record["keyframe_id"]), []).append(record)
    predicted = {
        key: " ".join(str(item["normalized_text"]) for item in values)
        for key, values in records_by_frame.items()
    }

    def aggregate(frame_ids: list[str]) -> dict[str, Any]:
        exact = sum(
            predicted[key] == str(gold_by_frame[key]["normalized_transcription"])
            for key in frame_ids
        )
        char_edits = sum(
            _distance(
                list(predicted[key]), list(str(gold_by_frame[key]["normalized_transcription"]))
            )
            for key in frame_ids
        )
        chars = sum(len(str(gold_by_frame[key]["normalized_transcription"])) for key in frame_ids)
        word_edits = sum(
            _distance(
                predicted[key].split(),
                str(gold_by_frame[key]["normalized_transcription"]).split(),
            )
            for key in frame_ids
        )
        words = sum(
            len(str(gold_by_frame[key]["normalized_transcription"]).split()) for key in frame_ids
        )
        return {
            "evaluated_frames": len(frame_ids),
            "exact_text_match_rate": _ratio(exact, len(frame_ids)),
            "normalized_character_error_rate": _ratio(char_edits, chars),
            "normalized_word_error_rate": _ratio(word_edits, words),
        }

    frame_ids = list(gold_by_frame)
    expected_positive = {
        key for key, item in gold_by_frame.items() if item["normalized_transcription"]
    }
    predicted_positive = {key for key, value in predicted.items() if value}
    true_positive = len(expected_positive & predicted_positive)
    false_positive = len(predicted_positive - expected_positive)
    false_negative = len(expected_positive - predicted_positive)
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    presence_f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    exact_unique = {
        (
            item["observation_id"],
            item["source_id"],
            item["keyframe_id"],
            item["timestamp_ms"],
            item["text"],
            item["normalized_text"],
            tuple(item["bounding_box"]),
            item["evidence_ref"],
        )
        for item in records
    }
    exact_duplicate_count = len(records) - len(exact_unique)
    gold_timestamps = {key: int(item["timestamp_ms"]) for key, item in gold_by_frame.items()}
    invalid_timestamps = sum(
        not isinstance(item.get("timestamp_ms"), int)
        or int(item["timestamp_ms"]) < 0
        or (
            item["keyframe_id"] in gold_timestamps
            and int(item["timestamp_ms"]) != gold_timestamps[item["keyframe_id"]]
        )
        for item in records
    )
    missing_evidence = sum(
        item["evidence_ref"] not in evidence or item["source_frame_evidence_ref"] not in evidence
        for item in records
    )
    categories = sorted({category for frame in gold["frames"] for category in frame["difficulty"]})
    by_category = {
        category: aggregate(
            [key for key, frame in gold_by_frame.items() if category in frame["difficulty"]]
        )
        for category in categories
    }
    overall = aggregate(frame_ids)
    frame_state = frame_results.get("adapter_state")
    expected_statuses = {
        "succeeded": {"success", "success_zero"},
        "partial": {"partial_success"},
        "partial_success": {"partial_success"},
        "failed": {"decode_failure", "resource_limit_failure", "permanent_failure"},
        "unavailable": {"unavailable_dependency"},
        "disabled": {"success_zero"},
        "skipped": {"unsupported_input"},
    }
    records_state_correct = (
        all(item.get("adapter_state") == "succeeded" for item in records) if records else True
    )
    adapter_state_correct = (
        frame_state in expected_statuses
        and adapter_status in expected_statuses[frame_state]
        and records_state_correct
        and not (adapter_status == "success" and not records)
        and not (adapter_status == "success_zero" and records)
    )
    track_members = sum(len(track["member_observation_ids"]) for track in tracks["tracks"])
    repeated_members = sum(
        max(0, len(track["member_observation_ids"]) - 1) for track in tracks["tracks"]
    )
    unresolved_track_evidence = sum(
        ref not in evidence
        for track in tracks["tracks"]
        for ref in track["source_frame_evidence_refs"]
    )
    return {
        **overall,
        "frames_containing_expected_text": len(expected_positive),
        "ocr_observations": len(records),
        "frame_text_presence_precision": precision,
        "frame_text_presence_recall": recall,
        "frame_text_presence_f1": presence_f1,
        "region_detection_precision": None,
        "region_detection_recall": None,
        "bounding_box_iou": None,
        "region_metric_limitation": (
            "Unsupported for this frozen set because its gold regions arrays are empty; "
            "predicted boxes are retained but cannot be matched to gold boxes."
        ),
        "exact_record_duplicate_rate": _ratio(exact_duplicate_count, len(records)) or 0.0,
        "duplicate_observation_rate": _ratio(exact_duplicate_count, len(records)) or 0.0,
        "temporal_repeated_observation_rate": _ratio(repeated_members, track_members) or 0.0,
        "derived_track_compression_ratio": (
            _ratio(len(records) - len(tracks["tracks"]), len(records)) or 0.0
        ),
        "derived_text_track_count": len(tracks["tracks"]),
        "unresolved_track_evidence_count": unresolved_track_evidence,
        "prediction_only_keyframe_count": len(set(records_by_frame) - set(gold_by_frame)),
        "gold_only_keyframe_count": len(expected_positive - predicted_positive),
        "missing_evidence_reference_count": missing_evidence,
        "invalid_timestamp_count": invalid_timestamps,
        "adapter_state_correctness": adapter_state_correct,
        "timeout_count": int(runtime["timeouts"]),
        "retry_count": int(runtime["retries"]),
        "wall_seconds": runtime["wall_seconds"],
        "cpu_seconds": runtime["cpu_seconds"],
        "peak_rss_kb": runtime["peak_rss_kb"],
        "frames_per_second": runtime["frames_per_second"],
        "media_minutes_per_compute_minute": None,
        "counts_and_metrics_by_difficulty": by_category,
    }


def _media_efficiency(metrics: dict[str, Any], duration_ms: int) -> None:
    wall = float(metrics["wall_seconds"])
    metrics["media_minutes_per_compute_minute"] = duration_ms / 1000 / wall if wall else None


def evaluate_ocr(run_dir: Path, gold_path: Path) -> dict[str, Any]:
    gold = _read(gold_path)
    validate_instance("ocr_gold", gold, gold_path.name)
    dependency = _read(run_dir / "ocr_dependency.json")
    inventory = _read(run_dir / "inventory.json")
    manifest = _read(run_dir / "run_manifest.json")
    load_and_validate_rights(
        run_dir / "rights_manifest.json",
        inventory["sha256"],
        inventory["source_id"],
        "evaluation",
        expected_manifest_hash=manifest["rights"]["manifest_hash"],
    )
    adapter = _read(run_dir / "adapter_results.json")
    state = next(
        (item["status"] for item in adapter["results"] if item["adapter"] == "ocr_frame"),
        "missing",
    )
    measured: dict[str, Any] | None = None
    if state in {"success", "success_zero", "partial_success"}:
        measured = _quality_metrics(run_dir, gold)
        _media_efficiency(measured, int(inventory["duration_ms"]))
    report = {
        "schema_version": "1.0.0",
        "evaluation_id": "OCR_" + gold["gold_id"],
        "category": "deterministic_synthetic_fixture",
        "adapter_state": state,
        "dependency": dependency,
        "measured_results": measured,
        "engineering_validation": {
            "records": len(_jsonl(run_dir / "ocr_observations.jsonl")),
            "gold_frames": len(gold["frames"]),
            "gold_sha256": sha256_file(gold_path),
            "source_sha256_matches_gold": (
                inventory["sha256"] == gold["source_sha256"]
                if gold["source_sha256"] is not None
                else None
            ),
            "source_hash_limitation": (
                None
                if gold["source_sha256"] is not None
                else "The frozen gold intentionally omits source_sha256; the fixture hash is "
                "verified separately before evaluation."
            ),
        },
        "pilot_results": None,
        "limitations": [
            *gold["limitations"],
            "Synthetic controlled-fixture results do not establish real-media accuracy.",
            "Authorized double-annotated real-media pilot pending.",
        ],
    }
    write_json(run_dir / "ocr_evaluation.json", report)
    (run_dir / "ocr_evaluation.md").write_text(
        "# OCR component evaluation\n\n"
        + (
            "OCR did not execute successfully; no OCR quality metrics were measured.\n"
            if measured is None
            else (
                f"Frozen synthetic exact match: {measured['exact_text_match_rate']:.6f}\n\n"
                f"Normalized CER: {measured['normalized_character_error_rate']:.6f}\n\n"
                f"Normalized WER: {measured['normalized_word_error_rate']:.6f}\n"
            )
        )
        + "\nNo semantic-vision, real-media, or generalized performance claim is made.\n",
        encoding="utf-8",
    )
    validate_instance("ocr_evaluation", report, "ocr_evaluation.json")
    _add_artifacts(run_dir, ["ocr_evaluation.json", "ocr_evaluation.md"])
    return report


def _benchmark_workspace(run_dir: Path, workers: int) -> Path:
    target = run_dir / "ocr_benchmark_runs" / f"workers-{workers}"
    if target.exists():
        raise AtlasError(f"benchmark workspace must be new and empty: {target}")
    (target / "keyframes").mkdir(parents=True)
    shutil.copy2(run_dir / "keyframes.jsonl", target / "keyframes.jsonl")
    shutil.copy2(run_dir / "evidence_index.json", target / "evidence_index.json")
    for record in _jsonl(run_dir / "keyframes.jsonl"):
        source = run_dir / str(record["path"])
        destination = target / str(record["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return target


def benchmark_ocr(run_dir: Path, gold_path: Path) -> dict[str, Any]:
    dependency = _read(run_dir / "ocr_dependency.json")
    inventory = _read(run_dir / "inventory.json")
    manifest = _read(run_dir / "run_manifest.json")
    load_and_validate_rights(
        run_dir / "rights_manifest.json",
        inventory["sha256"],
        inventory["source_id"],
        "evaluation",
        expected_manifest_hash=manifest["rights"]["manifest_hash"],
    )
    rows: list[dict[str, Any]]
    if dependency.get("state") != "available":
        rows = [
            {
                "workers": workers,
                "state": "blocked_unavailable_dependency",
                "configuration_sha256": None,
                "output_semantic_sha256": None,
                "wall_seconds": None,
                "cpu_seconds": None,
                "peak_rss_kb": None,
                "frames_per_second": None,
                "media_minutes_per_compute_minute": None,
                "ocr_observations": 0,
                "quality_metrics": None,
                "output_equivalent": None,
                "failures": 1,
                "retries": 0,
                "timeouts": 0,
            }
            for workers in (1, 2, 4)
        ]
        limitations = ["Tesseract unavailable; worker scaling was not measured."]
    else:
        gold = _read(gold_path)
        validate_instance("ocr_gold", gold, gold_path.name)
        config = BaselineConfig.load(run_dir / "config.snapshot.yaml")
        rows = []
        semantic_hashes: list[str] = []
        for workers in (1, 2, 4):
            workspace = _benchmark_workspace(run_dir, workers)
            worker_config = replace(config, ocr_workers=workers)
            output = TesseractOcrAdapter().run(
                AdapterContext(
                    run_dir / "fixture_manifest.json", inventory, workspace, worker_config
                )
            )
            runtime = _read(workspace / "ocr_runtime.json")
            metrics = _quality_metrics(workspace, gold)
            _media_efficiency(metrics, int(inventory["duration_ms"]))
            semantic_hash = sha256_file(workspace / "ocr_observations.jsonl")
            semantic_hashes.append(semantic_hash)
            configuration_payload = {
                "base_configuration_sha256": sha256_file(run_dir / "config.snapshot.yaml"),
                "ocr_workers": workers,
                "omp_thread_limit_per_process": 1,
            }
            configuration_path = workspace / "effective_configuration.json"
            write_json(configuration_path, configuration_payload)
            rows.append(
                {
                    "workers": workers,
                    "state": output.result.status,
                    "configuration_sha256": sha256_file(configuration_path),
                    "output_semantic_sha256": semantic_hash,
                    "wall_seconds": runtime["wall_seconds"],
                    "cpu_seconds": runtime["cpu_seconds"],
                    "peak_rss_kb": runtime["peak_rss_kb"],
                    "frames_per_second": runtime["frames_per_second"],
                    "media_minutes_per_compute_minute": metrics["media_minutes_per_compute_minute"],
                    "ocr_observations": len(output.records),
                    "quality_metrics": {
                        key: metrics[key]
                        for key in (
                            "exact_text_match_rate",
                            "normalized_character_error_rate",
                            "normalized_word_error_rate",
                            "frame_text_presence_precision",
                            "frame_text_presence_recall",
                            "frame_text_presence_f1",
                        )
                    },
                    "output_equivalent": None,
                    "failures": runtime["failures"],
                    "retries": runtime["retries"],
                    "timeouts": runtime["timeouts"],
                }
            )
        equivalent = len(set(semantic_hashes)) == 1
        for row in rows:
            row["output_equivalent"] = equivalent
        limitations = [
            "Resource measurements describe the frozen four-frame synthetic workload only.",
            "Peak RSS is the maximum of the parent or any single child, not their concurrent sum.",
        ]
    report = {
        "schema_version": "1.0.0",
        "dependency": dependency,
        "gold_sha256": sha256_file(gold_path),
        "cpu_only": True,
        "network_accessed": False,
        "measurements": rows,
        "semantic_outputs_equivalent": (
            all(row["output_equivalent"] is True for row in rows)
            if dependency.get("state") == "available"
            else None
        ),
        "limitations": limitations,
    }
    write_json(run_dir / "ocr_benchmark.json", report)
    (run_dir / "ocr_benchmark.md").write_text(
        "# OCR worker benchmark\n\n"
        + "\n".join(
            f"- {row['workers']} workers: state={row['state']}, wall={row['wall_seconds']}, "
            f"fps={row['frames_per_second']}, semantic={row['output_semantic_sha256']}"
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )
    validate_instance("ocr_benchmark", report, "ocr_benchmark.json")
    artifact_names = ["ocr_benchmark.json", "ocr_benchmark.md"]
    benchmark_root = run_dir / "ocr_benchmark_runs"
    if benchmark_root.is_dir():
        artifact_names.extend(
            str(path.relative_to(run_dir))
            for path in sorted(benchmark_root.rglob("*"))
            if path.is_file()
        )
    _add_artifacts(run_dir, artifact_names)
    return report


def _add_artifacts(run_dir: Path, names: list[str]) -> None:
    manifest = _read(run_dir / "run_manifest.json")
    for name in names:
        path = run_dir / name
        manifest["artifacts"][name] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    write_json(run_dir / "run_manifest.json", manifest)
