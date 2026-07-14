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

Changing retention, operation permission, expiry, source identity, or the declaration checksum
after interruption invalidates resume before any new derivative is created. The self-checksum is
not an authenticated signature; an operator assertion remains an assertion. Raw-frame retention is
false-only pending a separately reviewed derivative lifecycle and deletion design.
