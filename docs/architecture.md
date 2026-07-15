# Architecture

The current implementation establishes the low-level contracts required by later trainable modules:

```text
synthetic media + explicit rights + observation sidecar
  -> parser-free descriptor hash + rights permission closure
  -> synthetic-controlled basis + exact fixture 1.1 bundle -> immutable observations
  -> verified private transient snapshot (0700 directory / 0600 file)
  -> native-input 1.0 protocol/format/demuxer policy
  -> safe ffprobe inventory of snapshot + integer-ms timeline
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
  -> bounded descriptor copy + independently verified private snapshot
  -> parser-free EBML classification + forced Matroska/file-only input policy
  -> bounded ffprobe inventory of snapshot + identity confirmation
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

Source identity is a SHA-256-derived ID, not a filename. New runs never retain an external source
path; interrupted resume requires the operator to supply `--media`, whose exact identity and rights
are revalidated before a fresh snapshot is acquired. Configuration paths stored for resume are
run-relative. Structured logs contain run and source IDs but no raw user or snapshot path. External
programs are invoked with argument arrays, `shell=False`, and an option terminator. Original files
are never modified by inspection.

M2B.2 initial processing opens a regular non-symlink input without following its final symlink,
streams its hash through that descriptor, derives its canonical source ID, and verifies an
explicit rights declaration. Only a validated `synthetic-controlled` basis then admits an exact
current fixture bundle; ordinary rights do not open adjacent fixture data. No FFprobe, FFmpeg,
Tesseract, subtitle, shot, or perception process is invoked before authorization succeeds. The
same descriptor is rewound and copied into a unique private snapshot under source and temporary-
storage ceilings. Source identity/size/time metadata are checked before and after copying; the copy
is hashed while written, flushed, independently rehashed, and required to reproduce the authorized
hash, source ID, and size. The snapshot is then admitted only through native-input contract
`av-atlas-native-input/1.0.0`: parser-free EBML magic, forced `matroska` demuxer, input protocol
whitelist `file`, and format whitelist `matroska`. The same policy is rechecked immediately at each
runtime decode helper. HLS, DASH, concat/concatf, image sequences, Blu-ray navigation, MOV/MP4, and
unknown inputs are rejected before a native parser can dereference another resource. The operator
source identity, not the snapshot, remains canonical.

Chunking uses half-open conceptual intervals represented by inclusive start/exclusive end integer
milliseconds. The baseline uses 2,000 ms chunks with 250 ms overlap and 1,000 ms uniform samples.
Sidecar observations are ordered by `(start_ms, end_ms, observation_id)` and observations sharing an
exact interval are merged into one atomic event in this transparent B1-style baseline. Subtitle and
shot observations pass through the same merge and ledger path.

The run manifest is created before perception processing. `state.json` records a restart
checkpoint. `stable_input.json` is a path-free receipt for verified acquisition; it is canonical
metadata, not the snapshot itself. Media-inventory 1.1 records the exact native-input policy used
for the snapshot; inventory 1.0 remains validation-compatible. Final records retain stable event IDs and advance the
provisional revision rather than silently replacing history. Configuration is snapshotted into the
run, avoiding external configuration paths and protecting resume from later edits. The transient
snapshot is removed before the run can be marked complete or its final artifact map written. Resume
reacquires it from the exact operator-supplied source. Artifact content hashes are recorded only
after source artifacts are complete and cleanup succeeds. Validation
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

M2B.2 uses the same stable-input service for `run`, `resume`, `inspect`, `inspect-subtitles`, and
pilot source preparation. Standalone inspection now uses analysis-mode permission closure, so
every fixture and non-fixture needs explicit analysis and derivative-retention permission. Pilot preparation completes
parser-free authorization for every selected source before parsing any of them, then inventories
and extracts only from one verified snapshot at a time. Controlled-fixture trust exists only for
an explicit `synthetic-controlled` declaration plus an exact current bundle. Fresh fixture-manifest contract
`av-atlas-controlled-fixture/1.1.0` additionally lists the one currently accepted runtime sidecar
type with canonical basename, payload schema, SHA-256, and bounded size. Authorization opens it
without following a final symlink, checks descriptor/path identity before and after a bounded read,
verifies its declared hash and size, validates its schema, and converts it once to immutable
observations. Adapters receive those values, not a pathname. Missing, mismatched, replaced,
malformed, oversized, or unlisted sidecars fail before observations are accepted. Historical
fixture 1.0 records remain validation-compatible but cannot authorize fresh execution. For
ordinary rights bases, adjacent markers and sidecars are ignored and cannot change evidence.

The corrected stable-input contract is `av-atlas-stable-input/1.2.0`; its receipt schema is 1.2.0
and records the declaration-derived trust mode, rights basis/checksum, nullable current fixture
checksum/contract, and verified sidecar identities without paths. Run-manifest 1.1 records matching
trust linkage. Receipt schemas 1.0/1.1 and run-manifest 1.0 remain readable for historical artifacts,
while accepted v1/v1.1 releases predate current receipts.
The configuration schema ID is 1.2.0. Default source and temporary-copy ceilings are each 8 GiB and the
schema hard cap is 64 GiB. Lease directories and files use modes 0700/0600. Ordinary cleanup uses
pinned directory descriptors; crash recovery scans at most 64 entries and removes at most 16
marker-recognized, inactive leases without recursive traversal or symlink following. Recovery
accepts the known 1.0, 1.1, and 1.2 lease-marker contracts so a review-head crash residue is not stranded;
unknown versions remain untouched. `SIGKILL` and
power loss require later bounded recovery. A growing long-form stream must be segmented and
authorized as finalized chunks rather than copied as one live file.

Supported entry points and their low-level runtime decode helpers require the fixed native-input
policy and reclassify bytes before each parser invocation. This closes default libavformat protocol
and demuxer selection but is not a capability-typed API or an OS sandbox. Private modes do not
defend against a malicious process running as the same OS user. The allowlist currently excludes
otherwise common self-contained formats until each receives a separate transitive-I/O review.

Snapshot unlinking and lease-directory removal are logical lifecycle cleanup, not secure erasure.
The OS temporary root may be disk-backed, journaled, snapshotted, swapped, or backed up. A private,
capacity-bounded encrypted volume or suitably configured tmpfs—or explicit documented risk
acceptance—is required before real operator media; tmpfs can still swap unless configured not to.
