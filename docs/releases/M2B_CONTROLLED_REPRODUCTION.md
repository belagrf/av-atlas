# M2B controlled baseline reproduction

This is an offline, CPU-only fresh reproducibility replay. Calling a replay by the same
implementation on the same host “independent verification” would overstate the evidence.

The v1 procedure below remains the historical reproduction contract at the immutable v1 tag. The
v1.1 extension applies at its immutable tag and adds the reviewed M2B.1 secondary-track,
permission-closure, validation, and clean-checkout checks without changing v1 inputs or artifacts.
Those historical commands predate the current requirement for an explicit rights manifest on
every fresh fixture run. Use the v1.2 procedure at the end of this document on current source; do
not weaken current authorization merely to replay an older CLI transcript.

## Preconditions

Use a fresh checkout/worktree with locked project dependencies already present and approved
distribution packages for FFmpeg, ffprobe, Tesseract 5.3.4, and English tessdata. Disconnect
networking or use an enforced no-network environment. Do not use a GPU, cloud service, model
download, or external media. Confirm `uv sync --extra dev --locked --offline` succeeds before
deleting any existing environment cache.

A local container runtime was detected during v1, but its only cached Python image lacked FFmpeg,
Tesseract, and uv. No image was pulled and no package was installed, so no container result is
claimed.

## v1 fresh replay

From the repository root, choose new empty `REPLAY_FIXTURES` and `REPLAY_RUN` directories, then run:

```sh
uv lock --check
uv sync --extra dev --locked --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run av-atlas doctor
uv run av-atlas inspect-ocr
uv run av-atlas make-fixture --profile m2b --output "$REPLAY_FIXTURES"
sha256sum "$REPLAY_FIXTURES/m2b_ocr_controlled.mkv" \
  tests/gold/m2b-ocr-controlled.gold.json configs/m2b.yaml
uv run av-atlas run "$REPLAY_FIXTURES/m2b_ocr_controlled.mkv" \
  --config configs/m2b.yaml --output "$REPLAY_RUN"
uv run av-atlas evaluate-ocr "$REPLAY_RUN" tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas benchmark-ocr "$REPLAY_RUN" tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas validate "$REPLAY_RUN"
uv run av-atlas resume "$REPLAY_RUN" --media "$REPLAY_FIXTURES/m2b_ocr_controlled.mkv"
uv run av-atlas resume "$REPLAY_RUN" --media "$REPLAY_FIXTURES/m2b_ocr_controlled.mkv"
uv run av-atlas validate "$REPLAY_RUN"
```

Regenerate and validate M1 and M2A with their documented README commands as regression checks. To
test interruption, start a new M2B run, interrupt it during OCR, resume twice, and validate after
each resume.

Fixture, gold, configuration, and OCR observation hashes must exactly match the v1 release record.
Runtime-bearing evaluation, benchmark, BOM, logs, and run-manifest bytes can change across machines
and executions. Compare invariant fields and the observation semantic hash rather than expecting
those files to be byte-identical. Within a completed run, hash all keys listed in
`run_manifest.json` before and after each resume; every listed artifact must remain byte-identical.

## v1.1 fresh release replay

Use new empty ignored paths. `V11_FIXTURES`, `V11_RUN`, and `V11_INTERRUPTED` must not already
exist. No accepted v1 directory is overwritten.

```sh
uv lock --check
uv sync --extra dev --locked --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run av-atlas doctor
uv run av-atlas make-fixture --profile m2b --output "$V11_FIXTURES"
sha256sum "$V11_FIXTURES/m2b_ocr_controlled.mkv" \
  tests/gold/m2b-ocr-controlled.gold.json configs/m2b.yaml
uv run av-atlas run "$V11_FIXTURES/m2b_ocr_controlled.mkv" \
  --config configs/m2b.yaml --output "$V11_RUN"
uv run av-atlas evaluate-ocr "$V11_RUN" tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas benchmark-ocr "$V11_RUN" tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas validate "$V11_RUN"
uv run av-atlas resume "$V11_RUN" --media "$V11_FIXTURES/m2b_ocr_controlled.mkv"
uv run av-atlas resume "$V11_RUN" --media "$V11_FIXTURES/m2b_ocr_controlled.mkv"
uv run av-atlas validate "$V11_RUN"

uv run av-atlas run "$V11_FIXTURES/m2b_ocr_controlled.mkv" \
  --config configs/m2b.yaml --output "$V11_INTERRUPTED" --stop-after inventory
uv run av-atlas resume "$V11_INTERRUPTED" \
  --media "$V11_FIXTURES/m2b_ocr_controlled.mkv"
uv run av-atlas evaluate-ocr "$V11_INTERRUPTED" \
  tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas benchmark-ocr "$V11_INTERRUPTED" \
  tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas validate "$V11_INTERRUPTED"
uv run av-atlas resume "$V11_INTERRUPTED" \
  --media "$V11_FIXTURES/m2b_ocr_controlled.mkv"
uv run av-atlas resume "$V11_INTERRUPTED" \
  --media "$V11_FIXTURES/m2b_ocr_controlled.mkv"
uv run av-atlas validate "$V11_INTERRUPTED"
```

