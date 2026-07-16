from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from av_atlas.errors import AtlasError
from av_atlas.io import canonical_json, sha256_file, write_json, write_jsonl
from av_atlas.ocr import ocr_dependency_identity_sha256
from av_atlas.pilot_ocr_output import (
    COMPLETION_RECEIPT_FILENAME,
    DEPENDENCY_FILENAME,
    EVIDENCE_FILENAME,
    OBSERVATIONS_FILENAME,
    OUTPUT_MANIFEST_FILENAME,
    RUNTIME_FILENAME,
    build_pilot_ocr_output_binding,
    canonical_observation_semantic_sha256,
    output_binding_sha256,
    validate_pilot_ocr_output_package,
    write_pilot_ocr_output_manifest,
)
from av_atlas.schemas import validate_instance as real_validate_instance

POLICY_SHA256 = "1" * 64
RIGHTS_SHA256 = "2" * 64
CONFIG_PATH = Path(__file__).parents[2] / "configs/m2b.yaml"
CONFIG_SHA256 = sha256_file(CONFIG_PATH)
CONFIG_SIZE = CONFIG_PATH.stat().st_size
PILOT_SPEC_SHA256 = "4" * 64
SOURCE_SET_SHA256 = "5" * 64
ROOT_SHA256 = "6" * 64
PROFILE_SHA256 = "7" * 64
SANDBOX_DEPENDENCY_SHA256 = "8" * 64


def _retained_storage_binding() -> dict[str, Any]:
    return {
        "decision": "reviewed-remanence-acceptance",
        "root_identity_sha256": "c" * 64,
        "filesystem_type": "ext4",
        "byte_ceiling": 10_000_000,
        "reserve_bytes": 1_000_000,
    }


def _digest(value: dict[str, Any], excluded: str) -> str:
    import hashlib

    payload = {key: item for key, item in value.items() if key != excluded}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _receipt(pilot_id: str, stage: str, binding_sha256: str | None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "1.1.0",
        "contract_version": "av-atlas-pilot-security-receipt/1.1.0",
        "stage": stage,
        "pilot_id": pilot_id,
        "pilot_spec_sha256": PILOT_SPEC_SHA256,
        "pilot_spec_size_bytes": 1024,
        "policy_sha256": POLICY_SHA256,
        "source_rights_aggregate_sha256": RIGHTS_SHA256,
        "output_binding_sha256": binding_sha256,
        "root_identity_sha256": ROOT_SHA256,
        "filesystem_type": "ext4",
        "resource_limits": {"wall_timeout_seconds": 30},
        "retained_storage": _retained_storage_binding(),
        "sandbox": {
            "profile_contract_version": "av-atlas-bubblewrap-pilot/1.1.0",
            "profile_sha256": PROFILE_SHA256,
            "dependency_identity_sha256": SANDBOX_DEPENDENCY_SHA256,
        },
        "receipt_hash": "",
    }
    value["receipt_hash"] = _digest(value, "receipt_hash")
    return value


def _observation(pilot_suffix: str, *, text: str) -> dict[str, Any]:
    source_id = f"SRC_{pilot_suffix}"
    observation_id = f"OCR_{pilot_suffix}_0001_0001"
    return {
        "schema_version": "1.0.0",
        "observation_id": observation_id,
        "source_id": source_id,
        "shot_id": "SHOT_0001",
        "keyframe_id": f"FRM_{pilot_suffix}_0000001000",
        "timestamp_ms": 1000,
        "text": text,
        "normalized_text": text.lower(),
        "bounding_box": [10, 20, 200, 60],
        "confidence": 95.0,
        "language": "eng",
        "engine": "tesseract",
        "engine_version": "tesseract 5.3.0",
        "language_data_identity": "eng:sha256:" + "a" * 64,
        "preprocessing": {},
        "source_frame_evidence_ref": f"VID:{source_id}:frame:1000",
        "adapter_state": "succeeded",
        "warnings": [],
        "evidence_ref": f"OCR:{observation_id}",
    }


