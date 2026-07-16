"""Hash-bound OCR output packages for the rights-gated private pilot path.

Raw OCR observations and their evidence index remain authoritative.  This module
adds a secondary integrity envelope: a deterministic pre-receipt binding is
computed from those immutable artifacts, the OCR-complete security receipt binds
that digest, and a manifest written last binds the receipt itself.  The hashes
are integrity checksums, not authenticated signatures.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

from av_atlas.errors import AtlasError
from av_atlas.io import canonical_json, write_json_new
from av_atlas.ocr import ocr_dependency_identity_sha256
from av_atlas.schemas import validate_instance

OUTPUT_MANIFEST_FILENAME = "pilot_ocr_output_manifest.json"
COMPLETION_RECEIPT_FILENAME = "pilot_security_receipt.json"
DEPENDENCY_FILENAME = "ocr_dependency.json"
OBSERVATIONS_FILENAME = "ocr_observations.jsonl"
EVIDENCE_FILENAME = "evidence_index.json"
RUNTIME_FILENAME = "ocr_runtime.json"

OUTPUT_CONTRACT_VERSION = "av-atlas-pilot-ocr-output/1.0.0"
OUTPUT_BINDING_CONTRACT_VERSION = "av-atlas-pilot-ocr-output-binding/1.0.0"

_PACKAGE_FILES = frozenset(
    {
        OUTPUT_MANIFEST_FILENAME,
        COMPLETION_RECEIPT_FILENAME,
        DEPENDENCY_FILENAME,
        OBSERVATIONS_FILENAME,
        EVIDENCE_FILENAME,
        RUNTIME_FILENAME,
    }
)
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_OBSERVATION_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class AuthenticatedPilotOcrOutput:
    """Validated, fixed-file pilot OCR package contents."""

    manifest: dict[str, Any]
    manifest_file_sha256: str
    observations: tuple[dict[str, Any], ...]
    evidence_index: dict[str, Any]
    runtime: dict[str, Any]
    dependency: dict[str, Any]
    prepared_receipt: dict[str, Any]
    completion_receipt: dict[str, Any]


@dataclass(frozen=True)
class _BoundFile:
    data: bytes
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class _BindingInputs:
    binding: dict[str, Any]
    observations: tuple[dict[str, Any], ...]
    evidence_index: dict[str, Any]
    runtime: dict[str, Any]
    dependency: dict[str, Any]
    prepared_receipt: dict[str, Any]
    frozen_manifest: dict[str, Any]


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number {value!r} is forbidden")


def _digest(value: dict[str, Any], excluded_field: str) -> str:
    payload = {key: item for key, item in value.items() if key != excluded_field}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def output_binding_sha256(binding: dict[str, Any]) -> str:
    """Return the stable digest carried by the OCR-complete receipt."""
    return hashlib.sha256(canonical_json(binding).encode("utf-8")).hexdigest()


def canonical_observation_semantic_sha256(
    observations: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> str:
    """Hash parsed records independently of JSONL whitespace."""
    return hashlib.sha256(canonical_json(list(observations)).encode("utf-8")).hexdigest()


def _held_descriptor_reference(path: Path) -> int | None:
    """Recognize only the exact internal path used for an already-open file descriptor."""
    if path.parent != Path("/proc/self/fd") or not path.name.isdigit():
        return None
    descriptor = int(path.name)
    if descriptor < 0:
        return None
    return descriptor


def _bound_read(path: Path, *, label: str, maximum_bytes: int) -> _BoundFile:
    """Read one regular file through a no-follow descriptor and detect replacement."""
    descriptor: int | None = None
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        held_descriptor = _held_descriptor_reference(path)
        before = os.fstat(held_descriptor) if held_descriptor is not None else os.lstat(path)
        if not stat.S_ISREG(before.st_mode):
            raise AtlasError(f"{label} must be a regular non-symlink file")
        if before.st_size > maximum_bytes:
            raise AtlasError(f"{label} exceeds its bounded package size")
        descriptor = (
            os.dup(held_descriptor) if held_descriptor is not None else os.open(path, flags)
        )
        opened = os.fstat(descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        opened_identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        if opened_identity != before_identity:
            raise AtlasError(f"{label} changed while being opened")
        digest = hashlib.sha256()
        blocks: list[bytes] = []
        total = 0
        while True:
            block_size = min(1024 * 1024, maximum_bytes - total + 1)
            block = (
                os.pread(descriptor, block_size, total)
                if held_descriptor is not None
                else os.read(descriptor, block_size)
            )
            if not block:
                break
            total += len(block)
            if total > maximum_bytes:
                raise AtlasError(f"{label} exceeds its bounded package size")
            digest.update(block)
            blocks.append(block)
        after = os.fstat(descriptor)
        current = os.fstat(held_descriptor) if held_descriptor is not None else os.lstat(path)
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        current_identity = (
            current.st_dev,
            current.st_ino,
            current.st_mode,
            current.st_uid,
            current.st_size,
            current.st_mtime_ns,
            current.st_ctime_ns,
        )
        if after_identity != opened_identity or current_identity != opened_identity:
            raise AtlasError(f"{label} changed while being read")
        if total != before.st_size:
            raise AtlasError(f"{label} size changed while being read")
        return _BoundFile(b"".join(blocks), digest.hexdigest(), total)
    except FileNotFoundError as exc:
        raise AtlasError(f"required {label} is missing") from exc
    except OSError as exc:
        raise AtlasError(f"required {label} could not be read safely") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _json_object(bound: _BoundFile, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            bound.data.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise AtlasError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise AtlasError(f"{label} must contain a JSON object")
    return value


def _jsonl_objects(bound: _BoundFile) -> tuple[dict[str, Any], ...]:
    if not bound.data:
        return ()
    try:
        text = bound.data.decode("utf-8")
        lines = text.splitlines()
        if any(not line.strip() for line in lines):
            raise ValueError("blank JSONL records are forbidden")
        values = tuple(json.loads(line, parse_constant=_reject_json_constant) for line in lines)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise AtlasError("pilot OCR observations are not valid UTF-8 JSONL") from exc
    if any(not isinstance(value, dict) for value in values):
        raise AtlasError("every pilot OCR observation must be a JSON object")
    return cast(tuple[dict[str, Any], ...], values)


def _file_identity(bound: _BoundFile) -> dict[str, Any]:
    return {"sha256": bound.sha256, "size_bytes": bound.size_bytes}


def _validate_self_hash(value: dict[str, Any], field: str, label: str) -> None:
    if value.get(field) != _digest(value, field):
        raise AtlasError(f"{label} checksum mismatch")


def _reject_dependency_paths(value: Any) -> None:
    """Keep the authenticated dependency record path-free at every nesting level."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"resolved_executable_path", "license_file", "path"}:
                raise AtlasError("pilot OCR dependency output contains a private path field")
            _reject_dependency_paths(item)
    elif isinstance(value, list):
        for item in value:
            _reject_dependency_paths(item)
    elif isinstance(value, str) and (
        value.startswith(("/", "\\\\"))
        or (len(value) >= 3 and value[1:3] in {":\\", ":/"} and value[0].isalpha())
    ):
        raise AtlasError("pilot OCR dependency output contains an absolute private path")


