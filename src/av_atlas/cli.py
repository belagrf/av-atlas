"""AV-Atlas command-line interface."""

from __future__ import annotations

import argparse
import importlib.util
import json
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
from av_atlas.io import write_json
from av_atlas.media import inspect_media, tool_version
from av_atlas.ocr import inspect_ocr
from av_atlas.ocr_evaluation import benchmark_ocr, evaluate_ocr
from av_atlas.ocr_pilot import (
    compare_annotations,
    evaluate_pilot,
    freeze_pilot,
    make_annotation_packages,
    prepare_pilot,
    run_pilot_ocr,
)
from av_atlas.pipeline import export_run, initialize_run, resume_run
from av_atlas.rights import OPERATIONS, create_rights_manifest
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
    inspect_subtitles = commands.add_parser(
        "inspect-subtitles", help="list embedded subtitle tracks without extraction"
    )
    inspect_subtitles.add_argument("media", type=Path)
    inspect_ocr_parser = commands.add_parser(
        "inspect-ocr", help="inspect the local OCR dependency without installing it"
    )
    inspect_ocr_parser.add_argument(
        "--local-private-diagnostic",
        action="store_true",
        help="include full local paths; never attach this output to exported runs",
    )
    run = commands.add_parser("run", help="process a sidecar fixture into a complete run")
    run.add_argument("media", type=Path)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--rights-manifest", type=Path)
    run.add_argument("--operation", choices=OPERATIONS, default="analysis")
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
    return parser


def _doctor() -> int:
    required = {
        "python": platform.python_version(),
        **{name: tool_version(name) for name in ("ffmpeg", "ffprobe")},
    }
    optional = {
        "ocr": inspect_ocr(),
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
            inventory = inspect_media(args.media)
            if args.output:
                write_json(args.output, inventory)
            else:
                print(json.dumps(inventory, indent=2, sort_keys=True))
        elif args.command == "inspect-subtitles":
            inventory = inspect_media(args.media)
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
            print(json.dumps(prepare_pilot(args.spec, args.output), indent=2, sort_keys=True))
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
            report = run_pilot_ocr(args.pilot_dir, args.frozen_manifest, args.output)
            print(json.dumps(report, indent=2, sort_keys=True))
    except AtlasError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