def _dependency() -> dict[str, Any]:
    value = {
        "schema_version": "1.1.0",
        "state": "available",
        "engine": "tesseract",
        "network_accessed": False,
        "executable_sha256": "b" * 64,
        "version": "tesseract 5.3.0",
        "leptonica_version": "1.82.0",
        "available_languages": ["eng"],
        "language_data": [{"language": "eng", "sha256": "a" * 64}],
    }
    value["dependency_identity_sha256"] = ocr_dependency_identity_sha256(value)
    return value


def _runtime(frames: int = 1) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "workers": 1,
        "frames_processed": frames,
        "observation_count": 1,
        "wall_seconds": 0.1,
        "cpu_seconds": 0.1,
        "peak_rss_kb": 1024,
        "frames_per_second": 10.0,
        "failures": 0,
        "timeouts": 0,
        "retries": 0,
        "memory_scope": "maximum resident set of parent or one child",
        "thread_limit_per_tesseract_process": 1,
        "temporary_files_retained": False,
    }


def _selective_schema_validation(name: str, value: Any, label: str) -> None:
    # The package layer is tested independently of the evolving pilot-policy and
    # frozen-pilot schemas; their real contracts have separate contract tests.
    if name in {"ocr_pilot_manifest", "pilot_security_receipt"}:
        return
    real_validate_instance(name, value, label)


def _make_package(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    pilot_id: str = "PILOT_OUTPUT_A",
    suffix: str = "ABCDEF012345",
    text: str = "Synthetic text",
    frame_count: int = 1,
) -> dict[str, Path]:
    from av_atlas import pilot_ocr_output

    monkeypatch.setattr(
        pilot_ocr_output,
        "validate_instance",
        _selective_schema_validation,
    )
    root.mkdir(parents=True)
    package = root / "ocr-output"
    package.mkdir()
    prepared_dir = root / "prepared"
    prepared_dir.mkdir()
    prepared_path = prepared_dir / COMPLETION_RECEIPT_FILENAME
    prepared = _receipt(pilot_id, "prepared", None)
    write_json(prepared_path, prepared)
    frozen_path = root / "frozen.json"
    frames = [
        {
            "frame_id": f"FRM_{suffix}_{1000 + index * 1000:010d}",
            "source_id": f"SRC_{suffix}",
            "timestamp_ms": 1000 + index * 1000,
            "split": "evaluation",
            "categories": ["synthetic"],
            "difficulty": ["controlled"],
        }
        for index in range(frame_count)
    ]
    frame_id = str(frames[0]["frame_id"])
    gold_path = root / "adjudicated.json"
    gold_frames = []
    for index, frame in enumerate(frames):
        has_text = index == 0
        gold_frames.append(
            {
                "frame_id": frame["frame_id"],
                "source_id": frame["source_id"],
                "timestamp_ms": frame["timestamp_ms"],
                "exact_transcription": text if has_text else "",
                "normalized_transcription": text.lower() if has_text else "",
                "regions": (
                    [
                        {
                            "exact_transcription": text,
                            "normalized_transcription": text.lower(),
                            "geometry": {"bounding_box": [10, 20, 190, 40]},
                            "reading_order": 0,
                            "language": "eng",
                            "legibility": "legible",
                            "uncertain": False,
                            "occluded": False,
                            "truncated": False,
                            "notes": "synthetic test annotation",
                        }
                    ]
                    if has_text
                    else []
                ),
                "ignore_regions": [],
                "language": "eng" if has_text else None,
                "legibility": "legible" if has_text else None,
                "uncertain": False if has_text else None,
                "occluded": False if has_text else None,
                "truncated": False if has_text else None,
                "notes": "synthetic evaluator test",
            }
        )
    write_json(
        gold_path,
        {
            "schema_version": "1.0.0",
            "pilot_id": pilot_id,
            "annotator_pseudonym": "ADJUDICATOR_TEST",
            "annotation_timestamp": "2026-07-16T12:00:00+00:00",
            "independence_attestation": True,
            "frames": gold_frames,
        },
    )
    frozen: dict[str, Any] = {
        "schema_version": "1.2.0",
        "pilot_id": pilot_id,
        "state": "adjudicated_frozen",
        "ocr_configuration_sha256": CONFIG_SHA256,
        "sources": [{"source_id": f"SRC_{suffix}", "duration_ms": 100_000}],
        "frames": frames,
        "adjudicated_gold_sha256": sha256_file(gold_path),
        "pilot_security": {
            "policy_sha256": POLICY_SHA256,
            "receipt_sha256": sha256_file(prepared_path),
            "pilot_spec_sha256": PILOT_SPEC_SHA256,
            "pilot_spec_size_bytes": 1024,
            "source_set_sha256": SOURCE_SET_SHA256,
            "source_rights_aggregate_sha256": RIGHTS_SHA256,
        },
        "manifest_hash": "",
    }
    frozen["manifest_hash"] = _digest(frozen, "manifest_hash")
    write_json(frozen_path, frozen)

    observation = _observation(suffix, text=text)
    write_jsonl(package / OBSERVATIONS_FILENAME, [observation])
    video_ref = observation["source_frame_evidence_ref"]
    ocr_ref = observation["evidence_ref"]
    write_json(
        package / EVIDENCE_FILENAME,
        {
            "schema_version": "1.0.0",
            "evidence": {
                video_ref: {
                    "evidence_ref": video_ref,
                    "source_id": observation["source_id"],
                    "observation_id": frame_id,
                    "modality": "VID",
                    "start_ms": 1000,
                    "end_ms": 1001,
                },
                ocr_ref: {
                    "evidence_ref": ocr_ref,
                    "source_id": observation["source_id"],
                    "observation_id": observation["observation_id"],
                    "modality": "OCR",
                    "start_ms": 1000,
                    "end_ms": 1001,
                },
            },
        },
    )
    for frame in frames[1:]:
        video_ref = f"VID:{frame['source_id']}:frame:{frame['timestamp_ms']}"
        evidence_value = json.loads((package / EVIDENCE_FILENAME).read_text(encoding="utf-8"))
        evidence_value["evidence"][video_ref] = {
            "evidence_ref": video_ref,
            "source_id": frame["source_id"],
            "observation_id": frame["frame_id"],
            "modality": "VID",
            "start_ms": frame["timestamp_ms"],
            "end_ms": frame["timestamp_ms"] + 1,
        }
        write_json(package / EVIDENCE_FILENAME, evidence_value)
    write_json(package / RUNTIME_FILENAME, _runtime(frame_count))
    write_json(package / DEPENDENCY_FILENAME, _dependency())
    arguments = {
        "frozen_manifest_path": frozen_path,
        "prepared_receipt_path": prepared_path,
        "policy_sha256": POLICY_SHA256,
        "source_rights_aggregate_sha256": RIGHTS_SHA256,
        "ocr_configuration_sha256": CONFIG_SHA256,
        "ocr_configuration_size_bytes": CONFIG_SIZE,
    }
    binding = build_pilot_ocr_output_binding(package, **arguments)
    write_json(
        package / COMPLETION_RECEIPT_FILENAME,
        _receipt(pilot_id, "ocr-complete", output_binding_sha256(binding)),
    )
    write_pilot_ocr_output_manifest(package, **arguments)
    return {
        "root": root,
        "pilot": prepared_dir,
        "package": package,
        "frozen": frozen_path,
        "prepared": prepared_path,
        "gold": gold_path,
    }


