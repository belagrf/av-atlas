from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from av_atlas.errors import AtlasError
from av_atlas.schemas import validate_instance

SHA256 = "a" * 64


def _limits() -> dict[str, int]:
    return {
        "wall_timeout_seconds": 30,
        "cpu_time_seconds": 20,
        "address_space_bytes": 1_073_741_824,
        "output_file_size_bytes": 16_777_216,
        "open_files": 64,
        "process_count": 8,
        "core_dump_bytes": 0,
        "capture_bytes": 1_048_576,
        "cleanup_timeout_seconds": 5,
    }


def _policy() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "contract_version": "av-atlas-pilot-security-policy/1.0.0",
        "pilot_id": "PILOT_SCHEMA_TEST",
        "pilot_spec_sha256": SHA256,
        "pilot_spec_size_bytes": 4096,
        "created_at": "2026-07-16T12:00:00+00:00",
        "expires_at": "2026-07-17T12:00:00+00:00",
        "private_root": {
            "path": "/private/pilot-root",
            "expected_device": 8,
            "expected_inode": 42,
            "expected_uid": 1000,
            "expected_mode": "0700",
            "mount_identity_sha256": SHA256,
        },
        "storage": {
            "decision": "verified-tmpfs",
            "expected_filesystem_type": "tmpfs",
            "independently_reviewed": False,
            "review_record": None,
            "review_scope": None,
            "review_expires_at": None,
            "compensating_controls": [],
            "deletion_plan": None,
            "tmpfs_swap_warning_acknowledged": True,
            "secure_erasure_claimed": False,
        },
        "capacity": {
            "source_byte_ceiling": 8_388_608,
            "temporary_byte_ceiling": 16_777_216,
            "reserve_bytes": 1_048_576,
        },
        "sandbox": {
            "provider": "bubblewrap",
            "profile_contract_version": "av-atlas-bubblewrap-pilot/1.0.0",
            "profile_sha256": SHA256,
            "executable_basename": "bwrap",
            "executable_sha256": SHA256,
            "executable_size_bytes": 131_072,
            "dependency_identity_sha256": SHA256,
            "version": "bubblewrap 0.10.0",
            "capability_state": "passed",
        },
        "resource_limits": _limits(),
        "policy_hash": SHA256,
    }


def _capability() -> dict[str, bool]:
    return {
        "namespace_smoke_test_passed": True,
        "network_denied": True,
        "external_sentinel_denied": True,
        "outside_write_denied": True,
    }


def _lifecycle() -> dict[str, Any]:
    return {
        "cleanup_method": "logical-unlink-and-directory-removal",
        "cleanup_outcome": "logical-deletion-complete",
        "logical_deletion": True,
        "secure_erasure_claimed": False,
        "bounded_stale_recovery": True,
    }


def _privacy() -> dict[str, bool]:
    return {
        "private_paths_exported": False,
        "original_path_exported": False,
        "snapshot_path_exported": False,
        "user_identity_exported": False,
        "hostname_exported": False,
        "raw_environment_exported": False,
    }


def _receipt() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "contract_version": "av-atlas-pilot-security-receipt/1.0.0",
        "stage": "prepared",
        "measured_at": "2026-07-16T12:30:00+00:00",
        "pilot_id": "PILOT_SCHEMA_TEST",
        "pilot_spec_sha256": SHA256,
        "pilot_spec_size_bytes": 4096,
        "policy_sha256": SHA256,
        "source_rights_aggregate_sha256": SHA256,
        "root_identity_sha256": SHA256,
        "filesystem_type": "tmpfs",
        "storage": {
            "decision": "verified-tmpfs",
            "available_bytes": 536_870_912,
            "required_bytes": 25_165_824,
            "reserve_bytes": 1_048_576,
            "root_identity_verified": True,
            "owner_verified": True,
            "mode_verified": True,
            "local_filesystem_verified": True,
            "capacity_verified": True,
        },
        "sandbox": {
            "provider": "bubblewrap",
            "profile_contract_version": "av-atlas-bubblewrap-pilot/1.0.0",
            "profile_sha256": SHA256,
            "dependency_identity_sha256": SHA256,
            "executable_basename": "bwrap",
            "executable_sha256": SHA256,
            "executable_size_bytes": 131_072,
            "version": "bubblewrap 0.10.0",
            "package_identity": "bubblewrap:amd64 0.10.0-1",
            "source_identity": "bubblewrap 0.10.0-1",
            "license_id": "LGPL-2.0-or-later",
            "license_verification": "installed-package-metadata-read",
            "capability_smoke_test_passed": True,
            "namespaces": {
                "network": True,
                "user": True,
                "pid": True,
                "ipc": True,
                "uts": True,
                "mount": True,
            },
            "capabilities_dropped": True,
            "environment_cleared": True,
            "home_exposed": False,
            "whole_root_bound": False,
            "input_read_only": True,
            "output_only_writable": True,
            "private_tmp": True,
        },
        "resource_limits": _limits(),
        "capability": _capability(),
        "lifecycle": _lifecycle(),
        "privacy": _privacy(),
        "receipt_hash": SHA256,
    }


