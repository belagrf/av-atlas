# ADR-0001: Standard-library CLI and deterministic sidecar baseline

- Status: accepted
- Date: 2026-07-13
- Milestone: M0/M1 first assignment

## Context

The new repository needed a CPU-only offline vertical slice without model weights or API services.
The contracts require replaceable perception branches, strict evidence provenance, restart safety,
and an installable developer workflow.

## Decision

Use Python dataclasses and JSON Schema Draft 2020-12 for boundary contracts, `argparse` for the small
CLI, and `jsonschema` for runtime validation. Keep the human-authored baseline configuration as JSON
syntax inside a `.yaml` file (JSON is a YAML subset), allowing deterministic standard-library
loading without a second runtime parser. Use FFV1/PCM Matroska synthetic media and five typed
sidecar adapters. Each observation maps transparently to one atomic event.

## Consequences

The default path remains small, offline, inspectable, and independent of GPU libraries. Pydantic or
another generated-schema contract layer can be introduced later behind the same versioned schemas.
The current loader accepts the documented JSON-subset configuration, not arbitrary YAML. Sidecars
are a tested baseline and do not represent real perception or a trained model.

