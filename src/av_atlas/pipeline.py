"""CPU-only, offline sidecar-to-ledger baseline pipeline."""

from __future__ import annotations

import json
import resource
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from av_atlas import __version__
from av_atlas.adapters import AdapterContext, PerceptionAdapter, SidecarAdapter
from av_atlas.config import BaselineConfig
from av_atlas.contracts import AdapterResult, Observation, evidence_ref
from av_atlas.errors import AtlasError
from av_atlas.io import atomic_write_text, safe_relative_path, sha256_file, write_json, write_jsonl
from av_atlas.media import enforce_media_limits, inspect_media, tool_version
from av_atlas.ocr import TesseractOcrAdapter
from av_atlas.rights import (
    controlled_fixture_manifest,
    fixture_rights,
    load_and_validate_rights,
    validate_rights_artifact,
)
from av_atlas.schemas import validate_instance
from av_atlas.shots import ShotAdapter
from av_atlas.subtitles import SubtitleAdapter
from av_atlas.timeline import chunks, uniform_samples

ARTIFACTS = (
    "inventory.json",
    "provenance.json",
    "evidence_index.json",
    "events.provisional.jsonl",
    "events.final.jsonl",
    "entities.jsonl",
    "transcript.vtt",
    "transcript.srt",
    "timeline.md",
    "summary.md",
    "run.log.jsonl",
    "state.json",
    "rights_manifest.json",
    "config.snapshot.yaml",
    "adapter_results.json",
)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot read {path}: {exc}") from exc


def _manifest(
    run_dir: Path,
    config_path: Path,
    inventory: dict[str, Any],
    rights: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "run_id": run_dir.name,
        "status": "processing",
        "created_at": _timestamp(),
        "completed_at": None,
        "operation": operation,
        "rights": {
            "manifest_hash": rights["manifest_hash"],
            "independently_reviewed": rights["independently_reviewed"],
        },
        "source": {
            "source_id": inventory["source_id"],
            "sha256": inventory["sha256"],
            "duration_ms": inventory["duration_ms"],
        },
        "configuration": {
            "sha256": sha256_file(config_path),
            "path": safe_relative_path(config_path, run_dir),
        },
        "software": {
            "av_atlas": __version__,
            "ffmpeg": tool_version("ffmpeg"),
            "ffprobe": tool_version("ffprobe"),
        },
        "performance": {
            "runtime_seconds": 0.0,
            "peak_rss_kb": 0,
            "retry_count": 0,
            "processed_duration_ms": inventory["duration_ms"],
        },
        "artifacts": {},
    }


def _provenance(inventory: dict[str, Any], rights: dict[str, Any]) -> dict[str, Any]:
    basis = rights["rights_basis"]
    tier = {
        "synthetic-controlled": "D-synthetic-controlled",
        "public-domain": "A-clear-training-rights",
        "licensed": "A-clear-training-rights",
        "owned": "C-private-user-accessible",
        "other-documented-authorization": "C-private-user-accessible",
    }[basis]
    return {
        "schema_version": "1.0.0",
        "source_id": inventory["source_id"],
        "content_sha256": inventory["sha256"],
        "rights_tier": tier,
        "acquisition_basis": f"operator-declared:{basis}",
        "permitted_uses": [
            operation for operation, permitted in rights["permissions"].items() if permitted
        ],
        "restrictions": rights["restrictions"],
        "retention": (
            "derivative-retention-permitted"
            if rights["permissions"]["derivative_artifact_retention"]
            else "derivative-retention-not-permitted"
        ),
        "deletion_key": inventory["source_id"],
        "review_status": (
            "independently-reviewed"
            if rights["independently_reviewed"]
            else "operator-declared-not-independently-reviewed"
        ),
    }


