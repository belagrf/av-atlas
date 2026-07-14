"""Configuration loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av_atlas.errors import AtlasError


@dataclass(frozen=True)
class BaselineConfig:
    schema_version: str
    chunk_duration_ms: int
    chunk_overlap_ms: int
    sample_interval_ms: int
    adapters: tuple[str, ...]
    subtitle_mode: str = "disabled"
    subtitle_tracks: tuple[int, ...] = ()
    shot_enabled: bool = False
    shot_sample_fps: int = 10
    shot_hard_threshold: float = 0.35
    shot_gradual_threshold: float = 0.025
    shot_min_duration_ms: int = 500
    shot_max_duration_ms: int = 5000
    flash_suppression_ms: int = 250
    subprocess_timeout_seconds: int = 30
    max_duration_ms: int = 600_000
    max_video_width: int = 4096
    max_video_height: int = 4096
    max_keyframes: int = 1000
    ocr_enabled: bool = False
    ocr_executable: str = "auto"
    ocr_languages: tuple[str, ...] = ("eng",)
    ocr_page_segmentation_mode: int = 6
    ocr_engine_mode: int = 1
    ocr_grayscale: bool = True
    ocr_contrast_normalization: bool = False
    ocr_threshold: int | None = None
    ocr_resize_max_dimension: int = 1920
    ocr_min_confidence: float = 0.0
    ocr_timeout_seconds: int = 15
    ocr_workers: int = 1
    ocr_max_frames: int = 100
    ocr_unavailable_behavior: str = "degrade"
    ocr_retain_raw_frames: bool = False

    @classmethod
    def load(cls, path: Path) -> BaselineConfig:
        try:
            raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            subtitle = raw.get("subtitle", {})
            shot = raw.get("shot", {})
            resources = raw.get("resources", {})
            ocr = raw.get("ocr", {})
            allowed_top = {
                "schema_version",
                "chunk_duration_ms",
                "chunk_overlap_ms",
                "sample_interval_ms",
                "adapters",
                "subtitle",
                "shot",
                "resources",
                "ocr",
            }
            if set(raw) - allowed_top:
                raise AtlasError(f"unknown configuration keys: {sorted(set(raw) - allowed_top)}")
            allowed_ocr = {
                "enabled",
                "executable",
                "languages",
                "page_segmentation_mode",
                "engine_mode",
                "preprocessing",
                "minimum_confidence",
                "max_frame_dimension",
                "timeout_seconds",
                "workers",
                "maximum_frames_per_source",
                "unavailable_behavior",
                "retain_raw_frames",
            }
            if set(ocr) - allowed_ocr:
                raise AtlasError(
                    f"unknown OCR configuration keys: {sorted(set(ocr) - allowed_ocr)}"
                )
            config = cls(
                schema_version=str(raw["schema_version"]),
                chunk_duration_ms=int(raw["chunk_duration_ms"]),
                chunk_overlap_ms=int(raw["chunk_overlap_ms"]),
                sample_interval_ms=int(raw["sample_interval_ms"]),
                adapters=tuple(str(item) for item in raw["adapters"]),
                subtitle_mode=str(subtitle.get("mode", "disabled")),
                subtitle_tracks=tuple(int(item) for item in subtitle.get("tracks", [])),
                shot_enabled=bool(shot.get("enabled", False)),
                shot_sample_fps=int(shot.get("sample_fps", 10)),
                shot_hard_threshold=float(shot.get("hard_threshold", 0.35)),
                shot_gradual_threshold=float(shot.get("gradual_threshold", 0.025)),
                shot_min_duration_ms=int(shot.get("min_duration_ms", 500)),
                shot_max_duration_ms=int(shot.get("max_duration_ms", 5000)),
                flash_suppression_ms=int(shot.get("flash_suppression_ms", 250)),
                subprocess_timeout_seconds=int(resources.get("subprocess_timeout_seconds", 30)),
                max_duration_ms=int(resources.get("max_duration_ms", 600_000)),
                max_video_width=int(resources.get("max_video_width", 4096)),
                max_video_height=int(resources.get("max_video_height", 4096)),
                max_keyframes=int(resources.get("max_keyframes", 1000)),
                ocr_enabled=bool(ocr.get("enabled", False)),
                ocr_executable=str(ocr.get("executable", "auto")),
                ocr_languages=tuple(str(item) for item in ocr.get("languages", ["eng"])),
                ocr_page_segmentation_mode=int(ocr.get("page_segmentation_mode", 6)),
                ocr_engine_mode=int(ocr.get("engine_mode", 1)),
                ocr_grayscale=bool(ocr.get("preprocessing", {}).get("grayscale", True)),
                ocr_contrast_normalization=bool(
                    ocr.get("preprocessing", {}).get("contrast_normalization", False)
                ),
                ocr_threshold=(
                    None
                    if ocr.get("preprocessing", {}).get("threshold") is None
                    else int(ocr["preprocessing"]["threshold"])
                ),
                ocr_resize_max_dimension=int(ocr.get("max_frame_dimension", 1920)),
                ocr_min_confidence=float(ocr.get("minimum_confidence", 0.0)),
                ocr_timeout_seconds=int(ocr.get("timeout_seconds", 15)),
                ocr_workers=int(ocr.get("workers", 1)),
                ocr_max_frames=int(ocr.get("maximum_frames_per_source", 100)),
                ocr_unavailable_behavior=str(ocr.get("unavailable_behavior", "degrade")),
                ocr_retain_raw_frames=bool(ocr.get("retain_raw_frames", False)),
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AtlasError(f"invalid baseline configuration {path}: {exc}") from exc
        if config.chunk_duration_ms <= 0 or config.sample_interval_ms <= 0:
            raise AtlasError("chunk and sample durations must be positive")
        if not 0 <= config.chunk_overlap_ms < config.chunk_duration_ms:
            raise AtlasError("chunk overlap must be nonnegative and smaller than chunk duration")
        if config.subtitle_mode not in {"disabled", "all", "selected"}:
            raise AtlasError("subtitle mode must be disabled, all, or selected")
        if config.subtitle_mode == "selected" and not config.subtitle_tracks:
            raise AtlasError("selected subtitle mode requires at least one stream index")
        if not 0 < config.shot_gradual_threshold < config.shot_hard_threshold <= 1:
            raise AtlasError("shot thresholds must satisfy 0 < gradual < hard <= 1")
        if (
            config.shot_min_duration_ms <= 0
            or config.shot_max_duration_ms < config.shot_min_duration_ms
        ):
            raise AtlasError("shot duration limits are invalid")
        if (
            min(
                config.shot_sample_fps,
                config.subprocess_timeout_seconds,
                config.max_duration_ms,
                config.max_video_width,
                config.max_video_height,
                config.max_keyframes,
            )
            <= 0
        ):
            raise AtlasError("resource and sampling limits must be positive")
        if config.ocr_enabled:
            if not config.ocr_languages or any(not item.isalpha() for item in config.ocr_languages):
                raise AtlasError("OCR languages must be nonempty alphabetic identifiers")
            if config.ocr_page_segmentation_mode not in range(
                0, 14
            ) or config.ocr_engine_mode not in range(0, 4):
                raise AtlasError("unsupported Tesseract page-segmentation or engine mode")
            if not 0 <= config.ocr_min_confidence <= 100 or not 1 <= config.ocr_workers <= 4:
                raise AtlasError("OCR confidence/workers are outside safe bounds")
            if (
                min(
                    config.ocr_timeout_seconds,
                    config.ocr_max_frames,
                    config.ocr_resize_max_dimension,
                )
                <= 0
            ):
                raise AtlasError("OCR resource limits must be positive")
            if config.ocr_threshold is not None and not 0 <= config.ocr_threshold <= 255:
                raise AtlasError("OCR threshold must be between 0 and 255")
            if config.ocr_unavailable_behavior not in {"degrade", "fail"}:
                raise AtlasError("OCR unavailable_behavior must be degrade or fail")
        return config
