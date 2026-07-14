# AV-Atlas

No project license has yet been selected. Public visibility permits inspection of the source but
does not grant reuse rights beyond applicable law. AV-Atlas is therefore not currently described as
open source.

AV-Atlas is an evidence-first research implementation for comprehensive audiovisual
transcription. This repository implements M0/M1, M2A, and the bounded M2B frame-OCR increment. The original M1 path
remains available:
deterministic synthetic media is inventoried, chunked, sampled, combined with production-shaped
sidecar perception adapters, and written as a validated evidence ledger plus derived transcript and
timeline views. It is CPU-only, offline, and does not contain a trained model or measured model
performance. M2A adds rights-gated non-fixture ingest, real embedded text-subtitle extraction,
deterministic structural shot/keyframe perception, and synthetic component evaluation. It does not
complete full M2 or introduce an AV-Atlas-trained model. M2B adds rights-gated local Tesseract
frame text detection/recognition; it is not semantic visual understanding.

## Requirements and setup

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- FFmpeg and ffprobe on `PATH`
- DejaVu Sans at `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` for byte-stable fixtures

```bash
uv sync --extra dev
uv run av-atlas doctor
```

`doctor` exits nonzero when FFmpeg or ffprobe is missing and explicitly reports GPU support as
optional. No API key, network connection, checkpoint, or GPU is needed after environment setup.

## Run the offline baseline

```bash
uv run av-atlas make-fixture --output tests/fixtures/generated
uv run av-atlas inspect tests/fixtures/generated/synthetic.mkv \
  --output tests/fixtures/generated/inventory.json
uv run av-atlas run tests/fixtures/generated/synthetic.mkv \
  --config configs/baseline.yaml --output runs/example
uv run av-atlas validate runs/example
uv run av-atlas export runs/example
```

## Run the offline M2A demonstration

```bash
uv run av-atlas make-fixture --profile m2a --include-edge-fixtures \
  --output tests/fixtures/generated/m2a
uv run av-atlas make-rights tests/fixtures/generated/m2a/m2a_controlled.mkv \
  --output tests/fixtures/generated/m2a/rights.json \
  --operator-id controlled-demo-operator --basis synthetic-controlled \
  --allow analysis --allow evaluation --allow derivative_artifact_retention \
  --notes "Project-authored M2A controlled fixture"
uv run av-atlas inspect tests/fixtures/generated/m2a/m2a_controlled.mkv \
  --output tests/fixtures/generated/m2a/inventory.json
uv run av-atlas inspect-subtitles tests/fixtures/generated/m2a/m2a_controlled.mkv
uv run av-atlas run tests/fixtures/generated/m2a/m2a_controlled.mkv \
  --config configs/m2a.yaml --rights-manifest tests/fixtures/generated/m2a/rights.json \
  --operation analysis --output runs/m2a-demo
uv run av-atlas export runs/m2a-demo
uv run av-atlas validate runs/m2a-demo
uv run av-atlas evaluate runs/m2a-demo tests/gold/m2a-controlled.gold.json \
  --tolerance-ms 200
uv run av-atlas validate runs/m2a-demo
uv run av-atlas resume runs/m2a-demo
```

Non-fixture media is refused without `--rights-manifest`. A run requires both its requested
operation and derivative-artifact-retention permission. `evaluate` additionally requires evaluation
permission. Declarations are content-hash-bound and operator IDs are hashed; they are operator
assertions, not legal conclusions. When a source is outside the run directory's parent, its path is
not retained and interrupted resume requires `resume RUN --media MEDIA`.

`run` refuses to overwrite a nonempty directory. `resume RUN_DIR` completes an interrupted run and
is a no-op for a completed run. The checked-in tests simulate interruption at the inventory
checkpoint and prove that repeated resume does not duplicate final records.

The run contains canonical provisional and final JSONL ledgers, a resolvable evidence index,
pseudonymous entities, inventory and rights provenance, a manifest with artifact hashes, VTT/SRT,
Markdown timeline and summary, structured logs, state, and JSON/Markdown quality reports. Views are
derived only from `events.final.jsonl`. The quality report is created by validation and is not
self-hashed; every source/state/component artifact listed in the manifest is hash-checked.

