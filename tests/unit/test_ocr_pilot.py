import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from av_atlas.cli import main
from av_atlas.errors import AtlasError
from av_atlas.fixture import make_m2b_fixture
from av_atlas.io import sha256_file, source_id_from_sha256
from av_atlas.native_media import AUTHORIZED_MATROSKA, NativeInputPolicy
from av_atlas.native_process import PROFILE_SHA256, PROFILE_VERSION, profile_record
from av_atlas.ocr_pilot import (
    _copy_verified_file,
    _create_pinned_private_directory,
    _digest,
    _open_pinned_retained_json,
    _runner_for_policy,
    compare_annotations,
    freeze_pilot,
    make_annotation_packages,
    prepare_pilot,
    run_pilot_ocr,
    validate_pilot_security_artifacts,
)
from av_atlas.pilot_security import (
    create_pilot_security_policy,
    load_pilot_security_policy,
    open_verified_retained_root,
    retained_output_directory,
    validate_security_receipt,
)
from av_atlas.rights import create_rights_manifest
from av_atlas.schemas import validate_instance


def _limits() -> dict[str, int]:
    return {
        "wall_timeout_seconds": 30,
        "cpu_time_seconds": 20,
        "address_space_bytes": 1_073_741_824,
        "output_file_size_bytes": 16_777_216,
        "open_files": 64,
        "process_count": 512,
        "core_dump_bytes": 0,
        "capture_bytes": 1_048_576,
        "cleanup_timeout_seconds": 5,
    }


def _inventory() -> dict[str, Any]:
    profile = profile_record()
    return {
        "state": "available",
        "profile_version": PROFILE_VERSION,
        "profile_sha256": PROFILE_SHA256,
        "exposed_host_subtrees": profile["exposed_host_subtrees"],
        "masked_host_subtrees": profile["masked_host_subtrees"],
        "executable": {
            "basename": "bwrap",
            "path_class": "system",
            "sha256": "2" * 64,
            "size_bytes": 72_160,
        },
        "version": "bubblewrap 0.9.0",
        "package": {
            "package": "bubblewrap",
            "version": "0.9.0-1ubuntu0.1",
            "architecture": "amd64",
            "source_package": "bubblewrap",
            "source_version": "0.9.0-1ubuntu0.1",
            "license_id": "LGPL-2.0-or-later",
            "license_verification": "read installed package copyright metadata",
        },
        "capability_smoke": {"passed": True},
        "dependency_identity_sha256": "3" * 64,
    }


def _hostile_probe_result() -> dict[str, bool]:
    return {
        "outside_sentinel_denied": True,
        "outside_host_write_denied": True,
        "outside_root_write_denied": True,
        "device_directory_write_denied": True,
        "work_write_allowed": True,
        "tmp_write_allowed": True,
        "loopback_network_denied": True,
        "external_network_denied": True,
        "home_directory_denied": True,
        "inherited_environment_denied": True,
        "hostname_sanitized": True,
        "masked_runtime_sentinel_denied": True,
        "outside_write_positive_control": True,
    }


def _security_policy(
    tmp_path: Path,
    spec: Path,
    *,
    max_source_bytes: int = 1_000_000,
    max_temporary_bytes: int = 2_000_000,
    max_retained_bytes: int = 4_000_000,
) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "pilot-private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    retained_root = tmp_path / "pilot-retained"
    retained_root.mkdir(mode=0o700)
    retained_root.chmod(0o700)
    policy_path = tmp_path / "pilot-security-policy.local.json"
    pilot_id = str(json.loads(spec.read_text(encoding="utf-8"))["pilot_id"])
    create_pilot_security_policy(
        root=root,
        retained_root=retained_root,
        pilot_id=pilot_id,
        pilot_spec=spec,
        output=policy_path,
        expires_at="2099-01-01T00:00:00+00:00",
        storage_decision="reviewed-remanence-acceptance",
        retained_storage_decision="reviewed-remanence-acceptance",
        bubblewrap_inventory=_inventory(),
        resource_limits=_limits(),
        reviewer_pseudonym="REVIEWER_SECURITY",
        review_record="synthetic test private root review",
        review_expires_at="2099-01-01T00:00:00+00:00",
        compensating_controls=("synthetic test data only",),
        deletion_plan="logical unlink and bounded marker recovery",
        max_source_bytes=max_source_bytes,
        max_temporary_bytes=max_temporary_bytes,
        max_retained_bytes=max_retained_bytes,
        reserve_bytes=1_000_000,
        retained_reserve_bytes=1_000_000,
    )
    return policy_path, root, retained_root


def _fake_sandbox(monkeypatch: pytest.MonkeyPatch) -> object:
    runner = object()
    monkeypatch.setattr(
        "av_atlas.ocr_pilot._runner_for_policy",
        lambda _policy, _root=None, _retained_root=None: (runner, _inventory()),
    )
    monkeypatch.setattr(
        "av_atlas.ocr_pilot.run_hostile_sandbox_probes",
        lambda *_args, **_kwargs: _hostile_probe_result(),
    )
    return runner


def _inventory_for_snapshot(path: Path) -> dict[str, Any]:
    digest = sha256_file(path)
    return {
        "schema_version": "1.1.0",
        "source_id": source_id_from_sha256(digest),
        "sha256": digest,
        "size_bytes": path.stat().st_size,
        "duration_ms": 100_000,
        "format_names": ["matroska", "webm"],
        "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
        "streams": [],
        "chapters": [],
    }


def _ocr_inventory() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "state": "available",
        "engine": "tesseract",
        "network_accessed": False,
        "resolved_executable_path": "/usr/bin/tesseract",
        "executable_sha256": "4" * 64,
        "executable_size_bytes": 64_000,
        "version": "tesseract 5.3.4",
        "leptonica_version": "leptonica-1.82.0",
        "reported_build_features": [],
        "version_output": ["tesseract 5.3.4"],
        "executable_package": None,
        "tessdata_prefix": {"environment_value": None},
        "discovered_tessdata_directories": ["/usr/share/tesseract-ocr/5/tessdata"],
        "available_languages": ["eng"],
        "language_data": [
            {
                "language": "eng",
                "path": "/usr/share/tesseract-ocr/5/tessdata/eng.traineddata",
                "sha256": "5" * 64,
                "size_bytes": 4_113_088,
                "package": None,
            }
        ],
        "relevant_environment": {"TESSDATA_PREFIX": None},
    }


