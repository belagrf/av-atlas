# AV-Atlas

No project license has yet been selected. Public visibility permits inspection of the source but
does not grant reuse rights beyond applicable law. AV-Atlas is therefore not currently described as
open source.

AV-Atlas is an evidence-first research implementation for comprehensive audiovisual
transcription. This repository implements M0/M1, M2A, the bounded M2B frame-OCR increment, the
reviewed M2B.2 stable-input increment, and the M2B.3 pilot-security implementation now under source
review. The original M1 path
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
- Bubblewrap on Linux for the M2B.3 pilot path; controlled baseline commands remain usable without
  it, while pilot native parsing fails closed

```bash
uv sync --extra dev
uv run av-atlas doctor
```

`doctor` exits nonzero when FFmpeg or ffprobe is missing and explicitly reports GPU support as
optional. No API key, network connection, checkpoint, or GPU is needed after environment setup.

## Run the offline baseline

```bash
uv run av-atlas make-fixture --output tests/fixtures/generated
uv run av-atlas make-rights tests/fixtures/generated/synthetic.mkv \
  --output tests/fixtures/generated/rights.json \
  --operator-id controlled-demo-operator --basis synthetic-controlled \
  --allow analysis --allow evaluation --allow derivative_artifact_retention
uv run av-atlas inspect tests/fixtures/generated/synthetic.mkv \
  --rights-manifest tests/fixtures/generated/rights.json \
  --output tests/fixtures/generated/inventory.json
uv run av-atlas run tests/fixtures/generated/synthetic.mkv \
  --config configs/baseline.yaml --rights-manifest tests/fixtures/generated/rights.json \
  --output runs/example
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
  --rights-manifest tests/fixtures/generated/m2a/rights.json \
  --output tests/fixtures/generated/m2a/inventory.json
uv run av-atlas inspect-subtitles tests/fixtures/generated/m2a/m2a_controlled.mkv \
  --rights-manifest tests/fixtures/generated/m2a/rights.json
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

Every fresh run and standalone inspection requires an explicit source-bound rights manifest,
including controlled fixtures:

```bash
uv run av-atlas inspect LOCAL_MEDIA --rights-manifest LOCAL_RIGHTS
uv run av-atlas inspect-subtitles LOCAL_MEDIA --rights-manifest LOCAL_RIGHTS
```

`inspect --output` is create-only. It refuses an existing path, symlink, or hard link so inspection
cannot replace the source or another file.

All fresh media is refused without `--rights-manifest`. Only an explicit `synthetic-controlled`
rights basis plus an exact current fixture 1.1 bundle enables controlled-fixture status and bound
sidecar observations. Owned, licensed, public-domain, and other documented authorization remain
ordinary rights: adjacent fixture markers and sidecars are ignored. A marker checksum is an
integrity check, not a trust credential. Legacy fixture markers remain readable only in historical
run validation. Executable `run` modes are distinct from
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

The test suite uses no external network and no accelerator; one hostile-manifest regression binds
a loopback-only HTTP sentinel and proves that it receives zero requests. It covers schemas, invalid and zero-length
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
- `no sidecar observations are available`: M1 sidecars are accepted only when a fixture-manifest
  1.1 descriptor binds the canonical basename, type, payload schema, SHA-256, and bounded byte
  size. Use `make-fixture`; legacy or fabricated adjacent sidecars are never authoritative.
- `run directory is not empty`: choose a new output directory or validate/resume the existing run.
- validation errors are actionable and return a nonzero status; inspect `quality_report.json` for
  schema, evidence, time, revision, or hash failures.
- `fresh processing and inspection authorization requires --rights-manifest`: create an operator
  declaration with `make-rights`, including for a controlled fixture;
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
uv run av-atlas make-rights tests/fixtures/generated/m2b/m2b_ocr_controlled.mkv \
  --output tests/fixtures/generated/m2b/rights.json \
  --operator-id controlled-demo-operator --basis synthetic-controlled \
  --allow analysis --allow evaluation --allow derivative_artifact_retention
uv run av-atlas run tests/fixtures/generated/m2b/m2b_ocr_controlled.mkv \
  --config configs/m2b.yaml --rights-manifest tests/fixtures/generated/m2b/rights.json \
  --output runs/m2b-ocr
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
M2B.1 source-audit hardening without changing v1. The
[M2B controlled baseline v1.2](docs/releases/M2B_CONTROLLED_BASELINE_V1_2.md) release record freezes
the reviewed M2B.2 source at package version 0.2.2. Final annotated-tag and GitHub-release
identities are verified externally. Two workers are the provisional recommendation
for a future versioned configuration; the frozen baseline remains unchanged.

An authorized real-media pilot is prepared, annotated, frozen, run, and evaluated with
`pilot-prepare`, `pilot-annotation-packages`, `pilot-compare-annotations`, `pilot-freeze`,
`pilot-run-ocr`, and `pilot-evaluate`. These commands do nothing without operator-supplied local
media and sufficient rights. No real/operator-supplied pilot media or human annotation is present;
the M2B.3 security check uses only project-authored synthetic bytes.

M2B.1 hardening uses strict configuration types, fail-closed rights checksum/linkage validation,
versioned `partial_success` unit accounting, actual overlapping-chunk provenance, and a derived
temporal OCR text-track artifact. Raw OCR observations are never destructively deduplicated. A
rights `manifest_hash` is an integrity checksum, not an authenticated signature. Ordinary exported
OCR inventories redact full paths; `inspect-ocr --local-private-diagnostic` is explicitly local and
must not be attached to a public run.

M2B.2 `run`, `resume`, `inspect`, `inspect-subtitles`, and pilot preparation authorize and hash a
regular non-symlink source before creating a bounded 0600 byte-for-byte copy in a unique 0700
directory. Source and temporary-copy defaults are each 8 GiB (`configs/m2b2.yaml`); neither may
exceed 64 GiB. Before any media decode, parser-free magic classification selects fixed native-input
policy `av-atlas-native-input/1.0.0`. Authorized sources are limited to self-contained
Matroska/WebM, forced through the `matroska` demuxer with input protocol whitelist `file` and format
whitelist `matroska`. HLS, DASH, concat/concatf, image sequences, Blu-ray navigation, MOV/MP4, and
all unknown or network-capable source formats are rejected before a parser starts. Generated OCR
frames use the separate forced single-PNG `png_pipe` policy. FFprobe and FFmpeg receive only the
verified snapshot or a verified generated frame; Tesseract sees only snapshot-derived frames.

Fixture-manifest 1.1 binds the sole currently accepted runtime sidecar type by canonical basename,
payload schema, SHA-256, and size. It is opened without following a final symlink, read under a
1 MB ceiling with pre/post identity checks, parsed once, and supplied to adapters as immutable
`Observation` values. Adapters never reread an original adjacent sidecar path. Historical 1.0
fixture manifests remain validation-compatible but cannot authorize fresh execution. Neither a
current marker nor its self-checksum is an authorization credential.

Current stable-input receipt 1.2 records versioned, path-free explicit trust mode, rights basis,
rights-checksum linkage, exact current fixture-manifest checksum/contract when controlled, and
sidecar acquisition provenance. Run-manifest 1.1 records the same declaration-derived trust
decision. Media-inventory 1.1 records the exact native-input policy. Historical receipt, run, and
inventory contracts remain validation-compatible. The snapshot is unlinked before successful
completion. Interrupted resume always reacquires a fresh snapshot and requires the same trust
decision and exact bundle bindings:

```bash
uv run av-atlas run tests/fixtures/generated/m2b/m2b_ocr_controlled.mkv \
  --config configs/m2b2.yaml --rights-manifest tests/fixtures/generated/m2b/rights.json \
  --output runs/m2b2-controlled
