# ADR-0006: M2B.2 stable authorized input

- Status: proposed on `feat/m2b2-stable-input`; acceptance requires PR review and merge
- Date: 2026-07-15
- Milestone: M2B.2 input-integrity and inspection governance; no M2C implementation

## Context

M2B.1 completed parser-free rights authorization before FFprobe and compared source identity after
inspection. That ordering detected a concurrent same-path change, but it could not ensure that a
native parser consumed the already-authorized bytes. Standalone `inspect` and `inspect-subtitles`
also lacked an explicit rights argument. Issues 11, 12, and 14 selected a conservative design before
any authorized real-media pilot.

## Decision

Stable-input contract `av-atlas-stable-input/1.2.0` is the shared acquisition boundary for `run`,
`resume`, `inspect`, `inspect-subtitles`, and pilot preparation. It opens a regular non-symlink
source with `O_NOFOLLOW` where available, hashes through that file descriptor, derives the canonical
source ID, and completes the existing run-mode permission closure before a parser is invoked.
Every fresh analysis and inspection requires an explicit rights declaration with `analysis` plus
`derivative_artifact_retention`; evaluation additionally requires `evaluation`. Fixture trust is
derived only from that validated declaration. An explicit `synthetic-controlled` basis must match
an exact current fixture 1.1 bundle and is the only mode that admits bound fixture observations.
Owned, licensed, public-domain, and other documented authorization are ordinary trust: adjacent
markers and sidecars are not opened, do not change status, and cannot inject evidence. The rights
1.0 vocabulary and its integrity-checksum semantics do not change.

For controlled fixtures, contract `av-atlas-controlled-fixture/1.1.0` binds the only supported
sidecar type by canonical basename, payload schema, SHA-256, and bounded size. Authorization opens
the sidecar without following its final path component, verifies stable identity before and after a
bounded read, checks its hash and size, validates its schema, and converts it once into immutable
observations. Adapters receive values rather than a path. Legacy fixture-manifest 1.0 records remain
readable in historical validation, but they cannot authorize any fresh execution. No marker or
self-hash is an authorization credential. A fixture self-hash is an integrity checksum, not an
authenticated signature.

After authorization, one unique private lease directory is created with mode `0700` and a regular
snapshot with mode `0600`. Bytes are copied from the already-open descriptor, never by hard link.
The implementation enforces source and temporary-storage ceilings before and during the copy,
hashes while copying, handles partial writes, flushes and `fsync`s, independently rehashes the
snapshot, verifies SHA-256/source ID/size, and compares descriptor plus pathname identity metadata
before and after acquisition. Defaults are 8 GiB for both ceilings; configuration schema 1.2 caps
either value at 64 GiB.

The snapshot is then admitted through native-input contract `av-atlas-native-input/1.0.0`.
Parser-free EBML magic selects only self-contained Matroska/WebM. Every ingest FFprobe/FFmpeg call
uses input protocol whitelist `file`, format whitelist `matroska`, and forced `matroska` demuxing;
the reported format must remain within `matroska,webm`. Runtime decode helpers reclassify the bytes
immediately before invocation and never retry without the policy. The renderer accepts no arbitrary
input-option list; its sole optional input is a validated nonnegative integer-millisecond seek.
HLS, DASH, concat/concatf, image
sequences, Blu-ray navigation, MOV/MP4, unknown formats, and network protocols are unsupported.
Generated OCR frames separately require PNG magic and forced `png_pipe` demuxing. FFprobe and
FFmpeg therefore receive only a verified snapshot or generated frame under a fixed policy, while
Tesseract receives only snapshot-derived frames.

The original source hash and source ID remain canonical; the snapshot is transport, not evidence.
A versioned, path-free `stable_input.json` receipt records the verified method, limits, rights
basis/checksum linkage, explicit ordinary-or-controlled trust mode, exact current fixture checksum
and contract when controlled, bound sidecar identities, and lifecycle. Run-manifest 1.1 records the
same trust and fixture linkage. It never records either original or private path.

The lease is removed after success, adapter/parser failure, timeout, and handled interruption.
Run completion and artifact hashing happen only after successful lease cleanup. A marker and
advisory lock support bounded recovery after process death: at most 64 candidate entries are
inspected and at most 16 recognized inactive leases are removed per invocation, using directory
file descriptors without recursive deletion or symlink following. Unrecognized or live entries are
left untouched. Known 1.0, 1.1, and 1.2 lease-marker versions are recoverable so a residue is not stranded
by the receipt-version correction; unknown versions remain untouched. Resume retains no source path and reacquires a fresh verified snapshot from an
operator-provided `--media` path.

Accepted M2B v1 and v1.1 runs remain readable because the receipt is required only for AV-Atlas
0.2.2 and later. Stable-input receipts 1.0 and 1.1 remain readable for earlier review contracts;
current receipts are 1.2 because they record declaration-derived fixture trust. Run-manifest 1.0
and media inventory 1.0 remain readable; current run manifest and inventory are 1.1. Resume for a
current run requires the persisted rights basis, trust mode, fixture status, fixture checksum, and
sidecar bindings to remain coherent before receipt replacement or adapter work. No accepted
release artifact or rights schema is rewritten.

## Consequences and limitations

Acquisition performs two full snapshot reads in addition to parser work and temporarily consumes up
to the configured source size. A growing ten-hour livestream is explicitly unsupported; future
live ingest needs finalized, independently authorized segments. Acquisition and recovery require
POSIX directory-descriptor operations plus `flock`; unsupported platforms fail closed with an
actionable error rather than weakening deletion semantics. `SIGKILL` and power loss cannot run
immediate cleanup.

The private modes protect against other local users, not a malicious actor with the same operating-
system identity. The strict protocol/demuxer allowlist prevents default transitive-resource
selection for supported inputs but does not provide an OS sandbox or capability-typed guarantee for
arbitrary internal library callers. Low-level helpers still accept a `Path`; they reclassify bytes
and enforce the fixed policy, while FFmpeg, FFprobe, and Tesseract remain native attack surfaces.
Self-contained formats other than Matroska/WebM remain unsupported pending individual review.

Unlinking the snapshot and removing its lease is logical lifecycle cleanup, not secure erasure.
The default operating-system temporary root can be disk-backed, journaled, snapshotted, swapped, or
backed up. Before real operator media, an operator must select and document an appropriately
private, capacity-bounded temporary root (for example an encrypted volume or suitably configured
tmpfs) or explicitly accept the residual data-remanence risk. A tmpfs may still swap unless the
host is configured otherwise.

No retained-frame lifecycle, narrower `temporary_processing_copy` permission, real-media pilot,
model/checkpoint use, training, semantic visual capability, or M2C work is introduced.
