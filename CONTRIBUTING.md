# Contributing

Before proposing a change, read `AGENTS.md`, `AV-Atlas_GOAL.md`, the architecture, security, data
governance, and current project state. Keep changes small, evidence-linked, CPU-testable, and
offline-capable. Do not submit copyrighted/private media, extracted derivatives, credentials,
rights manifests with operator information, downloaded datasets, model checkpoints, Tesseract
language data, or generated run directories.

Run before submitting:

```sh
uv lock --check
uv sync --extra dev --locked --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run av-atlas doctor
```

Changes affecting schemas, evidence, rights, evaluation, dependencies, security, or milestone
claims require tests and documentation. Media-borne text is untrusted. Do not fabricate results,
annotations, rights, licenses, or independent review.

No project license has yet been selected. Public visibility permits inspection of the source but
does not grant reuse rights beyond applicable law. Discuss contribution licensing with the
maintainer before investing substantial work.