def _validate_receipt(
    value: dict[str, Any],
    *,
    label: str,
    stage: str,
    pilot_id: str,
    policy_sha256: str,
    pilot_spec_sha256: str,
    source_rights_aggregate_sha256: str,
) -> None:
    validate_instance("pilot_security_receipt", value, label)
    _validate_self_hash(value, "receipt_hash", label)
    if value.get("stage") != stage:
        raise AtlasError(f"{label} has the wrong lifecycle stage")
    expected = {
        "pilot_id": pilot_id,
        "policy_sha256": policy_sha256,
        "pilot_spec_sha256": pilot_spec_sha256,
        "source_rights_aggregate_sha256": source_rights_aggregate_sha256,
    }
    if any(value.get(field) != expected_value for field, expected_value in expected.items()):
        raise AtlasError(f"{label} is linked to another pilot, policy, or rights set")


def _validate_package_directory(package_dir: Path, *, expected: frozenset[str]) -> None:
    try:
        descriptor_root = package_dir.parent == Path("/proc/self/fd") and package_dir.name.isdigit()
        measured = os.stat(package_dir) if descriptor_root else os.lstat(package_dir)
    except OSError as exc:
        raise AtlasError("pilot OCR output package directory is unavailable") from exc
    if not stat.S_ISDIR(measured.st_mode):
        raise AtlasError("pilot OCR output package must be a regular non-symlink directory")
    try:
        names = {entry.name for entry in os.scandir(package_dir)}
    except OSError as exc:
        raise AtlasError("pilot OCR output package could not be inventoried") from exc
    if names != expected:
        missing = sorted(expected - names)
        unexpected = sorted(names - expected)
        detail = []
        if missing:
            detail.append(f"missing={','.join(missing)}")
        if unexpected:
            detail.append(f"unexpected={','.join(unexpected)}")
        raise AtlasError(f"pilot OCR output package file set mismatch ({'; '.join(detail)})")