def _arguments(paths: dict[str, Path], **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "frozen_manifest_path": paths["frozen"],
        "prepared_receipt_path": paths["prepared"],
        "policy_sha256": POLICY_SHA256,
        "source_rights_aggregate_sha256": RIGHTS_SHA256,
        "ocr_configuration_sha256": CONFIG_SHA256,
        "ocr_configuration_size_bytes": CONFIG_SIZE,
        "expected_retained_storage": _retained_storage_binding(),
    }
    values.update(overrides)
    return values


def _builder_arguments(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        key: item for key, item in _arguments(paths).items() if key != "expected_retained_storage"
    }


def _rebuild_with_false_retained_storage(
    paths: dict[str, Path], field: str, value: object
) -> dict[str, Any]:
    false_binding = _retained_storage_binding()
    false_binding[field] = value
    prepared = json.loads(paths["prepared"].read_text(encoding="utf-8"))
    prepared["retained_storage"] = false_binding
    prepared["receipt_hash"] = _digest(prepared, "receipt_hash")
    write_json(paths["prepared"], prepared)

    frozen = json.loads(paths["frozen"].read_text(encoding="utf-8"))
    frozen["pilot_security"]["receipt_sha256"] = sha256_file(paths["prepared"])
    frozen["pilot_security"]["retained_storage"] = false_binding
    frozen["manifest_hash"] = _digest(frozen, "manifest_hash")
    write_json(paths["frozen"], frozen)

    package = paths["package"]
    (package / OUTPUT_MANIFEST_FILENAME).unlink()
    (package / COMPLETION_RECEIPT_FILENAME).unlink()
    build_arguments = _builder_arguments(paths)
    binding = build_pilot_ocr_output_binding(package, **build_arguments)
    completion = _receipt(
        str(frozen["pilot_id"]),
        "ocr-complete",
        output_binding_sha256(binding),
    )
    completion["retained_storage"] = false_binding
    completion["receipt_hash"] = _digest(completion, "receipt_hash")
    write_json(package / COMPLETION_RECEIPT_FILENAME, completion)
    write_pilot_ocr_output_manifest(package, **build_arguments)
    return false_binding


