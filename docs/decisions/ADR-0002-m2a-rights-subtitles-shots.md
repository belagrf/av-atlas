# ADR-0002: Rights-gated ingest, canonical subtitles, and structural shots

- Status: accepted
- Date: 2026-07-13
- Milestone: M2A

## Context

M2A must admit operator-authorized non-fixture media without treating possession as authorization,
extract quoted subtitle evidence without a language model, and add replaceable structural video
perception while remaining CPU-only and offline. Media decoders are an attack surface, subtitle text
is untrusted content, and a deterministic synthetic evaluation cannot support real-media claims.

## Decision

1. A non-fixture run fails closed unless a versioned operator declaration is supplied. The
   declaration is bound to the exact source SHA-256, stores only a hashed operator ID, separately
   grants each operation, and records expiry and independent-review state. Analysis runs also
   require derivative-artifact-retention permission because this implementation always writes a run
   directory. The software validates declarations but makes no legal determination.
2. Embedded text subtitles are decoded locally by the installed FFmpeg build into WebVTT, retained
   as hashed raw intermediates, and parsed into canonical JSONL cues. Track index, codec, language,
   title, time base, and every disposition flag remain distinct. Cue text—including markup,
   newlines, Unicode, and prompt-like phrases—is inert evidence. Bitmap subtitles are explicitly
   unsupported rather than passed through OCR or fabricated.
3. Structural video perception decodes bounded 64x36 RGB samples at a configured rate. Mean
   absolute frame change proposes hard cuts and low-amplitude sustained change proposes gradual
   transitions. A return-to-prior-frame rule suppresses brief flashes. Each resulting half-open
   shot receives one deterministic midpoint PNG keyframe and evidence reference. This is not
   semantic visual understanding.
4. Sidecar, subtitle, and shot implementations execute through one adapter context/result protocol.
   Adapter failures carry an explicit status and never create observations.
5. Evaluation uses versioned project-authored synthetic gold. Runtime and memory are measured, but
   component accuracy is labeled fixture-only and carries sample-size limitations.

## Consequences

The core package gains no model or GPU dependency. FFmpeg remains mandatory and its configured GPL
build is recorded in the dependency BOM. Configuration and rights declarations are snapshotted in
the run; source paths outside the run parent are not retained, so resume requires `--media`.
Threshold-based shots are interpretable but domain-sensitive, and bitmap subtitles, semantic
vision, real ASR/OCR/diarization/acoustic perception, and real-media generalization remain M2 work.