def _frozen_manifest(prepared: dict[str, Any]) -> dict[str, Any]:
    frozen = {
        **prepared,
        "state": "adjudicated_frozen",
        "human_annotation_sha256": ["a" * 64, "b" * 64],
        "adjudicated_gold_sha256": "c" * 64,
        "disagreement_report_sha256": "d" * 64,
        "normalization_rules_sha256": "e" * 64,
        "ocr_configuration_sha256": sha256_file(Path(__file__).parents[2] / "configs/m2b.yaml"),
        "region_matching_rule": "IoU >= 0.5; one-to-one maximum-IoU matching",
        "metric_definition": "AV-Atlas OCR evaluation schema 1.0.0",
        "disagreement_count": 0,
        "manifest_hash": "",
    }
    frozen["manifest_hash"] = _digest(frozen)
    return frozen


def test_retained_json_is_stably_read_and_replacement_is_detected(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    spec.write_text('{"pilot_id":"PILOT_PINNED_JSON"}\n', encoding="utf-8")
    policy_path, _, retained_root = _security_policy(tmp_path, spec)
    package = retained_root / "package"
    package.mkdir(mode=0o700)
    retained_input = package / "input.json"
    retained_input.write_text('{"value":"original"}\n', encoding="utf-8")
    retained_input.chmod(0o600)
    moved = package / "moved.json"
    replacement = b'{"value":"replacement"}\n'
    policy = load_pilot_security_policy(policy_path)

    with (
        open_verified_retained_root(policy) as root,
        pytest.raises(AtlasError, match="JSON input identity changed"),
        _open_pinned_retained_json(
            root,
            retained_input,
            label="test retained JSON",
        ) as pinned,
    ):
        assert pinned.value == {"value": "original"}
        assert pinned.anchored_path == Path(f"/proc/self/fd/{pinned.descriptor}")
        retained_input.rename(moved)
        retained_input.write_bytes(replacement)
        retained_input.chmod(0o600)

    assert json.loads(moved.read_text(encoding="utf-8")) == {"value": "original"}
    assert retained_input.read_bytes() == replacement


def test_private_annotation_directory_replacement_cleans_only_original(
    tmp_path: Path,
) -> None:
    spec = tmp_path / "spec.json"
    spec.write_text('{"pilot_id":"PILOT_PINNED_PACKAGE"}\n', encoding="utf-8")
    policy_path, _, retained_root = _security_policy(tmp_path, spec)
    policy = load_pilot_security_policy(policy_path)
    output_path = retained_root / "annotation-package"

    with (
        open_verified_retained_root(policy) as root,
        retained_output_directory(policy, root, output_path) as output,
        pytest.raises(AtlasError, match="package identity changed"),
        _create_pinned_private_directory(output, output, "annotator_A"),
    ):
        (output_path / "annotator_A").rename(output_path / "moved-original")
        replacement = output_path / "annotator_A"
        replacement.mkdir(mode=0o700)
        sentinel = replacement / "sentinel"
        sentinel.write_bytes(b"replacement must survive cleanup")
        sentinel.chmod(0o600)

    assert not (output_path / "moved-original").exists()
    assert (output_path / "annotator_A/sentinel").read_bytes() == (
        b"replacement must survive cleanup"
    )


def test_nested_annotation_directory_placement_failure_leaves_no_partial_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import ocr_pilot

    spec = tmp_path / "spec.json"
    spec.write_text('{"pilot_id":"PILOT_NESTED_ROLLBACK"}\n', encoding="utf-8")
    policy_path, _, retained_root = _security_policy(tmp_path, spec)
    policy = load_pilot_security_policy(policy_path)
    output_path = retained_root / "annotation-package"
    with (
        open_verified_retained_root(policy) as root,
        retained_output_directory(policy, root, output_path) as output,
    ):
        monkeypatch.setattr(
            ocr_pilot.os,
            "fchmod",
            lambda _descriptor, _mode: (_ for _ in ()).throw(
                OSError("injected nested placement failure")
            ),
        )
        with (
            pytest.raises(OSError, match="injected nested placement failure"),
            _create_pinned_private_directory(output, output, "annotator_A"),
        ):
            pytest.fail("failed nested placement must not yield")
        assert not (output_path / "annotator_A").exists()
        assert root.measure_aggregate_bytes() == 0


def test_derivative_copy_rejects_replacement_without_deleting_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import ocr_pilot

    source = tmp_path / "source.png"
    source.write_bytes(b"project-authored frame")
    destination = tmp_path / "destination.png"
    moved_original = tmp_path / "moved-original.png"
    original_fsync = ocr_pilot.os.fsync
    replaced = False

    def replace_after_write(descriptor: int) -> None:
        nonlocal replaced
        original_fsync(descriptor)
        if not replaced and destination.exists():
            replaced = True
            destination.rename(moved_original)
            destination.write_bytes(b"replacement must survive")
            destination.chmod(0o600)

    monkeypatch.setattr(ocr_pilot.os, "fsync", replace_after_write)
    with pytest.raises(AtlasError, match="destination changed"):
        _copy_verified_file(
            source,
            destination,
            expected_sha256=sha256_file(source),
            expected_size=source.stat().st_size,
        )

    assert destination.read_bytes() == b"replacement must survive"
    assert moved_original.read_bytes() == b"project-authored frame"


def test_pilot_prepare_requires_policy_before_media_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "pilot_id": "PILOT_TEST",
                "selection_method": "pre-registered",
                "random_seed": None,
                "inclusion_criteria": ["visible frame"],
                "exclusion_criteria": ["decode failure"],
                "duplicate_frame_policy": "reject exact source/timestamp duplicates",
                "sources": [],
            }
        )
    )
    calls = 0

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("missing policy must fail before native processing")

    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", forbidden)
    monkeypatch.setattr("av_atlas.ocr_pilot._runner_for_policy", forbidden)
    with pytest.raises(AtlasError, match="explicit private security policy"):
        prepare_pilot(spec, tmp_path / "output")
    assert calls == 0
    assert not (tmp_path / "output").exists()


def test_pilot_prepare_rejects_exposed_spec_before_read_or_native_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import ocr_pilot

    reads = 0
    native_calls = 0

    def forbidden_read(*_args: object, **_kwargs: object) -> None:
        nonlocal reads
        reads += 1
        raise AssertionError("exposed pilot specification must fail before reading")

    def forbidden_native(*_args: object, **_kwargs: object) -> None:
        nonlocal native_calls
        native_calls += 1
        raise AssertionError("exposed pilot specification must fail before native work")

    monkeypatch.setattr(ocr_pilot, "load_bound_json", forbidden_read)
    monkeypatch.setattr(ocr_pilot, "_runner_for_policy", forbidden_native)
    with pytest.raises(AtlasError, match="overlaps a sandbox-exposed"):
        prepare_pilot(
            Path("/usr/bin/av-atlas-pilot-spec.json"),
            tmp_path / "output",
            tmp_path / "policy.local.json",
        )

    assert reads == 0
    assert native_calls == 0
    assert not (tmp_path / "output").exists()


