# ADR-0003: Optional bounded Tesseract frame OCR

- Status: accepted; controlled execution completed after operator installation
- Date: 2026-07-14
- Milestone: M2B engineering increment

## Decision

Use an optional replaceable adapter over M2A keyframes. It performs one bounded deterministic FFmpeg
preprocessing pass and invokes distribution-packaged Tesseract with argument arrays, `shell=False`,
timeouts, one OpenMP thread per process, no network, and at most four workers. Raw TSV text remains
distinct from normalized text. OCR evidence cites the exact source keyframe.

At the initial decision point Tesseract and English data were absent, so the adapter emitted
`unavailable_dependency` and no accuracy or scaling result. The operator subsequently installed the
approved distribution packages. Controlled execution and the BOM refresh then completed without
changing the adapter decision. The unavailable path remains a supported contract.

Temporary frames are deleted and symlinked/out-of-run frames are rejected. This is frame-level OCR,
not semantic visual understanding. Language data is third-party pretrained data, not AV-Atlas
weights.
