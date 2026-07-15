# AV-Atlas M2B controlled baseline v1.1

Status: “M2B.1 rights, configuration, partial-result, provenance, temporal-track, validation,
privacy, and clean-checkout hardening complete for the controlled synthetic baseline. Authorized
real-media evaluation remains pending.”

This patch release is a source-audit hardening release for the controlled baseline. Its source is
the reviewed post-merge M2B.1 commit
`4646f40e3c424a569fc8379c37df2fc67f99b7dd`; the AV-Atlas package version remains `0.2.1`.
The immutable v1 tag, release notes, fixture, gold, configuration, and accepted artifacts are not
retargeted or rewritten.

## Claim boundary

The controlled OCR fixture contains **four synthetic frames** and produced **thirteen OCR
observations**. No real-media OCR accuracy has been established. No semantic visual understanding
is claimed. No AV-Atlas model has been trained, and no foundation model has been trained. Region
precision, recall, and IoU remain unsupported because the frozen v1 gold contains no regions.

The authorized double-annotated real-media pilot remains pending. Full M2 remains incomplete, and
M2C remains unimplemented.

The rights self-hash is an integrity checksum, not an authenticated signature. No project license
has yet been selected. Public visibility permits inspection of the source but does not grant reuse
rights beyond applicable law.

## M2B.1 hardening scope

- The rights permission vocabulary is distinct from executable run modes. `analysis` requires
  analysis and derivative retention. `evaluation` requires analysis, evaluation, and derivative
  retention. Annotation, training, derivative retention, and redistribution are rejected as run
  modes.
- Configuration is schema-backed and rejects type coercion and unknown nested keys.
  `retain_raw_frames=true` is explicitly unsupported pending a rights-gated lifecycle design.
- Adapter result 1.1 uses `partial_success` with attempted, successful, failed, timed-out,
  unsupported, and emitted-observation counts.
- Initial run authorization hashes and authorizes a regular source before FFprobe. Inventory must
  reproduce the preflight source identity after inspection.
- Chunk provenance derives from actual generated chunk records and preserves every applicable
  reference across overlap.
- Raw per-keyframe OCR observations remain immutable authoritative evidence. Temporal text tracks
  are deterministic secondary artifacts and retain every member observation and evidence reference.
- Validation recomputes the complete expected track payload with `associate_temporal_text`, rejects
  omission, duplication, fabrication, splitting, merging, or reordering, and turns malformed
  artifacts into controlled quality-report errors without a traceback.
- Ordinary dependency records export hashes, basenames, and path classes rather than operator-local
  paths. Declared, measured, package-manager, and independently hashed inventory layers remain
  distinguishable.
- Public CI reconstructs fixtures from a clean tracked checkout and does not depend on ignored
  `runs/` evidence.

## Dependency identity

The operator installed the approved distribution packages before measured execution; Codex did not
install packages during this release continuation.

| Item | Measured identity |
|---|---|
| Tesseract | 5.3.4; Leptonica 1.82.0; Ubuntu `tesseract-ocr` 5.3.4-1build5 amd64 |
| Executable SHA-256 | `9f831cab7525c3dab04af41bda35182af7ea1df9dceeaaa2f3bf207ac45c06a5` |
| English tessdata | `tesseract-ocr-eng` 1:4.1.0-2; 4,113,088 bytes |
| English tessdata SHA-256 | `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2` |

Tesseract language data is an installed dependency and is not an AV-Atlas-trained checkpoint. The
checkpoint inventory remains empty.

## Preserved v1 identity

These content and accepted-result hashes remain exactly equal to v1:

| Item | SHA-256 |
|---|---|
| Fixture | `6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8` |
| Gold | `e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a` |
| Configuration | `8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55` |
| Raw OCR observations | `f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060` |
| Accepted v1 evaluation | `a1011542165e3b8974857aaee68bbaa8185987cbb3ca0353ad4afecda38803ad` |
| Accepted v1 benchmark | `479087002a126b1d442ca2e4d768bafd3e266e9f542dba92a01ea075a3280455` |
| Accepted v1 run manifest | `6779769594db6a7457ee30b7d9ffbdacc8ec345120433125e7e846978359b440` |
| Accepted v1 release manifest | `e545855c11ee23542939a35aecf03d00c6f12bbd056d6d4bcae43df139b7c9b2` |

The accepted 64-artifact v1 run validates read-only under the backward-compatible validator with
zero errors. It has no temporal-track artifact because that secondary contract was introduced
later; raw OCR records are unchanged.

## Fresh v1.1 replay identity

The release-branch replay was generated in new ignored directories. Content-stable hashes are:

| Item | SHA-256 |
|---|---|
| Fixture | `6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8` |
| Gold | `e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a` |
| Configuration | `8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55` |
| Raw OCR observations | `f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060` |
| Temporal OCR tracks | `f27d60f51c06cead4d0b6159b47865fd635a010e2faba9902057ae1c9cd4b9c2` |
| Sanitized OCR dependency inventory | `5ab8663ce63b7d6303ce84e3ec62ab3a9dd1ec55283e8f0c6852dd88740d5cce` |