The release comparison digest is SHA-256 over newline-delimited rows sorted by artifact path. Each
row is `<current-file-sha256><two spaces><manifest-relative-path>`. Paths are exactly the sorted keys
of `run_manifest.json`'s `artifacts` object. The digest is a compact report of a full per-file map;
validation still recomputes and checks each artifact independently. Capture the map before resume,
after first resume, and after repeated resume, and require exact equality rather than comparing only
the aggregate digest.

Fixture, gold, configuration, raw OCR observations, temporal OCR tracks, and the sanitized
dependency inventory are intended to be content-stable on the approved dependency set. Evaluation,
benchmark, BOM, logs, timestamps, resource measurements, and run-manifest bytes can legitimately
change with runtime or software inventory. Do not alter frozen inputs to force equality.

Regenerate and validate M1 and M2A using the README commands. The public CI workflow provides a
separate clean tracked-checkout test and must not depend on ignored local run evidence.

## Immutable release boundary

The `m2b-controlled-v1` tag predates the public-CI clean-checkout test fix. The annotated tag and
published release remain immutable and are not retargeted by M2B.1. The separately authorized v1.1
patch incorporates the clean-checkout fix and reviewed hardening changes at a new tag and commit.
The accepted v1 hashes remain historical release evidence; they are not silently regenerated.

## M2B.2/v1.2 fresh release replay

M2B.2 does not retarget either accepted tag or alter the frozen v1 fixture, gold, normalization,
metrics, or `configs/m2b.yaml`. From the release-preparation branch, use new empty ignored paths,
run the complete gates, regenerate all controlled fixtures, and use explicit synthetic rights. The
example below uses placeholders and never requires real media:

```bash
set -eu
V12_FIXTURES=tests/fixtures/generated/m2b-v1-2-replay
V12_RUNS=runs/m2b-v1-2-replay
test ! -e "$V12_FIXTURES"
test ! -e "$V12_RUNS"

uv lock --check
uv sync --extra dev --locked --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run av-atlas doctor

uv run av-atlas make-fixture --profile m1 --output "$V12_FIXTURES/m1"
uv run av-atlas make-fixture --profile m2a --include-edge-fixtures \
  --output "$V12_FIXTURES/m2a"
uv run av-atlas make-fixture --profile m2b --output "$V12_FIXTURES/m2b"

for profile in m1 m2a m2b; do
  case "$profile" in
    m1) media="$V12_FIXTURES/m1/synthetic.mkv" ;;
    m2a) media="$V12_FIXTURES/m2a/m2a_controlled.mkv" ;;
    m2b) media="$V12_FIXTURES/m2b/m2b_ocr_controlled.mkv" ;;
  esac
  uv run av-atlas make-rights "$media" \
    --output "$V12_FIXTURES/$profile/rights.json" \
    --operator-id controlled-replay --basis synthetic-controlled \
    --allow analysis --allow evaluation --allow derivative_artifact_retention
done

uv run av-atlas inspect "$V12_FIXTURES/m1/synthetic.mkv" \
  --rights-manifest "$V12_FIXTURES/m1/rights.json" \
  --output "$V12_FIXTURES/m1/inventory.json"
uv run av-atlas inspect "$V12_FIXTURES/m2a/m2a_controlled.mkv" \
  --rights-manifest "$V12_FIXTURES/m2a/rights.json" \
  --output "$V12_FIXTURES/m2a/inventory.json"
uv run av-atlas inspect-subtitles "$V12_FIXTURES/m2a/m2a_controlled.mkv" \
  --rights-manifest "$V12_FIXTURES/m2a/rights.json"

uv run av-atlas run "$V12_FIXTURES/m1/synthetic.mkv" \
  --config configs/baseline.yaml --rights-manifest "$V12_FIXTURES/m1/rights.json" \
  --operation analysis --output "$V12_RUNS/m1"
uv run av-atlas export "$V12_RUNS/m1"
uv run av-atlas validate "$V12_RUNS/m1"

uv run av-atlas run "$V12_FIXTURES/m2a/m2a_controlled.mkv" \
  --config configs/m2a.yaml --rights-manifest "$V12_FIXTURES/m2a/rights.json" \
  --operation analysis --output "$V12_RUNS/m2a"
uv run av-atlas export "$V12_RUNS/m2a"
uv run av-atlas evaluate "$V12_RUNS/m2a" tests/gold/m2a-controlled.gold.json \
  --tolerance-ms 200
uv run av-atlas validate "$V12_RUNS/m2a"

for pair in "m2b:configs/m2b.yaml" "m2b1:configs/m2b.yaml" "m2b2:configs/m2b2.yaml"; do
  name="${pair%%:*}"
  config="${pair#*:}"
  uv run av-atlas run "$V12_FIXTURES/m2b/m2b_ocr_controlled.mkv" \
    --config "$config" --rights-manifest "$V12_FIXTURES/m2b/rights.json" \
    --operation analysis --output "$V12_RUNS/$name"
  uv run av-atlas export "$V12_RUNS/$name"
  uv run av-atlas evaluate-ocr "$V12_RUNS/$name" \
    tests/gold/m2b-ocr-controlled.gold.json
  uv run av-atlas benchmark-ocr "$V12_RUNS/$name" \
    tests/gold/m2b-ocr-controlled.gold.json
  uv run av-atlas validate "$V12_RUNS/$name"
done

uv run av-atlas run "$V12_FIXTURES/m2b/m2b_ocr_controlled.mkv" \
  --config configs/m2b2.yaml --rights-manifest "$V12_FIXTURES/m2b/rights.json" \
  --operation analysis --output "$V12_RUNS/m2b2-interrupted" --stop-after inventory
uv run av-atlas resume "$V12_RUNS/m2b2-interrupted" \
  --media "$V12_FIXTURES/m2b/m2b_ocr_controlled.mkv"
uv run av-atlas export "$V12_RUNS/m2b2-interrupted"
uv run av-atlas evaluate-ocr "$V12_RUNS/m2b2-interrupted" \
  tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas benchmark-ocr "$V12_RUNS/m2b2-interrupted" \
  tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas validate "$V12_RUNS/m2b2-interrupted"

uv run av-atlas resume "$V12_RUNS/m2b2" \
  --media "$V12_FIXTURES/m2b/m2b_ocr_controlled.mkv"
uv run av-atlas resume "$V12_RUNS/m2b2" \
  --media "$V12_FIXTURES/m2b/m2b_ocr_controlled.mkv"
uv run av-atlas resume "$V12_RUNS/m2b2-interrupted" \
  --media "$V12_FIXTURES/m2b/m2b_ocr_controlled.mkv"
uv run av-atlas resume "$V12_RUNS/m2b2-interrupted" \
  --media "$V12_FIXTURES/m2b/m2b_ocr_controlled.mkv"
uv run av-atlas validate "$V12_RUNS/m2b2"
uv run av-atlas validate "$V12_RUNS/m2b2-interrupted"

sha256sum "$V12_FIXTURES/m2b/m2b_ocr_controlled.mkv" \
  "$V12_FIXTURES/m2b/m2b_ocr_controlled.fixture.json" \
  tests/gold/m2b-ocr-controlled.gold.json configs/m2b2.yaml
```