def _records(
    observations: list[Observation],
    source_id: str,
    duration_ms: int,
    status: str,
    run_id: str,
    chunk_values: list[dict[str, int]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for observation in observations:
        ref = evidence_ref(observation, source_id)
        evidence[ref] = {
            "evidence_ref": ref,
            "source_id": source_id,
            "observation_id": observation.observation_id,
            "modality": observation.modality,
            "start_ms": observation.start_ms,
            "end_ms": observation.end_ms,
        }

    grouped: dict[tuple[int, int], list[Observation]] = {}
    for observation in observations:
        grouped.setdefault((observation.start_ms, observation.end_ms), []).append(observation)

    records: list[dict[str, Any]] = []
    claim_index = 0
    for event_index, ((start_ms, end_ms), group) in enumerate(sorted(grouped.items()), 1):
        applicable_chunks = [
            f"CHK_{index:04d}"
            for index, chunk in enumerate(chunk_values, 1)
            if int(chunk["start_ms"]) < end_ms and int(chunk["end_ms"]) > start_ms
        ]
        if not applicable_chunks:
            raise AtlasError(f"event interval {start_ms}-{end_ms} resolves to no generated chunk")
        claims: list[dict[str, Any]] = []
        speech: list[dict[str, Any]] = []
        entities = sorted({item.speaker_id for item in group if item.speaker_id is not None})
        for observation in group:
            claim_index += 1
            ref = evidence_ref(observation, source_id)
            claims.append(
                {
                    "claim_id": f"CLM_{claim_index:06d}",
                    "type": observation.claim_type,
                    "text": observation.text,
                    "confidence": observation.confidence,
                    "evidence_refs": [ref],
                }
            )
            if observation.speech_text is not None:
                speech.append(
                    {
                        "speaker_id": observation.speaker_id or "SPEAKER_UNKNOWN",
                        "text": observation.speech_text,
                        "source": observation.speech_source or "sidecar_asr",
                        "evidence_ref": ref,
                        "confidence": observation.confidence,
                    }
                )
        records.append(
            {
                "schema_version": "1.1.0",
                "event_id": f"EVT_{event_index:06d}",
                "revision": 1 if status == "provisional" else 2,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "level": "atomic",
                "scene_id": "SCN_0001" if start_ms < duration_ms / 2 else "SCN_0002",
                "claims": claims,
                "speech": speech,
                "entities": entities,
                "uncertainty": [],
                "status": status,
                "provenance": {
                    "source_id": source_id,
                    "chunk_id": applicable_chunks[0],
                    "chunk_ids": applicable_chunks,
                    "run_id": run_id,
                },
            }
        )
    return records, {"schema_version": "1.0.0", "evidence": evidence}


def _timecode(milliseconds: int, srt: bool = False) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    separator = "," if srt else "."
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def _exports(run_dir: Path, records: list[dict[str, Any]]) -> None:
    speech = [(record, item) for record in records for item in record["speech"]]
    vtt_lines = ["WEBVTT", ""]
    srt_lines: list[str] = []
    for index, (record, item) in enumerate(speech, 1):
        vtt_lines.extend(
            [
                f"{_timecode(record['start_ms'])} --> {_timecode(record['end_ms'])}",
                f"{item['speaker_id']}: {item['text']}",
                "",
            ]
        )
        srt_lines.extend(
            [
                str(index),
                f"{_timecode(record['start_ms'], True)} --> {_timecode(record['end_ms'], True)}",
                f"{item['speaker_id']}: {item['text']}",
                "",
            ]
        )
    (run_dir / "transcript.vtt").write_text("\n".join(vtt_lines), encoding="utf-8")
    (run_dir / "transcript.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    timeline = ["# Audiovisual timeline", "", "Derived from `events.final.jsonl`.", ""]
    for record in records:
        for claim in record["claims"]:
            timeline.append(
                f"- **{_timecode(record['start_ms'])}-{_timecode(record['end_ms'])}** "
                f"{claim['text']} _[{claim['evidence_refs'][0]}]_"
            )
    (run_dir / "timeline.md").write_text("\n".join(timeline) + "\n", encoding="utf-8")
    scenes = sorted({record["scene_id"] for record in records})
    summary = ["# Ledger-derived summary", "", "No model-generated narrative is included.", ""]
    summary.extend(["## Scene summaries", ""])
    for scene_id in scenes:
        summary.extend([f"### {scene_id}", ""])
        for record in records:
            if record["scene_id"] == scene_id:
                for claim in record["claims"]:
                    summary.append(
                        f"- {claim['text']} _[{record['event_id']}; {claim['evidence_refs'][0]}]_"
                    )
        summary.append("")
    summary.extend(
        [
            "## Chapter summaries",
            "",
            f"- **CHAPTER_0001:** {len(records)} atomic events across {len(scenes)} scenes, "
            "derived from the event ledger.",
            "",
            "## Whole-source summary",
            "",
            f"- {len(records)} atomic events and "
            f"{sum(len(record['claims']) for record in records)} evidence-linked claims.",
            "",
        ]
    )
    (run_dir / "summary.md").write_text("\n".join(summary), encoding="utf-8")


def export_run(run_dir: Path) -> None:
    """Regenerate all deterministic human-readable views from the final ledger."""
    try:
        records = [
            json.loads(line)
            for line in (run_dir / "events.final.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot export invalid final ledger: {exc}") from exc
    _exports(run_dir, records)


def initialize_run(
    media: Path,
    config_path: Path,
    run_dir: Path,
    stop_after: str | None = None,
    rights_manifest: Path | None = None,
    operation: str = "analysis",
) -> None:
    config = BaselineConfig.load(config_path)
    inventory = inspect_media(media)
    enforce_media_limits(
        inventory, config.max_duration_ms, config.max_video_width, config.max_video_height
    )
    fixture_marker = controlled_fixture_manifest(media)
    if rights_manifest is None:
        if fixture_marker is None:
            raise AtlasError(
                "non-fixture media requires --rights-manifest bound to the exact source hash"
            )
        rights = fixture_rights(inventory)
    else:
        rights = load_and_validate_rights(
            rights_manifest, inventory["sha256"], inventory["source_id"], operation
        )
    validate_rights_artifact(
        rights,
        inventory["sha256"],
        inventory["source_id"],
        operation,
    )
    if run_dir.exists() and any(run_dir.iterdir()):
        raise AtlasError(f"run directory is not empty; refusing to overwrite: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    config_snapshot = run_dir / "config.snapshot.yaml"
    atomic_write_text(config_snapshot, config_path.read_text(encoding="utf-8"))
    write_json(run_dir / "rights_manifest.json", rights)
    bom_path = Path(__file__).resolve().parents[2] / "docs" / "dependency-bom.json"
    bom = _read_json(bom_path)
    validate_instance("dependency_bom", bom, bom_path.name)
    write_json(run_dir / "dependency_bom.json", bom)
    if fixture_marker is not None:
        write_json(run_dir / "fixture_manifest.json", fixture_marker)
    manifest = _manifest(run_dir, config_snapshot, inventory, rights, operation)
    write_json(run_dir / "run_manifest.json", manifest)
    write_jsonl(
        run_dir / "run.log.jsonl",
        [
            {
                "event": "run_started",
                "run_id": run_dir.name,
                "source_id": inventory["source_id"],
            }
        ],
    )
    write_json(run_dir / "inventory.json", inventory)
    write_json(run_dir / "provenance.json", _provenance(inventory, rights))
    try:
        source_path = safe_relative_path(media, run_dir)
        media.resolve().relative_to(run_dir.parent.resolve())
    except ValueError:
        source_path = "EXTERNAL_SOURCE_REQUIRED"
    write_json(
        run_dir / "state.json",
        {
            "schema_version": "1.0.0",
            "stage": "inventory",
            "source_path": source_path,
            "config_path": "config.snapshot.yaml",
        },
    )
    if stop_after == "inventory":
        return
    _complete(run_dir, media, config)


def resume_run(run_dir: Path, media_override: Path | None = None) -> None:
    state = _read_json(run_dir / "state.json")
    manifest = _read_json(run_dir / "run_manifest.json")
    validate_instance("run_manifest", manifest, "run_manifest.json")
    inventory = _read_json(run_dir / "inventory.json")
    validate_instance("inventory", inventory, "inventory.json")
    if (
        inventory["sha256"] != manifest["source"]["sha256"]
        or inventory["source_id"] != manifest["source"]["source_id"]
    ):
        raise AtlasError("run manifest source linkage does not match inventory")
    load_and_validate_rights(
        run_dir / "rights_manifest.json",
        str(manifest["source"]["sha256"]),
        str(manifest["source"]["source_id"]),
        str(manifest["operation"]),
        expected_manifest_hash=str(manifest["rights"]["manifest_hash"]),
    )
    if manifest.get("status") == "complete":
        return
    if state["source_path"] == "EXTERNAL_SOURCE_REQUIRED":
        if media_override is None:
            raise AtlasError("resume requires --media because no external source path was retained")
        media = media_override.resolve()
    else:
        media = (run_dir / str(state["source_path"])).resolve()
    config_path = (run_dir / str(state["config_path"])).resolve()
    if sha256_file(media) != manifest["source"]["sha256"]:
        raise AtlasError("source hash changed since run initialization")
    if sha256_file(config_path) != manifest["configuration"]["sha256"]:
        raise AtlasError("configuration hash changed since run initialization")
    _complete(run_dir, media, BaselineConfig.load(config_path))


def _complete(run_dir: Path, media: Path, config: BaselineConfig) -> None:
    started = time.perf_counter()
    inventory = _read_json(run_dir / "inventory.json")
    duration_ms = int(inventory["duration_ms"])
    chunk_values = [
        item.__dict__
        for item in chunks(duration_ms, config.chunk_duration_ms, config.chunk_overlap_ms)
    ]
    sample_values = uniform_samples(duration_ms, config.sample_interval_ms)
    observations: list[Observation] = []
    adapter_results: list[AdapterResult] = []
    dynamic_artifacts: list[Path] = []
    extra_evidence: dict[str, dict[str, Any]] = {}
    context = AdapterContext(media, inventory, run_dir, config)
    for name in config.adapters:
        adapter: PerceptionAdapter
        if name == "subtitle":
            adapter = SubtitleAdapter()
        elif name == "shot":
            adapter = ShotAdapter()
        elif name == "ocr_frame":
            adapter = TesseractOcrAdapter()
        else:
            adapter = SidecarAdapter(name)
        execution = adapter.run(context)
        adapter_results.append(execution.result)
        observations.extend(execution.result.observations)
        extra_evidence.update(execution.evidence)
        dynamic_artifacts.extend(execution.artifact_paths)
    observations.sort(key=lambda item: (item.start_ms, item.end_ms, item.observation_id))
    if not observations and not {"subtitle", "shot"}.intersection(config.adapters):
        raise AtlasError("no sidecar observations are available; explicit unavailable state")
    provisional, evidence = _records(
        observations,
        inventory["source_id"],
        duration_ms,
        "provisional",
        run_dir.name,
        chunk_values,
    )
    final, _ = _records(
        observations, inventory["source_id"], duration_ms, "final", run_dir.name, chunk_values
    )
    evidence["evidence"].update(extra_evidence)
    write_json(run_dir / "evidence_index.json", evidence)
    write_jsonl(run_dir / "events.provisional.jsonl", provisional)
    write_jsonl(run_dir / "events.final.jsonl", final)
    entity_records = []
    for speaker_id in sorted(
        {item.speaker_id for item in observations if item.speaker_id is not None}
    ):
        entity_records.append(
            {
                "schema_version": "1.0.0",
                "entity_id": speaker_id,
                "evidence_refs": [
                    evidence_ref(item, inventory["source_id"])
                    for item in observations
                    if item.speaker_id == speaker_id
                ],
            }
        )
    write_jsonl(run_dir / "entities.jsonl", entity_records)
    write_json(
        run_dir / "adapter_results.json",
        {
            "schema_version": "1.1.0",
            "results": [result.as_record() for result in adapter_results],
        },
    )
    _exports(run_dir, final)
    write_json(
        run_dir / "state.json",
        {
            "schema_version": "1.0.0",
            "stage": "artifacts_written",
            "source_path": _read_json(run_dir / "state.json")["source_path"],
            "config_path": _read_json(run_dir / "state.json")["config_path"],
            "chunks": chunk_values,
            "uniform_sample_timestamps_ms": sample_values,
        },
    )
    write_jsonl(
        run_dir / "run.log.jsonl",
        [
            {
                "event": "run_started",
                "run_id": run_dir.name,
                "source_id": inventory["source_id"],
            },
            {
                "event": "artifacts_written",
                "run_id": run_dir.name,
                "source_id": inventory["source_id"],
                "record_count": len(final),
            },
        ],
    )
    manifest = _read_json(run_dir / "run_manifest.json")
    manifest["status"] = "complete"
    manifest["completed_at"] = _timestamp()
    manifest["performance"] = {
        "runtime_seconds": round(time.perf_counter() - started, 6),
        "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "retry_count": 0,
        "processed_duration_ms": duration_ms,
    }
    optional_artifacts = [run_dir / "fixture_manifest.json", run_dir / "dependency_bom.json"]
    artifact_paths = [run_dir / name for name in ARTIFACTS]
    artifact_paths.extend(dynamic_artifacts)
    artifact_paths.extend(path for path in optional_artifacts if path.is_file())
    unique_paths = sorted(
        set(artifact_paths), key=lambda path: path.relative_to(run_dir).as_posix()
    )
    manifest["artifacts"] = {
        path.relative_to(run_dir).as_posix(): {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in unique_paths
    }
    write_json(run_dir / "run_manifest.json", manifest)
