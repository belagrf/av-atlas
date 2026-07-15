"""Production-shaped deterministic sidecar perception adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from av_atlas.config import BaselineConfig
from av_atlas.contracts import AdapterResult, Observation
from av_atlas.errors import AtlasError


@dataclass(frozen=True)
class AdapterContext:
    # ``media`` is always the verified transient snapshot for native adapters.
    media: Path
    inventory: dict[str, Any]
    run_dir: Path
    config: BaselineConfig
    # Verified controlled-fixture observations are immutable values, never source paths.
    sidecar_observations: tuple[Observation, ...] = ()


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

    def observe(self, observations: tuple[Observation, ...], duration_ms: int) -> list[Observation]:
        selected = [value for value in observations if value.adapter == self.name]
        for observation in selected:
            if observation.end_ms > duration_ms:
                raise AtlasError(
                    f"observation exceeds source duration: {observation.observation_id}"
                )
        return selected

    def run(self, context: AdapterContext) -> SidecarOutput:
        values = self.observe(
            context.sidecar_observations,
            int(context.inventory["duration_ms"]),
        )
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