def test_valid_authenticated_pilot_ocr_output_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _make_package(tmp_path / "a", monkeypatch)
    output = validate_pilot_ocr_output_package(paths["package"], **_arguments(paths))

    assert output.manifest["state"] == "complete"
    assert output.manifest["output_binding"]["counts"] == {
        "frames": 1,
        "observations": 1,
        "evidence_entries": 2,
        "source_frame_evidence_entries": 1,
        "ocr_evidence_entries": 1,
    }
    assert output.completion_receipt["stage"] == "ocr-complete"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("root_identity_sha256", "d" * 64),
        ("filesystem_type", "xfs"),
        ("byte_ceiling", 9_999_999),
        ("reserve_bytes", 999_999),
        ("decision", "reviewed-encrypted-volume"),
    ),
)
def test_output_validation_rejects_self_consistent_false_retained_storage_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    paths = _make_package(tmp_path / field, monkeypatch)
    false_binding = _rebuild_with_false_retained_storage(paths, field, value)

    # The altered receipt, frozen manifest, completion receipt, and output manifest
    # are all internally checksum-consistent; only the trusted current boundary
    # distinguishes the false claim.
    assert (
        validate_pilot_ocr_output_package(
            paths["package"],
            **_arguments(paths, expected_retained_storage=false_binding),
        ).manifest["state"]
        == "complete"
    )
    with pytest.raises(AtlasError, match="current retained-storage boundary"):
        validate_pilot_ocr_output_package(paths["package"], **_arguments(paths))


def test_authenticated_output_accepts_an_already_held_frozen_manifest_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _make_package(tmp_path / "a", monkeypatch)
    descriptor = os.open(paths["frozen"], os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.lseek(descriptor, 0, os.SEEK_END)
        output = validate_pilot_ocr_output_package(
            paths["package"],
            **_arguments(
                paths,
                frozen_manifest_path=Path(f"/proc/self/fd/{descriptor}"),
            ),
        )
    finally:
        os.close(descriptor)

    assert output.manifest["state"] == "complete"


@pytest.mark.parametrize(
    ("filename", "mutation"),
    (
        (OBSERVATIONS_FILENAME, lambda path: path.write_text("", encoding="utf-8")),
        (RUNTIME_FILENAME, lambda path: path.write_text("{}\n", encoding="utf-8")),
        (EVIDENCE_FILENAME, lambda path: path.write_text("{}\n", encoding="utf-8")),
    ),
)
def test_modified_output_artifact_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    mutation: Callable[[Path], object],
) -> None:
    paths = _make_package(tmp_path / "a", monkeypatch)
    mutation(paths["package"] / filename)

    with pytest.raises(AtlasError):
        validate_pilot_ocr_output_package(paths["package"], **_arguments(paths))


@pytest.mark.parametrize("filename", (OBSERVATIONS_FILENAME, RUNTIME_FILENAME, EVIDENCE_FILENAME))
def test_swapped_output_artifact_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
) -> None:
    first = _make_package(tmp_path / "a", monkeypatch, text="First output")
    second = _make_package(
        tmp_path / "b",
        monkeypatch,
        pilot_id="PILOT_OUTPUT_B",
        suffix="123456ABCDEF",
        text="Second output",
    )
    if filename == RUNTIME_FILENAME:
        runtime_path = second["package"] / RUNTIME_FILENAME
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["wall_seconds"] = 0.2
        write_json(runtime_path, runtime)
    shutil.copyfile(second["package"] / filename, first["package"] / filename)

    with pytest.raises(AtlasError):
        validate_pilot_ocr_output_package(first["package"], **_arguments(first))


