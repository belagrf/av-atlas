# Data governance

Every run writes a versioned provenance record with a stable source ID, content hash, rights tier,
acquisition basis, permitted uses, restrictions, retention description, deletion key, and review
status. The built-in fixture is Tier D: it is generated locally from solid colors, project-authored
text, synthetic tones, and DejaVu Sans. No copyrighted film or user media is committed.

Hash-bound fixture markers retain the automatic Tier D M1 path. All non-fixture media now requires a
schema-valid operator declaration with separate analysis, annotation, training, evaluation,
derivative-retention, and redistribution permissions. Expired, mismatched, malformed, or missing
permissions fail closed. `independently_reviewed` records review state; AV-Atlas does not determine
whether the declaration is legally sufficient. Entity output uses anonymous
IDs. No face recognition, unrestricted naming, training-data collection, or external service is
performed.

The dependency/model BOM is versioned and contains no AV-Atlas model checkpoints. Approved
Tesseract English language data is explicitly inventoried as third-party pretrained data, never as
an AV-Atlas-trained weight. Deletion
propagation beyond one run directory, independent rights review workflow, arbitrary-media retention
enforcement, and a real adjudicated pilot remain future governance work. The `source_id` doubles as
the current deletion lookup key.

OCR requires analysis and derivative-retention permission; evaluation additionally requires
evaluation permission. External-pilot intake and independent annotation are documented in
`ocr-annotation-guide.md`. The pilot tooling requires analysis, annotation, evaluation, and
derivative retention for each exact source hash, exports hash-derived IDs rather than local paths,
preserves both original annotations, and locks adjudicated gold. No external pilot or human
annotation occurred.

Rights-manifest permission names are not processing modes. Current executable modes are only
`analysis` (analysis + derivative retention) and `evaluation` (analysis + evaluation + derivative
retention). Annotation, training, derivative retention, and redistribution remain independently
recordable permissions but cannot invoke the perception pipeline.

Changing retention, operation permission, expiry, source identity, or the declaration checksum
after interruption invalidates resume before any new derivative is created. The self-checksum is
not an authenticated signature; an operator assertion remains an assertion. Raw-frame retention is
false-only pending a separately reviewed derivative lifecycle and deletion design.

M2B.2 treats a transient processing copy conservatively: non-fixture acquisition requires the same
analysis plus derivative-retention closure as analysis runs, and standalone `inspect` and
`inspect-subtitles` use that closure. Evaluation adds evaluation permission; pilot preparation also
requires annotation. This does not add or imply a `temporary_processing_copy` permission under the
rights 1.0 schema. The snapshot is private, noncanonical, excluded from the run artifact map, and
deleted before successful completion. New runs retain no operator source path and interrupted
resume requires the exact source again. Source-adjacent sidecars are accepted only for an exact
hash-bound controlled fixture.

The pilot remains unexecuted. Issues [#11](https://github.com/belagrf/av-atlas/issues/11) and
[#12](https://github.com/belagrf/av-atlas/issues/12) stay open pending review and merge of the
M2B.2 implementation; neither issue closure nor legal sufficiency is inferred on this branch.
