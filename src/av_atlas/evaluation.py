"""Versioned synthetic component evaluation for subtitle and shot adapters."""

from __future__ import annotations

import json
import platform
import resource
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

from av_atlas import __version__
from av_atlas.errors import AtlasError
from av_atlas.io import sha256_file, write_json
from av_atlas.media import tool_version
from av_atlas.rights import load_and_validate_rights
from av_atlas.schemas import validate_instance
from av_atlas.subtitles import normalize_subtitle_text


def _json(path: Path) -> dict[str, Any]:
    try:
        value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot read evaluation input {path}: {exc}") from exc


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot read evaluation input {path}: {exc}") from exc


def _prf(correct: int, predicted: int, gold: int) -> dict[str, Any]:
    precision = correct / predicted if predicted else (1.0 if gold == 0 else 0.0)
    recall = correct / gold if gold else (1.0 if predicted == 0 else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "correct": correct,
        "predicted": predicted,
        "gold": gold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _match_boundaries(
    predictions: list[dict[str, Any]], gold: list[dict[str, Any]], default_tolerance: int
) -> list[tuple[dict[str, Any], dict[str, Any], int]]:
    matches: list[tuple[dict[str, Any], dict[str, Any], int]] = []
    available = set(range(len(predictions)))
    for target in gold:
        tolerance = int(target.get("tolerance_ms", default_tolerance))
        candidates = [
            (abs(int(predictions[index]["start_ms"]) - int(target["boundary_ms"])), index)
            for index in available
            if abs(int(predictions[index]["start_ms"]) - int(target["boundary_ms"])) <= tolerance
        ]
        if candidates:
            error, index = min(candidates)
            available.remove(index)
            matches.append((predictions[index], target, error))
    return matches


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _code_state() -> dict[str, str]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout.strip()
        )
        return {"revision": revision, "dirty_state": str(dirty).lower()}
    except (FileNotFoundError, subprocess.SubprocessError):
        return {"revision": "unavailable-no-git-repository", "dirty_state": "unavailable"}


