"""Inspectable CPU-only structural shot and keyframe adapter."""

from __future__ import annotations

import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av_atlas.adapters import AdapterContext
from av_atlas.config import BaselineConfig
from av_atlas.contracts import AdapterResult, Observation
from av_atlas.errors import AtlasError, ResourceLimitError
from av_atlas.io import sha256_file, write_jsonl

FRAME_WIDTH = 64
FRAME_HEIGHT = 36
FRAME_BYTES = FRAME_WIDTH * FRAME_HEIGHT * 3


@dataclass(frozen=True)
class ShotOutput:
    result: AdapterResult
    shots: tuple[dict[str, Any], ...]
    keyframes: tuple[dict[str, Any], ...]
    evidence: dict[str, dict[str, Any]]
    artifact_paths: tuple[Path, ...]


class ShotAdapter:
    name = "shot"

    def run(self, context: AdapterContext) -> ShotOutput:
        if not context.config.shot_enabled:
            return ShotOutput(
                AdapterResult("shot", "success_zero", detail="shot adapter is disabled"),
                (),
                (),
                {},
                (),
            )
        return detect_shots(context.media, context.inventory, context.run_dir, context.config)


def _difference(left: bytes, right: bytes) -> float:
    return sum(abs(first - second) for first, second in zip(left, right, strict=True)) / (
        len(left) * 255
    )


def _decode_frames(media: Path, config: BaselineConfig, duration_ms: int) -> list[bytes]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AtlasError("ffmpeg is unavailable")
    maximum_frames = math.ceil(duration_ms * config.shot_sample_fps / 1000) + 2
    if maximum_frames > config.max_duration_ms * config.shot_sample_fps / 1000 + 2:
        raise ResourceLimitError("frame-count budget exceeds configured duration")
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-i",
                str(media),
                "-map",
                "0:v:0",
                "-vf",
                f"fps={config.shot_sample_fps},scale={FRAME_WIDTH}:{FRAME_HEIGHT}:flags=neighbor,format=rgb24",
                "-frames:v",
                str(maximum_frames),
                "-f",
                "rawvideo",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
            shell=False,
            timeout=config.subprocess_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ResourceLimitError("shot decoding exceeded the configured decode budget") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"unknown video decode error").decode(errors="replace")
        raise AtlasError(f"shot decoding failed: {detail.strip().splitlines()[-1]}") from exc
    if len(completed.stdout) > maximum_frames * FRAME_BYTES:
        raise ResourceLimitError("shot decoding exceeded the configured frame-count limit")
    complete_size = len(completed.stdout) - len(completed.stdout) % FRAME_BYTES
    if complete_size == 0:
        raise AtlasError("shot decoding produced no complete video frames")
    return [
        completed.stdout[offset : offset + FRAME_BYTES]
        for offset in range(0, complete_size, FRAME_BYTES)
    ]


