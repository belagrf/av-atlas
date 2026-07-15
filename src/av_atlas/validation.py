"""Run-level schema, evidence, revision, timeline, and hash validation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError
from av_atlas.io import canonical_json, sha256_file, write_json
from av_atlas.ocr_tracks import POLICY_VERSION, associate_temporal_text, spatially_compatible
from av_atlas.pipeline import ARTIFACTS
from av_atlas.rights import load_and_validate_rights
from av_atlas.schemas import validate_instance


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"invalid JSON artifact {path.name}: {exc}") from exc


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"invalid JSONL artifact {path.name}: {exc}") from exc


def _validate_ocr_tracks(
    run_dir: Path,
    ocr_records: list[dict[str, Any]],
    known_refs: set[str],
    errors: list[str],
) -> int:
    """Verify the complete derived track payload against immutable OCR observations."""
    try:
        payload = _json(run_dir / "ocr_text_tracks.json")
    except AtlasError as exc:
        errors.append(str(exc))
        return 0
    if not isinstance(payload, dict):
        errors.append("OCR text-track artifact must be a JSON object")
        return 0
    try:
        configured_gap = BaselineConfig.load(
            run_dir / "config.snapshot.yaml"
        ).ocr_temporal_association_max_gap_ms
    except (AtlasError, OSError, TypeError, ValueError, OverflowError) as exc:
        errors.append(f"cannot verify OCR text-track configured association gap: {exc}")
        configured_gap = None

    policy = payload.get("association_policy_version")
    if policy != POLICY_VERSION:
        errors.append(f"unsupported OCR text-track association policy: {policy}")
    maximum_gap = payload.get("maximum_association_gap_ms")
    if not isinstance(maximum_gap, int) or isinstance(maximum_gap, bool) or maximum_gap < 0:
        errors.append("OCR text-track maximum association gap must be a nonnegative integer")
        maximum_gap = None
    if maximum_gap is not None and configured_gap is not None and maximum_gap != configured_gap:
        errors.append("OCR text-track association gap does not match the run configuration")

    expected_payload: dict[str, Any] | None = None
    if configured_gap is not None:
        try:
            expected_payload = associate_temporal_text(ocr_records, configured_gap)
        except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
            errors.append(f"cannot deterministically derive OCR text tracks: {exc}")

    tracks = payload.get("tracks")
    if not isinstance(tracks, list):
        errors.append("OCR text-track tracks field must be an array")
        return 0
    observations_by_id: dict[str, dict[str, Any]] = {}
    for item in ocr_records:
        if not isinstance(item, dict):
            continue
        observation_id = item.get("observation_id")
        if isinstance(observation_id, str):
            observations_by_id[observation_id] = item
    raw_ids = list(observations_by_id)
    if len(raw_ids) != len(ocr_records):
        errors.append("raw OCR observations contain missing or duplicate observation IDs")
    if not tracks and raw_ids:
        errors.append("OCR text tracks are empty while eligible raw observations exist")

    checked = 0
    track_ids: list[str] = []
    member_counts: dict[str, int] = {}
    fields = (
        "member_observation_ids",
        "source_frame_evidence_refs",
        "spatial_boxes",
        "confidence_values",
    )
    for index, candidate in enumerate(tracks, 1):
        checked += 1
        label = f"OCR text track {index}"
        if not isinstance(candidate, dict):
            errors.append(f"{label} must be an object")
            continue
        track_id = candidate.get("track_id")
        if not isinstance(track_id, str):
            errors.append(f"{label} track ID must be a string")
        else:
            track_ids.append(track_id)
            label = f"OCR text track {track_id}"
        arrays: dict[str, list[Any]] = {}
        for field in fields:
            value = candidate.get(field)
            if not isinstance(value, list):
                errors.append(f"{label} field {field} must be an array")
            else:
                arrays[field] = value
        if len(arrays) != len(fields):
            continue
        lengths = {field: len(arrays[field]) for field in fields}
        if len(set(lengths.values())) != 1:
            detail = ", ".join(f"{name}={count}" for name, count in lengths.items())
            errors.append(f"{label} parallel member-array lengths disagree: {detail}")
            continue
        member_ids = arrays["member_observation_ids"]
        if not member_ids:
            errors.append(f"{label} parallel member arrays must be nonempty")
            continue
        if len(member_ids) != len(set(str(item) for item in member_ids)):
            errors.append(f"{label} contains duplicate member observation IDs")
        if candidate.get("association_policy_version") != POLICY_VERSION:
            errors.append(
                f"{label} uses unsupported association policy: "
                f"{candidate.get('association_policy_version')}"
            )
        if candidate.get("maximum_association_gap_ms") != maximum_gap:
            errors.append(f"{label} association gap disagrees with the artifact policy")

        resolved: list[dict[str, Any]] = []
        numeric_confidences: list[float] = []
        for position, observation_id in enumerate(member_ids):
            ref = arrays["source_frame_evidence_refs"][position]
            box = arrays["spatial_boxes"][position]
            confidence = arrays["confidence_values"][position]
            if not isinstance(observation_id, str):
                errors.append(f"{label} member observation ID must be a string")
                continue
            member_counts[observation_id] = member_counts.get(observation_id, 0) + 1
            if not isinstance(ref, str):
                errors.append(f"{label} evidence reference must be a string")
            elif ref not in known_refs:
                errors.append(f"{label} evidence reference is unresolved: {ref}")
            observation = observations_by_id.get(observation_id)
            if observation is None:
                errors.append(f"{label} member observation is unresolved: {observation_id}")
                continue
            resolved.append(observation)
            if observation.get("source_id") != candidate.get("source_id"):
                errors.append(f"{label} member {observation_id} has the wrong source ID")
            if observation.get("shot_id") != candidate.get("shot_id"):
                errors.append(f"{label} member {observation_id} crosses a shot boundary")
            if observation.get("normalized_text") != candidate.get("normalized_text"):
                errors.append(f"{label} member {observation_id} has different normalized text")
            if observation.get("source_frame_evidence_ref") != ref:
                errors.append(f"{label} member {observation_id} has the wrong evidence reference")
            if observation.get("bounding_box") != box:
                errors.append(f"{label} member {observation_id} has the wrong spatial box")
            try:
                expected_confidence = float(observation["confidence"])
                actual_confidence = float(confidence)
                if not math.isfinite(expected_confidence) or not math.isfinite(actual_confidence):
                    raise ValueError("confidence must be finite")
            except (KeyError, TypeError, ValueError, OverflowError):
                errors.append(f"{label} member {observation_id} has malformed confidence data")
            else:
                numeric_confidences.append(actual_confidence)
                if not math.isclose(
                    actual_confidence, expected_confidence, rel_tol=1e-9, abs_tol=1e-9
                ):
                    errors.append(f"{label} member {observation_id} has the wrong confidence value")

        if len(resolved) != len(member_ids):
            continue
        try:
            ordered = sorted(
                resolved,
                key=lambda item: (int(item["timestamp_ms"]), str(item["observation_id"])),
            )
            timestamps = [int(item["timestamp_ms"]) for item in resolved]
        except (KeyError, TypeError, ValueError, IndexError, OverflowError):
            errors.append(f"{label} members contain malformed ordering or timestamp data")
            continue
        if [item["observation_id"] for item in resolved] != [
            item["observation_id"] for item in ordered
        ]:
            errors.append(f"{label} members are not deterministically ordered")
        first_timestamp = candidate.get("first_timestamp_ms")
        last_timestamp = candidate.get("last_timestamp_ms")
        if first_timestamp != min(timestamps):
            errors.append(f"{label} first timestamp does not match its members")
        if last_timestamp != max(timestamps):
            errors.append(f"{label} last timestamp does not match its members")
        if not isinstance(first_timestamp, int) or not isinstance(last_timestamp, int):
            errors.append(f"{label} timestamp bounds must be integers")
        elif first_timestamp > last_timestamp:
            errors.append(f"{label} first timestamp exceeds its last timestamp")

        expected_variants: list[str] = []
        for observation in resolved:
            raw_text = observation.get("text")
            if isinstance(raw_text, str) and raw_text not in expected_variants:
                expected_variants.append(raw_text)
        if candidate.get("raw_text_variants") != expected_variants:
            errors.append(f"{label} raw text variants do not match its ordered members")

        if maximum_gap is not None:
            for left, right in zip(resolved, resolved[1:], strict=False):
                try:
                    gap = int(right["timestamp_ms"]) - int(left["timestamp_ms"])
                except (KeyError, TypeError, ValueError, OverflowError):
                    errors.append(f"{label} member gap is malformed")
                    continue
                if gap < 0 or gap > maximum_gap:
                    errors.append(f"{label} members exceed the configured association gap")
                left_box, right_box = left.get("bounding_box"), right.get("bounding_box")
                if (
                    isinstance(left_box, list)
                    and isinstance(right_box, list)
                    and len(left_box) == 4
                    and len(right_box) == 4
                    and all(
                        isinstance(value, int) and not isinstance(value, bool)
                        for value in [*left_box, *right_box]
                    )
                    and not spatially_compatible(left_box, right_box)
                ):
                    errors.append(f"{label} members violate spatial compatibility")
        if len(numeric_confidences) == len(member_ids):
            expected_mean = sum(numeric_confidences) / len(numeric_confidences)
            try:
                actual_mean = float(candidate["mean_confidence"])
                if not math.isfinite(actual_mean):
                    raise ValueError("mean confidence must be finite")
            except (KeyError, TypeError, ValueError, OverflowError):
                errors.append(f"{label} mean confidence is malformed")
            else:
                if not math.isclose(actual_mean, expected_mean, rel_tol=1e-9, abs_tol=1e-9):
                    errors.append(f"{label} mean confidence is not the arithmetic mean")

    if len(track_ids) != len(set(track_ids)):
        errors.append("OCR text-track IDs are not unique")
    for observation_id in raw_ids:
        count = member_counts.get(observation_id, 0)
        if count == 0:
            errors.append(f"raw OCR observation is omitted from temporal tracks: {observation_id}")
        elif count > 1:
            errors.append(
                f"raw OCR observation appears in multiple temporal tracks: {observation_id}"
            )
    for observation_id in sorted(set(member_counts).difference(raw_ids)):
        errors.append(f"temporal track contains a fabricated member: {observation_id}")

    if expected_payload is not None:
        expected_tracks = expected_payload["tracks"]
        expected_track_ids = [item["track_id"] for item in expected_tracks]
        if track_ids != expected_track_ids:
            errors.append("OCR text tracks are not globally deterministically ordered")
        if canonical_json(payload) != canonical_json(expected_payload):
            errors.append(
                "OCR text-track artifact does not equal the deterministic derivation of all raw "
                "OCR observations"
            )
    return checked


def _validate_legacy_m0(
    run_dir: Path, manifest: dict[str, Any], write_report: bool
) -> dict[str, Any]:
    """Validate preserved 0.1.0 evidence without inventing later rights artifacts."""
    errors: list[str] = []
    checks = {
        "json_schema": 0,
        "events": 0,
        "evidence_refs": 0,
        "revision_chains": 0,
        "artifact_hashes": 0,
        "rights_linkage": 0,
        "adapter_contracts": 0,
        "subtitle_cues": 0,
        "shots": 0,
        "keyframes": 0,
    }
    try:
        inventory = _json(run_dir / "inventory.json")
        evidence = _json(run_dir / "evidence_index.json")
        for filename in ("provenance.json", "state.json"):
            _json(run_dir / filename)
        known_refs = set(evidence.get("evidence", {}))
        for filename in (
            "events.final.jsonl",
            "events.provisional.jsonl",
            "entities.jsonl",
            "run.log.jsonl",
        ):
            for line_number, record in enumerate(_jsonl(run_dir / filename), 1):
                if not isinstance(record, dict):
                    errors.append(f"legacy JSONL record is not an object: {filename}:{line_number}")
                if filename == "events.final.jsonl":
                    checks["events"] += 1
                    if (
                        not 0
                        <= int(record["start_ms"])
                        < int(record["end_ms"])
                        <= int(inventory["duration_ms"])
                    ):
                        errors.append(
                            f"legacy event {record['event_id']} is outside source duration"
                        )
                    for claim in record["claims"]:
                        for ref in claim["evidence_refs"]:
                            checks["evidence_refs"] += 1
                            if ref not in known_refs:
                                errors.append(f"dangling legacy evidence reference: {ref}")
        for name, descriptor in manifest.get("artifacts", {}).items():
            path = run_dir / str(name)
            if not path.is_file() or sha256_file(path) != descriptor.get("sha256"):
                errors.append(f"legacy artifact hash mismatch: {name}")
            else:
                checks["artifact_hashes"] += 1
    except AtlasError as exc:
        errors.append(str(exc))
    report = {
        "schema_version": "1.0.0",
        "valid": not errors,
        "checks": checks,
        "errors": errors,
    }
    validate_instance("quality_report", report, "quality_report.json")
    if write_report:
        write_json(run_dir / "quality_report.json", report)
        (run_dir / "quality_report.md").write_text(
            "# Quality report\n\n"
            f"Valid: **{str(not errors).lower()}**\n\n"
            "Legacy AV-Atlas 0.1.0 contract: later rights, configuration snapshot, and adapter "
            "artifacts are not retroactively asserted.\n",
            encoding="utf-8",
        )
    if errors:
        raise AtlasError("legacy run validation failed: " + "; ".join(errors))
    return report


def validate_run(run_dir: Path, write_report: bool = True) -> dict[str, Any]:
    initial_manifest = _json(run_dir / "run_manifest.json")
    if (
        initial_manifest.get("software", {}).get("av_atlas") == "0.1.0"
        and "rights" not in initial_manifest
    ):
        return _validate_legacy_m0(run_dir, initial_manifest, write_report)
    validate_instance("run_manifest", initial_manifest, "run_manifest.json")
    initial_inventory = _json(run_dir / "inventory.json")
    validate_instance("inventory", initial_inventory, "inventory.json")
    if (
        initial_inventory["sha256"] != initial_manifest["source"]["sha256"]
        or initial_inventory["source_id"] != initial_manifest["source"]["source_id"]
    ):
        raise AtlasError("run manifest source linkage does not match inventory")
    load_and_validate_rights(
        run_dir / "rights_manifest.json",
        str(initial_manifest["source"]["sha256"]),
        str(initial_manifest["source"]["source_id"]),
        str(initial_manifest["operation"]),
        expected_manifest_hash=str(initial_manifest["rights"]["manifest_hash"]),
    )
    errors: list[str] = []
    checks = {
        "json_schema": 0,
        "events": 0,
        "evidence_refs": 0,
        "revision_chains": 0,
        "artifact_hashes": 0,
        "rights_linkage": 0,
        "adapter_contracts": 0,
        "subtitle_cues": 0,
        "shots": 0,
        "keyframes": 0,
        "ocr_text_tracks": 0,
    }
    manifest: dict[str, Any] = {}
    inventory: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    state: dict[str, Any] = {}
    final: list[dict[str, Any]] = []
    provisional: list[dict[str, Any]] = []
    try:
        manifest = _json(run_dir / "run_manifest.json")
        inventory = _json(run_dir / "inventory.json")
        provenance = _json(run_dir / "provenance.json")
        evidence = _json(run_dir / "evidence_index.json")
        state = _json(run_dir / "state.json")
        rights = _json(run_dir / "rights_manifest.json")
        adapter_results = _json(run_dir / "adapter_results.json")
        dependency_bom = _json(run_dir / "dependency_bom.json")
        for name, value in (
            ("run_manifest", manifest),
            ("inventory", inventory),
            ("provenance", provenance),
            ("evidence_index", evidence),
            ("state", state),
            ("rights_manifest", rights),
            ("adapter_results", adapter_results),
            ("dependency_bom", dependency_bom),
        ):
            validate_instance(name, value, f"{name}.json")
            checks["json_schema"] += 1
        final = _jsonl(run_dir / "events.final.jsonl")
        provisional = _jsonl(run_dir / "events.provisional.jsonl")
        entities = _jsonl(run_dir / "entities.jsonl")
        logs = _jsonl(run_dir / "run.log.jsonl")
        for filename, records, schema in (
            ("events.final.jsonl", final, "event"),
            ("events.provisional.jsonl", provisional, "event"),
            ("entities.jsonl", entities, "entity"),
            ("run.log.jsonl", logs, "structured_log"),
        ):
            for line_number, record in enumerate(records, 1):
                validate_instance(schema, record, f"{filename}:{line_number}")
                checks["json_schema"] += 1
        if (run_dir / "fixture_manifest.json").is_file():
            validate_instance(
                "fixture_manifest",
                _json(run_dir / "fixture_manifest.json"),
                "fixture_manifest.json",
            )
            checks["json_schema"] += 1
        if (run_dir / "subtitle_tracks.json").is_file():
            validate_instance(
                "subtitle_tracks", _json(run_dir / "subtitle_tracks.json"), "subtitle_tracks.json"
            )
            checks["json_schema"] += 1
        legacy_ocr = False
        if (run_dir / "ocr_dependency.json").is_file():
            legacy_ocr = "schema_version" not in _json(run_dir / "ocr_dependency.json")
        for filename, schema in (
            ("subtitles.jsonl", "subtitle_cue"),
            ("shots.jsonl", "shot"),
            ("keyframes.jsonl", "keyframe"),
            ("ocr_observations.jsonl", "ocr_observation"),
        ):
            if (run_dir / filename).is_file() and not legacy_ocr:
                for line_number, record in enumerate(_jsonl(run_dir / filename), 1):
                    validate_instance(schema, record, f"{filename}:{line_number}")
                    checks["json_schema"] += 1
        if (run_dir / "evaluation.json").is_file():
            validate_instance(
                "component_evaluation", _json(run_dir / "evaluation.json"), "evaluation.json"
            )
            checks["json_schema"] += 1
        if (run_dir / "evaluation_gold.json").is_file():
            validate_instance(
                "component_gold", _json(run_dir / "evaluation_gold.json"), "evaluation_gold.json"
            )
            checks["json_schema"] += 1
        for filename, schema in (
            ("ocr_dependency.json", "ocr_dependency"),
            ("ocr_frame_results.json", "ocr_frame_results"),
            ("ocr_runtime.json", "ocr_runtime"),
            ("ocr_evaluation.json", "ocr_evaluation"),
            ("ocr_benchmark.json", "ocr_benchmark"),
            ("ocr_text_tracks.json", "ocr_text_tracks"),
        ):
            if (run_dir / filename).is_file() and not legacy_ocr:
                validate_instance(schema, _json(run_dir / filename), filename)
                checks["json_schema"] += 1
    except AtlasError as exc:
        errors.append(str(exc))

    if manifest and inventory:
        checks["rights_linkage"] += 1

    duration_ms = int(inventory.get("duration_ms", 0))
    provisional_by_id = {record.get("event_id"): record for record in provisional}
    prior_key = (-1, -1, "")
    seen_revisions: dict[str, int] = {}
    known_refs = set(evidence.get("evidence", {}))
    state_chunks = state.get("chunks", []) if isinstance(state, dict) else []
    for record in final:
        checks["events"] += 1
        start, end = int(record.get("start_ms", -1)), int(record.get("end_ms", -1))
        key = (start, end, str(record.get("event_id", "")))
        if not 0 <= start < end <= duration_ms:
            errors.append(f"event {record.get('event_id')} is outside source duration")
        if key < prior_key:
            errors.append("final events are not deterministically ordered")
        prior_key = key
        if record.get("schema_version") == "1.1.0":
            expected_chunks = [
                f"CHK_{index:04d}"
                for index, chunk in enumerate(state_chunks, 1)
                if int(chunk["start_ms"]) < end and int(chunk["end_ms"]) > start
            ]
            provenance_chunks = record.get("provenance", {}).get("chunk_ids", [])
            if (
                not expected_chunks
                or provenance_chunks != expected_chunks
                or record["provenance"]["chunk_id"] != expected_chunks[0]
            ):
                errors.append(f"event {record.get('event_id')} has incorrect chunk provenance")
        event_id, revision = str(record.get("event_id")), int(record.get("revision", 0))
        if event_id in seen_revisions and revision <= seen_revisions[event_id]:
            errors.append(f"non-increasing revision chain for {event_id}")
        seen_revisions[event_id] = revision
        earlier = provisional_by_id.get(event_id)
        if earlier is None or earlier.get("status") != "provisional":
            errors.append(f"missing provisional predecessor for {event_id}")
        elif int(earlier.get("revision", 0)) >= revision:
            errors.append(f"final revision does not advance {event_id}")
        else:
            checks["revision_chains"] += 1
        refs = [ref for claim in record.get("claims", []) for ref in claim.get("evidence_refs", [])]
        refs.extend(item.get("evidence_ref") for item in record.get("speech", []))
        for ref in refs:
            checks["evidence_refs"] += 1
            if ref not in known_refs:
                errors.append(f"dangling evidence reference: {ref}")
        for item in record.get("speech", []):
            if item.get("source") not in {
                "asr",
                "subtitle",
                "caption",
                "sidecar_asr",
                "provided_transcript",
            }:
                errors.append(f"unauthorized quoted speech source in {event_id}")
            if not str(item.get("evidence_ref", "")).startswith(("ASR:", "SUB:")):
                errors.append(f"quoted speech lacks ASR/subtitle evidence in {event_id}")

    if (run_dir / "adapter_results.json").is_file():
        adapter_payload = _json(run_dir / "adapter_results.json")
        for result in adapter_payload.get("results", []):
            checks["adapter_contracts"] += 1
            if (
                result["status"] not in {"success", "success_zero", "partial_success"}
                and result["observation_count"]
            ):
                errors.append(f"failed adapter {result['adapter']} reports fabricated observations")
            counts = result.get("unit_counts")
            if counts is not None:
                if counts["emitted_observations"] != result["observation_count"]:
                    errors.append(f"adapter {result['adapter']} observation counts disagree")
                accounted = counts["successful"] + counts["failed"] + counts["unsupported"]
                if accounted != counts["attempted"]:
                    errors.append(f"adapter {result['adapter']} unit counts do not balance")
                if counts["timed_out"] > counts["failed"]:
                    errors.append(f"adapter {result['adapter']} timeout count exceeds failures")
                if result["status"] == "partial_success" and not (
                    counts["successful"] > 0 and (counts["failed"] + counts["unsupported"]) > 0
                ):
                    errors.append(f"adapter {result['adapter']} has invalid partial_success counts")

    if (run_dir / "subtitles.jsonl").is_file():
        cues = _jsonl(run_dir / "subtitles.jsonl")
        for cue in cues:
            checks["subtitle_cues"] += 1
            if not 0 <= int(cue["start_ms"]) < int(cue["end_ms"]) <= duration_ms:
                errors.append(f"subtitle cue {cue['evidence_ref']} is outside source duration")
            if cue["evidence_ref"] not in known_refs:
                errors.append(f"subtitle cue evidence is unresolved: {cue['evidence_ref']}")

    shots: list[dict[str, Any]] = []
    if (run_dir / "shots.jsonl").is_file():
        shots = _jsonl(run_dir / "shots.jsonl")
        prior_end = 0
        for shot in shots:
            checks["shots"] += 1
            if int(shot["start_ms"]) != prior_end:
                errors.append(f"shot chronology is discontinuous at {shot['shot_id']}")
            if not 0 <= int(shot["start_ms"]) < int(shot["end_ms"]) <= duration_ms:
                errors.append(f"shot {shot['shot_id']} is outside source duration")
            prior_end = int(shot["end_ms"])
        if shots and prior_end != duration_ms:
            errors.append("terminal shot does not end at source duration")

    if (run_dir / "keyframes.jsonl").is_file():
        shots_by_id = {shot["shot_id"]: shot for shot in shots}
        seen_shots: set[str] = set()
        for keyframe in _jsonl(run_dir / "keyframes.jsonl"):
            checks["keyframes"] += 1
            matched_shot = shots_by_id.get(keyframe["shot_id"])
            if matched_shot is None:
                errors.append(f"keyframe references unknown shot: {keyframe['shot_id']}")
                continue
            if keyframe["shot_id"] in seen_shots:
                errors.append(f"duplicate keyframe for shot: {keyframe['shot_id']}")
            seen_shots.add(keyframe["shot_id"])
            timestamp = int(keyframe["timestamp_ms"])
            if not int(matched_shot["start_ms"]) <= timestamp < int(matched_shot["end_ms"]):
                errors.append(f"keyframe is outside shot: {keyframe['keyframe_id']}")
            if keyframe["evidence_ref"] not in known_refs:
                errors.append(f"keyframe evidence is unresolved: {keyframe['evidence_ref']}")
            path = run_dir / str(keyframe["path"])
            if not path.is_file() or sha256_file(path) != keyframe["sha256"]:
                errors.append(f"keyframe content hash mismatch: {keyframe['keyframe_id']}")
        if shots and len(seen_shots) != len(shots):
            errors.append("one or more shots lack a keyframe")

    if (run_dir / "ocr_observations.jsonl").is_file():
        try:
            ocr_records = _jsonl(run_dir / "ocr_observations.jsonl")
        except AtlasError as exc:
            errors.append(str(exc))
            ocr_records = []
        for record in ocr_records:
            if not isinstance(record, dict):
                errors.append("OCR observation must be an object")
                continue
            evidence_ref = record.get("evidence_ref")
            source_frame_ref = record.get("source_frame_evidence_ref")
            if evidence_ref not in known_refs:
                errors.append(f"OCR evidence is unresolved: {evidence_ref}")
            if source_frame_ref not in known_refs:
                errors.append(f"OCR source frame is unresolved: {source_frame_ref}")
        if (run_dir / "ocr_text_tracks.json").is_file():
            checks["ocr_text_tracks"] += _validate_ocr_tracks(
                run_dir, ocr_records, known_refs, errors
            )

    for name in ARTIFACTS:
        if name not in manifest.get("artifacts", {}):
            errors.append(f"manifest omits required artifact: {name}")
    for name, descriptor in manifest.get("artifacts", {}).items():
        path = run_dir / str(name)
        expected = descriptor.get("sha256")
        if not path.is_file():
            errors.append(f"missing artifact: {name}")
        elif expected != sha256_file(path):
            errors.append(f"artifact hash mismatch: {name}")
        else:
            checks["artifact_hashes"] += 1

    report = {
        "schema_version": "1.0.0",
        "valid": not errors,
        "checks": checks,
        "errors": errors,
    }
    validate_instance("quality_report", report, "quality_report.json")
    if write_report:
        write_json(run_dir / "quality_report.json", report)
        lines = ["# Quality report", "", f"Valid: **{str(not errors).lower()}**", ""]
        lines.extend(f"- {name}: {count}" for name, count in checks.items())
        if errors:
            lines.extend(["", "## Errors", "", *(f"- {error}" for error in errors)])
        (run_dir / "quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if errors:
        raise AtlasError("run validation failed: " + "; ".join(errors))
    return report