def _manifest(version: str) -> dict[str, Any]:
    sources = [{"source_id": f"SRC_{index:012X}"} for index in range(3)]
    frames: list[dict[str, Any]] = [{} for _ in range(80)]
    privacy: dict[str, Any] = {"absolute_paths_exported": False}
    if version == "1.1.0":
        sources = [
            {
                "source_id": f"SRC_{index:012X}",
                "source_sha256": f"{index + 1:064x}",
                "duration_ms": 100_000,
                "rights_manifest": f"rights/SRC_{index:012X}.rights.json",
                "rights_manifest_sha256": f"{index + 4:064x}",
                "rights_manifest_hash": f"{index + 7:064x}",
            }
            for index in range(3)
        ]
        frames = []
        for index in range(80):
            suffix = f"{index % 3:012X}"
            frame_id = f"FRM_{suffix}_{index * 1000:010d}"
            frames.append(
                {
                    "frame_id": frame_id,
                    "source_id": f"SRC_{suffix}",
                    "timestamp_ms": index * 1000,
                    "split": "calibration" if index < 20 else "evaluation",
                    "categories": ["synthetic"],
                    "difficulty": ["controlled"],
                    "path": f"frames/{frame_id}.png",
                    "sha256": f"{index + 10:064x}",
                    "size_bytes": 1024 + index,
                }
            )
        privacy = {
            "source_media_copied": False,
            "source_ids_hash_derived": True,
            "absolute_paths_exported": False,
            "legal_determination": False,
        }
    value: dict[str, Any] = {
        "schema_version": version,
        "pilot_id": "PILOT_SCHEMA_TEST",
        "state": "prepared_unannotated",
        "selection_protocol": {
            "method": "pre-registered synthetic schema test",
            "random_seed": None,
            "inclusion_criteria": ["project-authored synthetic frame"],
            "exclusion_criteria": ["invalid frame"],
            "duplicate_frame_policy": "reject source/timestamp duplicates",
        },
        "sources": sources,
        "frames": frames,
        "counts": {"sources": 3, "calibration_frames": 20, "evaluation_frames": 60},
        "privacy": privacy,
        "manifest_hash": SHA256,
    }
    if version == "1.1.0":
        value["pilot_security"] = {
            "policy_sha256": SHA256,
            "receipt_path": "pilot_security_receipt.json",
            "receipt_sha256": SHA256,
            "receipt_stage": "prepared",
            "pilot_spec_sha256": SHA256,
            "pilot_spec_size_bytes": 4096,
            "source_set_sha256": SHA256,
            "source_rights_aggregate_sha256": SHA256,
            "root_identity_sha256": SHA256,
            "filesystem_type": "tmpfs",
            "storage_decision": "verified-tmpfs",
            "sandbox": {
                "provider": "bubblewrap",
                "profile_contract_version": "av-atlas-bubblewrap-pilot/1.0.0",
                "profile_sha256": SHA256,
                "dependency_identity_sha256": SHA256,
                "capability_smoke_test_passed": True,
            },
            "resource_limits": _limits(),
            "capability": _capability(),
            "lifecycle": _lifecycle(),
            "privacy": _privacy(),
        }
    return value


