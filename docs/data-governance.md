# Data governance

Every run writes a versioned provenance record with a stable source ID, content hash, rights tier,
acquisition basis, permitted uses, restrictions, retention description, deletion key, and review
status. The built-in fixture is Tier D: it is generated locally from solid colors, project-authored
text, synthetic tones, and DejaVu Sans. No copyrighted film or user media is committed.

Every fresh source, including Tier D fixtures, requires a schema-valid explicit operator
declaration with separate analysis, annotation, training, evaluation,
derivative-retention, and redistribution permissions. Expired, mismatched, malformed, or missing
permissions fail closed. `independently_reviewed` records review state; AV-Atlas does not determine
whether the declaration is legally sufficient. Entity output uses anonymous
IDs. No face recognition, unrestricted naming, training-data collection, or external service is
performed. An explicit `synthetic-controlled` basis is the only fixture trust signal and still
remains an operator assertion, not a legal or authenticated authorship finding. It must match the
exact current fixture bundle. Ordinary rights bases ignore adjacent fixture metadata and cannot
admit its observations.

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

M2B.2 treats a transient processing copy conservatively: every fresh acquisition requires the same
analysis plus derivative-retention closure as analysis runs, and standalone `inspect` and
`inspect-subtitles` use that closure. Evaluation adds evaluation permission; pilot preparation also
requires annotation. This does not add or imply a `temporary_processing_copy` permission under the
rights 1.0 schema. The snapshot is private, noncanonical, excluded from the run artifact map, and
deleted before successful completion. New runs retain no operator source path and interrupted
resume requires the exact source again. Snapshot unlinking and lease removal are logical lifecycle
cleanup, not secure erasure. The default temporary root can be disk-backed, journaled, snapshotted,
swapped, or backed up. Before real operator media, the operator must select and document a private,
capacity-bounded temporary root such as an encrypted local volume or appropriately configured
tmpfs, or explicitly accept the residual data-remanence risk.

Fixture-manifest contract `av-atlas-controlled-fixture/1.1.0` binds the sole accepted observation
sidecar by canonical basename, payload schema, SHA-256, and bounded byte size. Authorization reads
it once through a no-follow descriptor with pre/post identity checks and supplies immutable parsed
observations to adapters; adapters never reread the original adjacent path. A fabricated,
unlisted, changed, or legacy-adjacent sidecar cannot acquire fixture trust. The marker self-hash is
an integrity checksum, not an authenticated signature, proof of authorship, or authorization
credential. Historical 1.0 records remain validation-compatible without authorizing fresh
execution.

Native-input policy `av-atlas-native-input/1.0.0` permits only parser-free-classified,
self-contained Matroska/WebM source bytes through a forced `matroska` demuxer, `file`-only protocol
whitelist, and matching format whitelist. It rejects manifests, playlists, image sequences,
Blu-ray navigation, and other unreviewed formats before native parsing. This limits transitive
resource access but is not an operating-system sandbox and does not establish safety for arbitrary
hostile media.

The pilot remains unexecuted. Issues [#11](https://github.com/belagrf/av-atlas/issues/11) and
[#12](https://github.com/belagrf/av-atlas/issues/12) stay open pending review and merge of the
M2B.2 implementation; neither issue closure nor legal sufficiency is inferred on this branch.