uv run av-atlas validate runs/m2b2-controlled
uv run av-atlas resume runs/m2b2-controlled --media \
  tests/fixtures/generated/m2b/m2b_ocr_controlled.mkv
```

Crash recovery examines only a bounded set of marker-recognized inactive private leases; it never
recursively deletes an unrecognized directory or follows a symlink. `SIGKILL`/power loss, hostile
same-UID host processes, growing livestream input, and a retained-frame lifecycle outside the
policy-bound pilot path remain limitations. Pilot-retained frames and other pilot derivatives use
the separate retained-root contract below. Runtime decode helpers reclassify their input and
require the fixed policy. The controlled non-pilot compatibility path is still not an operating-
system sandbox; every pilot native child uses the mandatory boundary described below.

Snapshot cleanup unlinks the private file and removes its lease directory. This is logical
lifecycle cleanup, not cryptographic or secure erasure. The default OS temporary root may be
disk-backed, journaled, snapshotted, swapped, or backed up. Before real operator media, the operator
must select and document an appropriately private, capacity-bounded temporary root—such as an
encrypted local volume or suitably configured tmpfs—or obtain an independent, pilot-scoped,
expiring residual-remanence acceptance with compensating controls and a deletion plan. A tmpfs may
still swap unless configured appropriately. Storage-remanence acceptance never waives the mandatory
native-process sandbox.

## M2B.3 private pilot-security path

M2B.3 adds versioned local-private policy and sanitized public-receipt contracts without
authorizing real media. Current policy `av-atlas-pilot-security-policy/1.1.0` binds one pilot ID
and frozen specification to distinct pre-created current-UID-owned `0700` transient and retained
local roots, their device/inode and filesystem identities, expiring storage decisions, separate
capacity ceilings and reserves, exact Bubblewrap identity/profile, and native resource limits.
Both roots must be outside the tracked checkout and every retained package is a direct,
descriptor-created child of the retained root. The policy is mode `0600`, must be named
`pilot-security-policy.local.json` or
`*.pilot-security-policy.local.json`, is ignored by Git, and must never be copied into a run, log,
report, annotation package, release, or PR. Reviewed storage decisions persist a pilot-scoped,
expiring reviewer pseudonym in that private policy; sanitized receipt 1.1 deliberately omits it.
Cleanup is logical deletion only, never a secure-erasure claim; tmpfs may swap and reviewed
encryption remains an operator/reviewer assertion. Policy and receipt self-hashes are integrity
checksums, not authenticated signatures. Historical 1.0 records remain validation compatible but
cannot authorize current execution.

Every production pilot writer creates files relative to a pinned retained-package descriptor,
uses create-only private files, and applies the policy's aggregate-byte and current-capacity checks
before each bounded write. Inputs reused by compare, freeze, OCR, or evaluation are stably read and
hash/size-verified from that retained package rather than reopened through an arbitrary pathname.

Pilot FFprobe, FFmpeg, and Tesseract calls share the typed Bubblewrap profile
`av-atlas-bubblewrap-pilot/1.1.0`. It has no direct-execution fallback: missing or changed
Bubblewrap or failed namespace capability checks stop before pilot parsing. The profile denies
networking, exposes descriptor-verified inputs read-only, makes only host-backed `/work` writable,
provides a writable sandbox-local private `/tmp`, clears the environment, exposes no home
directory, drops capabilities, and applies CPU, address-space, file-size, descriptor,
process-count, capture, core-dump, and wall-time bounds. Instead of all of `/usr`, it exposes only
the reviewed runtime subtrees `/usr/bin`, `/usr/lib`, optional `/usr/lib64`,
`/usr/share/tesseract-ocr`, and optional `/etc/alternatives`; mutable/source/documentation subtrees
are masked or unexposed. Operator inputs and both storage roots may not overlap an exposed runtime
subtree. The published profile SHA-256 binds that declarative mount/argument record; it does not
separately hash-bind the Python overlap guard or runner code, which is identified by the source
commit and exercised by regressions.

The project-authored M2B.3 synthetic check authorizes its source before either FFprobe or FFmpeg
runs: it requires an explicit source-bound `synthetic-controlled` declaration with the full
evaluation permission closure and the exact current controlled-fixture bundle. The local-private
security policy supplements that media authorization; it does not replace it. Current synthetic
reports use `av-atlas-m2b3-synthetic-pilot/1.1.0`; legacy 1.0 reports remain historical-validation
compatible but cannot authorize a new execution.

Raw OCR observations and their evidence index remain authoritative. Completed pilot OCR is a
fixed-file `av-atlas-pilot-ocr-output/1.0.0` package: its manifest hash-binds the frozen pilot,
policy, prepared and `ocr-complete` receipts, rights aggregate, configuration, sanitized
dependency, observations, evidence, runtime, record counts, and semantic output. `pilot-evaluate`
accepts that package rather than loose observation/runtime paths and recomputes every binding
before metrics. Package checksums detect corruption and substitution but are not signatures.

The local operator flow is explicit. `LOCAL_TRANSIENT_ROOT` and `LOCAL_RETAINED_ROOT` must be
distinct absolute canonical paths outside the checkout. The policy path
`PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json` must also be outside the checkout;
all three paths are private and must remain outside tracked/public artifacts. Every retained
output argument below names a fresh direct child of `LOCAL_RETAINED_ROOT`, not an arbitrary path:

```bash
uv run av-atlas inspect-bubblewrap
uv run av-atlas pilot-security-create \
  --root LOCAL_TRANSIENT_ROOT --retained-root LOCAL_RETAINED_ROOT \
  --pilot-id PILOT_ID --pilot-spec PILOT_SPEC \
  --output PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json \
  --expires-at EXPIRY_RFC3339 \
  --storage-decision verified-tmpfs \
  --retained-storage-decision verified-tmpfs
