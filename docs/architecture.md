# Architecture

The current implementation establishes the low-level contracts required by later trainable modules:

```text
synthetic media + rights/observation sidecar
  -> parser-free hash/fixture/rights authorization preflight
  -> safe ffprobe inventory + preflight identity confirmation + integer-ms timeline
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
  -> parser-free exact-hash/source/operation/retention/expiry authorization
  -> bounded ffprobe inventory + preflight identity confirmation
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

Initial processing first checks that the input is a regular file, hashes it directly, derives its
source ID through the canonical source-ID helper, and verifies either a hash-bound controlled
fixture marker or an explicit rights declaration. No FFprobe, FFmpeg, Tesseract, subtitle, shot, or
perception process is invoked before that authorization succeeds. FFprobe then independently
rehashes the source for inventory; a hash or source-ID difference from preflight is treated as a
source change and aborts before the run directory is created. Authorization completes before parser
invocation, and post-inspection identity verification detects source changes. A concurrent
same-path modification race remains until a stable-input mechanism is implemented.

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

Temporal tracks are secondary indexes, never source evidence. Validation does not trust schema
conformance alone: it resolves every member back to the immutable OCR observation and recomputes
source, shot, normalized text, evidence, box, confidence, timestamp range, ordering, configured
gap, spatial compatibility, and arithmetic-mean confidence. Confidence comparisons use relative
and absolute tolerance `1e-9`; malformed parallel arrays produce quality-report errors rather than
exceptions.

The validator also runs the authoritative `associate_temporal_text` function over the complete raw
OCR record set and compares the canonical expected payload with the supplied artifact. This proves
global coverage, exactly-once membership, unique and ordered track IDs, ordered members, ordered
unique raw-text variants, and complete deterministic derivation. An empty track list is valid only
for an empty raw OCR record set.

Initial authorization, resume, and validation share schema, digest, source, operation, retention,
and expiry checks; persisted runs additionally enforce run-manifest linkage. All checks precede
native parsers or adapters. The declaration checksum is not a signature.

The permission vocabulary remains the rights-manifest 1.0 vocabulary, but executable modes are
narrower. `analysis` closes over analysis and derivative retention; `evaluation` closes over
analysis, evaluation, and derivative retention. Annotation, training, retention, and redistribution
cannot be selected as perception-processing modes.
