"""Deterministic embedded text-subtitle discovery and canonicalization."""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av_atlas.adapters import AdapterContext
from av_atlas.contracts import AdapterResult, AdapterStatus, Observation
from av_atlas.errors import AtlasError, ResourceLimitError
from av_atlas.io import atomic_write_text, sha256_file, write_json, write_jsonl

TEXT_CODECS = {"subrip", "srt", "webvtt", "ass", "ssa", "mov_text", "text"}
BITMAP_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}
TIMING = re.compile(
    r"^(?:(?P<h1>\d+):)?(?P<m1>\d{2}):(?P<s1>\d{2})[.,](?P<ms1>\d{3})\s+-->\s+"
    r"(?:(?P<h2>\d+):)?(?P<m2>\d{2}):(?P<s2>\d{2})[.,](?P<ms2>\d{3})(?:\s+.*)?$"
)
TAG = re.compile(r"<[^>]*>")


@dataclass(frozen=True)
class SubtitleOutput:
    result: AdapterResult
    tracks: dict[str, Any]
    cues: tuple[dict[str, Any], ...]
    artifact_paths: tuple[Path, ...]
    evidence: dict[str, dict[str, Any]]


class SubtitleAdapter:
    name = "subtitle"

    def run(self, context: AdapterContext) -> SubtitleOutput:
        return extract_subtitles(
            context.media,
            context.inventory,
            context.run_dir,
            context.config.subtitle_mode,
            context.config.subtitle_tracks,
            context.config.subprocess_timeout_seconds,
        )


def _timestamp(match: re.Match[str], suffix: str) -> int:
    hours = int(match.group(f"h{suffix}") or 0)
    minutes = int(match.group(f"m{suffix}"))
    seconds = int(match.group(f"s{suffix}"))
    millis = int(match.group(f"ms{suffix}"))
    if minutes >= 60 or seconds >= 60:
        raise AtlasError("subtitle cue contains a non-canonical timestamp")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def normalize_subtitle_text(value: str) -> str:
    return " ".join(html.unescape(TAG.sub("", value)).split())