M2A runs additionally contain a rights declaration, dependency BOM, adapter statuses, subtitle
track inventory, canonical cues, hashed raw WebVTT, shot boundaries, keyframe index and PNGs, and
machine/human component evaluation. Bitmap subtitle codecs have explicit unsupported status.

## Quality gates

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

The test suite uses no network and no accelerator. It covers schemas, invalid and zero-length
intervals, overlapping chunk boundaries, missing streams, corrupt ffprobe metadata, unsafe file
names, prompt-injection content isolation, deterministic fixtures and semantic artifacts, dangling
evidence, interruption, and idempotent resume.
M2A coverage adds rights mismatch/permission/expiry, subtitle track metadata and parsing edge cases,
bitmap degradation, hard/gradual/flash behavior, keyframe evidence, missing modalities, resource
limits, component metrics, and M2A resume/determinism.

## Troubleshooting

- `required executable not found`: install the system FFmpeg package and rerun `doctor`.
- `required deterministic fixture font is unavailable`: install DejaVu Sans. This explicit failure
  avoids silently creating a different fixture.
- `no sidecar observations are available`: M1 intentionally supports deterministic sidecars only;
  use `make-fixture` or supply a schema-compatible `.observations.json` beside the media.
- `run directory is not empty`: choose a new output directory or validate/resume the existing run.
- validation errors are actionable and return a nonzero status; inspect `quality_report.json` for
  schema, evidence, time, revision, or hash failures.
- `non-fixture media requires --rights-manifest`: create an operator declaration with `make-rights`;
  do not select permissions you do not actually possess.
- `resume requires --media`: the source path was intentionally not retained outside the bounded run
  parent; provide the original exact file, whose hash is rechecked.

See [architecture](docs/architecture.md), [security](docs/security.md),
[data governance](docs/data-governance.md), and [project state](docs/PROJECT_STATE.md).

## M2B frame-OCR engineering path

Tesseract is optional and never installed automatically:

```bash
uv run av-atlas inspect-ocr
uv run av-atlas make-fixture --profile m2b --output tests/fixtures/generated/m2b
uv run av-atlas run tests/fixtures/generated/m2b/m2b_ocr_controlled.mkv \
  --config configs/m2b.yaml --output runs/m2b-ocr
uv run av-atlas export runs/m2b-ocr
uv run av-atlas validate runs/m2b-ocr
uv run av-atlas evaluate-ocr runs/m2b-ocr tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas benchmark-ocr runs/m2b-ocr tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas resume runs/m2b-ocr
```

The verified Ubuntu host has operator-installed `tesseract-ocr` 5.3.4-1build5 and
`tesseract-ocr-eng` 1:4.1.0-2. `inspect-ocr` records executable/package/license/build-feature and
language-data identities and hashes; AV-Atlas never installs them. Machines without the approved
dependency retain an explicit actionable unavailable state.
See [OCR annotation guide](docs/ocr-annotation-guide.md) for external-pilot handling.
The accepted controlled release and offline replay procedure are recorded in
[M2B controlled baseline v1](docs/releases/M2B_CONTROLLED_BASELINE_V1.md). Two workers are the
provisional recommendation for a future versioned configuration; the frozen baseline remains
unchanged.

An authorized real-media pilot is prepared, annotated, frozen, run, and evaluated with
`pilot-prepare`, `pilot-annotation-packages`, `pilot-compare-annotations`, `pilot-freeze`,
`pilot-run-ocr`, and `pilot-evaluate`. These commands do nothing without operator-supplied local
media and sufficient rights. No pilot media or human annotation is currently present.

M2B.1 hardening uses strict configuration types, fail-closed rights checksum/linkage validation,
versioned `partial_success` unit accounting, actual overlapping-chunk provenance, and a derived
temporal OCR text-track artifact. Raw OCR observations are never destructively deduplicated. A
rights `manifest_hash` is an integrity checksum, not an authenticated signature. Ordinary exported
OCR inventories redact full paths; `inspect-ocr --local-private-diagnostic` is explicitly local and
must not be attached to a public run.