def test_pilot_prepare_rejects_undersized_spec_before_media_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "pilot_id": "PILOT_TEST",
                "selection_method": "pre-registered",
                "random_seed": None,
                "inclusion_criteria": ["visible frame"],
                "exclusion_criteria": ["decode failure"],
                "duplicate_frame_policy": "reject exact source/timestamp duplicates",
                "sources": [],
            }
        )
    )
    policy, _, retained_root = _security_policy(tmp_path, spec)
    calls = 0

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("undersized pilot must fail before native processing")

    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", forbidden)
    monkeypatch.setattr("av_atlas.ocr_pilot._runner_for_policy", forbidden)
    with pytest.raises(AtlasError, match="at least three"):
        prepare_pilot(spec, retained_root / "output", policy)
    assert calls == 0
    assert not (retained_root / "output").exists()


def test_legacy_pilot_execution_cannot_create_annotation_derivatives(tmp_path: Path) -> None:
    pilot = tmp_path / "pilot"
    (pilot / "frames").mkdir(parents=True)
    frames = []
    for index in range(80):
        frame_id = f"FRM_TEST_{index:04d}"
        path = pilot / "frames" / f"{frame_id}.png"
        path.write_bytes(f"frame-{index}".encode())
        frames.append(
            {
                "frame_id": frame_id,
                "source_id": f"SRC_{index % 3:012X}",
                "timestamp_ms": index * 1000,
                "split": "calibration" if index < 20 else "evaluation",
                "categories": ["test"],
                "difficulty": ["test"],
                "path": f"frames/{frame_id}.png",
                "sha256": "0" * 64,
            }
        )
    manifest = {
        "schema_version": "1.0.0",
        "pilot_id": "PILOT_TEST",
        "state": "prepared_unannotated",
        "selection_protocol": {
            "method": "test",
            "random_seed": None,
            "inclusion_criteria": ["test"],
            "exclusion_criteria": ["none"],
            "duplicate_frame_policy": "reject",
        },
        "sources": [{"source_id": f"SRC_{i:012X}"} for i in range(3)],
        "frames": frames,
        "counts": {"sources": 3, "calibration_frames": 20, "evaluation_frames": 60},
        "privacy": {"source_media_copied": False},
        "manifest_hash": "",
    }
    manifest["manifest_hash"] = _digest(manifest)
    (pilot / "pilot_manifest.json").write_text(json.dumps(manifest))
    validate_instance("ocr_pilot_manifest", manifest, "legacy pilot manifest")
    with pytest.raises(AtlasError, match="explicit private security policy"):
        make_annotation_packages(pilot)
    comparison_output = tmp_path / "comparison"
    with pytest.raises(AtlasError, match="explicit private security policy"):
        compare_annotations(
            pilot,
            tmp_path / "unused-first.json",
            tmp_path / "unused-second.json",
            comparison_output,
        )
    freeze_output = tmp_path / "freeze"
    with pytest.raises(AtlasError, match="explicit private security policy"):
        freeze_pilot(
            pilot,
            tmp_path / "unused-first.json",
            tmp_path / "unused-second.json",
            tmp_path / "unused-gold.json",
            freeze_output,
        )
    assert not (pilot / "annotator_A").exists()
    assert not (pilot / "annotator_B").exists()
    assert not comparison_output.exists()
    assert not freeze_output.exists()


def test_pilot_cli_reports_fail_closed_error(tmp_path: Path) -> None:
    spec = tmp_path / "bad.json"
    spec.write_text("{}")
    assert (
        main(
            [
                "pilot-prepare",
                str(spec),
                "--output",
                str(tmp_path / "out"),
                "--security-policy",
                str(tmp_path / "missing-policy.json"),
            ]
        )
        == 2
    )


def _pilot_spec(tmp_path: Path, *, deny_last: bool = False) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    sources = []
    for source_index in range(3):
        media = tmp_path / f"source-{source_index}.bin"
        media.write_bytes(f"synthetic-pilot-source-{source_index}".encode())
        rights = tmp_path / f"source-{source_index}.rights.json"
        permissions = {
            "analysis",
            "annotation",
            "evaluation",
            "derivative_artifact_retention",
        }
        if deny_last and source_index == 2:
            permissions.remove("analysis")
        create_rights_manifest(
            media,
            rights,
            "pilot-test",
            "owned",
            permissions,
        )
        if source_index == 0:
            splits = ["calibration"] * 20 + ["evaluation"] * 20
        else:
            splits = ["evaluation"] * 20
        selections = [
            {
                "timestamp_ms": index * 1000,
                "split": split,
                "categories": ["synthetic-test"],
                "difficulty": ["controlled"],
            }
            for index, split in enumerate(splits)
        ]
        sources.append(
            {
                "media_path": str(media),
                "rights_manifest_path": str(rights),
                "selections": selections,
            }
        )
    spec = tmp_path / "pilot-spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "pilot_id": "PILOT_SYNTHETIC_STABLE_INPUT",
                "selection_method": "pre-registered synthetic",
                "random_seed": None,
                "inclusion_criteria": ["project-authored synthetic source"],
                "exclusion_criteria": ["none"],
                "duplicate_frame_policy": "reject source/timestamp duplicates",
                "sources": sources,
            }
        )
    )
    return spec


def test_pilot_denied_later_source_invokes_no_parser_or_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _pilot_spec(tmp_path, deny_last=True)
    policy, _, retained_root = _security_policy(tmp_path, spec)
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("pilot parser must not run before every source is authorized")

    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", forbidden)
    monkeypatch.setattr("av_atlas.ocr_pilot._runner_for_policy", forbidden)
    monkeypatch.setattr("av_atlas.ocr_pilot._extract_frame", forbidden)
    with pytest.raises(AtlasError, match="requested operation: analysis"):
        prepare_pilot(spec, retained_root / "pilot", policy)
    assert calls == 0
    assert not (retained_root / "pilot").exists()


