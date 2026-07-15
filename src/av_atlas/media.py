"""Safe ffmpeg/ffprobe wrappers and normalized media inventory."""

from __future__ import annotations

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from av_atlas.errors import AtlasError
from av_atlas.io import sha256_file, source_id_from_sha256


def _run(
    arguments: list[str], timeout_seconds: int = 30, max_output_chars: int = 4_000_000
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise AtlasError(f"required executable not found: {arguments[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown error").strip().splitlines()[-1]
        raise AtlasError(f"{arguments[0]} failed: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AtlasError(f"{arguments[0]} exceeded the {timeout_seconds}s decode budget") from exc
    if len(completed.stdout) + len(completed.stderr) > max_output_chars:
        raise AtlasError(f"{arguments[0]} exceeded the metadata output-size limit")
    return completed


def tool_version(name: str) -> str | None:
    executable = shutil.which(name)
    if executable is None:
        return None
    first_line = _run([executable, "-version"]).stdout.splitlines()[0]
    return first_line


def _milliseconds(value: Any) -> int | None:
    try:
        return round(float(value) * 1000)
    except (TypeError, ValueError):
        return None


def inspect_media(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AtlasError(f"media source is not a regular file: {path}")
    executable = shutil.which("ffprobe")
    if executable is None:
        raise AtlasError("ffprobe is required; install FFmpeg or use tested sidecar fixtures")
    completed = _run(
        [
            executable,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            "-of",
            "json",
            "--",
            str(path),
        ]
    )
    try:
        raw: dict[str, Any] = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AtlasError("ffprobe returned corrupt JSON metadata") from exc
    duration_ms = _milliseconds(raw.get("format", {}).get("duration"))
    if duration_ms is None:
        stream_durations = [
            value
            for stream in raw.get("streams", [])
            if (value := _milliseconds(stream.get("duration"))) is not None
        ]
        duration_ms = max(stream_durations, default=0)
    if duration_ms <= 0:
        raise AtlasError("media duration is missing or zero")
    streams: list[dict[str, Any]] = []
    for stream in raw.get("streams", []):
        frame_rate = stream.get("avg_frame_rate")
        normalized_rate: str | None = None
        if frame_rate and frame_rate != "0/0":
            try:
                normalized_rate = str(Fraction(frame_rate))
            except (ValueError, ZeroDivisionError):
                normalized_rate = None
        tags = stream.get("tags", {})
        disposition = {
            str(name): bool(value) for name, value in stream.get("disposition", {}).items()
        }
        streams.append(
            {
                "index": int(stream["index"]),
                "codec_type": str(stream.get("codec_type", "unknown")),
                "codec_name": stream.get("codec_name"),
                "language": tags.get("language"),
                "title": tags.get("title"),
                "time_base": stream.get("time_base"),
                "frame_rate": normalized_rate,
                "duration_ms": _milliseconds(stream.get("duration")),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "disposition": disposition,
            }
        )
    chapters = [
        {
            "id": int(chapter.get("id", index)),
            "start_ms": _milliseconds(chapter.get("start_time")) or 0,
            "end_ms": _milliseconds(chapter.get("end_time")) or 0,
            "title": chapter.get("tags", {}).get("title"),
        }
        for index, chapter in enumerate(raw.get("chapters", []))
    ]
    source_hash = sha256_file(path)
    return {
        "schema_version": "1.0.0",
        "source_id": source_id_from_sha256(source_hash),
        "sha256": source_hash,
        "size_bytes": path.stat().st_size,
        "duration_ms": duration_ms,
        "format_names": sorted(str(raw.get("format", {}).get("format_name", "")).split(",")),
        "streams": streams,
        "chapters": chapters,
    }


def enforce_media_limits(
    inventory: dict[str, Any], max_duration_ms: int, max_width: int, max_height: int
) -> None:
    if int(inventory["duration_ms"]) > max_duration_ms:
        raise AtlasError(
            f"source duration {inventory['duration_ms']}ms exceeds "
            f"configured limit {max_duration_ms}ms"
        )
    for stream in inventory["streams"]:
        width, height = stream.get("width"), stream.get("height")
        if width is not None and int(width) > max_width:
            raise AtlasError(f"video width {width} exceeds configured limit {max_width}")
        if height is not None and int(height) > max_height:
            raise AtlasError(f"video height {height} exceeds configured limit {max_height}")