def test_missing_or_wrong_completion_receipt_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _make_package(tmp_path / "missing", monkeypatch)
    (paths["package"] / COMPLETION_RECEIPT_FILENAME).unlink()
    with pytest.raises(AtlasError, match="file set mismatch"):
        validate_pilot_ocr_output_package(paths["package"], **_arguments(paths))

    paths = _make_package(tmp_path / "wrong", monkeypatch)
    receipt_path = paths["package"] / COMPLETION_RECEIPT_FILENAME
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["output_binding_sha256"] = "f" * 64
    receipt["receipt_hash"] = _digest(receipt, "receipt_hash")
    write_json(receipt_path, receipt)
    with pytest.raises(AtlasError, match="does not authenticate"):
        validate_pilot_ocr_output_package(paths["package"], **_arguments(paths))


def test_wrong_completion_stage_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _make_package(tmp_path / "a", monkeypatch)
    receipt_path = paths["package"] / COMPLETION_RECEIPT_FILENAME
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["stage"] = "prepared"
    receipt["receipt_hash"] = _digest(receipt, "receipt_hash")
    write_json(receipt_path, receipt)

    with pytest.raises(AtlasError, match="wrong lifecycle stage"):
        validate_pilot_ocr_output_package(paths["package"], **_arguments(paths))


def test_cross_pilot_and_cross_policy_substitution_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _make_package(tmp_path / "a", monkeypatch)
    second = _make_package(
        tmp_path / "b",
        monkeypatch,
        pilot_id="PILOT_OUTPUT_B",
        suffix="123456ABCDEF",
    )
    with pytest.raises(AtlasError):
        validate_pilot_ocr_output_package(
            first["package"],
            **_arguments(
                first,
                frozen_manifest_path=second["frozen"],
                prepared_receipt_path=second["prepared"],
            ),
        )
    with pytest.raises(AtlasError, match="another security policy"):
        validate_pilot_ocr_output_package(
            first["package"],
            **_arguments(first, policy_sha256="e" * 64),
        )


def test_missing_manifest_and_replacement_attempt_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _make_package(tmp_path / "a", monkeypatch)
    (paths["package"] / OUTPUT_MANIFEST_FILENAME).unlink()
    with pytest.raises(AtlasError, match="manifest is missing"):
        validate_pilot_ocr_output_package(paths["package"], **_arguments(paths))

    write_pilot_ocr_output_manifest(paths["package"], **_builder_arguments(paths))
    with pytest.raises(AtlasError, match="refusing to replace"):
        write_pilot_ocr_output_manifest(paths["package"], **_builder_arguments(paths))


def test_semantic_hash_is_independent_of_jsonl_formatting() -> None:
    observation = _observation("ABCDEF012345", text="Synthetic text")
    compact = json.loads(canonical_json(observation))
    indented = json.loads(json.dumps(observation, indent=2))
    assert canonical_observation_semantic_sha256([compact]) == (
        canonical_observation_semantic_sha256([indented])
    )


@pytest.mark.parametrize(
    "tamper_kind",
    ("legacy-schema", "identity", "engine-version", "language-data", "private-path"),
)
def test_dependency_identity_and_observation_linkage_tampering_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper_kind: str,
) -> None:
    paths = _make_package(tmp_path / tamper_kind, monkeypatch)
    dependency_path = paths["package"] / DEPENDENCY_FILENAME
    dependency = json.loads(dependency_path.read_text(encoding="utf-8"))
    if tamper_kind == "legacy-schema":
        dependency["schema_version"] = "1.0.0"
    elif tamper_kind == "identity":
        dependency["dependency_identity_sha256"] = "f" * 64
    elif tamper_kind == "engine-version":
        dependency["version"] = "tesseract 9.9.9"
        dependency["dependency_identity_sha256"] = ocr_dependency_identity_sha256(dependency)
    elif tamper_kind == "language-data":
        dependency["language_data"][0]["sha256"] = "e" * 64
        dependency["dependency_identity_sha256"] = ocr_dependency_identity_sha256(dependency)
    elif tamper_kind == "private-path":
        dependency["executable_package"] = {"license_file": "/private/package/copyright"}
    write_json(dependency_path, dependency)

    with pytest.raises(AtlasError):
        validate_pilot_ocr_output_package(paths["package"], **_arguments(paths))