def evaluate_run(run_dir: Path, gold_path: Path, tolerance_ms: int = 200) -> dict[str, Any]:
    started = time.perf_counter()
    if tolerance_ms < 0:
        raise AtlasError("evaluation tolerance must be nonnegative")
    gold = _json(gold_path)
    validate_instance("component_gold", gold, gold_path.name)
    inventory = _json(run_dir / "inventory.json")
    fixture = _json(run_dir / "fixture_manifest.json")
    if gold["fixture_recipe"] != fixture["fixture_id"]:
        raise AtlasError("gold fixture recipe does not match the evaluated run")
    if gold["source_sha256"] is not None and gold["source_sha256"] != inventory["sha256"]:
        raise AtlasError("gold source hash does not match the evaluated run")
    shots = _jsonl(run_dir / "shots.jsonl")
    keyframes = _jsonl(run_dir / "keyframes.jsonl")
    cues = _jsonl(run_dir / "subtitles.jsonl")
    tracks_payload = _json(run_dir / "subtitle_tracks.json")
    adapter_payload = _json(run_dir / "adapter_results.json")
    manifest = _json(run_dir / "run_manifest.json")
    load_and_validate_rights(
        run_dir / "rights_manifest.json",
        inventory["sha256"],
        inventory["source_id"],
        "evaluation",
        expected_manifest_hash=manifest["rights"]["manifest_hash"],
    )

    predicted_boundaries = [shot for shot in shots if shot["boundary_type"] != "source_start"]
    boundary_matches = _match_boundaries(predicted_boundaries, gold["shots"], tolerance_ms)
    boundary_metrics = _prf(len(boundary_matches), len(predicted_boundaries), len(gold["shots"]))
    errors = [error for _, _, error in boundary_matches]
    boundary_metrics["timing_error_ms"] = {
        "values": errors,
        "mean": statistics.fmean(errors) if errors else None,
        "median": statistics.median(errors) if errors else None,
        "minimum": min(errors) if errors else None,
        "maximum": max(errors) if errors else None,
    }
    confusion: dict[str, dict[str, int]] = {}
    for prediction, target, _ in boundary_matches:
        confusion.setdefault(target["transition_type"], {}).setdefault(
            prediction["boundary_type"], 0
        )
        confusion[target["transition_type"]][prediction["boundary_type"]] += 1
    boundary_metrics["transition_type_confusion"] = confusion

    keyframes_by_shot: dict[str, list[dict[str, Any]]] = {}
    for keyframe in keyframes:
        keyframes_by_shot.setdefault(keyframe["shot_id"], []).append(keyframe)
    missing_keyframes = sum(not keyframes_by_shot.get(shot["shot_id"]) for shot in shots)
    duplicate_keyframes = sum(
        max(0, len(keyframes_by_shot.get(shot["shot_id"], [])) - 1) for shot in shots
    )
    covered_keyframes = sum(
        any(
            int(shot["start_ms"]) <= int(item["timestamp_ms"]) < int(shot["end_ms"])
            for item in keyframes_by_shot.get(shot["shot_id"], [])
        )
        for shot in shots
    )

    predicted_tracks = tracks_payload["tracks"]
    track_keys = {
        (
            track.get("language"),
            track.get("title"),
            bool(track["disposition"].get("default", False)),
            bool(track["disposition"].get("forced", False)),
        )
        for track in predicted_tracks
    }
    gold_track_keys = {
        (track["language"], track["title"], track["default"], track["forced"])
        for track in gold["subtitle_tracks"]
    }
    track_correct = len(track_keys.intersection(gold_track_keys))
    track_metrics = _prf(track_correct, len(track_keys), len(gold_track_keys))
    track_metrics["discovery_accuracy"] = (
        track_correct / len(gold_track_keys) if gold_track_keys else 1.0
    )

    language_by_track = {track["track_id"]: track["language"] for track in predicted_tracks}
    remaining_cues = set(range(len(cues)))
    cue_matches: list[tuple[dict[str, Any], dict[str, Any], int, int]] = []
    for target in gold["subtitle_cues"]:
        candidates = []
        for index in remaining_cues:
            prediction = cues[index]
            if language_by_track.get(prediction["track_id"]) != target["language"]:
                continue
            start_error = abs(int(prediction["start_ms"]) - int(target["start_ms"]))
            end_error = abs(int(prediction["end_ms"]) - int(target["end_ms"]))
            if max(start_error, end_error) <= tolerance_ms:
                candidates.append((start_error + end_error, index, start_error, end_error))
        if candidates:
            _, index, start_error, end_error = min(candidates)
            remaining_cues.remove(index)
            cue_matches.append((cues[index], target, start_error, end_error))
    cue_metrics = _prf(len(cue_matches), len(cues), len(gold["subtitle_cues"]))
    exact = sum(prediction["text"] == target["text"] for prediction, target, _, _ in cue_matches)
    edit_distance = sum(
        _levenshtein(
            normalize_subtitle_text(str(prediction["text"])),
            normalize_subtitle_text(str(target["text"])),
        )
        for prediction, target, _, _ in cue_matches
    )
    gold_characters = sum(
        len(normalize_subtitle_text(str(target["text"]))) for _, target, _, _ in cue_matches
    )
    cue_metrics.update(
        {
            "text_exact_match_rate": exact / len(cue_matches) if cue_matches else None,
            "normalized_character_error_rate": (
                edit_distance / gold_characters if gold_characters else 0.0
            ),
            "start_timing_errors_ms": [item[2] for item in cue_matches],
            "end_timing_errors_ms": [item[3] for item in cue_matches],
        }
    )
    observed_states = {item["adapter"]: item["status"] for item in adapter_payload["results"]}
    expected_states = {
        key: value for key, value in gold["expected_adapter_states"].items() if "." not in key
    }
    state_correct = sum(observed_states.get(key) == value for key, value in expected_states.items())

    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "evaluation_id": f"EVAL_{inventory['source_id']}",
        "measured_fixture_results": {
            "shot_boundaries": boundary_metrics,
            "keyframes": {
                "shot_count": len(shots),
                "coverage_count": covered_keyframes,
                "coverage_rate": covered_keyframes / len(shots) if shots else 1.0,
                "missing_count": missing_keyframes,
                "duplicate_count": duplicate_keyframes,
            },
            "subtitle_tracks": track_metrics,
            "subtitle_cues": cue_metrics,
            "adapter_state_correctness": {
                "correct": state_correct,
                "expected": len(expected_states),
                "accuracy": state_correct / len(expected_states) if expected_states else 1.0,
            },
        },
        "unmeasured_targets": [
            "real-media generalization",
            "supported-claim precision",
            "salient-event recall",
            "statistical significance",
        ],
        "unsupported_metrics": [
            "ASR WER/alignment",
            "diarization error",
            "OCR accuracy",
            "acoustic-event F1",
            "semantic visual accuracy",
        ],
        "sample_size_limitations": gold["limitations"],
        "reproducibility": {
            "av_atlas_version": __version__,
            "configuration_sha256": manifest["configuration"]["sha256"],
            "source_sha256": inventory["sha256"],
            "gold_sha256": sha256_file(gold_path),
            "gold_schema_version": gold["schema_version"],
            "fixture_generator_version": fixture["generator_version"],
            "python": platform.python_version(),
            "platform": platform.platform(),
            "ffmpeg": tool_version("ffmpeg"),
            "code_state": _code_state(),
            "timestamp_tolerance_ms": tolerance_ms,
        },
        "efficiency": {
            "pipeline_runtime_seconds": manifest["performance"]["runtime_seconds"],
            "evaluation_runtime_seconds": round(time.perf_counter() - started, 6),
            "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "output_storage_bytes": sum(
                path.stat().st_size for path in run_dir.rglob("*") if path.is_file()
            ),
            "retry_count": manifest["performance"]["retry_count"],
            "processed_media_duration_ms": inventory["duration_ms"],
        },
    }
    validate_instance("component_evaluation", report, "evaluation.json")
    gold_snapshot = run_dir / "evaluation_gold.json"
    write_json(gold_snapshot, gold)
    evaluation_path, markdown_path = run_dir / "evaluation.json", run_dir / "evaluation.md"
    write_json(evaluation_path, report)
    _write_markdown(markdown_path, report)
    manifest["artifacts"].update(
        {
            path.name: {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
            for path in (gold_snapshot, evaluation_path, markdown_path)
        }
    )
    write_json(run_dir / "run_manifest.json", manifest)
    return report


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    shots = report["measured_fixture_results"]["shot_boundaries"]
    cues = report["measured_fixture_results"]["subtitle_cues"]
    tracks = report["measured_fixture_results"]["subtitle_tracks"]
    keyframes = report["measured_fixture_results"]["keyframes"]
    lines = [
        "# M2A component evaluation",
        "",
        "Measured only on a project-authored synthetic fixture.",
        "",
        "## Measured fixture results",
        "",
        f"- Shot boundary precision/recall/F1: {shots['precision']:.6f} / "
        f"{shots['recall']:.6f} / {shots['f1']:.6f}",
        f"- Keyframe coverage: {keyframes['coverage_count']}/{keyframes['shot_count']}",
        f"- Subtitle track discovery accuracy: {tracks['discovery_accuracy']:.6f}",
        f"- Subtitle cue precision/recall/F1: {cues['precision']:.6f} / "
        f"{cues['recall']:.6f} / {cues['f1']:.6f}",
        f"- Subtitle exact text match: {cues['text_exact_match_rate']:.6f}",
        "",
        "## Limitations",
        "",
        *(f"- {item}" for item in report["sample_size_limitations"]),
        "",
        "No statistical significance or real-media/model-performance claim is made.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
