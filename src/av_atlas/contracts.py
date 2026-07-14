"""Typed boundary contracts for observations and evidence-ledger records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from av_atlas.errors import AtlasError

Modality = Literal["VID", "AUD", "ASR", "SUB", "OCR", "ENTITY"]
AdapterStatus = Literal[
    "success",
    "success_zero",
    "unsupported_input",
    "unavailable_dependency",
    "decode_failure",
    "resource_limit_failure",
    "invalid_configuration",
    "interrupted_retryable_failure",
    "permanent_failure",
]


@dataclass(frozen=True)
class Observation:
    observation_id: str
    adapter: str
    start_ms: int
    end_ms: int
    claim_type: str
    text: str
    confidence: float
    modality: Modality
    speaker_id: str | None = None
    speech_text: str | None = None
    speech_source: str | None = None
    evidence_ref_override: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Observation:
        try:
            item = cls(
                observation_id=str(value["observation_id"]),
                adapter=str(value["adapter"]),
                start_ms=int(value["start_ms"]),
                end_ms=int(value["end_ms"]),
                claim_type=str(value["claim_type"]),
                text=str(value["text"]),
                confidence=float(value["confidence"]),
                modality=value["modality"],
                speaker_id=value.get("speaker_id"),
                speech_text=value.get("speech_text"),
                speech_source=value.get("speech_source"),
                evidence_ref_override=value.get("evidence_ref_override"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AtlasError(f"invalid sidecar observation: {exc}") from exc
        if item.start_ms < 0 or item.end_ms <= item.start_ms:
            raise AtlasError(f"zero-length or invalid observation {item.observation_id}")
        if not 0 <= item.confidence <= 1:
            raise AtlasError(f"invalid confidence for {item.observation_id}")
        if item.modality not in {"VID", "AUD", "ASR", "SUB", "OCR", "ENTITY"}:
            raise AtlasError(f"invalid modality for {item.observation_id}")
        if item.speech_text is not None and item.modality not in {"ASR", "SUB"}:
            raise AtlasError("quoted speech is permitted only on ASR or subtitle evidence")
        return item


@dataclass(frozen=True)
class AdapterResult:
    adapter: str
    status: AdapterStatus
    observations: tuple[Observation, ...] = ()
    detail: str = ""
    retryable: bool = False

    def as_record(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "status": self.status,
            "observation_count": len(self.observations),
            "detail": self.detail,
            "retryable": self.retryable,
        }


def evidence_ref(observation: Observation, source_id: str) -> str:
    if observation.evidence_ref_override is not None:
        return observation.evidence_ref_override
    if observation.modality in {"VID", "AUD"}:
        return f"{observation.modality}:{source_id}:ms:{observation.start_ms}-{observation.end_ms}"
    return f"{observation.modality}:{observation.observation_id}"
