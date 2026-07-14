# M2B controlled baseline v1 reproduction

This is an offline, CPU-only fresh reproducibility replay. Calling a replay by the same implementation on the same host “independent verification” would overstate the evidence.

## Preconditions

Use a fresh checkout/worktree with the locked project dependencies already present and approved distribution packages for FFmpeg, ffprobe, Tesseract 5.3.4, and English tessdata. Disconnect networking or use an enforced no-network environment. Do not use a GPU, cloud service, model download, or external media. Confirm `uv sync --extra dev --locked --offline` succeeds before deleting any existing environment cache.

A local container runtime was detected during this release, but its only cached Python image lacked FFmpeg, Tesseract, and uv. No image was pulled and no package was installed, so no container result is claimed.

## Fresh replay

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
sha256sum "$REPLAY_FIXTURES/m2b_ocr_controlled.mkv" tests/gold/m2b-ocr-controlled.gold.json configs/m2b.yaml
uv run av-atlas run "$REPLAY_FIXTURES/m2b_ocr_controlled.mkv" --config configs/m2b.yaml --output "$REPLAY_RUN"
uv run av-atlas evaluate-ocr "$REPLAY_RUN" tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas benchmark-ocr "$REPLAY_RUN" tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas validate "$REPLAY_RUN"
uv run av-atlas resume "$REPLAY_RUN" --media "$REPLAY_FIXTURES/m2b_ocr_controlled.mkv"
uv run av-atlas resume "$REPLAY_RUN" --media "$REPLAY_FIXTURES/m2b_ocr_controlled.mkv"
uv run av-atlas validate "$REPLAY_RUN"
```

Regenerate and validate M1 and M2A with their documented README commands as regression checks. To test interruption, start a new M2B run, send SIGTERM while OCR is active, resume twice, and validate after each resume.

Fixture, gold, configuration, and OCR observation hashes must exactly match the release record. Runtime-bearing evaluation, benchmark, BOM, logs, and run-manifest bytes can change across machines and executions. Compare their invariant fields and the observation semantic hash rather than expecting those files to be byte-identical. Within a completed run, hash all keys listed in `run_manifest.json` before and after each resume; every listed artifact must remain byte-identical.