def test_private_policy_and_sanitized_receipt_v1_are_strict() -> None:
    validate_instance("pilot_security_policy", _policy(), "pilot security policy")
    validate_instance("pilot_security_receipt", _receipt(), "pilot security receipt")

    unsafe_policy = deepcopy(_policy())
    unsafe_policy["private_root"]["expected_mode"] = "0755"
    with pytest.raises(AtlasError, match="expected_mode"):
        validate_instance("pilot_security_policy", unsafe_policy, "unsafe policy")

    leaking_receipt = deepcopy(_receipt())
    leaking_receipt["private_root"] = "/home/operator/private"
    with pytest.raises(AtlasError, match="Additional properties"):
        validate_instance("pilot_security_receipt", leaking_receipt, "leaking receipt")


def test_reviewed_storage_decisions_require_review_evidence() -> None:
    policy = _policy()
    policy["storage"].update(
        {
            "decision": "reviewed-remanence-acceptance",
            "expected_filesystem_type": "ext4",
            "independently_reviewed": False,
            "review_record": None,
            "review_scope": None,
            "review_expires_at": None,
            "compensating_controls": [],
            "deletion_plan": None,
        }
    )
    with pytest.raises(AtlasError, match="schema validation failed"):
        validate_instance("pilot_security_policy", policy, "unreviewed storage policy")


def test_historical_pilot_manifest_v1_remains_valid() -> None:
    historical = _manifest("1.0.0")
    historical["privacy"] = {"source_media_copied": False}
    validate_instance("ocr_pilot_manifest", historical, "historical pilot manifest")


def test_sandboxed_pilot_manifest_v1_1_requires_complete_security_linkage() -> None:
    validate_instance("ocr_pilot_manifest", _manifest("1.1.0"), "sandboxed pilot manifest")

    missing_receipt_link = _manifest("1.1.0")
    del missing_receipt_link["pilot_security"]["receipt_sha256"]
    with pytest.raises(AtlasError, match="schema validation failed"):
        validate_instance("ocr_pilot_manifest", missing_receipt_link, "missing receipt link")


def test_synthetic_pilot_security_report_is_strict_and_path_free() -> None:
    report = {
        "schema_version": "1.0.0",
        "contract_version": "av-atlas-m2b3-synthetic-pilot/1.0.0",
        "state": "succeeded",
        "pilot_id": "PILOT_SCHEMA_TEST",
        "source_id": "SRC_0123456789AB",
        "source_sha256": SHA256,
        "policy_sha256": SHA256,
        "security_receipt_sha256": SHA256,
        "tools": {
            "ffprobe_sandboxed": True,
            "ffmpeg_sandboxed": True,
            "tesseract_sandboxed": True,
        },
        "measurements": {
            "wall_seconds": 1.0,
            "cpu_seconds": 0.5,
            "peak_rss_kb": 1024,
            "source_size_bytes": 4096,
            "frame_size_bytes": 1024,
            "ocr_observation_count": 1,
            "ocr_frames_processed": 1,
            "ocr_timeouts": 0,
            "ocr_retries": 0,
        },
        "resource_limits": _limits(),
        "capability": _capability(),
        "privacy": {
            "real_media_processed": False,
            "private_paths_exported": False,
            "source_media_exported": False,
            "frame_derivative_exported": False,
        },
        "artifact_hashes": {
            "ocr_observations": SHA256,
            "ocr_dependency": SHA256,
            "security_receipt": SHA256,
        },
        "report_hash": SHA256,
    }
    validate_instance(
        "pilot_security_synthetic_report",
        report,
        "synthetic security report",
    )
    leaking = deepcopy(report)
    leaking["private_root"] = "/home/operator/private"
    with pytest.raises(AtlasError, match="Additional properties"):
        validate_instance(
            "pilot_security_synthetic_report",
            leaking,
            "leaking synthetic report",
        )

    unsafe_capability = _manifest("1.1.0")
    unsafe_capability["pilot_security"]["capability"]["network_denied"] = False
    with pytest.raises(AtlasError, match="network_denied"):
        validate_instance("ocr_pilot_manifest", unsafe_capability, "unsafe capability")


def test_sanitized_receipt_rejects_unproven_isolation_and_unknown_fields() -> None:
    receipt = _receipt()
    receipt["sandbox"]["home_exposed"] = True
    with pytest.raises(AtlasError, match="home_exposed"):
        validate_instance("pilot_security_receipt", receipt, "home-exposing receipt")

    receipt = _receipt()
    receipt["capability"]["network_denied"] = False
    with pytest.raises(AtlasError, match="network_denied"):
        validate_instance("pilot_security_receipt", receipt, "network-capable receipt")