def test_observation_source_frame_reference_must_match_its_exact_source_and_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _make_package(tmp_path / "wrong-source-frame", monkeypatch, frame_count=2)
    observations_path = paths["package"] / OBSERVATIONS_FILENAME
    observation = json.loads(observations_path.read_text(encoding="utf-8"))
    observation["source_frame_evidence_ref"] = (
        f"VID:{observation['source_id']}:frame:{observation['timestamp_ms'] + 1000}"
    )
    write_jsonl(observations_path, [observation])

    with pytest.raises(AtlasError, match="wrong source-frame evidence reference"):
        validate_pilot_ocr_output_package(paths["package"], **_arguments(paths))


@pytest.mark.parametrize("modality", ("VID", "OCR"))
def test_evidence_end_timestamp_is_recomputed_from_frozen_source_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    modality: str,
) -> None:
    paths = _make_package(tmp_path / modality.lower(), monkeypatch)
    evidence_path = paths["package"] / EVIDENCE_FILENAME
    evidence_index = json.loads(evidence_path.read_text(encoding="utf-8"))
    selected = next(
        item for item in evidence_index["evidence"].values() if item["modality"] == modality
    )
    selected["end_ms"] += 1
    write_json(evidence_path, evidence_index)

    with pytest.raises(AtlasError, match="evidence differs"):
        validate_pilot_ocr_output_package(paths["package"], **_arguments(paths))


def _install_evaluation_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    retained_root: Path,
    *,
    policy_sha256: str = POLICY_SHA256,
) -> None:
    from av_atlas import ocr_pilot

    policy = {"policy_hash": policy_sha256}

    for candidate in [retained_root, *retained_root.rglob("*")]:
        candidate.chmod(0o700 if candidate.is_dir() else 0o600)

    @contextmanager
    def open_root(_policy: dict[str, Any]) -> Any:
        descriptor = os.open(
            retained_root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            yield SimpleNamespace(
                path=retained_root,
                descriptor=descriptor,
                verify=lambda: None,
            )
        finally:
            os.close(descriptor)

    @contextmanager
    def open_existing(_policy: dict[str, Any], _root: object, path: Path) -> Any:
        yield SimpleNamespace(descriptor_path=path, verify=lambda: None)

    @contextmanager
    def create_output(_policy: dict[str, Any], _root: object, path: Path) -> Any:
        path.mkdir(mode=0o700)

        def write_bounded_bytes(name: str, value: bytes) -> None:
            destination = path / name
            descriptor = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
                0o600,
            )
            try:
                os.write(descriptor, value)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

        yield SimpleNamespace(
            descriptor_path=path,
            verify=lambda: None,
            write_bounded_bytes=write_bounded_bytes,
        )

    monkeypatch.setattr(ocr_pilot, "load_pilot_security_policy", lambda *_args, **_kwargs: policy)
    monkeypatch.setattr(ocr_pilot, "open_verified_retained_root", open_root)
    monkeypatch.setattr(ocr_pilot, "open_retained_output_directory", open_existing)
    monkeypatch.setattr(ocr_pilot, "retained_output_directory", create_output)
    monkeypatch.setattr(ocr_pilot, "reject_exposed_host_path", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ocr_pilot,
        "_validate_sandboxed_pilot_manifest",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        ocr_pilot,
        "_validate_pilot_security_linkage",
        lambda *_args, **_kwargs: ({}, RIGHTS_SHA256),
    )
    monkeypatch.setattr(
        ocr_pilot,
        "verified_retained_storage_binding",
        lambda *_args, **_kwargs: _retained_storage_binding(),
    )


def _evaluate(paths: dict[str, Path], output: Path, policy_path: Path) -> dict[str, Any]:
    from av_atlas.ocr_pilot import evaluate_pilot

    return evaluate_pilot(
        paths["pilot"],
        paths["frozen"],
        paths["gold"],
        paths["package"],
        output,
        policy_path,
    )


