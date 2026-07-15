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

Stable-input contract `av-atlas-stable-input/1.0.0` is the shared acquisition boundary for `run`,
`resume`, `inspect`, `inspect-subtitles`, and pilot preparation. It opens a regular non-symlink
source with `O_NOFOLLOW` where available, hashes through that file descriptor, derives the canonical
source ID, and completes the existing run-mode permission closure before a parser is invoked.
Non-fixture analysis and inspection require `analysis` plus `derivative_artifact_retention`;
evaluation additionally requires `evaluation`. Controlled fixtures retain automatic authorization
only when their marker is schema-valid and exactly hash-bound. The rights 1.0 vocabulary and its
integrity-checksum semantics do not change.

After authorization, one unique private lease directory is created with mode `0700` and a regular
snapshot with mode `0600`. Bytes are copied from the already-open descriptor, never by hard link.
The implementation enforces source and temporary-storage ceilings before and during the copy,
hashes while copying, handles partial writes, flushes and `fsync`s, independently rehashes the
snapshot, verifies SHA-256/source ID/size, and compares descriptor plus pathname identity metadata
before and after acquisition. Defaults are 8 GiB for both ceilings; configuration schema 1.2 caps
either value at 64 GiB.

FFprobe and FFmpeg receive only the verified snapshot path. Tesseract receives keyframes derived
from that snapshot. The original source hash and source ID remain canonical; the snapshot is
transport, not evidence. A versioned, path-free `stable_input.json` receipt records the verified
method, limits, rights linkage, and lifecycle. It never records either original or private path.
Source-adjacent sidecars are admitted only for a currently verified controlled fixture.

The lease is removed after success, adapter/parser failure, timeout, and handled interruption.
Run completion and artifact hashing happen only after successful lease cleanup. A marker and
advisory lock support bounded recovery after process death: at most 64 candidate entries are
inspected and at most 16 recognized inactive leases are removed per invocation, using directory
file descriptors without recursive deletion or symlink following. Unrecognized or live entries are
left untouched. Resume retains no source path and reacquires a fresh verified snapshot from an
operator-provided `--media` path.

Accepted M2B v1 and v1.1 runs remain readable because the receipt is required only for AV-Atlas
0.2.2 and later. No accepted release artifact or rights schema is rewritten.

## Consequences and limitations

Acquisition performs two full snapshot reads in addition to parser work and temporarily consumes up
to the configured source size. A growing ten-hour livestream is explicitly unsupported; future
live ingest needs finalized, independently authorized segments. Acquisition and recovery require
POSIX directory-descriptor operations plus `flock`; unsupported platforms fail closed with an
actionable error rather than weakening deletion semantics. `SIGKILL` and power loss cannot run
immediate cleanup.

The private modes protect against other local users, not a malicious actor with the same operating-
system identity. The final snapshot check narrows the race but does not provide an OS sandbox or a
capability-typed guarantee for arbitrary internal library callers: supported CLI/pipeline/pilot
entry points enforce snapshot routing, while low-level parser helpers still accept a `Path`.
FFmpeg, FFprobe, and Tesseract remain native attack surfaces.

No retained-frame lifecycle, narrower `temporary_processing_copy` permission, real-media pilot,
model/checkpoint use, training, semantic visual capability, or M2C work is introduced.