The fixture, gold, configuration, inventory, raw OCR, temporal-track, and sanitized dependency
hashes must match the v1.2 release record on the approved dependency set. Stable-input receipts,
rights files, evaluation, benchmarks, BOMs, logs, and run manifests contain runtime or
authorization metadata and are compared by invariant fields and fresh reported hashes rather than
forced to equal a prior execution.

For completed and interrupted runs, build both a map of every run file and a map containing only
the sorted `run_manifest.json` artifact keys. Capture each map after completion, after first resume,
and after repeated resume; require byte-for-byte equality of every row, not merely the aggregate
digest. Validate accepted v1 and v1.1 runs with `validate_run(..., write_report=False)` so historical
evidence is never rewritten.

The focused hostile-input and fixture-trust suite is:

```bash
uv run pytest -q tests/unit/test_native_media_policy.py tests/unit/test_fixture_sidecars.py \
  tests/unit/test_initial_authorization.py tests/unit/test_rights_gated_inspection.py
```

It proves that HLS/DASH/concat/sequence/navigation inputs start no parser, a local sentinel is not
accessed, a loopback endpoint receives zero requests, and missing/mismatched/replaced/symlinked/
malformed/oversized/unlisted/concurrently changed sidecars fail before evidence admission. It also
proves that forged 1.0/1.1 markers without rights start no parser, ordinary rights admit no adjacent
observation, synthetic rights require the exact bundle, and resume cannot change trust mode.

Confirm that current `stable_input.json` validates against stable-input schema 1.2, contains no
path, and matches inventory source hash/ID/size plus run-manifest 1.1 rights basis/checksum, explicit
synthetic trust mode, current fixture checksum/contract, fixture-sidecar bindings, and configured
byte ceilings. Confirm that media-inventory 1.1 records native-input contract
`av-atlas-native-input/1.0.0`; every ingest parser command uses `file`/`matroska` whitelists and the
forced `matroska` demuxer, while generated OCR PNG decoding uses `png_pipe`.

Scan every run file for the original absolute path, `source.snapshot`, sidecar paths, private-root
prefixes, and credentials. The private root must contain no lease after completion. The tracked
publication candidate must contain no run directory, generated fixture, rights manifest, media,
snapshot, traineddata, checkpoint, model weight, private annotation, archive, or personal path.

Snapshot unlinking and lease removal are logical cleanup, not secure erasure. This synthetic replay
does not establish a production temporary-root policy. Before real media, issue 17 requires a
documented private, capacity-bounded encrypted volume or appropriately configured tmpfs, or
explicit residual-remanence risk acceptance.

This is a fresh reproducibility replay in the same environment, not independent verification. It
uses only project-authored synthetic media. During release preparation it creates no tag or release
and establishes no real-media accuracy, native-parser sandbox, trained-model capability, full M2
completion, or M2C work.
