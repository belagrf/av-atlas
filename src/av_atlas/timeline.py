"""Normalized integer-millisecond timeline operations."""

from __future__ import annotations

from dataclasses import dataclass

from av_atlas.errors import AtlasError


@dataclass(frozen=True)
class Interval:
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise AtlasError(f"invalid interval {self.start_ms}-{self.end_ms}")


def chunks(duration_ms: int, size_ms: int, overlap_ms: int) -> list[Interval]:
    if duration_ms <= 0 or size_ms <= 0 or overlap_ms < 0 or overlap_ms >= size_ms:
        raise AtlasError("invalid duration, chunk size, or overlap")
    result: list[Interval] = []
    start = 0
    while start < duration_ms:
        end = min(start + size_ms, duration_ms)
        result.append(Interval(start, end))
        if end == duration_ms:
            break
        start = end - overlap_ms
    return result


def uniform_samples(duration_ms: int, interval_ms: int) -> list[int]:
    if duration_ms <= 0 or interval_ms <= 0:
        raise AtlasError("duration and sample interval must be positive")
    return list(range(0, duration_ms, interval_ms))