Runtime- or software-bearing replay hashes are:

| Item | SHA-256 |
|---|---|
| OCR evaluation | `b2bc510bfffcda2792bec62069cde2f1701e513e837f1c808525331bcf3bd1f5` |
| 1/2/4-worker benchmark | `5b5c753ebe93b652f7d29b8f1afcd82911916f16196ebbfef47fe4c16697bea7` |
| BOM snapshot | `abca366e47275ef2d5ff2825b53b0d47436e03a56e29a696f903cb194d188868` |
| Run manifest | `633c4ed36e477179cd513c8270fc28275b64c6046e6ec2a44645e8a191661781` |

The completed-run comparison digest is
`7b754c8808e578e54905f223569f1a06c410642968ecdab72cfe1ac68980a428`;
the interrupted/completed/repeated-resume digest is
`1f22e6ffc956d074a50939c199fbe3a0b55c64b11d26feed503c10a0c5aa754c`.
Every manifest-tracked byte remained identical across both repeated resumes.

The rendered release-manifest and publication-manifest detached SHA-256 values are computed only
after their final bytes exist, avoiding circular self-reference, and are reported in release
verification. The publication manifest also carries its normalized self-hash entry.

## Synthetic measurements

The fresh release replay measured exact text match 0.75, normalized CER 0.0125, normalized WER
0.07692307692307693, and text-presence precision/recall/F1 of 1.0/1.0/1.0. It emitted 13
observations and 13 secondary tracks with zero unresolved track evidence, invalid timestamps,
retries, or timeouts. Evaluation wall/CPU time was 2.584538/1.941979 seconds, peak single-process
RSS was 180,556 KiB, and throughput was 1.5476651249747477 frames/s.

| Workers | Config SHA-256 | Wall s | CPU s | Peak KiB | Frames/s |
|---:|---|---:|---:|---:|---:|
| 1 | `7020e5ea8bb54c00d99963dd0eed00a02f521859cbe222400232969c5a83fd3c` | 1.912063 | 1.896013 | 180424 | 2.091981631168112 |
| 2 | `6fb1b15f8c0e6411c8ef9d10493d2f0654f20aaea9007f1e2e1be385bf48b33e` | 1.714091 | 1.906876 | 180552 | 2.3335983803188296 |
| 4 | `cdd9168fdf983922ed0233f8b2d81d865ee49e98a5f1096a920e707181a5c08d` | 1.557332 | 1.953582 | 180556 | 2.5684946471343415 |

All worker counts produced 13 observations, identical quality metrics and semantic output, and zero
failures/timeouts. These synthetic measurements do not generalize to real media.

## Contracts and gates

The relevant contracts are adapter results 1.1; configuration contract 1.1 with instance version
1.0; OCR frame results, OCR dependency, dependency BOM, and event-ledger 1.1 records with 1.0
backward compatibility; and OCR tracks, observations, gold, evaluation, benchmark, rights, run
manifest, and quality report 1.0. Exact schema hashes are in the machine-readable release record.

On source commit `4646f40e…`, locked offline sync, Ruff formatting/lint, mypy over 21 source files,
140 tests, doctor, fresh M1/M2A/M2B/M2B.1 validation, and resume checks passed. Public clean-checkout
[CI](https://github.com/belagrf/av-atlas/actions/runs/29434632938) and
[CodeQL](https://github.com/belagrf/av-atlas/actions/runs/29434632160) both succeeded.

## Reproduction

Use [the controlled reproduction procedure](M2B_CONTROLLED_REPRODUCTION.md). It rebuilds the
synthetic inputs and uses fresh ignored outputs. A same-host replay is a fresh reproducibility
replay, not independent verification by a second implementation or environment.

## Open limitations and gates

- [Security issue #11](https://github.com/belagrf/av-atlas/issues/11) remains open: authorization
  precedes parsing and post-inspection identity detects changes, but a concurrent same-path mutation
  can reach FFprobe until a stable-input design or explicit risk acceptance exists.
- [Governance issue #12](https://github.com/belagrf/av-atlas/issues/12) leaves standalone `inspect`
  and `inspect-subtitles` authorization policy undecided.
- Native FFmpeg and Tesseract parsing is not an operating-system sandbox.
- Retained source-frame lifecycle remains unsupported.
- Patent and public-release review remain unresolved beyond this explicitly authorized source
  disclosure and controlled patch release.
- The project license decision remains unresolved; the repository must not be described as open
  source.
- The authorized double-annotated real-media pilot cannot start until issues #11 and #12 are
  resolved or their risks are explicitly accepted.
- ASR/alignment, diarization, acoustic-event recognition, semantic visual perception, the real
  pilot, and direct-VLM comparison remain incomplete. Full M2 is not complete.
