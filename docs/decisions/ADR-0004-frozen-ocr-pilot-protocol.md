# ADR-0004: Freeze-before-evaluation OCR pilot protocol

- Status: accepted; pilot inputs pending
- Date: 2026-07-14
- Milestone: post-M2B controlled baseline

## Decision

Freeze M2B as a four-frame synthetic engineering baseline in a versioned release record. Recommend
two OCR workers provisionally, but do not alter the frozen one-worker configuration. Runtime-bearing
artifacts compare by invariant fields and semantic hashes; intended stable inputs and OCR records
compare byte-for-byte.

For any real-media OCR pilot, require at least three operator-supplied local sources, 20 calibration
frames, 60 evaluation frames, exact hash-bound rights permitting local analysis, annotation,
evaluation, and derivative retention, and a pre-registered selection protocol. Extract no frame
until all permissions validate. Freeze the evaluation frame hashes, two genuinely independent
human annotations, adjudicated gold, normalization, region matching, metric definitions, and the
unchanged adapter configuration before the first quality evaluation.

Keep media outside version control, use hash-derived source identifiers, preserve both original
annotations, and separate inter-annotator, synthetic, and real-pilot results. Codex does not create
human annotations or decide legal sufficiency. Expiry or permission failure closes the path. A
pilot result remains a small-pilot result, not generalized OCR accuracy or semantic vision.