def test_pilot_rehashed_rights_after_all_source_preflight_invokes_no_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import ocr_pilot
    from av_atlas.rights import manifest_digest

    spec = _pilot_spec(tmp_path)
    policy, _, retained_root = _security_policy(tmp_path, spec)
    sources = json.loads(spec.read_text())["sources"]
    rights_path = Path(sources[0]["rights_manifest_path"])
    original_preflight = ocr_pilot.preflight_authorized_source
    preflight_calls = 0
    parser_calls = 0

    def preflight(*args: object, **kwargs: object) -> object:
        nonlocal preflight_calls
        result = original_preflight(*args, **kwargs)  # type: ignore[arg-type]
        preflight_calls += 1
        if preflight_calls == 3:
            rights = json.loads(rights_path.read_text())
            rights["notes"] = "validly rehashed after all-source authorization"
            rights["manifest_hash"] = manifest_digest(rights)
            rights_path.write_text(json.dumps(rights))
        return result

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal parser_calls
        parser_calls += 1
        raise AssertionError("changed pilot rights must fail before parsing")

    monkeypatch.setattr(ocr_pilot, "preflight_authorized_source", preflight)
    _fake_sandbox(monkeypatch)
    monkeypatch.setattr(ocr_pilot, "inspect_media", forbidden)
    monkeypatch.setattr(ocr_pilot, "_extract_frame", forbidden)
    output = retained_root / "pilot"
    with pytest.raises(AtlasError, match="expected rights manifest hash"):
        prepare_pilot(spec, output, policy)
    assert preflight_calls == 3
    assert parser_calls == 0
    assert not output.exists()


def test_synthetic_pilot_preparation_parses_and_extracts_only_from_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _pilot_spec(tmp_path)
    policy, root, retained_root = _security_policy(tmp_path, spec)
    runner = _fake_sandbox(monkeypatch)
    original_paths = {
        Path(source["media_path"]) for source in json.loads(spec.read_text())["sources"]
    }
    parser_paths: list[Path] = []
    extraction_paths: list[Path] = []

    def inspect(
        path: Path,
        *,
        native_runner: object,
        sandbox_work_directory: Path,
        expected_source_sha256: str,
        expected_source_size: int,
    ) -> dict[str, Any]:
        assert native_runner is runner
        assert sandbox_work_directory.is_relative_to(root)
        assert path.is_relative_to(root)
        parser_paths.append(path)
        digest = sha256_file(path)
        assert digest == expected_source_sha256
        assert path.stat().st_size == expected_source_size
        return {
            "schema_version": "1.1.0",
            "source_id": source_id_from_sha256(digest),
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "duration_ms": 100_000,
            "format_names": ["matroska", "webm"],
            "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
            "streams": [],
            "chapters": [],
        }

    def extract(
        path: Path,
        timestamp_ms: int,
        output: Path,
        native_policy: NativeInputPolicy,
        *,
        native_runner: object,
        expected_source_sha256: str,
        expected_source_size: int,
    ) -> None:
        assert native_policy == AUTHORIZED_MATROSKA
        assert native_runner is runner
        assert path.is_relative_to(root)
        assert output.is_relative_to(root)
        assert sha256_file(path) == expected_source_sha256
        assert path.stat().st_size == expected_source_size
        extraction_paths.append(path)
        output.write_bytes(f"synthetic-frame-{timestamp_ms}".encode())

    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.ocr_pilot._extract_frame", extract)
    pilot = retained_root / "pilot"
    manifest = prepare_pilot(spec, pilot, policy)
    assert manifest["counts"] == {
        "sources": 3,
        "calibration_frames": 20,
        "evaluation_frames": 60,
    }
    assert len(parser_paths) == 3
    assert len(extraction_paths) == 80
    assert not ({*parser_paths, *extraction_paths} & original_paths)
    assert all(path.name == "source.snapshot" for path in parser_paths + extraction_paths)
    assert all(not path.exists() for path in parser_paths)
    validate_instance("ocr_pilot_manifest", manifest, "prepared pilot")
    receipt = json.loads((pilot / "pilot_security_receipt.json").read_text())
    validate_security_receipt(
        receipt,
        policy_hash=manifest["pilot_security"]["policy_sha256"],
        pilot_spec_sha256=manifest["pilot_security"]["pilot_spec_sha256"],
    )
    assert (
        sha256_file(pilot / "pilot_security_receipt.json")
        == manifest["pilot_security"]["receipt_sha256"]
    )
    exported = json.dumps({"manifest": manifest, "receipt": receipt}, sort_keys=True)
    assert str(root) not in exported
    assert str(tmp_path) not in exported
    assert str(Path.home()) not in exported
    assert not any(root.iterdir())
    linkage = validate_pilot_security_artifacts(pilot, security_policy_path=policy)
    assert linkage["state"] == "valid"
    assert linkage["local_policy_verified"] is True

    from av_atlas.pilot_security import _digest as security_digest

    replacement_policy = tmp_path / "replacement-policy.local.json"
    replacement_value = json.loads(policy.read_text(encoding="utf-8"))
    replacement_value["expires_at"] = "2098-01-01T00:00:00+00:00"
    replacement_value["policy_hash"] = security_digest(replacement_value, "policy_hash")
    replacement_policy.write_text(json.dumps(replacement_value), encoding="utf-8")
    replacement_policy.chmod(0o600)
    with pytest.raises(AtlasError, match="linked to another policy"):
        validate_pilot_security_artifacts(
            pilot,
            security_policy_path=replacement_policy,
        )


def test_current_policy_rejects_rehashed_false_prepared_retained_storage_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas.pilot_security import _digest as security_digest

    spec = _pilot_spec(tmp_path)
    policy, _, retained_root = _security_policy(tmp_path, spec)
    _fake_sandbox(monkeypatch)
    monkeypatch.setattr(
        "av_atlas.ocr_pilot.inspect_media",
        lambda path, **_kwargs: _inventory_for_snapshot(path),
    )
    monkeypatch.setattr(
        "av_atlas.ocr_pilot._extract_frame",
        lambda _path, timestamp_ms, output, _policy, **_kwargs: output.write_bytes(
            f"synthetic-frame-{timestamp_ms}".encode()
        ),
    )
    pilot = retained_root / "pilot"
    original_manifest = prepare_pilot(spec, pilot, policy)
    receipt_path = pilot / "pilot_security_receipt.json"
    manifest_path = pilot / "pilot_manifest.json"
    original_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    false_values: tuple[tuple[str, object], ...] = (
        ("root_identity_sha256", "d" * 64),
        ("filesystem_type", "xfs"),
        ("byte_ceiling", int(original_receipt["retained_storage"]["byte_ceiling"]) - 1),
        ("reserve_bytes", int(original_receipt["retained_storage"]["reserve_bytes"]) - 1),
        ("decision", "reviewed-encrypted-volume"),
    )

    for field, false_value in false_values:
        receipt = json.loads(json.dumps(original_receipt))
        receipt["retained_storage"][field] = false_value
        receipt["receipt_hash"] = security_digest(receipt, "receipt_hash")
        receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")

        manifest = json.loads(json.dumps(original_manifest))
        manifest["pilot_security"]["receipt_sha256"] = sha256_file(receipt_path)
        manifest["pilot_security"]["retained_storage"] = receipt["retained_storage"]
        manifest["manifest_hash"] = _digest(manifest)
        manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")

        with pytest.raises(AtlasError, match="retained-storage boundary"):
            validate_pilot_security_artifacts(
                pilot,
                security_policy_path=policy,
            )