def _artifact_record(path: str, bound: _BoundFile, schema_version: str) -> dict[str, Any]:
    return {
        "path": path,
        **_file_identity(bound),
        "schema_version": schema_version,
    }


def _load_binding_inputs(
    package_dir: Path,
    *,
    frozen_manifest_path: Path,
    prepared_receipt_path: Path,
    policy_sha256: str,
    source_rights_aggregate_sha256: str,
    ocr_configuration_sha256: str,
    ocr_configuration_size_bytes: int,
    expected_files: frozenset[str],
) -> _BindingInputs:
    _validate_package_directory(package_dir, expected=expected_files)

    frozen_file = _bound_read(
        frozen_manifest_path,
        label="frozen pilot manifest",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    frozen = _json_object(frozen_file, "frozen pilot manifest")
    validate_instance("ocr_pilot_manifest", frozen, "frozen pilot manifest")
    _validate_self_hash(frozen, "manifest_hash", "frozen pilot manifest")
    if frozen.get("schema_version") != "1.2.0" or frozen.get("state") != "adjudicated_frozen":
        raise AtlasError("pilot OCR output requires the current adjudicated frozen manifest")
    security = frozen.get("pilot_security")
    if not isinstance(security, dict):
        raise AtlasError("frozen pilot manifest lacks its security linkage")
    pilot_id = str(frozen["pilot_id"])
    if security.get("policy_sha256") != policy_sha256:
        raise AtlasError("frozen pilot manifest is linked to another security policy")
    if security.get("source_rights_aggregate_sha256") != source_rights_aggregate_sha256:
        raise AtlasError("frozen pilot manifest is linked to another source-rights set")
    if frozen.get("ocr_configuration_sha256") != ocr_configuration_sha256:
        raise AtlasError("frozen pilot manifest is linked to another OCR configuration")
    if ocr_configuration_size_bytes < 1:
        raise AtlasError("OCR configuration size must be a positive exact byte count")

    if prepared_receipt_path.name != COMPLETION_RECEIPT_FILENAME:
        raise AtlasError("prepared security receipt must use its fixed package filename")
    prepared_file = _bound_read(
        prepared_receipt_path,
        label="prepared pilot security receipt",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    prepared = _json_object(prepared_file, "prepared pilot security receipt")
    _validate_receipt(
        prepared,
        label="prepared pilot security receipt",
        stage="prepared",
        pilot_id=pilot_id,
        policy_sha256=policy_sha256,
        pilot_spec_sha256=str(security["pilot_spec_sha256"]),
        source_rights_aggregate_sha256=source_rights_aggregate_sha256,
    )
    if (
        prepared_file.sha256 != security.get("receipt_sha256")
        or prepared.get("receipt_hash") is None
        or prepared.get("pilot_spec_size_bytes") != security.get("pilot_spec_size_bytes")
    ):
        raise AtlasError("prepared security receipt differs from its frozen linkage")
    retained_storage = prepared.get("retained_storage")
    if not isinstance(retained_storage, dict):
        raise AtlasError("prepared security receipt lacks retained-storage identity")

    dependency_file = _bound_read(
        package_dir / DEPENDENCY_FILENAME,
        label="sanitized OCR dependency inventory",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    dependency = _json_object(dependency_file, "sanitized OCR dependency inventory")
    validate_instance("ocr_dependency", dependency, "sanitized OCR dependency inventory")
    dependency_identity = dependency.get("dependency_identity_sha256")
    if (
        dependency.get("schema_version") != "1.1.0"
        or dependency.get("state") != "available"
        or not isinstance(dependency_identity, str)
    ):
        raise AtlasError("pilot OCR output requires an available sanitized dependency identity")
    if dependency_identity != ocr_dependency_identity_sha256(dependency):
        raise AtlasError("sanitized OCR dependency identity checksum mismatch")
    _reject_dependency_paths(dependency)
    language_hashes = {
        str(item["language"]): str(item["sha256"])
        for item in dependency["language_data"]
        if isinstance(item, dict) and "language" in item and "sha256" in item
    }

    observations_file = _bound_read(
        package_dir / OBSERVATIONS_FILENAME,
        label="pilot OCR observations",
        maximum_bytes=_MAX_OBSERVATION_BYTES,
    )
    observations = _jsonl_objects(observations_file)
    for index, observation in enumerate(observations):
        validate_instance(
            "pilot_ocr_observation",
            observation,
            f"pilot OCR observation {index}",
        )
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                str(item["source_id"]),
                int(item["timestamp_ms"]),
                tuple(int(value) for value in item["bounding_box"]),
                str(item["observation_id"]),
            ),
        )
    )
    if observations != ordered:
        raise AtlasError("pilot OCR observations are not deterministically ordered")
    observation_ids = [str(item["observation_id"]) for item in observations]
    if len(observation_ids) != len(set(observation_ids)):
        raise AtlasError("pilot OCR observation IDs are not unique")

    evidence_file = _bound_read(
        package_dir / EVIDENCE_FILENAME,
        label="pilot OCR evidence index",
        maximum_bytes=_MAX_OBSERVATION_BYTES,
    )
    evidence_index = _json_object(evidence_file, "pilot OCR evidence index")
    validate_instance("evidence_index", evidence_index, "pilot OCR evidence index")

    runtime_file = _bound_read(
        package_dir / RUNTIME_FILENAME,
        label="pilot OCR runtime",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    runtime = _json_object(runtime_file, "pilot OCR runtime")
    validate_instance("ocr_runtime", runtime, "pilot OCR runtime")

    evaluation_frames = {
        str(frame["frame_id"]): frame
        for frame in frozen["frames"]
        if frame["split"] == "evaluation"
    }
    source_durations: dict[str, int] = {}
    for source in frozen["sources"]:
        source_id = source.get("source_id")
        duration_ms = source.get("duration_ms")
        if (
            not isinstance(source_id, str)
            or not isinstance(duration_ms, int)
            or isinstance(duration_ms, bool)
            or duration_ms < 1
            or source_id in source_durations
        ):
            raise AtlasError("frozen pilot source duration identity is malformed")
        source_durations[source_id] = duration_ms
    for observation in observations:
        frame = evaluation_frames.get(str(observation["keyframe_id"]))
        if frame is None:
            raise AtlasError("pilot OCR observation refers to a non-evaluation frame")
        if (
            observation["source_id"] != frame["source_id"]
            or observation["timestamp_ms"] != frame["timestamp_ms"]
        ):
            raise AtlasError("pilot OCR observation source or timestamp differs from its frame")
        expected_source_frame_ref = (
            f"VID:{observation['source_id']}:frame:{observation['timestamp_ms']}"
        )
        if observation["source_frame_evidence_ref"] != expected_source_frame_ref:
            raise AtlasError("pilot OCR observation has the wrong source-frame evidence reference")
        languages = str(observation["language"]).split("+")
        if any(language not in language_hashes for language in languages):
            raise AtlasError("pilot OCR observation uses unavailable language data")
        expected_language_identity = "+".join(
            f"{language}:sha256:{language_hashes[language]}" for language in languages
        )
        if (
            observation["engine"] != dependency["engine"]
            or observation["engine_version"] != dependency["version"]
            or observation["language_data_identity"] != expected_language_identity
        ):
            raise AtlasError("pilot OCR observation differs from its dependency identity")

    evidence = evidence_index["evidence"]
    expected_video_refs: dict[str, dict[str, Any]] = {}
    for frame in evaluation_frames.values():
        reference = f"VID:{frame['source_id']}:frame:{frame['timestamp_ms']}"
        if reference in expected_video_refs:
            raise AtlasError("frozen evaluation frames have a duplicate source-frame reference")
        expected_video_refs[reference] = frame
    expected_ocr_refs = {str(item["evidence_ref"]): item for item in observations}
    if set(evidence) != set(expected_video_refs) | set(expected_ocr_refs):
        raise AtlasError("pilot OCR evidence index is not the complete derived evidence set")
    for reference, frame in expected_video_refs.items():
        item = evidence[reference]
        expected_end_ms = min(
            int(frame["timestamp_ms"]) + 1,
            source_durations[str(frame["source_id"])],
        )
        if (
            item.get("evidence_ref") != reference
            or item.get("source_id") != frame["source_id"]
            or item.get("observation_id") != frame["frame_id"]
            or item.get("modality") != "VID"
            or item.get("start_ms") != frame["timestamp_ms"]
            or item.get("end_ms") != expected_end_ms
        ):
            raise AtlasError("pilot source-frame evidence differs from its frozen frame")
    for reference, observation in expected_ocr_refs.items():
        item = evidence[reference]
        expected_end_ms = min(
            int(observation["timestamp_ms"]) + 1,
            source_durations[str(observation["source_id"])],
        )
        if (
            observation["source_frame_evidence_ref"] not in expected_video_refs
            or item.get("evidence_ref") != reference
            or item.get("source_id") != observation["source_id"]
            or item.get("observation_id") != observation["observation_id"]
            or item.get("modality") != "OCR"
            or item.get("start_ms") != observation["timestamp_ms"]
            or item.get("end_ms") != expected_end_ms
        ):
            raise AtlasError("pilot OCR evidence differs from its immutable observation")

    if runtime.get("frames_processed") != len(evaluation_frames) or runtime.get(
        "observation_count"
    ) != len(observations):
        raise AtlasError("pilot OCR runtime counts differ from the authenticated output")

    binding = {
        "contract_version": OUTPUT_BINDING_CONTRACT_VERSION,
        "pilot_id": pilot_id,
        "pilot_spec_sha256": security["pilot_spec_sha256"],
        "pilot_spec_size_bytes": security["pilot_spec_size_bytes"],
        "frozen_manifest": {
            **_file_identity(frozen_file),
            "embedded_manifest_hash": frozen["manifest_hash"],
        },
        "policy_sha256": policy_sha256,
        "prepared_receipt": {
            "path": COMPLETION_RECEIPT_FILENAME,
            **_file_identity(prepared_file),
            "embedded_receipt_hash": prepared["receipt_hash"],
            "stage": "prepared",
        },
        "source_set_sha256": security["source_set_sha256"],
        "source_rights_aggregate_sha256": source_rights_aggregate_sha256,
        "ocr_configuration_sha256": ocr_configuration_sha256,
        "ocr_configuration_size_bytes": ocr_configuration_size_bytes,
        "retained_storage": {
            field: retained_storage[field]
            for field in (
                "decision",
                "root_identity_sha256",
                "filesystem_type",
                "byte_ceiling",
                "reserve_bytes",
            )
        },
        "ocr_dependency_identity_sha256": dependency_identity,
        "artifacts": {
            "dependency": _artifact_record(
                DEPENDENCY_FILENAME,
                dependency_file,
                str(dependency["schema_version"]),
            ),
            "observations": _artifact_record(
                OBSERVATIONS_FILENAME,
                observations_file,
                "1.0.0",
            ),
            "evidence_index": _artifact_record(
                EVIDENCE_FILENAME,
                evidence_file,
                str(evidence_index["schema_version"]),
            ),
            "runtime": _artifact_record(
                RUNTIME_FILENAME,
                runtime_file,
                str(runtime["schema_version"]),
            ),
        },
        "counts": {
            "frames": len(evaluation_frames),
            "observations": len(observations),
            "evidence_entries": len(evidence),
            "source_frame_evidence_entries": len(expected_video_refs),
            "ocr_evidence_entries": len(expected_ocr_refs),
        },
        "semantic_output_sha256": canonical_observation_semantic_sha256(observations),
    }
    return _BindingInputs(
        binding=binding,
        observations=observations,
        evidence_index=evidence_index,
        runtime=runtime,
        dependency=dependency,
        prepared_receipt=prepared,
        frozen_manifest=frozen,
    )


def build_pilot_ocr_output_binding(
    package_dir: Path,
    *,
    frozen_manifest_path: Path,
    prepared_receipt_path: Path,
    policy_sha256: str,
    source_rights_aggregate_sha256: str,
    ocr_configuration_sha256: str,
    ocr_configuration_size_bytes: int,
) -> dict[str, Any]:
    """Build the deterministic payload digest input before the completion receipt exists."""
    return _load_binding_inputs(
        package_dir,
        frozen_manifest_path=frozen_manifest_path,
        prepared_receipt_path=prepared_receipt_path,
        policy_sha256=policy_sha256,
        source_rights_aggregate_sha256=source_rights_aggregate_sha256,
        ocr_configuration_sha256=ocr_configuration_sha256,
        ocr_configuration_size_bytes=ocr_configuration_size_bytes,
        expected_files=_PACKAGE_FILES - {OUTPUT_MANIFEST_FILENAME, COMPLETION_RECEIPT_FILENAME},
    ).binding


def _manifest_from_inputs(
    package_dir: Path,
    *,
    inputs: _BindingInputs,
    policy_sha256: str,
    source_rights_aggregate_sha256: str,
) -> dict[str, Any]:
    binding_sha256 = output_binding_sha256(inputs.binding)
    completion_file = _bound_read(
        package_dir / COMPLETION_RECEIPT_FILENAME,
        label="OCR-complete pilot security receipt",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    completion = _json_object(completion_file, "OCR-complete pilot security receipt")
    security = inputs.frozen_manifest["pilot_security"]
    _validate_receipt(
        completion,
        label="OCR-complete pilot security receipt",
        stage="ocr-complete",
        pilot_id=str(inputs.frozen_manifest["pilot_id"]),
        policy_sha256=policy_sha256,
        pilot_spec_sha256=str(security["pilot_spec_sha256"]),
        source_rights_aggregate_sha256=source_rights_aggregate_sha256,
    )
    if completion.get("output_binding_sha256") != binding_sha256:
        raise AtlasError("OCR-complete receipt does not authenticate this output binding")
    prepared = inputs.prepared_receipt
    for field in (
        "pilot_spec_size_bytes",
        "root_identity_sha256",
        "filesystem_type",
        "resource_limits",
    ):
        if completion.get(field) != prepared.get(field):
            raise AtlasError("OCR-complete receipt differs from the prepared security boundary")
    for field in ("profile_contract_version", "profile_sha256", "dependency_identity_sha256"):
        if completion["sandbox"].get(field) != prepared["sandbox"].get(field):
            raise AtlasError("OCR-complete receipt uses another sandbox identity")
    completion_retained = completion.get("retained_storage")
    if not isinstance(completion_retained, dict) or any(
        completion_retained.get(field) != inputs.binding["retained_storage"][field]
        for field in (
            "decision",
            "root_identity_sha256",
            "filesystem_type",
            "byte_ceiling",
            "reserve_bytes",
        )
    ):
        raise AtlasError("OCR-complete receipt uses another retained-storage identity")
    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "state": "complete",
        "pilot_id": inputs.binding["pilot_id"],
        "output_binding": inputs.binding,
        "output_binding_sha256": binding_sha256,
        "completion_receipt": {
            "path": COMPLETION_RECEIPT_FILENAME,
            **_file_identity(completion_file),
            "embedded_receipt_hash": completion["receipt_hash"],
            "stage": "ocr-complete",
            "output_binding_sha256": binding_sha256,
        },
        "manifest_hash": "",
    }
    manifest["manifest_hash"] = _digest(manifest, "manifest_hash")
    validate_instance("pilot_ocr_output_manifest", manifest, "pilot OCR output manifest")
    return manifest


def build_pilot_ocr_output_manifest(
    package_dir: Path,
    *,
    frozen_manifest_path: Path,
    prepared_receipt_path: Path,
    policy_sha256: str,
    source_rights_aggregate_sha256: str,
    ocr_configuration_sha256: str,
    ocr_configuration_size_bytes: int,
) -> dict[str, Any]:
    """Build a final manifest after the output-bound OCR-complete receipt is present."""
    inputs = _load_binding_inputs(
        package_dir,
        frozen_manifest_path=frozen_manifest_path,
        prepared_receipt_path=prepared_receipt_path,
        policy_sha256=policy_sha256,
        source_rights_aggregate_sha256=source_rights_aggregate_sha256,
        ocr_configuration_sha256=ocr_configuration_sha256,
        ocr_configuration_size_bytes=ocr_configuration_size_bytes,
        expected_files=_PACKAGE_FILES - {OUTPUT_MANIFEST_FILENAME},
    )
    return _manifest_from_inputs(
        package_dir,
        inputs=inputs,
        policy_sha256=policy_sha256,
        source_rights_aggregate_sha256=source_rights_aggregate_sha256,
    )


def write_pilot_ocr_output_manifest(
    package_dir: Path,
    *,
    frozen_manifest_path: Path,
    prepared_receipt_path: Path,
    policy_sha256: str,
    source_rights_aggregate_sha256: str,
    ocr_configuration_sha256: str,
    ocr_configuration_size_bytes: int,
) -> dict[str, Any]:
    """Write the manifest last without replacing an existing completion claim."""
    try:
        os.lstat(package_dir / OUTPUT_MANIFEST_FILENAME)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise AtlasError("pilot OCR output manifest path could not be checked safely") from exc
    else:
        raise AtlasError("refusing to replace the pilot OCR output manifest")
    manifest = build_pilot_ocr_output_manifest(
        package_dir,
        frozen_manifest_path=frozen_manifest_path,
        prepared_receipt_path=prepared_receipt_path,
        policy_sha256=policy_sha256,
        source_rights_aggregate_sha256=source_rights_aggregate_sha256,
        ocr_configuration_sha256=ocr_configuration_sha256,
        ocr_configuration_size_bytes=ocr_configuration_size_bytes,
    )
    try:
        write_json_new(package_dir / OUTPUT_MANIFEST_FILENAME, manifest)
    except OSError as exc:
        raise AtlasError("refusing to replace the pilot OCR output manifest") from exc
    return manifest


def validate_pilot_ocr_output_package(
    package_dir: Path,
    *,
    frozen_manifest_path: Path,
    prepared_receipt_path: Path,
    policy_sha256: str,
    source_rights_aggregate_sha256: str,
    ocr_configuration_sha256: str,
    ocr_configuration_size_bytes: int,
) -> AuthenticatedPilotOcrOutput:
    """Recompute and verify every package relationship before evaluation."""
    manifest_file = _bound_read(
        package_dir / OUTPUT_MANIFEST_FILENAME,
        label="pilot OCR output manifest",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    manifest = _json_object(manifest_file, "pilot OCR output manifest")
    validate_instance("pilot_ocr_output_manifest", manifest, "pilot OCR output manifest")
    _validate_self_hash(manifest, "manifest_hash", "pilot OCR output manifest")

    inputs = _load_binding_inputs(
        package_dir,
        frozen_manifest_path=frozen_manifest_path,
        prepared_receipt_path=prepared_receipt_path,
        policy_sha256=policy_sha256,
        source_rights_aggregate_sha256=source_rights_aggregate_sha256,
        ocr_configuration_sha256=ocr_configuration_sha256,
        ocr_configuration_size_bytes=ocr_configuration_size_bytes,
        expected_files=_PACKAGE_FILES,
    )
    expected = _manifest_from_inputs(
        package_dir,
        inputs=inputs,
        policy_sha256=policy_sha256,
        source_rights_aggregate_sha256=source_rights_aggregate_sha256,
    )
    if manifest != expected:
        raise AtlasError("pilot OCR output manifest differs from deterministic recomputation")
    completion_file = _bound_read(
        package_dir / COMPLETION_RECEIPT_FILENAME,
        label="OCR-complete pilot security receipt",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    completion = _json_object(completion_file, "OCR-complete pilot security receipt")
    return AuthenticatedPilotOcrOutput(
        manifest=manifest,
        manifest_file_sha256=manifest_file.sha256,
        observations=inputs.observations,
        evidence_index=inputs.evidence_index,
        runtime=inputs.runtime,
        dependency=inputs.dependency,
        prepared_receipt=inputs.prepared_receipt,
        completion_receipt=completion,
    )
