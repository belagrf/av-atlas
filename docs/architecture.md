# Architecture

The current implementation establishes the low-level contracts required by later trainable modules:

```text
synthetic media + rights/observation sidecar
  -> safe ffprobe inventory + normalized integer-ms timeline
  -> deterministic overlapping chunks + uniform sample schedule
  -> visual/OCR/ASR/speaker/acoustic sidecar adapters
  -> ordered atomic records + stable evidence index
  -> provisional ledger (revision 1)
  -> final ledger (revision 2)
  -> VTT/SRT and Markdown views
  -> cross-artifact validation + quality report
```

M2A extends that flow without replacing it:

```text
media + hash-bound operator declaration
  -> fail-closed operation/retention gate + bounded ffprobe inventory
  -> common adapter context
       -> embedded subtitle tracks -> hashed WebVTT -> canonical SUB cues
       -> bounded RGB samples -> hard/gradual/flash rules -> shots + hashed keyframes
       -> explicit success/zero/unsupported/unavailable/decode/resource/error status
  -> co-timed observation merge -> canonical revisions and evidence index
  -> manifest-driven schema, rights, bounds, evidence, keyframe, and hash validation
  -> fixture-only component evaluation against versioned gold
```

JSONL is canonical. Generated prose is never fed back as evidence. Each adapter implements the same
timestamped observation interface, so M2 can replace a sidecar branch without changing fusion or
ledger contracts. Missing sidecars fail explicitly instead of fabricating observations.

Source identity is a SHA-256-derived ID, not a filename. Media and configuration paths stored for
resume are relative to the run directory; structured logs contain run and source IDs but no raw
user path. External programs are invoked with argument arrays, `shell=False`, and an option
terminator. Files are never modified by inspection.

Chunking uses half-open conceptual intervals represented by inclusive start/exclusive end integer
milliseconds. The baseline uses 2,000 ms chunks with 250 ms overlap and 1,000 ms uniform samples.
Sidecar observations are ordered by `(start_ms, end_ms, observation_id)` and observations sharing an
exact interval are merged into one atomic event in this transparent B1-style baseline. Subtitle and
shot observations pass through the same merge and ledger path.

The run manifest is created before processing. `state.json` records a restart checkpoint. Final
records retain stable event IDs and advance the provisional revision rather than silently replacing
history. Configuration is snapshotted into the run, avoiding external configuration paths and
protecting resume from later edits. External source paths are retained only when bounded beneath the
run parent; otherwise resume requires the operator to provide the source again. Artifact content
hashes are recorded only after source artifacts are complete. Validation
checks schemas, duration bounds, ordering, revision predecessors, dialogue source rules, dangling
evidence, and hashes.

The current implementation has deterministic structural perception but no learned perception,
adaptive sampling, event fusion model,
verifier model, hierarchical memory, or retrospective semantic correction. Those remain later
milestones and are not implied by the rule-based M1 baseline.

M2B adds an optional `ocr_frame` adapter after structural keyframe extraction. It applies one
recorded preprocessing path, invokes the approved local Tesseract executable through argument-array
subprocesses, bounds each process to one OpenMP thread, and runs at most four frames concurrently.
It writes distinct raw/normalized OCR fields, word boxes/confidences, frame status, runtime, and
dependency provenance, then links each OCR claim to its source keyframe. Output ordering is restored
after concurrent execution. Absence and frame failures are explicit and never fabricate
observations. This is frame-level text recognition, not semantic vision.

The post-baseline pilot path is deliberately separate from canonical synthetic runs: a
pre-registered local intake validates four rights operations, extracts exactly 20 calibration and
60 evaluation frames, creates two isolated blank human-annotation packages, compares completed
submissions, and hash-freezes adjudicated gold before running the unchanged adapter. Pilot OCR
records retain frame evidence and are evaluated in a separate real-pilot report. No pilot data
enters source control, and no pilot result is merged with the controlled baseline.

M2B.1 introduces additive 1.1 contracts. Adapter results can be `partial_success` only with balanced
unit counts and at least one successful plus one failed or unsupported unit. Raw OCR observations
stay canonical and immutable; `ocr_text_tracks.json` retains every observation ID and source-frame
reference. Its policy requires equal normalized text, the same shot, a bounded gap, and spatial
compatibility. New events preserve all overlapping generated chunk IDs and one stable primary
chunk; 1.0 event and adapter artifacts remain readable.

Rights resume and validation share one schema, digest, source, operation, retention, expiry, and
run-linkage path before any adapter executes. The declaration checksum is not a signature.