def test_current_annotation_packages_are_private_bounded_and_rollback_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import ocr_pilot

    spec = _pilot_spec(tmp_path)
    policy, _, retained_root = _security_policy(tmp_path, spec)
    _fake_sandbox(monkeypatch)
    monkeypatch.setattr(
        "av_atlas.ocr_pilot.inspect_media",
        lambda path, **_kwargs: _inventory_for_snapshot(path),
    )
    monkeypatch.setattr(
        "av_atlas.ocr_pilot._extract_frame",
        lambda _path, timestamp_ms, output, _policy, **_kwargs: output.write_bytes(
            f"synthetic-frame-{timestamp_ms}".encode()
        ),
    )
    pilot = retained_root / "pilot"
    prepare_pilot(spec, pilot, policy)
    original_write = ocr_pilot._write_pinned_package_bytes
    writes = 0

    def fail_second(*args: object, **kwargs: object) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise AtlasError("injected bounded annotation write failure")
        original_write(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ocr_pilot, "_write_pinned_package_bytes", fail_second)
    with pytest.raises(AtlasError, match="injected bounded annotation write failure"):
        make_annotation_packages(pilot, policy)
    assert not (pilot / "annotator_A").exists()
    assert not (pilot / "annotator_B").exists()
    assert not list(pilot.glob("annotation-*.pending.json"))

    monkeypatch.setattr(ocr_pilot, "_write_pinned_package_bytes", original_write)
    make_annotation_packages(pilot, policy)
    for label in ("A", "B"):
        package = pilot / f"annotator_{label}"
        annotation = package / "annotation.json"
        assert package.stat().st_mode & 0o777 == 0o700
        assert (package / "frames").stat().st_mode & 0o777 == 0o700
        assert annotation.stat().st_mode & 0o777 == 0o600
        assert json.loads(annotation.read_text(encoding="utf-8"))["annotator_pseudonym"] == (
            f"ANNOTATOR_{label}"
        )
    assert not list(pilot.glob("annotation-*.pending.json"))


