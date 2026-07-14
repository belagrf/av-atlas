"""Run-level schema, evidence, revision, timeline, and hash validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from av_atlas.errors import AtlasError
from av_atlas.io import sha256_file, write_json
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
        ocr_records = _jsonl(run_dir / "ocr_observations.jsonl")
        for record in ocr_records:
            if record["evidence_ref"] not in known_refs:
                errors.append(f"OCR evidence is unresolved: {record['evidence_ref']}")
            if record["source_frame_evidence_ref"] not in known_refs:
                errors.append(
                    f"OCR source frame is unresolved: {record['source_frame_evidence_ref']}"
                )
        if (run_dir / "ocr_text_tracks.json").is_file():
            observations_by_id = {item["observation_id"]: item for item in ocr_records}
            for track in _json(run_dir / "ocr_text_tracks.json").get("tracks", []):
                for observation_id, ref in zip(
                    track["member_observation_ids"],
                    track["source_frame_evidence_refs"],
                    strict=True,
                ):
                    observation = observations_by_id.get(observation_id)
                    if observation is None:
                        errors.append(f"OCR text track member is unresolved: {observation_id}")
                    elif observation["source_frame_evidence_ref"] != ref or ref not in known_refs:
                        errors.append(f"OCR text track evidence is unresolved: {ref}")

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
