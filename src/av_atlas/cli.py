"""AV-Atlas command-line interface."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import sys
from pathlib import Path

from av_atlas import __version__
from av_atlas.errors import AtlasError
from av_atlas.evaluation import evaluate_run
from av_atlas.fixture import (
    make_fixture,
    make_m2a_fixture,
    make_m2b_fixture,
    make_modality_edge_fixtures,
)
from av_atlas.io import write_json_new
from av_atlas.media import inspect_media, tool_version
from av_atlas.native_process import (
    BUBBLEWRAP_INSTALL_COMMAND,
    NativeResourceLimits,
    inspect_bubblewrap,
)
from av_atlas.ocr import inspect_ocr
from av_atlas.ocr_evaluation import benchmark_ocr, evaluate_ocr
from av_atlas.ocr_pilot import (
    compare_annotations,
    evaluate_pilot,
    freeze_pilot,
    make_annotation_packages,
    prepare_pilot,
    run_pilot_ocr,
    run_synthetic_pilot_security_check,
    validate_current_pilot_sandbox,
    validate_pilot_security_artifacts,
)
from av_atlas.pilot_security import (
    DEFAULT_MAX_SOURCE_BYTES as DEFAULT_PILOT_MAX_SOURCE_BYTES,
)
from av_atlas.pilot_security import (
    DEFAULT_MAX_TEMPORARY_BYTES as DEFAULT_PILOT_MAX_TEMPORARY_BYTES,
)
from av_atlas.pilot_security import (
    DEFAULT_RESERVE_BYTES,
    create_pilot_security_policy,
    load_pilot_security_policy,
    open_verified_pilot_root,
    policy_resource_limits,
    preflight_pilot_security_root,
    validate_private_policy_output_path,
)
from av_atlas.pipeline import export_run, initialize_run, resume_run
from av_atlas.rights import OPERATIONS, create_rights_manifest, required_permissions_for_run_mode
from av_atlas.stable_input import (
    DEFAULT_MAX_SOURCE_BYTES,
    DEFAULT_MAX_TEMPORARY_BYTES,
    StableInputPolicy,
    acquire_authorized_input,
)
from av_atlas.validation import validate_run


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="av-atlas")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check required and optional local dependencies")
    fixture = commands.add_parser("make-fixture", help="generate deterministic synthetic media")
    fixture.add_argument("--output", type=Path, required=True)
    fixture.add_argument("--profile", choices=["m1", "m2a", "m2b"], default="m1")
    fixture.add_argument("--include-edge-fixtures", action="store_true")
    rights = commands.add_parser("make-rights", help="create a source-bound operator declaration")
    rights.add_argument("media", type=Path)
    rights.add_argument("--output", type=Path, required=True)
    rights.add_argument(
        "--operator-id", required=True, help="input is hashed; raw identity is not stored"
    )
    rights.add_argument(
        "--basis",
        required=True,
        choices=[
            "owned",
            "licensed",
            "public-domain",
            "synthetic-controlled",
            "other-documented-authorization",
        ],
    )
    rights.add_argument("--allow", action="append", choices=OPERATIONS, required=True)
    rights.add_argument("--restriction", action="append", default=[])
    rights.add_argument("--expires-at")
    rights.add_argument("--notes", default="")
    rights.add_argument("--independently-reviewed", action="store_true")
    rights.add_argument("--review-record")
    inspect = commands.add_parser("inspect", help="inventory a media source without modifying it")
    inspect.add_argument("media", type=Path)
    inspect.add_argument("--output", type=Path)
    _add_inspection_rights_arguments(inspect)
    inspect_subtitles = commands.add_parser(
        "inspect-subtitles", help="list embedded subtitle tracks without extraction"
    )
    inspect_subtitles.add_argument("media", type=Path)
    _add_inspection_rights_arguments(inspect_subtitles)
    inspect_ocr_parser = commands.add_parser(
        "inspect-ocr", help="inspect the local OCR dependency without installing it"
    )
    inspect_ocr_parser.add_argument(
        "--local-private-diagnostic",
        action="store_true",
        help="include full local paths; never attach this output to exported runs",
    )
    inspect_bubblewrap_parser = commands.add_parser(
        "inspect-bubblewrap",
        help="inspect the mandatory local pilot sandbox dependency",
    )
    inspect_bubblewrap_parser.add_argument(
        "--local-private-diagnostic",
        action="store_true",
        help="include the resolved local path; never export or publish this output",
    )
    security_create = commands.add_parser(
        "pilot-security-create",
        help="create a private, pilot-bound storage and sandbox policy",
    )
    security_create.add_argument("--root", type=Path, required=True)
    security_create.add_argument("--pilot-id", required=True)
    security_create.add_argument("--pilot-spec", type=Path, required=True)
    security_create.add_argument("--output", type=Path, required=True)
    security_create.add_argument("--expires-at", required=True)
    security_create.add_argument(
        "--storage-decision",
        required=True,
        choices=[
            "verified-tmpfs",
            "reviewed-encrypted-volume",
            "reviewed-remanence-acceptance",
        ],
    )
    security_create.add_argument(
        "--source-byte-ceiling", type=int, default=DEFAULT_PILOT_MAX_SOURCE_BYTES
    )
    security_create.add_argument(
        "--temporary-byte-ceiling", type=int, default=DEFAULT_PILOT_MAX_TEMPORARY_BYTES
    )
    security_create.add_argument("--reserve-bytes", type=int, default=DEFAULT_RESERVE_BYTES)
    security_create.add_argument("--reviewer-pseudonym")
    security_create.add_argument("--review-record")
    security_create.add_argument("--review-expires-at")
    security_create.add_argument("--compensating-control", action="append", default=[])
    security_create.add_argument("--deletion-plan")
    _add_native_resource_limit_arguments(security_create)
    for name, help_text in (
        ("pilot-security-inspect", "inspect a private pilot policy without revealing its root"),
        ("pilot-security-validate", "validate a private pilot policy and its bound root"),
    ):
        security_command = commands.add_parser(name, help=help_text)
        security_command.add_argument("policy", type=Path)
        security_command.add_argument("--pilot-spec", type=Path)
        security_command.add_argument("--pilot-id")
    security_artifacts = commands.add_parser(
        "pilot-security-validate-artifacts",
        help="validate sanitized receipt, rights, and pilot-manifest linkage",
    )
    security_artifacts.add_argument("pilot_dir", type=Path)
    security_artifacts.add_argument("--manifest", type=Path)
    security_artifacts.add_argument("--security-policy", type=Path)
    synthetic_check = commands.add_parser(
        "pilot-security-synthetic-check",
        help="exercise the sandboxed native stack on an authorized controlled fixture",
    )
    synthetic_check.add_argument("media", type=Path)
    synthetic_check.add_argument("rights_manifest", type=Path)
    synthetic_check.add_argument("pilot_spec", type=Path)
    synthetic_check.add_argument("security_policy", type=Path)
    synthetic_check.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="process a sidecar fixture into a complete run")
    run.add_argument("media", type=Path)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--rights-manifest", type=Path)
    run.add_argument("--operation", type=_run_mode, default="analysis")
    run.add_argument("--stop-after", choices=["inventory"], help=argparse.SUPPRESS)
    resume = commands.add_parser("resume", help="idempotently continue an interrupted run")
    resume.add_argument("run_dir", type=Path)
    resume.add_argument("--media", type=Path)
    validate = commands.add_parser("validate", help="validate schemas, evidence, times, and hashes")
    validate.add_argument("run_dir", type=Path)
    export = commands.add_parser("export", help="regenerate views from the canonical ledger")
    export.add_argument("run_dir", type=Path)
    evaluate = commands.add_parser(
        "evaluate", help="evaluate M2A components against versioned gold"
    )
    evaluate.add_argument("run_dir", type=Path)
    evaluate.add_argument("gold", type=Path)
    evaluate.add_argument("--tolerance-ms", type=int, default=200)
    ocr_evaluate = commands.add_parser(
        "evaluate-ocr", help="evaluate frame OCR against versioned synthetic gold"
    )
    ocr_evaluate.add_argument("run_dir", type=Path)
    ocr_evaluate.add_argument("gold", type=Path)
    ocr_benchmark = commands.add_parser(
        "benchmark-ocr", help="run or report the 1/2/4-worker OCR benchmark"
    )
    ocr_benchmark.add_argument("run_dir", type=Path)
    ocr_benchmark.add_argument("gold", type=Path)
    pilot_prepare = commands.add_parser(
        "pilot-prepare", help="prepare an authorized local OCR pilot"
    )
    pilot_prepare.add_argument("spec", type=Path)
    pilot_prepare.add_argument("--output", type=Path, required=True)
    pilot_prepare.add_argument("--security-policy", type=Path, required=True)
    pilot_packages = commands.add_parser(
        "pilot-annotation-packages", help="create two independent blank annotation packages"
    )
    pilot_packages.add_argument("pilot_dir", type=Path)
    pilot_compare = commands.add_parser(
        "pilot-compare-annotations", help="compare two completed human annotation packages"
    )
    pilot_compare.add_argument("pilot_dir", type=Path)
    pilot_compare.add_argument("first", type=Path)
    pilot_compare.add_argument("second", type=Path)
    pilot_compare.add_argument("--output", type=Path, required=True)
    pilot_freeze = commands.add_parser(
        "pilot-freeze", help="freeze completed, adjudicated pilot gold"
    )
    pilot_freeze.add_argument("pilot_dir", type=Path)
    pilot_freeze.add_argument("first", type=Path)
    pilot_freeze.add_argument("second", type=Path)
    pilot_freeze.add_argument("adjudicated", type=Path)
    pilot_freeze.add_argument("--output", type=Path, required=True)
    pilot_evaluate = commands.add_parser(
        "pilot-evaluate", help="evaluate OCR against frozen adjudicated pilot gold"
    )
    pilot_evaluate.add_argument("pilot_dir", type=Path)
    pilot_evaluate.add_argument("frozen_manifest", type=Path)
    pilot_evaluate.add_argument("adjudicated_gold", type=Path)
    pilot_evaluate.add_argument("observations", type=Path)
    pilot_evaluate.add_argument("runtime", type=Path)
    pilot_evaluate.add_argument("--output", type=Path, required=True)
    pilot_run = commands.add_parser(
        "pilot-run-ocr", help="run frozen M2B OCR on a frozen authorized pilot"
    )
    pilot_run.add_argument("pilot_dir", type=Path)
    pilot_run.add_argument("frozen_manifest", type=Path)
    pilot_run.add_argument("--output", type=Path, required=True)
    pilot_run.add_argument("--security-policy", type=Path, required=True)
    return parser


def _add_native_resource_limit_arguments(parser: argparse.ArgumentParser) -> None:
    defaults = NativeResourceLimits()
    parser.add_argument("--wall-timeout-seconds", type=int, default=int(defaults.wall_seconds))
    parser.add_argument("--cpu-time-seconds", type=int, default=defaults.cpu_seconds)
    parser.add_argument("--address-space-bytes", type=int, default=defaults.address_space_bytes)
    parser.add_argument("--output-file-size-bytes", type=int, default=defaults.file_size_bytes)
    parser.add_argument("--open-files", type=int, default=defaults.open_files)
    parser.add_argument("--process-count", type=int, default=defaults.process_count)
    parser.add_argument("--capture-bytes", type=int, default=defaults.stdout_bytes)
    parser.add_argument(
        "--cleanup-timeout-seconds",
        type=int,
        default=int(defaults.termination_grace_seconds),
    )


def _add_inspection_rights_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--rights-manifest", type=Path)
    parser.add_argument(
        "--max-source-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
        help="parser-free source/snapshot byte ceiling",
    )
    parser.add_argument(
        "--max-temporary-bytes",
        type=int,
        default=DEFAULT_MAX_TEMPORARY_BYTES,
        help="private transient snapshot byte ceiling",
    )


def _inspection_policy(args: argparse.Namespace) -> StableInputPolicy:
    policy = StableInputPolicy(
        max_source_bytes=args.max_source_bytes,
        max_temporary_bytes=args.max_temporary_bytes,
    )
    policy.validate()
    return policy


def _validate_inspection_output(source: Path, output: Path | None) -> None:
    if output is None:
        return
    try:
        source_stat = os.lstat(source)
    except OSError:
        return  # Stable-input preflight reports the source failure without parsing.
    try:
        output_stat = os.lstat(output)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise AtlasError("inspection output path cannot be validated safely") from exc
    if (source_stat.st_dev, source_stat.st_ino) == (output_stat.st_dev, output_stat.st_ino):
        raise AtlasError("inspection output must not identify the source file")
    raise AtlasError("inspection output must be a new path; existing targets are not overwritten")


def _run_mode(value: str) -> str:
    try:
        required_permissions_for_run_mode(value)
    except AtlasError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


def _native_resource_limits(args: argparse.Namespace) -> NativeResourceLimits:
    return NativeResourceLimits(
        wall_seconds=args.wall_timeout_seconds,
        cpu_seconds=args.cpu_time_seconds,
        address_space_bytes=args.address_space_bytes,
        file_size_bytes=args.output_file_size_bytes,
        open_files=args.open_files,
        process_count=args.process_count,
        stdout_bytes=args.capture_bytes,
        stderr_bytes=args.capture_bytes,
        termination_grace_seconds=args.cleanup_timeout_seconds,
    )


def _sanitized_pilot_policy_summary(
    policy: dict[str, object], *, root_validation: str
) -> dict[str, object]:
    private_root = policy["private_root"]
    storage = policy["storage"]
    if not isinstance(private_root, dict) or not isinstance(storage, dict):
        raise AtlasError("private pilot security policy has invalid structured fields")
    return {
        "schema_version": policy["schema_version"],
        "contract_version": policy["contract_version"],
        "pilot_id": policy["pilot_id"],
        "pilot_spec_sha256": policy["pilot_spec_sha256"],
        "pilot_spec_size_bytes": policy["pilot_spec_size_bytes"],
        "created_at": policy["created_at"],
        "expires_at": policy["expires_at"],
        "policy_hash": policy["policy_hash"],
        "private_root": {
            "path_redacted": True,
            "identity_bound": True,
            "expected_mode": private_root["expected_mode"],
            "root_validation": root_validation,
        },
        "storage": {
            "decision": storage["decision"],
            "expected_filesystem_type": storage["expected_filesystem_type"],
            "independently_reviewed": storage["independently_reviewed"],
            "review_expires_at": storage["review_expires_at"],
            "secure_erasure_claimed": storage["secure_erasure_claimed"],
        },
        "capacity": policy["capacity"],
        "sandbox": policy["sandbox"],
        "resource_limits": policy["resource_limits"],
        "contains_private_paths": False,
    }


def _doctor() -> int:
    pilot_sandbox = inspect_bubblewrap()
    required = {
        "python": platform.python_version(),
        **{name: tool_version(name) for name in ("ffmpeg", "ffprobe")},
    }
    optional = {
        "ocr": inspect_ocr(),
        "pilot_sandbox": pilot_sandbox,
        "gpu": "available" if shutil.which("nvidia-smi") else "not detected (not required)",
        "pytorch": (
            "available"
            if importlib.util.find_spec("torch") is not None
            else "not installed (not required for M0/M1)"
        ),
    }
    print(json.dumps({"required": required, "optional": optional}, indent=2, sort_keys=True))
    missing = [name for name, version in required.items() if version is None]
    if missing:
        print(f"Install FFmpeg; missing required tools: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("Required CPU/offline dependencies are available. GPU/model dependencies are optional.")
    if pilot_sandbox["state"] != "available":
        print(
            "M2B.3 pilot execution is unavailable and fails closed. "
            f"Operator installation command: {BUBBLEWRAP_INSTALL_COMMAND}",
            file=sys.stderr,
        )
    return 0


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        if args.command == "doctor":
            return _doctor()
        if args.command == "inspect-ocr":
            print(
                json.dumps(
                    inspect_ocr(include_private_paths=args.local_private_diagnostic),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "inspect-bubblewrap":
            print(
                json.dumps(
                    inspect_bubblewrap(include_private_path=args.local_private_diagnostic),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "pilot-security-create":
            validate_private_policy_output_path(args.output)
            preflight_pilot_security_root(
                args.root,
                args.storage_decision,
                args.source_byte_ceiling,
                args.temporary_byte_ceiling,
                args.reserve_bytes,
            )
            policy = create_pilot_security_policy(
                root=args.root,
                pilot_id=args.pilot_id,
                pilot_spec=args.pilot_spec,
                output=args.output,
                expires_at=args.expires_at,
                storage_decision=args.storage_decision,
                bubblewrap_inventory=inspect_bubblewrap(),
                resource_limits=policy_resource_limits(_native_resource_limits(args)),
                reviewer_pseudonym=args.reviewer_pseudonym,
                review_record=args.review_record,
                review_expires_at=args.review_expires_at,
                compensating_controls=tuple(args.compensating_control),
                deletion_plan=args.deletion_plan,
                max_source_bytes=args.source_byte_ceiling,
                max_temporary_bytes=args.temporary_byte_ceiling,
                reserve_bytes=args.reserve_bytes,
            )
            print(
                json.dumps(
                    _sanitized_pilot_policy_summary(policy, root_validation="creation-measured"),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command in {"pilot-security-inspect", "pilot-security-validate"}:
            policy = load_pilot_security_policy(
                args.policy,
                pilot_id=args.pilot_id,
                pilot_spec=args.pilot_spec,
            )
            root_state = "not-requested"
            if args.command == "pilot-security-validate":
                with open_verified_pilot_root(policy):
                    validate_current_pilot_sandbox(policy)
                    root_state = "passed-with-current-sandbox"
            print(
                json.dumps(
                    _sanitized_pilot_policy_summary(policy, root_validation=root_state),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "pilot-security-validate-artifacts":
            report = validate_pilot_security_artifacts(
                args.pilot_dir,
                args.manifest,
                args.security_policy,
            )
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        if args.command == "pilot-security-synthetic-check":
            report = run_synthetic_pilot_security_check(
                args.media,
                args.rights_manifest,
                args.pilot_spec,
                args.security_policy,
                args.output,
            )
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        if args.command == "make-fixture":
            media = {"m1": make_fixture, "m2a": make_m2a_fixture, "m2b": make_m2b_fixture}[
                args.profile
            ](args.output)
            if args.include_edge_fixtures:
                make_modality_edge_fixtures(args.output)
            print(media)
        elif args.command == "make-rights":
            value = create_rights_manifest(
                args.media,
                args.output,
                args.operator_id,
                args.basis,
                set(args.allow),
                args.restriction,
                args.expires_at,
                args.notes,
                args.independently_reviewed,
                args.review_record,
            )
            print(json.dumps(value, indent=2, sort_keys=True))
        elif args.command == "inspect":
            _validate_inspection_output(args.media, args.output)
            with acquire_authorized_input(
                args.media,
                args.rights_manifest,
                "analysis",
                policy=_inspection_policy(args),
            ) as stable:
                inventory = inspect_media(stable.snapshot_path)
            if args.output:
                try:
                    write_json_new(args.output, inventory)
                except OSError as exc:
                    raise AtlasError("inspection output could not be created safely") from exc
            else:
                print(json.dumps(inventory, indent=2, sort_keys=True))
        elif args.command == "inspect-subtitles":
            with acquire_authorized_input(
                args.media,
                args.rights_manifest,
                "analysis",
                policy=_inspection_policy(args),
            ) as stable:
                inventory = inspect_media(stable.snapshot_path)
            tracks = [
                stream for stream in inventory["streams"] if stream["codec_type"] == "subtitle"
            ]
            print(
                json.dumps(
                    {"source_id": inventory["source_id"], "tracks": tracks},
                    indent=2,
                    sort_keys=True,
                )
            )
        elif args.command == "run":
            initialize_run(
                args.media,
                args.config,
                args.output,
                args.stop_after,
                args.rights_manifest,
                args.operation,
            )
            if args.stop_after is None:
                validate_run(args.output)
            print(args.output)
        elif args.command == "resume":
            resume_run(args.run_dir, args.media)
            validate_run(args.run_dir)
            print(args.run_dir)
        elif args.command == "validate":
            report = validate_run(args.run_dir)
            print(json.dumps(report, indent=2, sort_keys=True))
        elif args.command == "export":
            validate_run(args.run_dir, write_report=False)
            export_run(args.run_dir)
            print(args.run_dir)
        elif args.command == "evaluate":
            validate_run(args.run_dir, write_report=False)
            report = evaluate_run(args.run_dir, args.gold, args.tolerance_ms)
            print(json.dumps(report, indent=2, sort_keys=True))
        elif args.command == "evaluate-ocr":
            validate_run(args.run_dir, write_report=False)
            print(json.dumps(evaluate_ocr(args.run_dir, args.gold), indent=2, sort_keys=True))
        elif args.command == "benchmark-ocr":
            validate_run(args.run_dir, write_report=False)
            print(json.dumps(benchmark_ocr(args.run_dir, args.gold), indent=2, sort_keys=True))
        elif args.command == "pilot-prepare":
            print(
                json.dumps(
                    prepare_pilot(args.spec, args.output, args.security_policy),
                    indent=2,
                    sort_keys=True,
                )
            )
        elif args.command == "pilot-annotation-packages":
            make_annotation_packages(args.pilot_dir)
            print(args.pilot_dir)
        elif args.command == "pilot-compare-annotations":
            report = compare_annotations(args.pilot_dir, args.first, args.second, args.output)
            print(json.dumps(report, indent=2, sort_keys=True))
        elif args.command == "pilot-freeze":
            frozen = freeze_pilot(
                args.pilot_dir, args.first, args.second, args.adjudicated, args.output
            )
            print(json.dumps(frozen, indent=2, sort_keys=True))
        elif args.command == "pilot-evaluate":
            report = evaluate_pilot(
                args.pilot_dir,
                args.frozen_manifest,
                args.adjudicated_gold,
                args.observations,
                args.runtime,
                args.output,
            )
            print(json.dumps(report, indent=2, sort_keys=True))
        elif args.command == "pilot-run-ocr":
            report = run_pilot_ocr(
                args.pilot_dir,
                args.frozen_manifest,
                args.output,
                args.security_policy,
            )
            print(json.dumps(report, indent=2, sort_keys=True))
    except AtlasError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
