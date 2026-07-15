# AV-Atlas

No project license has yet been selected. Public visibility permits inspection of the source but
does not grant reuse rights beyond applicable law. AV-Atlas is therefore not currently described as
open source.

AV-Atlas is an evidence-first research implementation for comprehensive audiovisual
transcription. This repository implements M0/M1, M2A, the bounded M2B frame-OCR increment, and an
M2B.2 stable-input hardening candidate. The original M1 path
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

Controlled fixtures auto-authorize only when their marker matches the exact bytes. For any other
local source, standalone inspection is rights-gated too:

```bash
uv run av-atlas inspect LOCAL_MEDIA --rights-manifest LOCAL_RIGHTS
uv run av-atlas inspect-subtitles LOCAL_MEDIA --rights-manifest LOCAL_RIGHTS
```

`inspect --output` is create-only. It refuses an existing path, symlink, or hard link so inspection
cannot replace the source or another file.

Non-fixture media is refused without `--rights-manifest`. Executable `run` modes are distinct from
the broader rights vocabulary: `analysis` requires analysis plus derivative retention, while
`evaluation` requires analysis, evaluation, and derivative retention. Annotation, training,
derivative retention, and redistribution are permissions but are not executable run modes.
Declarations are content-hash-bound and operator IDs are hashed; they are operator
assertions, not legal conclusions. New runs never retain an external source path. Interrupted
resume therefore requires `resume RUN --media MEDIA`; the exact bytes, rights linkage, and
permissions are rechecked before a fresh private snapshot is acquired.

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
- `no sidecar observations are available`: M1 sidecars are accepted only for an exact hash-bound
  controlled fixture; use `make-fixture` rather than placing an arbitrary sidecar beside media.
- `run directory is not empty`: choose a new output directory or validate/resume the existing run.
- validation errors are actionable and return a nonzero status; inspect `quality_report.json` for
  schema, evidence, time, revision, or hash failures.
- `non-fixture media requires --rights-manifest`: create an operator declaration with `make-rights`;
  do not select permissions you do not actually possess.
- `resume requires --media`: the source path was intentionally not retained; provide the original
  exact file, whose hash and rights are rechecked before a fresh snapshot is acquired.

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
[M2B controlled baseline v1](docs/releases/M2B_CONTROLLED_BASELINE_V1.md). The separately versioned
[M2B controlled baseline v1.1](docs/releases/M2B_CONTROLLED_BASELINE_V1_1.md) freezes the reviewed
M2B.1 source-audit hardening without changing v1. Two workers are the provisional recommendation
for a future versioned configuration; the frozen baseline remains unchanged.

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

M2B.2 `run`, `resume`, `inspect`, `inspect-subtitles`, and pilot preparation authorize and hash a
regular non-symlink source before creating a bounded 0600 byte-for-byte copy in a unique 0700
directory. Source and temporary-copy defaults are each 8 GiB (`configs/m2b2.yaml`); neither may
exceed 64 GiB. FFprobe and FFmpeg see only the verified snapshot, and Tesseract sees only frames
derived from it. `stable_input.json` records a versioned, path-free receipt while the snapshot is
deleted before successful completion. Interrupted resume always reacquires a fresh snapshot:

```bash
uv run av-atlas run tests/fixtures/generated/m2b/m2b_ocr_controlled.mkv \
  --config configs/m2b2.yaml --output runs/m2b2-controlled
uv run av-atlas validate runs/m2b2-controlled
uv run av-atlas resume runs/m2b2-controlled --media \
  tests/fixtures/generated/m2b/m2b_ocr_controlled.mkv
```

Crash recovery examines only a bounded set of marker-recognized inactive private leases; it never
recursively deletes an unrecognized directory or follows a symlink. `SIGKILL`/power loss, same-UID
hostility, native-parser sandboxing, growing livestream input, and retained-frame lifecycle remain
limitations. Supported entry points enforce snapshot routing, while low-level internal parser
helpers still accept plain paths.

Temporal OCR tracks are validated relationally against immutable raw observations; malformed
parallel arrays become actionable quality-report errors rather than validator tracebacks.

M2B.1 status: “M2B.1 rights, configuration, partial-result, provenance, temporal-track, validation,
privacy, and clean-checkout hardening complete for the controlled synthetic baseline. Authorized
real-media evaluation remains pending.” This describes four synthetic frames and 13 OCR
observations only. It establishes no real-media accuracy, semantic understanding, or trained-model
capability. M2B.2 stable-input and rights-gated inspection are implemented on this review branch,
not released or merged. Full M2 is incomplete, and M2C is unimplemented. The real-media pilot
remains gated by
[stable-input security issue #11](https://github.com/belagrf/av-atlas/issues/11) and
[standalone-inspection governance issue #12](https://github.com/belagrf/av-atlas/issues/12) until
this M2B.2 pull request is reviewed and merged. No pilot media was processed.
