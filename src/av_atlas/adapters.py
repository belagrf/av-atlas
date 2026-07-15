"""Production-shaped deterministic sidecar perception adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from av_atlas.config import BaselineConfig
from av_atlas.contracts import AdapterResult, Observation
from av_atlas.errors import AtlasError


@dataclass(frozen=True)
class AdapterContext:
    media: Path
    inventory: dict[str, Any]
    run_dir: Path
    config: BaselineConfig
    source_media: Path | None = None


class AdapterExecution(Protocol):
    @property
    def result(self) -> AdapterResult: ...

    @property
    def evidence(self) -> dict[str, dict[str, Any]]: ...

    @property
    def artifact_paths(self) -> tuple[Path, ...]: ...


class PerceptionAdapter(Protocol):
    name: str

    def run(self, context: AdapterContext) -> AdapterExecution: ...


@dataclass(frozen=True)
class SidecarOutput:
    result: AdapterResult
    evidence: dict[str, dict[str, Any]]
    artifact_paths: tuple[Path, ...] = ()


class SidecarAdapter:
    """Read deterministic observations for one perception branch."""

    def __init__(self, name: str) -> None:
        self.name = name

    def observe(self, media: Path, duration_ms: int) -> list[Observation]:
        sidecar = media.with_suffix(".observations.json")
        if not sidecar.is_file():
            return []
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            values = payload["observations"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AtlasError(f"invalid observation sidecar {sidecar.name}: {exc}") from exc
        observations = [
            Observation.from_dict(value) for value in values if value.get("adapter") == self.name
        ]
        for observation in observations:
            if observation.end_ms > duration_ms:
                raise AtlasError(
                    f"observation exceeds source duration: {observation.observation_id}"
                )
        return observations

    def run(self, context: AdapterContext) -> SidecarOutput:
        sidecar_media = context.source_media or context.media
        values = self.observe(sidecar_media, int(context.inventory["duration_ms"]))
        return SidecarOutput(
            AdapterResult(
                self.name,
                "success" if values else "success_zero",
                tuple(values),
                f"loaded {len(values)} deterministic sidecar observations",
                attempted_units=len(values),
                successful_units=len(values),
            ),
            {},
        )