def test_valid_prepared_frozen_to_sandboxed_ocr_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _pilot_spec(tmp_path)
    policy, root, retained_root = _security_policy(tmp_path, spec)
    _fake_sandbox(monkeypatch)

    def inspect(path: Path, **_kwargs: object) -> dict[str, Any]:
        return _inventory_for_snapshot(path)

    def extract(
        _path: Path,
        timestamp_ms: int,
        output: Path,
        _native_policy: NativeInputPolicy,
        **_kwargs: object,
    ) -> None:
        output.write_bytes(f"synthetic-frame-{timestamp_ms}".encode())

    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.ocr_pilot._extract_frame", extract)
    pilot = retained_root / "pilot"
    prepared = prepare_pilot(spec, pilot, policy)
    frozen = _frozen_manifest(prepared)
    validate_instance("ocr_pilot_manifest", frozen, "frozen sandboxed pilot")
    frozen_path = pilot / "frozen.json"
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    frozen_path.chmod(0o600)
    _fake_sandbox(monkeypatch)
    monkeypatch.setattr(
        "av_atlas.ocr_pilot.inspect_ocr",
        lambda *_args, **_kwargs: _ocr_inventory(),
    )

    def fake_ocr(_self: object, context: object) -> SimpleNamespace:
        run_dir = context.run_dir  # type: ignore[attr-defined]
        (run_dir / "ocr_observations.jsonl").write_text("", encoding="utf-8")
        (run_dir / "ocr_runtime.json").write_text(
            json.dumps(
                {
                    "wall_seconds": 0.01,
                    "cpu_seconds": 0.01,
                    "peak_rss_kb": 1024,
                    "retries": 0,
                    "timeouts": 0,
                    "frames_processed": 20,
                    "failures": 0,
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(result=SimpleNamespace(status="success_zero"))

    monkeypatch.setattr("av_atlas.ocr_pilot.TesseractOcrAdapter.run", fake_ocr)
    output = retained_root / "ocr-output"
    result = run_pilot_ocr(pilot, frozen_path, output, policy)
    assert result["observations"] == 0
    assert result["frames_processed"] == 60
    assert not any(root.iterdir())
    rendered = "".join(
        path.read_text(encoding="utf-8") for path in output.iterdir() if path.is_file()
    )
    assert str(root) not in rendered
    assert str(tmp_path) not in rendered

    moved_frozen = pilot / "frozen-original.json"
    mutated = False

    def mutate_frozen_during_ocr(_self: object, context: object) -> SimpleNamespace:
        nonlocal mutated
        result = fake_ocr(_self, context)
        if not mutated:
            frozen_path.rename(moved_frozen)
            replacement = {**frozen, "disagreement_count": 1, "manifest_hash": ""}
            replacement["manifest_hash"] = _digest(replacement)
            frozen_path.write_text(json.dumps(replacement), encoding="utf-8")
            frozen_path.chmod(0o600)
            mutated = True
        return result

    monkeypatch.setattr(
        "av_atlas.ocr_pilot.TesseractOcrAdapter.run",
        mutate_frozen_during_ocr,
    )
    replaced_output = retained_root / "replaced-input-ocr-output"
    with pytest.raises(AtlasError, match="JSON input identity changed"):
        run_pilot_ocr(pilot, frozen_path, replaced_output, policy)
    assert not replaced_output.exists()
    frozen_path.unlink()
    moved_frozen.rename(frozen_path)

    native_calls = 0

    def forbidden_native(*_args: object, **_kwargs: object) -> None:
        nonlocal native_calls
        native_calls += 1
        raise AssertionError("malformed frozen frame must fail before native execution")

    monkeypatch.setattr("av_atlas.ocr_pilot._runner_for_policy", forbidden_native)
    for field, bad_value in (("path", "../../private.png"), ("size_bytes", 0)):
        malformed = json.loads(json.dumps(frozen))
        malformed["frames"][0][field] = bad_value
        malformed["manifest_hash"] = _digest(malformed)
        malformed_path = pilot / f"malformed-{field}.json"
        malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
        malformed_path.chmod(0o600)
        with pytest.raises(AtlasError, match="schema validation failed"):
            run_pilot_ocr(
                pilot,
                malformed_path,
                retained_root / f"malformed-output-{field}",
                policy,
            )
    assert native_calls == 0


@pytest.mark.parametrize(
    ("expiry_kind", "message"),
    (("policy", "policy has expired"), ("storage-review", "storage review has expired")),
)
def test_mid_source_policy_or_storage_review_expiry_stops_prepare_and_emits_no_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expiry_kind: str,
    message: str,
) -> None:
    from av_atlas import pilot_security

    spec = _pilot_spec(tmp_path)
    policy_path, root, retained_root = _security_policy(tmp_path, spec)
    policy_value = json.loads(policy_path.read_text(encoding="utf-8"))
    policy_value["expires_at"] = (
        "2099-01-01T00:00:00+00:00" if expiry_kind == "policy" else "2200-01-01T00:00:00+00:00"
    )
    policy_value["storage"]["review_expires_at"] = (
        "2200-01-01T00:00:00+00:00" if expiry_kind == "policy" else "2099-01-01T00:00:00+00:00"
    )
    policy_value["policy_hash"] = pilot_security._digest(policy_value, "policy_hash")
    policy_path.write_text(json.dumps(policy_value), encoding="utf-8")
    policy_path.chmod(0o600)
    expired = False
    monkeypatch.setattr(
        pilot_security,
        "_utc_now",
        lambda: datetime(2100 if expired else 2026, 1, 1, tzinfo=UTC),
    )
    _fake_sandbox(monkeypatch)
    inspect_calls = 0
    extract_calls = 0

    def inspect(path: Path, **_kwargs: object) -> dict[str, Any]:
        nonlocal inspect_calls
        inspect_calls += 1
        return _inventory_for_snapshot(path)

    def extract(
        _path: Path,
        timestamp_ms: int,
        output: Path,
        _native_policy: NativeInputPolicy,
        **_kwargs: object,
    ) -> None:
        nonlocal expired, extract_calls
        extract_calls += 1
        output.write_bytes(f"synthetic-frame-{timestamp_ms}".encode())
        expired = True

    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.ocr_pilot._extract_frame", extract)
    output = retained_root / "expired-output"
    with pytest.raises(AtlasError, match=message):
        prepare_pilot(spec, output, policy_path)

    assert inspect_calls == 1
    assert extract_calls == 1
    assert not output.exists()
    assert not any(root.iterdir())


def test_policy_bound_runner_rechecks_policy_and_root_before_every_native_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import ocr_pilot
    from av_atlas.native_process import PROFILE_SHA256, PROFILE_VERSION
    from av_atlas.pilot_security import (
        load_pilot_security_policy,
        open_verified_pilot_root,
        open_verified_retained_root,
    )

    spec = _pilot_spec(tmp_path)
    policy_path, root_path, _ = _security_policy(tmp_path, spec)
    policy = load_pilot_security_policy(policy_path)
    inventory_record = _inventory()
    inventory_record["profile_version"] = PROFILE_VERSION
    inventory_record["profile_sha256"] = PROFILE_SHA256
    policy["sandbox"]["profile_contract_version"] = PROFILE_VERSION
    policy["sandbox"]["profile_sha256"] = PROFILE_SHA256
    inventory = SimpleNamespace(as_record=lambda: inventory_record)
    monkeypatch.setattr(
        ocr_pilot,
        "load_bubblewrap_inventory",
        lambda **_kwargs: inventory,
    )
    executed = 0

    class GuardRecordingRunner:
        def __init__(
            self,
            _inventory_value: object,
            _limits: object,
            *,
            before_run: object,
        ) -> None:
            self.before_run = before_run

        def run(self, _invocation: object) -> object:
            nonlocal executed
            self.before_run()  # type: ignore[operator]
            executed += 1
            return object()

    monkeypatch.setattr(ocr_pilot, "BubblewrapNativeRunner", GuardRecordingRunner)
    with (
        open_verified_pilot_root(policy) as root,
        open_verified_retained_root(policy) as retained_root,
    ):
        runner, _ = _runner_for_policy(policy, root, retained_root)
        runner.run(object())  # type: ignore[arg-type]
        assert executed == 1
        policy["expires_at"] = "2000-01-01T00:00:00+00:00"
        with pytest.raises(AtlasError, match="policy has expired"):
            runner.run(object())  # type: ignore[arg-type]
        assert executed == 1

    policy = load_pilot_security_policy(policy_path)
    policy["sandbox"]["profile_contract_version"] = PROFILE_VERSION
    policy["sandbox"]["profile_sha256"] = PROFILE_SHA256
    with (
        open_verified_pilot_root(policy) as root,
        open_verified_retained_root(policy) as retained_root,
    ):
        runner, _ = _runner_for_policy(policy, root, retained_root)
        root_path.chmod(0o755)
        try:
            with pytest.raises(AtlasError, match="identity, owner, or permissions"):
                runner.run(object())  # type: ignore[arg-type]
            assert executed == 1
        finally:
            root_path.chmod(0o700)


def test_mid_source_policy_expiry_stops_pilot_ocr_and_emits_no_success_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import pilot_security

    spec = _pilot_spec(tmp_path)
    policy, root, retained_root = _security_policy(tmp_path, spec)
    _fake_sandbox(monkeypatch)
    monkeypatch.setattr(
        "av_atlas.ocr_pilot.inspect_media",
        lambda path, **_kwargs: _inventory_for_snapshot(path),
    )
    monkeypatch.setattr(
        "av_atlas.ocr_pilot._extract_frame",
        lambda _path, timestamp_ms, output, _policy, **_kwargs: output.write_bytes(
            f"synthetic-frame-{timestamp_ms}".encode()
        ),
    )
    pilot = retained_root / "pilot"
    frozen = _frozen_manifest(prepare_pilot(spec, pilot, policy))
    frozen_path = pilot / "frozen.json"
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    frozen_path.chmod(0o600)

    expired = False
    monkeypatch.setattr(
        pilot_security,
        "_utc_now",
        lambda: datetime(2100 if expired else 2026, 1, 1, tzinfo=UTC),
    )
    _fake_sandbox(monkeypatch)
    monkeypatch.setattr(
        "av_atlas.ocr_pilot.inspect_ocr",
        lambda *_args, **_kwargs: _ocr_inventory(),
    )
    ocr_calls = 0

    def fake_ocr(_self: object, context: object) -> SimpleNamespace:
        nonlocal expired, ocr_calls
        ocr_calls += 1
        run_dir = context.run_dir  # type: ignore[attr-defined]
        (run_dir / "ocr_observations.jsonl").write_text("", encoding="utf-8")
        (run_dir / "ocr_runtime.json").write_text(
            json.dumps(
                {
                    "wall_seconds": 0.01,
                    "cpu_seconds": 0.01,
                    "peak_rss_kb": 1024,
                    "retries": 0,
                    "timeouts": 0,
                    "frames_processed": 20,
                    "failures": 0,
                }
            ),
            encoding="utf-8",
        )
        expired = True
        return SimpleNamespace(result=SimpleNamespace(status="success_zero"))

    monkeypatch.setattr("av_atlas.ocr_pilot.TesseractOcrAdapter.run", fake_ocr)
    output = retained_root / "expired-ocr-output"
    with pytest.raises(AtlasError, match="policy has expired"):
        run_pilot_ocr(pilot, frozen_path, output, policy)

    assert ocr_calls == 1
    assert not output.exists()
    assert not any(root.iterdir())
    assert {item.name for item in retained_root.iterdir()} == {pilot.name}


def test_synthetic_check_rejects_output_outside_policy_retained_root_before_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas.ocr_pilot import run_synthetic_pilot_security_check

    media = make_m2b_fixture(tmp_path / "controlled-fixture")
    media_hash = sha256_file(media)
    source_id = source_id_from_sha256(media_hash)
    rights = tmp_path / "synthetic.rights.json"
    create_rights_manifest(
        media,
        rights,
        "m2b3-retained-output-test",
        "synthetic-controlled",
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    spec = tmp_path / "synthetic-pilot-spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "pilot_id": "PILOT_M2B3_RETAINED_OUTPUT_TEST",
                "source_sha256": media_hash,
                "source_id": source_id,
                "timestamp_ms": 1000,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    policy, root, retained_root = _security_policy(
        tmp_path,
        spec,
        max_source_bytes=64 * 1024 * 1024,
        max_temporary_bytes=256 * 1024 * 1024,
    )
    sandbox_calls = 0

    def forbidden_sandbox(*_args: object, **_kwargs: object) -> None:
        nonlocal sandbox_calls
        sandbox_calls += 1
        raise AssertionError("out-of-policy output must fail before sandbox execution")

    monkeypatch.setattr("av_atlas.ocr_pilot._runner_for_policy", forbidden_sandbox)
    output = tmp_path / "outside-retained-root"
    with pytest.raises(AtlasError, match="direct child"):
        run_synthetic_pilot_security_check(media, rights, spec, policy, output)

    assert sandbox_calls == 0
    assert not output.exists()
    assert not any(root.iterdir())
    assert not any(retained_root.iterdir())


def test_synthetic_check_rejects_exposed_source_before_authorization_or_native_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas.ocr_pilot import run_synthetic_pilot_security_check

    exposed_source = Path("/usr/bin/ffprobe")
    if not exposed_source.exists():
        pytest.skip("system FFprobe path is unavailable")
    calls = 0

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("exposed source must fail before authorization or native work")

    monkeypatch.setattr("av_atlas.ocr_pilot.preflight_authorized_source", forbidden)
    monkeypatch.setattr("av_atlas.ocr_pilot._runner_for_policy", forbidden)
    with pytest.raises(AtlasError, match="overlaps a sandbox-exposed"):
        run_synthetic_pilot_security_check(
            exposed_source,
            tmp_path / "unused-rights.json",
            tmp_path / "unused-spec.json",
            tmp_path / "unused-policy.json",
            tmp_path / "unused-output",
        )
    assert calls == 0


def test_mid_unit_policy_expiry_stops_synthetic_check_before_receipt_or_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import pilot_security

    media = make_m2b_fixture(tmp_path / "controlled-fixture")
    media_hash = sha256_file(media)
    source_id = source_id_from_sha256(media_hash)
    rights = tmp_path / "synthetic.rights.json"
    create_rights_manifest(
        media,
        rights,
        "m2b3-expiry-test",
        "synthetic-controlled",
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    spec = tmp_path / "synthetic-pilot-spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "pilot_id": "PILOT_M2B3_EXPIRY_TEST",
                "source_sha256": media_hash,
                "source_id": source_id,
                "timestamp_ms": 1000,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    policy, root, retained_root = _security_policy(
        tmp_path,
        spec,
        max_source_bytes=64 * 1024 * 1024,
        max_temporary_bytes=256 * 1024 * 1024,
    )
    _fake_sandbox(monkeypatch)
    monkeypatch.setattr(
        "av_atlas.ocr_pilot.inspect_media",
        lambda path, **_kwargs: _inventory_for_snapshot(path),
    )
    monkeypatch.setattr(
        "av_atlas.ocr_pilot._extract_frame",
        lambda _path, _timestamp, output, _policy, **_kwargs: output.write_bytes(
            b"synthetic-frame"
        ),
    )
    monkeypatch.setattr(
        "av_atlas.ocr_pilot.inspect_ocr",
        lambda *_args, **_kwargs: {"state": "available"},
    )
    expired = False
    monkeypatch.setattr(
        pilot_security,
        "_utc_now",
        lambda: datetime(2100 if expired else 2026, 1, 1, tzinfo=UTC),
    )
    ocr_calls = 0

    def fake_ocr(_self: object, context: object) -> SimpleNamespace:
        nonlocal expired, ocr_calls
        ocr_calls += 1
        run_dir = context.run_dir  # type: ignore[attr-defined]
        (run_dir / "ocr_observations.jsonl").write_text("", encoding="utf-8")
        (run_dir / "ocr_dependency.json").write_text(
            json.dumps({"state": "available"}), encoding="utf-8"
        )
        (run_dir / "ocr_runtime.json").write_text(
            json.dumps({"frames_processed": 1, "timeouts": 0, "retries": 0}),
            encoding="utf-8",
        )
        expired = True
        return SimpleNamespace(result=SimpleNamespace(status="success_zero"))

    monkeypatch.setattr("av_atlas.ocr_pilot.TesseractOcrAdapter.run", fake_ocr)
    output = retained_root / "expired-synthetic-output"
    with pytest.raises(AtlasError, match="policy has expired"):
        from av_atlas.ocr_pilot import run_synthetic_pilot_security_check

        run_synthetic_pilot_security_check(media, rights, spec, policy, output)

    assert ocr_calls == 1
    assert not output.exists()
    assert not any(root.iterdir())


@pytest.mark.parametrize("failure", [AtlasError("synthetic parser failure"), KeyboardInterrupt()])
def test_pilot_prepare_cleans_private_and_public_output_on_failure_or_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    spec = _pilot_spec(tmp_path)
    policy, root, retained_root = _security_policy(tmp_path, spec)
    _fake_sandbox(monkeypatch)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", fail)
    output = retained_root / "pilot"
    with pytest.raises(type(failure)):
        prepare_pilot(spec, output, policy)
    assert not output.exists()
    assert not any(root.iterdir())


def test_pilot_policy_spec_expiry_and_root_replacement_fail_before_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas.pilot_security import _digest as security_digest

    spec = _pilot_spec(tmp_path)
    policy_path, root, retained_root = _security_policy(tmp_path, spec)
    parser_calls = 0

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal parser_calls
        parser_calls += 1
        raise AssertionError("invalid private policy must fail before parsing")

    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", forbidden)
    monkeypatch.setattr("av_atlas.ocr_pilot._extract_frame", forbidden)
    monkeypatch.setattr("av_atlas.ocr_pilot._runner_for_policy", forbidden)

    changed = json.loads(spec.read_text())
    changed["selection_method"] = "changed after policy freeze"
    spec.write_text(json.dumps(changed))
    with pytest.raises(AtlasError, match="does not match the pilot specification"):
        prepare_pilot(spec, retained_root / "spec-mismatch", policy_path)
    assert parser_calls == 0

    # Restore the exact spec and create a separately valid policy to test expiry.
    spec = _pilot_spec(tmp_path / "expiry")
    policy_path, _, expired_retained_root = _security_policy(tmp_path / "expiry", spec)
    value = json.loads(policy_path.read_text())
    value["expires_at"] = "2000-01-01T00:00:00+00:00"
    value["policy_hash"] = security_digest(value, "policy_hash")
    policy_path.write_text(json.dumps(value))
    policy_path.chmod(0o600)
    with pytest.raises(AtlasError, match="has expired"):
        prepare_pilot(spec, expired_retained_root / "expired", policy_path)
    assert parser_calls == 0

    spec = _pilot_spec(tmp_path / "replacement")
    policy_path, root, replacement_retained_root = _security_policy(tmp_path / "replacement", spec)
    moved = root.with_name("pilot-private-original")
    root.rename(moved)
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    sandbox_calls = 0

    def forbidden_sandbox(*_args: object, **_kwargs: object) -> None:
        nonlocal sandbox_calls
        sandbox_calls += 1
        raise AssertionError("invalid private root must fail before Bubblewrap inventory")

    monkeypatch.setattr("av_atlas.ocr_pilot._runner_for_policy", forbidden_sandbox)
    monkeypatch.setattr("av_atlas.ocr_pilot.inspect_media", forbidden)
    with pytest.raises(AtlasError, match="identity"):
        prepare_pilot(spec, replacement_retained_root / "root-replaced", policy_path)
    assert parser_calls == 0
    assert sandbox_calls == 0
    assert not (replacement_retained_root / "root-replaced").exists()


def test_pilot_ocr_requires_policy_and_rejects_historical_execution(
    tmp_path: Path,
) -> None:
    pilot = tmp_path / "pilot"
    pilot.mkdir()
    frozen = {
        "schema_version": "1.0.0",
        "pilot_id": "PILOT_HISTORICAL",
        "state": "adjudicated_frozen",
        "sources": [],
        "frames": [],
        "manifest_hash": "",
    }
    frozen["manifest_hash"] = _digest(frozen)
    frozen_path = pilot / "frozen.json"
    frozen_path.write_text(json.dumps(frozen))
    with pytest.raises(AtlasError, match="explicit private security policy"):
        run_pilot_ocr(pilot, frozen_path, tmp_path / "ocr")

    spec = tmp_path / "spec.json"
    spec.write_text('{"pilot_id":"PILOT_HISTORICAL"}\n')
    policy, _, retained_root = _security_policy(tmp_path, spec)
    historical_pilot = retained_root / "historical-pilot"
    historical_pilot.mkdir(mode=0o700)
    frozen["ocr_configuration_sha256"] = sha256_file(Path(__file__).parents[2] / "configs/m2b.yaml")
    frozen["manifest_hash"] = _digest(frozen)
    historical_frozen = historical_pilot / "frozen.json"
    historical_frozen.write_text(json.dumps(frozen), encoding="utf-8")
    historical_frozen.chmod(0o600)
    with pytest.raises(AtlasError, match="manifest contract 1.1.0 or 1.2.0"):
        run_pilot_ocr(
            historical_pilot,
            historical_frozen,
            retained_root / "ocr",
            policy,
        )


def test_historical_pilot_manifest_remains_schema_compatible(tmp_path: Path) -> None:
    pilot = tmp_path / "pilot"
    (pilot / "frames").mkdir(parents=True)
    frames = []
    for index in range(80):
        frame_id = f"FRM_HISTORICAL_{index:04d}"
        frames.append(
            {
                "frame_id": frame_id,
                "source_id": f"SRC_{index % 3:012X}",
                "timestamp_ms": index * 1000,
                "split": "calibration" if index < 20 else "evaluation",
                "categories": ["historical"],
                "difficulty": ["controlled"],
                "path": f"frames/{frame_id}.png",
                "sha256": "0" * 64,
            }
        )
    historical = {
        "schema_version": "1.0.0",
        "pilot_id": "PILOT_HISTORICAL",
        "state": "prepared_unannotated",
        "selection_protocol": {
            "method": "historical",
            "random_seed": None,
            "inclusion_criteria": ["historical"],
            "exclusion_criteria": ["none"],
            "duplicate_frame_policy": "reject",
        },
        "sources": [{"source_id": f"SRC_{index:012X}"} for index in range(3)],
        "frames": frames,
        "counts": {"sources": 3, "calibration_frames": 20, "evaluation_frames": 60},
        "privacy": {"source_media_copied": False},
        "manifest_hash": "0" * 64,
    }
    validate_instance("ocr_pilot_manifest", historical, "historical pilot")


def test_controlled_release_manifest_is_private_and_claim_bounded() -> None:
    root = Path(__file__).parents[2]
    raw = (root / "docs/releases/M2B_CONTROLLED_BASELINE_V1.json").read_text()
    value = json.loads(raw)
    assert "/home/" not in raw
    assert value["scope"] == "four-frame project-authored synthetic controlled fixture only"
    assert value["claims"] == {
        "real_media_accuracy": False,
        "semantic_visual_understanding": False,
        "full_m2_complete": False,
    }
    assert (
        value["frozen_hashes"]["observations_semantic"]
        == "f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060"
    )