def parse_webvtt(
    text: str, track_id: str, source_id: str, duration_ms: int
) -> list[dict[str, Any]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip("\ufeff")
        match = TIMING.match(line)
        if match is None and index + 1 < len(lines):
            match = TIMING.match(lines[index + 1])
            if match is not None:
                index += 1
        if match is None:
            if "-->" in line:
                raise AtlasError(f"subtitle cue has an invalid or non-finite interval: {line}")
            index += 1
            continue
        start_ms, end_ms = _timestamp(match, "1"), _timestamp(match, "2")
        index += 1
        cue_lines: list[str] = []
        while index < len(lines) and lines[index] != "":
            cue_lines.append(lines[index])
            index += 1
        if start_ms < 0 or end_ms <= start_ms or end_ms > duration_ms:
            raise AtlasError(f"subtitle cue interval {start_ms}-{end_ms} is outside the source")
        cue_id = f"CUE_{len(cues) + 1:06d}"
        cue_text = "\n".join(cue_lines)
        cues.append(
            {
                "schema_version": "1.0.0",
                "cue_id": cue_id,
                "track_id": track_id,
                "source_id": source_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": cue_text,
                "normalized_text": normalize_subtitle_text(cue_text),
                "evidence_ref": f"SUB:{track_id}:{cue_id}",
            }
        )
        index += 1
    return cues


def _extract_track(media: Path, stream_index: int, timeout_seconds: int) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AtlasError("ffmpeg is unavailable")
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
                f"0:{stream_index}",
                "-c:s",
                "webvtt",
                "-f",
                "webvtt",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ResourceLimitError(
            "subtitle extraction exceeded the configured decode budget"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "unknown subtitle decode error").strip().splitlines()[-1]
        raise AtlasError(f"subtitle extraction failed: {detail}") from exc
    if len(completed.stdout.encode("utf-8")) > 16_000_000:
        raise ResourceLimitError("subtitle extraction exceeded the 16 MB output limit")
    return completed.stdout


def extract_subtitles(
    media: Path,
    inventory: dict[str, Any],
    run_dir: Path,
    mode: str,
    selected_indexes: tuple[int, ...],
    timeout_seconds: int,
) -> SubtitleOutput:
    source_id, duration_ms = inventory["source_id"], int(inventory["duration_ms"])
    streams = [stream for stream in inventory["streams"] if stream["codec_type"] == "subtitle"]
    available_indexes = {int(stream["index"]) for stream in streams}
    if mode == "selected" and not set(selected_indexes).issubset(available_indexes):
        missing = sorted(set(selected_indexes).difference(available_indexes))
        result = AdapterResult(
            "subtitle",
            "invalid_configuration",
            detail=f"unknown subtitle stream indexes: {missing}",
            attempted_units=len(selected_indexes),
            failed_units=len(selected_indexes),
        )
        return SubtitleOutput(result, _tracks_payload(source_id, mode, []), (), (), {})
    chosen = available_indexes if mode == "all" else set(selected_indexes)
    if chosen and shutil.which("ffmpeg") is None:
        result = AdapterResult(
            "subtitle",
            "unavailable_dependency",
            detail="ffmpeg is unavailable",
            attempted_units=len(chosen),
            failed_units=len(chosen),
        )
        return SubtitleOutput(result, _tracks_payload(source_id, mode, []), (), (), {})
    tracks: list[dict[str, Any]] = []
    cues: list[dict[str, Any]] = []
    artifacts: list[Path] = []
    decode_errors: list[str] = []
    resource_errors: list[str] = []
    unsupported = 0
    extracted = 0
    raw_dir = run_dir / "subtitles" / "raw"
    for stream in streams:
        stream_index = int(stream["index"])
        track_id = f"TRACK_{stream_index:04d}"
        codec = stream.get("codec_name")
        disposition = {
            str(key): bool(value) for key, value in stream.get("disposition", {}).items()
        }
        record: dict[str, Any] = {
            "track_id": track_id,
            "stream_index": stream_index,
            "codec": codec,
            "language": stream.get("language"),
            "title": stream.get("title"),
            "time_base": stream.get("time_base"),
            "disposition": disposition,
            "status": "not_selected",
            "raw_artifact": None,
        }
        if stream_index not in chosen:
            tracks.append(record)
            continue
        if codec in BITMAP_CODECS or codec not in TEXT_CODECS:
            record["status"] = "unsupported_bitmap" if codec in BITMAP_CODECS else "decode_failure"
            unsupported += 1
            tracks.append(record)
            continue
        try:
            raw = _extract_track(media, stream_index, timeout_seconds)
            raw_path = raw_dir / f"{track_id}.vtt"
            atomic_write_text(raw_path, raw)
            record["status"] = "extracted"
            record["raw_artifact"] = {
                "path": raw_path.relative_to(run_dir).as_posix(),
                "sha256": sha256_file(raw_path),
                "size_bytes": raw_path.stat().st_size,
            }
            track_cues = parse_webvtt(raw, track_id, source_id, duration_ms)
            cues.extend(track_cues)
            artifacts.append(raw_path)
            extracted += 1
        except ResourceLimitError as exc:
            record["status"] = "decode_failure"
            resource_errors.append(f"{track_id}: {exc}")
        except AtlasError as exc:
            record["status"] = "decode_failure"
            decode_errors.append(f"{track_id}: {exc}")
        tracks.append(record)
    payload = _tracks_payload(source_id, mode, tracks)
    tracks_path, cues_path, vtt_path = (
        run_dir / "subtitle_tracks.json",
        run_dir / "subtitles.jsonl",
        run_dir / "subtitles.vtt",
    )
    write_json(tracks_path, payload)
    write_jsonl(cues_path, cues)
    _write_normalized_vtt(vtt_path, cues)
    artifacts.extend((tracks_path, cues_path, vtt_path))
    observations = tuple(
        Observation(
            observation_id=f"{cue['track_id']}_{cue['cue_id']}",
            adapter="subtitle",
            start_ms=int(cue["start_ms"]),
            end_ms=int(cue["end_ms"]),
            claim_type="subtitle_text",
            text=f"Embedded subtitle text: {cue['text']}",
            confidence=1.0,
            modality="SUB",
            speaker_id="SPEAKER_UNKNOWN",
            speech_text=str(cue["text"]),
            speech_source="subtitle",
            evidence_ref_override=str(cue["evidence_ref"]),
        )
        for cue in cues
        if cue["text"] != ""
    )
    failed = len(resource_errors) + len(decode_errors)
    if extracted and (failed or unsupported):
        status: AdapterStatus = "partial_success"
        detail = (
            f"extracted {len(cues)} cues; successful_tracks={extracted}; "
            f"failed_tracks={failed}; unsupported_tracks={unsupported}"
        )
    elif resource_errors:
        status = "resource_limit_failure"
        detail = "; ".join(resource_errors)
    elif decode_errors:
        status = "decode_failure"
        detail = "; ".join(decode_errors)
    elif observations:
        status = "success"
        detail = f"extracted {len(cues)} cues from {len(streams)} tracks"
    elif unsupported:
        status = "unsupported_input"
        detail = "selected subtitle tracks are not text-decodable"
    else:
        status = "success_zero"
        detail = "no selected embedded subtitle cues"
    evidence = {
        str(cue["evidence_ref"]): {
            "evidence_ref": cue["evidence_ref"],
            "source_id": source_id,
            "observation_id": f"{cue['track_id']}_{cue['cue_id']}",
            "modality": "SUB",
            "start_ms": cue["start_ms"],
            "end_ms": cue["end_ms"],
        }
        for cue in cues
    }
    return SubtitleOutput(
        AdapterResult(
            "subtitle",
            status,
            observations,
            detail,
            attempted_units=len(chosen),
            successful_units=extracted,
            failed_units=failed,
            timed_out_units=len(resource_errors),
            unsupported_units=unsupported,
        ),
        payload,
        tuple(cues),
        tuple(artifacts),
        evidence,
    )


def _tracks_payload(source_id: str, selection: str, tracks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "source_id": source_id,
        "selection": selection,
        "tracks": tracks,
    }


def _vtt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _write_normalized_vtt(path: Path, cues: list[dict[str, Any]]) -> None:
    lines = ["WEBVTT", ""]
    for cue in cues:
        lines.extend(
            [
                f"NOTE {cue['track_id']} {cue['cue_id']} {cue['evidence_ref']}",
                f"{_vtt_timestamp(cue['start_ms'])} --> {_vtt_timestamp(cue['end_ms'])}",
                cue["text"],
                "",
            ]
        )
    atomic_write_text(path, "\n".join(lines))