def _boundaries(
    frames: list[bytes], config: BaselineConfig, duration_ms: int
) -> list[tuple[int, str, float]]:
    scores = [0.0] + [
        _difference(frames[index - 1], frames[index]) for index in range(1, len(frames))
    ]
    flash_window = max(1, math.ceil(config.flash_suppression_ms * config.shot_sample_fps / 1000))
    suppressed: set[int] = set()
    hard: list[tuple[int, str, float]] = []
    for index in range(1, len(frames)):
        if scores[index] < config.shot_hard_threshold or index in suppressed:
            continue
        for later in range(index + 1, min(len(frames), index + flash_window + 1)):
            if _difference(frames[index - 1], frames[later]) < config.shot_gradual_threshold:
                suppressed.update(range(index, later + 1))
                break
        if index not in suppressed:
            hard.append(
                (
                    round(index * 1000 / config.shot_sample_fps),
                    "hard_cut",
                    min(1.0, scores[index]),
                )
            )

    gradual: list[tuple[int, str, float]] = []
    index = 1
    while index < len(scores):
        if (
            index not in suppressed
            and config.shot_gradual_threshold <= scores[index] < config.shot_hard_threshold
        ):
            group = [index]
            index += 1
            while (
                index < len(scores)
                and index not in suppressed
                and config.shot_gradual_threshold <= scores[index] < config.shot_hard_threshold
            ):
                group.append(index)
                index += 1
            if len(group) >= 2 and max(scores[item] for item in group) <= (
                config.shot_hard_threshold * 0.25
            ):
                middle = group[len(group) // 2]
                gradual.append(
                    (
                        round(middle * 1000 / config.shot_sample_fps),
                        "gradual_transition",
                        min(1.0, max(scores[item] for item in group) / config.shot_hard_threshold),
                    )
                )
        else:
            index += 1
    candidates = sorted([*hard, *gradual])
    accepted: list[tuple[int, str, float]] = [(0, "source_start", 1.0)]
    for boundary in candidates:
        if boundary[0] <= 0 or boundary[0] >= duration_ms:
            continue
        if boundary[0] - accepted[-1][0] < config.shot_min_duration_ms:
            continue
        while boundary[0] - accepted[-1][0] > config.shot_max_duration_ms:
            accepted.append((accepted[-1][0] + config.shot_max_duration_ms, "uncertain", 0.0))
        accepted.append(boundary)
    while duration_ms - accepted[-1][0] > config.shot_max_duration_ms:
        accepted.append((accepted[-1][0] + config.shot_max_duration_ms, "uncertain", 0.0))
    return accepted


def _extract_keyframe(media: Path, path: Path, timestamp_ms: int, timeout_seconds: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AtlasError("ffmpeg is unavailable")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-ss",
                f"{timestamp_ms / 1000:.3f}",
                "-i",
                str(media),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-vf",
                "scale=320:180:force_original_aspect_ratio=decrease",
                "-c:v",
                "png",
                "-y",
                "--",
                str(path),
            ],
            check=True,
            capture_output=True,
            shell=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        path.unlink(missing_ok=True)
        raise ResourceLimitError(
            "keyframe extraction exceeded the configured decode budget"
        ) from exc
    except subprocess.CalledProcessError as exc:
        path.unlink(missing_ok=True)
        detail = (exc.stderr or b"unknown keyframe error").decode(errors="replace")
        raise AtlasError(f"keyframe extraction failed: {detail.strip().splitlines()[-1]}") from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise AtlasError("keyframe extraction produced no image")
    if path.stat().st_size > 8_000_000:
        path.unlink(missing_ok=True)
        raise ResourceLimitError("keyframe exceeded the 8 MB output limit")


def detect_shots(
    media: Path, inventory: dict[str, Any], run_dir: Path, config: BaselineConfig
) -> ShotOutput:
    video_streams = [stream for stream in inventory["streams"] if stream["codec_type"] == "video"]
    if not video_streams:
        return ShotOutput(
            AdapterResult(
                "shot",
                "unsupported_input",
                detail="source has no video stream",
                attempted_units=1,
                unsupported_units=1,
            ),
            (),
            (),
            {},
            (),
        )
    if shutil.which("ffmpeg") is None:
        return ShotOutput(
            AdapterResult(
                "shot",
                "unavailable_dependency",
                detail="ffmpeg is unavailable",
                attempted_units=1,
                failed_units=1,
            ),
            (),
            (),
            {},
            (),
        )
    try:
        frames = _decode_frames(media, config, int(inventory["duration_ms"]))
        boundaries = _boundaries(frames, config, int(inventory["duration_ms"]))
        if len(boundaries) > config.max_keyframes:
            raise ResourceLimitError("detected shot count exceeds the configured keyframe limit")
        shots: list[dict[str, Any]] = []
        keyframes: list[dict[str, Any]] = []
        observations: list[Observation] = []
        evidence: dict[str, dict[str, Any]] = {}
        artifacts: list[Path] = []
        duration_ms = int(inventory["duration_ms"])
        for index, (start_ms, boundary_type, confidence) in enumerate(boundaries, 1):
            end_ms = boundaries[index][0] if index < len(boundaries) else duration_ms
            if end_ms <= start_ms:
                raise AtlasError("shot detector produced a zero-length or reversed shot")
            shot_id, keyframe_id = f"SHOT_{index:04d}", f"KEY_{index:04d}"
            timestamp_ms = start_ms + (end_ms - start_ms) // 2
            keyframe_path = run_dir / "keyframes" / f"{keyframe_id}.png"
            _extract_keyframe(media, keyframe_path, timestamp_ms, config.subprocess_timeout_seconds)
            shot_ref = f"VID:{inventory['source_id']}:ms:{start_ms}-{end_ms}"
            key_ref = f"VID:{inventory['source_id']}:frame:{timestamp_ms}"
            shots.append(
                {
                    "schema_version": "1.0.0",
                    "shot_id": shot_id,
                    "source_id": inventory["source_id"],
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "boundary_type": boundary_type,
                    "boundary_confidence": confidence,
                    "keyframe_id": keyframe_id,
                    "evidence_ref": shot_ref,
                }
            )
            keyframes.append(
                {
                    "schema_version": "1.0.0",
                    "keyframe_id": keyframe_id,
                    "shot_id": shot_id,
                    "source_id": inventory["source_id"],
                    "timestamp_ms": timestamp_ms,
                    "frame_index": round(timestamp_ms * config.shot_sample_fps / 1000),
                    "path": keyframe_path.relative_to(run_dir).as_posix(),
                    "sha256": sha256_file(keyframe_path),
                    "size_bytes": keyframe_path.stat().st_size,
                    "evidence_ref": key_ref,
                }
            )
            observations.append(
                Observation(
                    observation_id=shot_id,
                    adapter="shot",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    claim_type="structural_shot",
                    text=f"A structural shot interval begins with boundary type {boundary_type}.",
                    confidence=confidence,
                    modality="VID",
                    evidence_ref_override=shot_ref,
                )
            )
            evidence[key_ref] = {
                "evidence_ref": key_ref,
                "source_id": inventory["source_id"],
                "observation_id": keyframe_id,
                "modality": "VID",
                "start_ms": timestamp_ms,
                "end_ms": min(duration_ms, timestamp_ms + 1),
            }
            artifacts.append(keyframe_path)
        shots_path, keyframes_path = run_dir / "shots.jsonl", run_dir / "keyframes.jsonl"
        write_jsonl(shots_path, shots)
        write_jsonl(keyframes_path, keyframes)
        artifacts.extend((shots_path, keyframes_path))
        return ShotOutput(
            AdapterResult(
                "shot",
                "success" if observations else "success_zero",
                tuple(observations),
                f"decoded {len(frames)} structural sample frames and produced {len(shots)} shots",
                attempted_units=len(shots),
                successful_units=len(shots),
            ),
            tuple(shots),
            tuple(keyframes),
            evidence,
            tuple(artifacts),
        )
    except ResourceLimitError as exc:
        return ShotOutput(
            AdapterResult(
                "shot", "resource_limit_failure", detail=str(exc), attempted_units=1, failed_units=1
            ),
            (),
            (),
            {},
            (),
        )
    except AtlasError as exc:
        return ShotOutput(
            AdapterResult(
                "shot", "decode_failure", detail=str(exc), attempted_units=1, failed_units=1
            ),
            (),
            (),
            {},
            (),
        )
