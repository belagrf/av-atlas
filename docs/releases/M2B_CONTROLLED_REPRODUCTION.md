# M2B controlled baseline reproduction

This is an offline, CPU-only fresh reproducibility replay. Calling a replay by the same
implementation on the same host “independent verification” would overstate the evidence.

The v1 procedure below remains the historical reproduction contract. The v1.1 extension adds the
reviewed M2B.1 secondary-track, permission-closure, validation, and clean-checkout checks without
changing v1 inputs or artifacts.

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

## Additive M2B.2 review replay (not a release)

M2B.2 does not retarget either accepted tag or alter the frozen v1 fixture, gold, normalization,
metrics, or `configs/m2b.yaml`. From the review branch, regenerate the controlled fixture and use
the separately versioned stable-input configuration in fresh ignored paths:

```bash
uv run av-atlas make-fixture --profile m2b --output tests/fixtures/generated/m2b2-review
uv run av-atlas run tests/fixtures/generated/m2b2-review/m2b_ocr_controlled.mkv \
  --config configs/m2b2.yaml --output runs/m2b2-review
uv run av-atlas evaluate-ocr runs/m2b2-review tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas benchmark-ocr runs/m2b2-review tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas validate runs/m2b2-review
```

Confirm that `stable_input.json` validates against stable-input schema 1.0, contains no path, and
matches inventory source hash/ID/size plus the run rights link and configured byte ceilings. Scan
every run file for the original absolute path, `source.snapshot`, and the private-root prefix. The
private root must contain no lease after completion. Run a second fresh directory with
`--stop-after inventory`, resume with the exact `--media` path, and compare every file after first
and repeated resume. Also validate accepted v1/v1.1 runs with `write_report=False`; their lack of a
stable-input receipt remains valid because their software versions predate 0.2.2.

This is a fresh reproducibility replay in the same environment, not independent verification. It
uses only project-authored synthetic media. It creates no tag or release and establishes no real-
media accuracy, native-parser sandbox, trained-model capability, full M2 completion, or M2C work.
