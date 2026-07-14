"""Bounded local frame OCR through a replaceable Tesseract TSV adapter."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import resource
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av_atlas.adapters import AdapterContext
from av_atlas.contracts import AdapterResult, AdapterStatus, Observation
from av_atlas.errors import AtlasError
from av_atlas.io import canonical_json, sha256_file, write_json, write_jsonl
from av_atlas.ocr_tracks import associate_temporal_text

INSTALL_COMMAND = "sudo apt-get install tesseract-ocr tesseract-ocr-eng"
LANGUAGE_DIRECTORY = re.compile(r'List of available languages in "(?P<path>.+)"')


def _completed(args: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        shell=False,
        timeout=timeout,
    )


def _package_record(path: Path) -> dict[str, Any] | None:
    dpkg_query = shutil.which("dpkg-query")
    if dpkg_query is None:
        return None
    try:
        owner = _completed([dpkg_query, "-S", str(path)]).stdout.split(":", 1)[0]
        fields = (
            _completed(
                [
                    dpkg_query,
                    "-W",
                    "-f=${binary:Package}\t${Version}\t${Architecture}\t${source:Package}\t${source:Version}",
                    owner,
                ]
            )
            .stdout.strip()
            .split("\t")
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    package = fields[0].split(":", 1)[0]
    copyright_path = Path("/usr/share/doc") / package / "copyright"
    license_id = "unknown-not-verified"
    license_verification = "package copyright metadata unavailable"
    if copyright_path.is_file():
        try:
            copyright_text = copyright_path.read_text(encoding="utf-8", errors="replace").lower()
            if "apache license" in copyright_text or "licenses/apache-2.0" in copyright_text:
                license_id = "Apache-2.0"
            license_verification = "read installed package copyright metadata"
        except OSError:
            license_verification = "installed package copyright metadata unreadable"
    return {
        "package": fields[0],
        "version": fields[1],
        "architecture": fields[2],
        "source_package": fields[3] or package,
        "source_version": fields[4] or fields[1],
        "license_id": license_id,
        "license_verification": license_verification,
        "license_file": str(copyright_path) if copyright_path.is_file() else None,
        "license_file_sha256": (sha256_file(copyright_path) if copyright_path.is_file() else None),
    }


def _path_class(path: Path) -> str:
    resolved = path.resolve()
    return (
        "system" if str(resolved).startswith(("/usr/", "/bin/", "/opt/")) else "operator-supplied"
    )


def sanitize_ocr_inventory(value: dict[str, Any]) -> dict[str, Any]:
    """Remove host-private absolute paths from ordinary exported dependency records."""
    if value.get("state") != "available":
        return value
    sanitized: dict[str, Any] = json.loads(json.dumps(value))
    executable = Path(sanitized.pop("resolved_executable_path"))
    sanitized["schema_version"] = "1.1.0"
    sanitized["executable"] = {
        "basename": executable.name,
        "path_class": _path_class(executable),
        "sha256": sanitized["executable_sha256"],
        "size_bytes": sanitized["executable_size_bytes"],
    }
    package = sanitized.get("executable_package")
    if package and package.get("license_file"):
        package["license_file_basename"] = Path(package.pop("license_file")).name
    sanitized["discovered_tessdata_directories"] = [
        {"basename": Path(path).name, "path_class": _path_class(Path(path))}
        for path in sanitized.get("discovered_tessdata_directories", [])
    ]
    for item in sanitized.get("language_data", []):
        path = Path(item.pop("path"))
        item["basename"] = path.name
        item["path_class"] = _path_class(path)
        language_package = item.get("package")
        if language_package and language_package.get("license_file"):
            language_package["license_file_basename"] = Path(
                language_package.pop("license_file")
            ).name
    prefix = sanitized.get("tessdata_prefix", {}).get("environment_value")
    sanitized["tessdata_prefix"]["environment_value"] = None
    sanitized["tessdata_prefix"]["path_class"] = (
        _path_class(Path(prefix)) if prefix else "distribution-default"
    )
    sanitized["relevant_environment"] = {
        key: ("set-path-redacted" if key == "TESSDATA_PREFIX" and item else item)
        for key, item in sanitized.get("relevant_environment", {}).items()
    }
    identity_payload = {
        "engine": sanitized["engine"],
        "version": sanitized["version"],
        "executable_sha256": sanitized["executable_sha256"],
        "language_data": [
            (item["language"], item["sha256"]) for item in sanitized["language_data"]
        ],
    }
    sanitized["dependency_identity_sha256"] = hashlib.sha256(
        canonical_json(identity_payload).encode()
    ).hexdigest()
    sanitized["inventory_layers"] = {
        "declared_metadata": "adapter configuration and project BOM",
        "measured_current_host": True,
        "package_manager_claims": bool(sanitized.get("executable_package")),
        "independently_verified_hashes": True,
    }
    return sanitized


def inspect_ocr(executable: str = "auto", *, include_private_paths: bool = False) -> dict[str, Any]:
    """Inventory a local Tesseract installation without network or mutation."""
    path = shutil.which("tesseract") if executable == "auto" else shutil.which(executable)
    if path is None:
        return {
            "schema_version": "1.0.0",
            "state": "unavailable",
            "engine": "tesseract",
            "installation_command": INSTALL_COMMAND,
            "network_accessed": False,
        }
    resolved = Path(path).resolve()
    try:
        version_process = _completed([str(resolved), "--version"])
        version_output = (version_process.stdout + version_process.stderr).strip()
        version_lines = [line.strip() for line in version_output.splitlines() if line.strip()]
        languages_process = _completed([str(resolved), "--list-langs"])
        languages_output = (languages_process.stdout + languages_process.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "schema_version": "1.0.0",
            "state": "unavailable",
            "engine": "tesseract",
            "detail": f"Tesseract inventory failed: {type(exc).__name__}",
            "installation_command": INSTALL_COMMAND,
            "network_accessed": False,
        }
    directory_match = LANGUAGE_DIRECTORY.search(languages_output)
    tessdata_directory = (
        Path(directory_match.group("path")).resolve() if directory_match is not None else None
    )
    languages = sorted(
        line.strip()
        for line in languages_output.splitlines()
        if line.strip() and not line.startswith("List of available languages")
    )
    language_data: list[dict[str, Any]] = []
    if tessdata_directory is not None:
        for language in languages:
            traineddata = tessdata_directory / f"{language}.traineddata"
            if traineddata.is_file():
                language_data.append(
                    {
                        "language": language,
                        "path": str(traineddata),
                        "sha256": sha256_file(traineddata),
                        "size_bytes": traineddata.stat().st_size,
                        "package": _package_record(traineddata),
                        "used_by_default_m2b": language == "eng",
                    }
                )
    discovered = sorted(
        {
            str(path.resolve())
            for path in Path("/usr/share/tesseract-ocr").glob("*/tessdata")
            if path.is_dir()
        }
        | ({str(tessdata_directory)} if tessdata_directory is not None else set())
    )
    relevant_environment = {
        key: os.environ.get(key)
        for key in ("TESSDATA_PREFIX", "OMP_THREAD_LIMIT", "LANG", "LC_ALL", "LC_CTYPE")
    }
    result = {
        "schema_version": "1.0.0",
        "state": "available",
        "engine": "tesseract",
        "resolved_executable_path": str(resolved),
        "executable_sha256": sha256_file(resolved),
        "executable_size_bytes": resolved.stat().st_size,
        "version": version_lines[0] if version_lines else "unknown",
        "leptonica_version": (
            version_lines[1].removeprefix("leptonica-") if len(version_lines) > 1 else "unknown"
        ),
        "reported_build_features": [
            line.removeprefix("Found ") for line in version_lines[2:] if line.startswith("Found ")
        ],
        "version_output": version_lines,
        "executable_package": _package_record(resolved),
        "tessdata_prefix": {
            "environment_value": os.environ.get("TESSDATA_PREFIX"),
            "behavior": (
                "explicit_environment_override"
                if os.environ.get("TESSDATA_PREFIX")
                else "unset_uses_distribution_default"
            ),
        },
        "discovered_tessdata_directories": discovered,
        "available_languages": languages,
        "language_data": language_data,
        "relevant_environment": relevant_environment,
        "network_accessed": False,
    }
    return result if include_private_paths else sanitize_ocr_inventory(result)


@dataclass(frozen=True)
class OcrOutput:
    result: AdapterResult
    records: tuple[dict[str, Any], ...]
    evidence: dict[str, dict[str, Any]]
    artifact_paths: tuple[Path, ...]


def parse_tsv(value: str, minimum_confidence: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        reader = csv.DictReader(io.StringIO(value), delimiter="\t")
        required = {"left", "top", "width", "height", "conf", "text"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("required TSV columns are missing")
        for row_index, row in enumerate(reader, 1):
            text = row.get("text", "")
            confidence = float(row.get("conf", "-1"))
            if text.strip() and confidence >= minimum_confidence:
                left, top, width, height = (
                    int(row[name]) for name in ("left", "top", "width", "height")
                )
                if min(left, top, width, height) < 0 or width == 0 or height == 0:
                    raise ValueError("invalid OCR geometry")
                rows.append(
                    {
                        "row_index": row_index,
                        "text": text,
                        "confidence": confidence,
                        "bbox": [left, top, left + width, top + height],
                    }
                )
    except (KeyError, TypeError, ValueError) as exc:
        raise AtlasError(f"invalid Tesseract TSV output: {exc}") from exc
    return rows


def _preprocessing_filter(config: Any) -> str:
    values = [
        f"scale='min(iw,{config.ocr_resize_max_dimension})':"
        f"'min(ih,{config.ocr_resize_max_dimension})':force_original_aspect_ratio=decrease"
    ]
    if config.ocr_grayscale:
        values.append("format=gray")
    if config.ocr_contrast_normalization:
        values.append("normalize")
    if config.ocr_threshold is not None:
        values.append(f"lut=y='if(gte(val,{config.ocr_threshold}),255,0)'")
    return ",".join(values)


def _process_frame(
    context: AdapterContext,
    dependency: dict[str, Any],
    temporary: Path,
    frame_number: int,
    keyframe: dict[str, Any],
) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
    config = context.config
    source = context.run_dir / str(keyframe["path"])
    if source.is_symlink():
        raise AtlasError("unsafe OCR keyframe symlink")
    source = source.resolve()
    if context.run_dir.resolve() not in source.parents:
        raise AtlasError("unsafe OCR keyframe path traversal")
    if not source.is_file():
        raise AtlasError("OCR keyframe is missing or not a regular file")
    if source.stat().st_size > 8_000_000:
        raise AtlasError("OCR keyframe exceeds the 8 MB input limit")
    if sha256_file(source) != keyframe.get("sha256"):
        raise AtlasError("OCR keyframe content hash mismatch")
    prepared = temporary / f"frame-{frame_number:04d}.png"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AtlasError("ffmpeg is unavailable for OCR preprocessing")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            str(source),
            "-vf",
            _preprocessing_filter(config),
            "-frames:v",
            "1",
            "-y",
            "--",
            str(prepared),
        ],
        check=True,
        capture_output=True,
        shell=False,
        timeout=config.ocr_timeout_seconds,
    )
    if not prepared.is_file() or prepared.stat().st_size == 0:
        raise AtlasError("OCR preprocessing produced no frame")
    if prepared.stat().st_size > 16_000_000:
        raise AtlasError("OCR prepared frame exceeds the 16 MB limit")
    environment = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    completed = subprocess.run(
        [
            dependency["resolved_executable_path"],
            str(prepared),
            "stdout",
            "-l",
            "+".join(config.ocr_languages),
            "--psm",
            str(config.ocr_page_segmentation_mode),
            "--oem",
            str(config.ocr_engine_mode),
            "tsv",
        ],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
        timeout=config.ocr_timeout_seconds,
        env=environment,
    )
    if len(completed.stdout.encode("utf-8")) > 8_000_000:
        raise AtlasError("Tesseract TSV output exceeds the 8 MB limit")
    return (
        frame_number,
        parse_tsv(completed.stdout, config.ocr_min_confidence),
        {
            "keyframe_id": keyframe["keyframe_id"],
            "shot_id": keyframe["shot_id"],
            "timestamp_ms": keyframe["timestamp_ms"],
            "source_frame_evidence_ref": keyframe["evidence_ref"],
            "state": "succeeded",
            "warning": None,
        },
    )


def _language_identity(dependency: dict[str, Any], languages: tuple[str, ...]) -> str:
    hashes = {item["language"]: item["sha256"] for item in dependency.get("language_data", [])}
    return "+".join(f"{language}:sha256:{hashes[language]}" for language in languages)


class TesseractOcrAdapter:
    name = "ocr_frame"

    def run(self, context: AdapterContext) -> OcrOutput:
        started = time.perf_counter()
        cpu_started = time.process_time()
        child_started = resource.getrusage(resource.RUSAGE_CHILDREN)
        config = context.config
        private_dependency = inspect_ocr(config.ocr_executable, include_private_paths=True)
        dependency = sanitize_ocr_inventory(private_dependency)
        dependency_path = context.run_dir / "ocr_dependency.json"
        output_path = context.run_dir / "ocr_observations.jsonl"
        frames_path = context.run_dir / "ocr_frame_results.json"
        runtime_path = context.run_dir / "ocr_runtime.json"
        tracks_path = context.run_dir / "ocr_text_tracks.json"
        write_json(dependency_path, dependency)
        base_artifacts = (dependency_path, output_path, frames_path, runtime_path, tracks_path)
        if not config.ocr_enabled:
            write_jsonl(output_path, [])
            write_json(
                tracks_path,
                associate_temporal_text([], config.ocr_temporal_association_max_gap_ms),
            )
            write_json(
                frames_path,
                {"schema_version": "1.0.0", "adapter_state": "disabled", "frames": []},
            )
            self._write_runtime(runtime_path, started, cpu_started, child_started, 0, 0, 0, 0, 0)
            return OcrOutput(
                AdapterResult(self.name, "success_zero", detail="OCR disabled"),
                (),
                {},
                base_artifacts,
            )
        if private_dependency["state"] != "available":
            write_jsonl(output_path, [])
            write_json(
                tracks_path,
                associate_temporal_text([], config.ocr_temporal_association_max_gap_ms),
            )
            write_json(
                frames_path,
                {"schema_version": "1.0.0", "adapter_state": "unavailable", "frames": []},
            )
            self._write_runtime(runtime_path, started, cpu_started, child_started, 0, 0, 0, 1, 0)
            if config.ocr_unavailable_behavior == "fail":
                raise AtlasError("Tesseract is unavailable")
            return OcrOutput(
                AdapterResult(
                    self.name,
                    "unavailable_dependency",
                    detail="Tesseract is unavailable; install tesseract-ocr and tesseract-ocr-eng",
                    attempted_units=0,
                ),
                (),
                {},
                base_artifacts,
            )
        available = set(private_dependency["available_languages"])
        missing = sorted(set(config.ocr_languages) - available)
        if missing:
            write_jsonl(output_path, [])
            write_json(
                tracks_path,
                associate_temporal_text([], config.ocr_temporal_association_max_gap_ms),
            )
            write_json(
                frames_path,
                {"schema_version": "1.0.0", "adapter_state": "failed", "frames": []},
            )
            self._write_runtime(runtime_path, started, cpu_started, child_started, 0, 0, 0, 1, 0)
            return OcrOutput(
                AdapterResult(
                    self.name,
                    "invalid_configuration",
                    detail=f"unsupported Tesseract languages: {missing}",
                    attempted_units=0,
                ),
                (),
                {},
                base_artifacts,
            )
        keyframes_path = context.run_dir / "keyframes.jsonl"
        if not keyframes_path.is_file():
            write_jsonl(output_path, [])
            write_json(
                tracks_path,
                associate_temporal_text([], config.ocr_temporal_association_max_gap_ms),
            )
            write_json(
                frames_path,
                {"schema_version": "1.0.0", "adapter_state": "skipped", "frames": []},
            )
            self._write_runtime(runtime_path, started, cpu_started, child_started, 0, 0, 0, 1, 0)
            return OcrOutput(
                AdapterResult(
                    self.name,
                    "unsupported_input",
                    detail="OCR requires shot keyframes",
                    attempted_units=1,
                    unsupported_units=1,
                ),
                (),
                {},
                base_artifacts,
            )
        try:
            keyframes = [
                json.loads(line)
                for line in keyframes_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
        except (OSError, json.JSONDecodeError) as exc:
            raise AtlasError(f"invalid OCR keyframe index: {exc}") from exc
        if len(keyframes) > config.ocr_max_frames:
            write_jsonl(output_path, [])
            write_json(
                tracks_path,
                associate_temporal_text([], config.ocr_temporal_association_max_gap_ms),
            )
            write_json(
                frames_path,
                {"schema_version": "1.0.0", "adapter_state": "failed", "frames": []},
            )
            self._write_runtime(runtime_path, started, cpu_started, child_started, 0, 0, 0, 1, 0)
            return OcrOutput(
                AdapterResult(
                    self.name,
                    "resource_limit_failure",
                    detail="OCR frame limit exceeded",
                    attempted_units=len(keyframes),
                    failed_units=len(keyframes),
                ),
                (),
                {},
                base_artifacts,
            )

        # A hard process interruption can bypass TemporaryDirectory cleanup. Only the
        # adapter's fixed, run-root prefix is eligible for resume cleanup.
        for stale in context.run_dir.glob("av-atlas-ocr-*"):
            if stale.is_symlink() or stale.is_file():
                stale.unlink()
            elif stale.is_dir():
                shutil.rmtree(stale)

        frame_outputs: list[tuple[int, list[dict[str, Any]], dict[str, Any]]] = []
        frame_failures: list[dict[str, Any]] = []
        timeouts = 0
        with tempfile.TemporaryDirectory(prefix="av-atlas-ocr-", dir=context.run_dir) as value:
            temporary = Path(value)
            with ThreadPoolExecutor(max_workers=config.ocr_workers) as executor:
                futures = {
                    executor.submit(
                        _process_frame, context, private_dependency, temporary, index, keyframe
                    ): (index, keyframe)
                    for index, keyframe in enumerate(keyframes, 1)
                }
                for future in as_completed(futures):
                    index, keyframe = futures[future]
                    try:
                        frame_outputs.append(future.result())
                    except subprocess.TimeoutExpired:
                        timeouts += 1
                        frame_failures.append(
                            {
                                "keyframe_id": keyframe["keyframe_id"],
                                "shot_id": keyframe["shot_id"],
                                "timestamp_ms": keyframe["timestamp_ms"],
                                "source_frame_evidence_ref": keyframe["evidence_ref"],
                                "state": "failed",
                                "warning": "subprocess_timeout",
                            }
                        )
                    except (OSError, subprocess.SubprocessError, AtlasError) as exc:
                        frame_failures.append(
                            {
                                "keyframe_id": keyframe["keyframe_id"],
                                "shot_id": keyframe["shot_id"],
                                "timestamp_ms": keyframe["timestamp_ms"],
                                "source_frame_evidence_ref": keyframe["evidence_ref"],
                                "state": "failed",
                                "warning": type(exc).__name__,
                            }
                        )
        frame_outputs.sort(key=lambda item: item[0])
        frame_results = [item[2] for item in frame_outputs] + frame_failures
        frame_results.sort(key=lambda item: (int(item["timestamp_ms"]), str(item["keyframe_id"])))
        records: list[dict[str, Any]] = []
        observations: list[Observation] = []
        evidence: dict[str, dict[str, Any]] = {}
        language_identity = _language_identity(private_dependency, config.ocr_languages)
        duration_ms = int(context.inventory["duration_ms"])
        for frame_number, regions, frame_result in frame_outputs:
            for region_index, region in enumerate(regions, 1):
                observation_id = f"OCR_{frame_number:04d}_{region_index:04d}"
                evidence_id = f"OCR:{observation_id}"
                timestamp = int(frame_result["timestamp_ms"])
                warnings = ["low_confidence"] if float(region["confidence"]) < 50 else []
                record = {
                    "schema_version": "1.0.0",
                    "observation_id": observation_id,
                    "source_id": context.inventory["source_id"],
                    "shot_id": frame_result["shot_id"],
                    "keyframe_id": frame_result["keyframe_id"],
                    "timestamp_ms": timestamp,
                    "text": region["text"],
                    "normalized_text": " ".join(str(region["text"]).split()),
                    "bounding_box": region["bbox"],
                    "confidence": region["confidence"],
                    "language": "+".join(config.ocr_languages),
                    "engine": "tesseract",
                    "engine_version": private_dependency["version"],
                    "language_data_identity": language_identity,
                    "preprocessing": {
                        "grayscale": config.ocr_grayscale,
                        "contrast_normalization": config.ocr_contrast_normalization,
                        "threshold": config.ocr_threshold,
                        "max_dimension": config.ocr_resize_max_dimension,
                        "rotation_correction": "disabled",
                    },
                    "source_frame_evidence_ref": frame_result["source_frame_evidence_ref"],
                    "adapter_state": "succeeded",
                    "warnings": warnings,
                    "evidence_ref": evidence_id,
                }
                records.append(record)
                observations.append(
                    Observation(
                        observation_id,
                        self.name,
                        timestamp,
                        min(timestamp + 1, duration_ms),
                        "on_screen_text",
                        f"On-screen untrusted OCR data reads: {region['text']}",
                        float(region["confidence"]) / 100,
                        "OCR",
                        evidence_ref_override=evidence_id,
                    )
                )
                evidence[evidence_id] = {
                    "evidence_ref": evidence_id,
                    "source_id": context.inventory["source_id"],
                    "observation_id": observation_id,
                    "modality": "OCR",
                    "start_ms": timestamp,
                    "end_ms": min(timestamp + 1, duration_ms),
                }
        records.sort(key=lambda item: (int(item["timestamp_ms"]), str(item["observation_id"])))
        write_jsonl(output_path, records)
        write_json(
            tracks_path,
            associate_temporal_text(records, config.ocr_temporal_association_max_gap_ms),
        )
        write_json(
            frames_path,
            {
                "schema_version": "1.1.0",
                "adapter_state": (
                    "partial_success"
                    if frame_failures and frame_outputs
                    else "failed"
                    if frame_failures
                    else "succeeded"
                ),
                "unit_counts": {
                    "attempted": len(keyframes),
                    "successful": len(frame_outputs),
                    "failed": len(frame_failures),
                    "timed_out": timeouts,
                    "unsupported": 0,
                    "emitted_observations": len(records),
                },
                "frames": frame_results,
            },
        )
        self._write_runtime(
            runtime_path,
            started,
            cpu_started,
            child_started,
            len(keyframes),
            len(records),
            config.ocr_workers,
            len(frame_failures),
            timeouts,
        )
        if frame_failures and not frame_outputs:
            status: AdapterStatus = (
                "resource_limit_failure" if timeouts == len(frame_failures) else "decode_failure"
            )
        elif frame_failures:
            status = "partial_success"
        else:
            status = "success" if records else "success_zero"
        detail = (
            f"processed {len(frame_outputs)}/{len(keyframes)} frames with {config.ocr_workers} "
            f"workers; recognized {len(records)} text regions; failures={len(frame_failures)}"
        )
        return OcrOutput(
            AdapterResult(
                self.name,
                status,
                tuple(observations),
                detail,
                attempted_units=len(keyframes),
                successful_units=len(frame_outputs),
                failed_units=len(frame_failures),
                timed_out_units=timeouts,
            ),
            tuple(records),
            evidence,
            base_artifacts,
        )

    @staticmethod
    def _write_runtime(
        path: Path,
        started: float,
        cpu_started: float,
        child_started: resource.struct_rusage,
        frames: int,
        observations: int,
        workers: int,
        failures: int,
        timeouts: int,
    ) -> None:
        elapsed = time.perf_counter() - started
        child = resource.getrusage(resource.RUSAGE_CHILDREN)
        child_cpu = (child.ru_utime + child.ru_stime) - (
            child_started.ru_utime + child_started.ru_stime
        )
        cpu_seconds = time.process_time() - cpu_started + child_cpu
        write_json(
            path,
            {
                "schema_version": "1.0.0",
                "workers": workers,
                "frames_processed": frames,
                "observation_count": observations,
                "wall_seconds": round(elapsed, 6),
                "cpu_seconds": round(cpu_seconds, 6),
                "peak_rss_kb": max(
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, child.ru_maxrss
                ),
                "frames_per_second": frames / elapsed if elapsed and frames else 0.0,
                "failures": failures,
                "timeouts": timeouts,
                "retries": 0,
                "memory_scope": "maximum resident set of the parent or any single child process",
                "thread_limit_per_tesseract_process": 1,
                "temporary_files_retained": False,
            },
        )