uv run av-atlas pilot-security-inspect \
  PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json --pilot-spec PILOT_SPEC
uv run av-atlas pilot-security-validate \
  PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json --pilot-spec PILOT_SPEC
uv run av-atlas pilot-security-synthetic-check \
  CONTROLLED_MEDIA CONTROLLED_RIGHTS PILOT_SPEC \
  PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json \
  --output FRESH_IGNORED_SYNTHETIC_REPORT_DIR
uv run av-atlas pilot-prepare PILOT_SPEC \
  --security-policy PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json \
  --output FRESH_PRIVATE_PILOT_DIR
uv run av-atlas pilot-run-ocr FRESH_PRIVATE_PILOT_DIR FROZEN_MANIFEST \
  --security-policy PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json \
  --output FRESH_PRIVATE_OCR_DIR
uv run av-atlas pilot-evaluate FRESH_PRIVATE_PILOT_DIR FROZEN_MANIFEST \
  ADJUDICATED_GOLD FRESH_PRIVATE_OCR_DIR \
  --security-policy PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json \
  --output FRESH_PRIVATE_EVALUATION_DIR
uv run av-atlas pilot-security-validate-artifacts FRESH_PRIVATE_PILOT_DIR \
  --security-policy PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json
```

`pilot-evaluate` accepts the authenticated OCR package directory, validates its fixed manifest and
every bound component, and only then computes metrics. It does not accept loose OCR observation or
runtime files.

On the measured Ubuntu host, approved locally installed, system-packaged Bubblewrap 0.9.0 actually
ran a project-authored synthetic fixture through sandboxed FFprobe, FFmpeg, and Tesseract.
Measured hostile probes denied loopback/external network, an out-of-mount sentinel, the masked
mutable runtime sentinel, and root/device/host-backed writes outside `/work`; a parent-created
writable outside positive control remained unchanged. The UTS hostname was replaced with a fixed
non-host value, and the private sandbox-local `/tmp` remained writable as designed. Transient
workspace cleanup, retained-output bounds, and path-redaction checks passed. These are
host-security engineering measurements, not real-media OCR accuracy or proof that native parsers
contain no vulnerabilities. Final M2B.3
acceptance remains pending source review of issue
[#17](https://github.com/belagrf/av-atlas/issues/17); the issue and PR remain open and unmerged.

Temporal OCR tracks are validated relationally against immutable raw observations; malformed
parallel arrays become actionable quality-report errors rather than validator tracebacks.

M2B.2 status: “M2B.2 stable authorized input, rights-gated inspection, fixture-trust, and
native-input hardening complete for the controlled synthetic baseline. Authorized real-media
evaluation remains pending.” This describes four synthetic frames and 13 OCR observations only. It
establishes no real-media accuracy, semantic understanding, or trained-model capability. The
implementation is merged, and the v1.2 release record freezes the reviewed source at package
version 0.2.2; final annotated-tag and GitHub-release identities are verified externally. Full M2
is incomplete, and M2C is unimplemented. Issues
[#11](https://github.com/belagrf/av-atlas/issues/11),
[#12](https://github.com/belagrf/av-atlas/issues/12), and
[#14](https://github.com/belagrf/av-atlas/issues/14) closed with reviewed M2B.2 implementation.
The real-media pilot remains gated by
[#17](https://github.com/belagrf/av-atlas/issues/17). No real or operator-supplied pilot media was
processed.