def test_evaluate_pilot_consumes_authenticated_output_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _make_package(tmp_path / "valid", monkeypatch, frame_count=60)
    _install_evaluation_boundaries(monkeypatch, paths["root"])
    output = paths["root"] / "evaluation-output"

    report = _evaluate(paths, output, paths["root"] / "policy.local.json")

    assert report["ocr_observation_count"] == 1
    assert report["exact_frame_level_match"] == 1.0
    assert (
        report["ocr_output_binding_sha256"]
        == (
            json.loads((paths["package"] / OUTPUT_MANIFEST_FILENAME).read_text(encoding="utf-8"))[
                "output_binding_sha256"
            ]
        )
    )
    assert (output / "ocr_evaluation.json").is_file()


@pytest.mark.parametrize(
    "failure_kind",
    (
        "modified-observations",
        "modified-runtime",
        "swapped-observations",
        "swapped-runtime",
        "swapped-evidence",
        "missing-manifest",
        "missing-receipt",
        "wrong-receipt-stage",
        "cross-policy",
        "cross-pilot-package",
    ),
)
def test_evaluate_pilot_rejects_unauthenticated_or_substituted_package_before_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    paths = _make_package(tmp_path / "primary", monkeypatch, frame_count=60)
    policy_sha256 = POLICY_SHA256
    if failure_kind == "modified-observations":
        observations = paths["package"] / OBSERVATIONS_FILENAME
        observations.write_text(
            observations.read_text(encoding="utf-8").replace("Synthetic text", "Tampered text"),
            encoding="utf-8",
        )
    elif failure_kind == "modified-runtime":
        runtime_path = paths["package"] / RUNTIME_FILENAME
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["wall_seconds"] = 0.2
        write_json(runtime_path, runtime)
    elif failure_kind in {"swapped-observations", "swapped-runtime", "swapped-evidence"}:
        other = _make_package(
            tmp_path / "other-output",
            monkeypatch,
            pilot_id="PILOT_OUTPUT_B",
            suffix="123456ABCDEF",
            text="Other output",
            frame_count=60,
        )
        if failure_kind == "swapped-runtime":
            other_runtime_path = other["package"] / RUNTIME_FILENAME
            other_runtime = json.loads(other_runtime_path.read_text(encoding="utf-8"))
            other_runtime["wall_seconds"] = 0.2
            write_json(other_runtime_path, other_runtime)
        selected = {
            "swapped-observations": OBSERVATIONS_FILENAME,
            "swapped-runtime": RUNTIME_FILENAME,
            "swapped-evidence": EVIDENCE_FILENAME,
        }[failure_kind]
        shutil.copyfile(
            other["package"] / selected,
            paths["package"] / selected,
        )
    elif failure_kind == "missing-manifest":
        (paths["package"] / OUTPUT_MANIFEST_FILENAME).unlink()
    elif failure_kind == "missing-receipt":
        (paths["package"] / COMPLETION_RECEIPT_FILENAME).unlink()
    elif failure_kind == "wrong-receipt-stage":
        receipt_path = paths["package"] / COMPLETION_RECEIPT_FILENAME
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["stage"] = "prepared"
        receipt["output_binding_sha256"] = None
        receipt["receipt_hash"] = _digest(receipt, "receipt_hash")
        write_json(receipt_path, receipt)
    elif failure_kind == "cross-policy":
        policy_sha256 = "e" * 64
    elif failure_kind == "cross-pilot-package":
        other = _make_package(
            tmp_path / "other-pilot",
            monkeypatch,
            pilot_id="PILOT_OUTPUT_B",
            suffix="123456ABCDEF",
            text="Other output",
            frame_count=60,
        )
        foreign = paths["root"] / "foreign-ocr-output"
        shutil.copytree(other["package"], foreign)
        paths["package"] = foreign
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(f"unknown failure kind: {failure_kind}")

    _install_evaluation_boundaries(
        monkeypatch,
        paths["root"],
        policy_sha256=policy_sha256,
    )
    output = paths["root"] / "evaluation-output"
    with pytest.raises(AtlasError):
        _evaluate(paths, output, paths["root"] / "policy.local.json")
    assert not output.exists()
