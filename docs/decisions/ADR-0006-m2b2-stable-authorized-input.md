# ADR-0006: M2B.2 stable authorized input and rights-gated inspection

- Status: proposed on `feature/m2b2-stable-input`
- Date: 2026-07-15
- Milestone: M2B.2 real-media-pilot gate; no M2C implementation
- Tracks: #14
- Resolves when implemented and reviewed: #11, #12

## Context

M2B.1 authorizes exact source bytes before parser invocation and verifies source identity after
FFprobe. That closes the original authorization-order defect, but a concurrent writer can still
change the same path between preflight hashing and parser open. The run is rejected after inventory,
yet the native parser may already have observed bytes that were not the complete authorized source.

Standalone `inspect` and `inspect-subtitles` also invoke FFprobe without an explicit rights argument,
which conflicts with the repository's broader fail-closed policy for non-fixture media.

The authorized real-media OCR pilot must not begin while either boundary remains ambiguous.

## Decision

### 1. No standalone parser exemption

Choose the rights-gated policy for standalone inspection.

`run`, `resume`, `inspect`, `inspect-subtitles`, and real-media pilot preparation must share one
parser-free authorization foundation. A controlled synthetic fixture may use its exact hash-bound
fixture marker; every non-fixture source requires an explicit rights declaration.

For this conservative increment, `inspect` and `inspect-subtitles` use analysis-mode permission
closure:

- `analysis`
- `derivative_artifact_retention`

This is intentionally stricter than a hypothetical ephemeral metadata-only permission. A narrower
mode requires a separately versioned rights contract and is not introduced implicitly.

### 2. Parsers consume a verified transient copy

After authorization succeeds, AV-Atlas creates a private bounded byte-for-byte transient snapshot.
FFprobe, FFmpeg, Tesseract, and later media/model adapters receive the snapshot path only. They must
never receive the operator source path.

The first implementation uses a regular copy because its security semantics are portable and easy
to verify. Reflink/copy-on-write may be added later as an optimization only after capability and
correctness are positively verified; it must not be required for correctness.

### 3. Snapshot acquisition protocol

The acquisition sequence is:

1. Reject a missing source, directory, symlink, or non-regular file without running a parser.
2. Open the source without following a final symlink where the platform supports it.
3. Compute the parser-free source SHA-256 and canonical source ID.
4. Validate the fixture marker or explicit rights declaration, including schema, self-checksum,
   source binding, permission closure, expiry, and expected persisted linkage where applicable.
5. Enforce a configured or documented byte ceiling before allocating/copying.
6. Create a private temporary directory and mode-0600 snapshot file.
7. Copy from the opened source descriptor in bounded chunks while computing the snapshot hash.
8. Flush the snapshot and verify:
   - complete byte count;
   - snapshot SHA-256 equals the authorized source SHA-256;
   - source descriptor identity and metadata did not change during acquisition;
   - the source path was not replaced during acquisition.
9. Only then call a native parser using the snapshot.
10. Verify parser inventory still reports the authorized content identity.
11. Delete the snapshot on normal completion and every ordinary exception/failure path.

A hard link is forbidden as the stability mechanism because in-place writes to the original inode
would remain visible through the link.

### 4. Snapshot lifetime and resume

A snapshot is a private processing aid, not canonical evidence and not a retained run artifact.
Ordinary exported records may contain only:

- original source ID;
- original source SHA-256;
- snapshot method identifier;
- snapshot verification outcome;
- size and bounded resource facts that do not reveal a private path.

No absolute snapshot or source path may be exported.

`resume` reacquires a new verified snapshot from the operator source after revalidating persisted
rights and run linkage. It does not trust a stale private path. A future optimization may reuse a
live snapshot only if its ownership, hash, permissions, lifecycle, and run linkage are verified.

Normal exceptions, adapter failures, timeouts, SIGINT, and handled SIGTERM paths must clean up.
SIGKILL and power loss cannot run process cleanup; the implementation must use a recognizable private
prefix and safely remove stale owned snapshot directories on a later invocation according to a
bounded age policy. It must never delete an unverified arbitrary directory.

### 5. Pilot and livestream boundary

OCR pilot frame selection and extraction must use verified snapshots. The pilot may not parse the
operator source before rights closure.

A continuously growing ten-hour livestream is not copied as one monolithic source. Future live
support finalizes bounded rolling segments, hashes and authorizes each segment, then processes a
verified transient snapshot of that finalized segment. Live segmentation is not implemented in
M2B.2.

### 6. Rights interpretation

The current rights schema has no distinct `temporary_processing_copy` permission. M2B.2 therefore
requires the existing derivative-retention permission before creating a transient copy. This is a
conservative closure rule, not a claim that the snapshot is a retained or redistributable artifact.

A future narrower permission requires a separately reviewed and versioned schema. M2B.2 must not
weaken the existing permission matrix merely to reduce operator friction.

## Required invariants

- Authorization completes before snapshot creation and before every parser invocation.
- No native parser receives the operator source path.
- A parser runs only after snapshot hash equality is established.
- Any mutation, replacement, partial copy, oversize source, or rights failure prevents parsing.
- Raw source and snapshot paths never appear in exported records or ordinary logs.
- Snapshot bytes never enter Git, public releases, or canonical ledgers.
- Existing M1, M2A, M2B, M2B.1, v1, and v1.1 evidence remains validation-compatible.
- Generated prose remains non-evidence; this change affects source acquisition only.

## Consequences

Positive:

- The parser receives stable, hash-verified bytes rather than a mutable operator path.
- Rights policy is consistent across run and standalone inspection commands.
- Pilot frame extraction inherits the same source identity boundary.
- Large-file risk is explicit and bounded.

Costs and limitations:

- Full-copy acquisition adds local I/O, temporary storage, and latency.
- Native parsers are still not operating-system sandboxed.
- A transient copy can remain after SIGKILL/power loss until safe stale cleanup runs.
- The current permission closure is intentionally conservative.
- This does not establish real-media accuracy and does not implement any learned capability.

## Rejected alternatives

### Read-only inspection exemption

Rejected because metadata inspection still invokes a native parser, reveals source information, and
can persist a structured derivative. It would create a second, weaker governance path.

### Post-FFprobe hash check only

Rejected because it detects changed content after a parser may already have consumed it.

### Hard-link snapshot

Rejected because it does not isolate against writes to the original inode.

### Reflink-only design

Rejected as the first correctness mechanism because support and copy-on-write behavior vary by
filesystem and platform. It may be an audited optimization later.

### Retain the snapshot in the run directory

Rejected because the source copy is not canonical evidence, introduces a large private derivative,
and complicates deletion and publication policy.
