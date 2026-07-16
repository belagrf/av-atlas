# AV-Atlas M2B controlled baseline v1.2

The v1.2 release record freezes the reviewed M2B.2 implementation tree from
commit `2555a297153c9b5ff059b7d8dc7e49de5d93c43b` (tree
`f8ca95eab8c1988cee00ab774a2bf30f5cad1776`) at package version `0.2.2`. Under issue 18, tagging
occurs only after source review and merge. Final annotated-tag and GitHub-release identities are
verified externally rather than predicted by this record.

**M2B.2 stable authorized input, rights-gated inspection, fixture-trust, and native-input hardening
complete for the controlled synthetic baseline. Authorized real-media evaluation remains pending.**

This controlled fixture contains four project-authored synthetic frames and produced 13 raw OCR
observations plus 13 secondary temporal text tracks. It establishes no real-media OCR accuracy, no
semantic visual understanding, and no audiovisual reasoning. No AV-Atlas model or foundation model
was trained. Region metrics remain unsupported because the frozen v1 gold has empty region arrays.
Full M2 is incomplete, and M2C is unimplemented.

## Release boundary

M2B.2 adds no new perception model. It hardens how already-authorized bytes reach native parsers:

- every fresh `run`, `inspect`, and `inspect-subtitles` call requires an explicit, source-bound
  rights manifest before a parser runs;
- `analysis` and standalone inspection require `analysis` plus
  `derivative_artifact_retention`; `evaluation` additionally requires `evaluation`;
- stable-input contract `av-atlas-stable-input/1.2.0` opens a regular non-symlink source with
  no-follow protection where supported, streams and hashes it through one descriptor, and creates a
  size-bounded `0600` byte copy in a unique `0700` private directory;
- copied and independently reread SHA-256, size, and canonical source ID must match, with pre/post
  descriptor and pathname mutation checks;
- FFprobe and FFmpeg receive only that verified transient snapshot. Tesseract receives only
  snapshot-derived, independently verified PNG keyframes;
- native-input contract `av-atlas-native-input/1.0.0` selects self-contained Matroska/WebM by
  parser-free EBML magic, forces the `matroska` demuxer and format whitelist, and restricts the
  protocol whitelist to `file`; manifest, playlist, multi-resource, unknown, and network-capable
  inputs fail before parser invocation;
- generated OCR frames use the separate forced `png_pipe` policy;
- fixture contract `av-atlas-controlled-fixture/1.1.0` binds observation sidecars by canonical
  basename, schema, SHA-256, and byte size. A bounded no-follow descriptor read creates immutable
  observations; adapters never reread an adjacent original path;
- trust is declaration-derived. `ordinary-explicit-rights` ignores adjacent fixture metadata;
  `synthetic-controlled-explicit-rights` requires the exact current fixture bundle. The current
  marker self-checksum is an integrity check, not an authorization credential or signature;
- run-manifest 1.1 records rights basis/checksum and the same trust linkage. Interrupted resume
  revalidates it and reacquires a fresh private snapshot; completed resume is a no-op;
- accepted v1/v1.1 evidence remains readable even though those releases predate stable-input
  receipts. Review-era stable-input 1.0/1.1 plus historical run-manifest, inventory, and fixture
  records are separately validation-compatible, but cannot downgrade current execution.

Snapshot unlink and lease removal are logical lifecycle cleanup, not cryptographic secure erasure.
The fixed protocol/demuxer policy is defense in depth, not an operating-system sandbox.

## Preserved inputs and fresh replay identities

Immutable v1 identities remain unchanged:

| Record | SHA-256 |
| --- | --- |
| Four-frame fixture media | `6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8` |
| Frozen gold | `e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a` |
| Frozen v1 configuration | `8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55` |
| Raw OCR observations/semantic output | `f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060` |

Fresh v1.2 identities are stable only within the stated contract, software, and dependency scope:

| Record | Fresh SHA-256 | Stability boundary |
| --- | --- | --- |
| Fixture-manifest 1.1 file | `4186ed28525803033e4131275d2217c401ef12ab5c16e623f2fdff25c2a373d5` | Current controlled bundle |
| Fixture-manifest self-checksum | `001dd0b0a755a780434ea621616392a18abbadf9085317dda6d5915f644205ad` | Current controlled bundle |
| M2B.2 configuration | `9c0d2b71c928912671f10cee3c0b2e0676f2b5e81de7ca68962832ebfb99313b` | Versioned configuration bytes |
| Media inventory | `91ada0947d3da15c53b8a99076fa3f9841ebad026fcf96ec91da87cde5e7d6d5` | Recorded FFprobe/software environment |
| Secondary temporal OCR tracks | `f27d60f51c06cead4d0b6159b47865fd635a010e2faba9902057ae1c9cd4b9c2` | Recorded AV-Atlas/Tesseract dependency set |
| Sanitized OCR dependency inventory | `5ab8663ce63b7d6303ce84e3ec62ab3a9dd1ec55283e8f0c6852dd88740d5cce` | Recorded host/package inventory |

Fresh execution-bearing files legitimately include authorization timestamps, resource
measurements, software inventory, or run times:

| Record | Fresh SHA-256 |
| --- | --- |
| Stable-input receipt | `5f7019bf07b012e87ff44c7f9368b24ae04c49f905307388729955f1c5b07a3c` |
| OCR evaluation | `d82c56376cdcbd8c2eaeb273aac63af4706500530d393d0711f028019fe0c3e2` |
| Worker benchmark | `27f1e68189ed5ba06f1d30cf406f0c61be4c17701e75270e7721edab4aa9053c` |
| Dependency BOM snapshot | `abca366e47275ef2d5ff2825b53b0d47436e03a56e29a696f903cb194d188868` |
| Run manifest | `543f7ba9fe4a9f20f0301b04a675d55bfa22c061700658e4b3577e0d23fa4f77` |
| Quality report | `ee0936365cb0574518918e5a9d73826f039519c32a31ca9f709bdeae260b3b9d` |

The machine-readable record contains the complete tracked schema-file hash inventory and the
relevant accepted schema versions. Its detached file hash
and the final publication-manifest hash are computed only after final rendering and reported in the
release-preparation review, avoiding circular self-reference.

## Synthetic controlled evaluation

The fresh unchanged-adapter replay measured:

- 4 evaluated frames, all with expected text; 13 OCR observations and 13 tracks;
- exact frame transcription match `0.75`;
- normalized CER `0.0125`; normalized WER `0.07692307692307693`;
- text-presence precision/recall/F1 `1.0 / 1.0 / 1.0`;
- exact-record duplicate rate `0.0`; zero prediction-only or gold-only keyframes;
- zero missing evidence references, invalid timestamps, unresolved track references, retries, or
  timeouts;
- wall `2.104130 s`, CPU `2.057794 s`, peak RSS `180796 KiB`, `1.9010231661` frames/s, and
  `3.8020464515` media minutes per compute minute;
- region precision, recall, and IoU: unsupported, because the frozen gold has no region geometry.

These values describe four synthetic frames on one controlled host. They are not estimates of
performance on films, episodes, livestreams, or any other real media.

## Worker replay

All worker counts produced the same 13 observations and semantic SHA-256
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`, with zero failures,
retries, or timeouts.

| Workers | Config SHA-256 | Wall s | CPU s | Peak RSS KiB | Frames/s | Media min/compute min |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `180266786c33110b4fa2b166fcddcb222f88740638bb932b97bf5e8fbb26b107` | 2.094113 | 2.068903 | 180800 | 1.9101169485 | 3.8202331966 |
| 2 | `9edd7622e421e846ed634382034c58aa97c5ed150f91900616c5e3b255de1980` | 1.816275 | 2.091952 | 180800 | 2.2023091970 | 4.4046193445 |
| 4 | `c16d806cc51a1dfc0722bd29dba004132026eba0e08011e8475ddbf72c2b0040` | 1.756431 | 2.187848 | 180800 | 2.2773452216 | 4.5546907337 |

These timing measurements are runtime-bearing and are not expected to be byte-stable across hosts.

## Gates, validation, and resume

The release branch ran exactly:

```text
uv lock --check
uv sync --extra dev --locked --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run av-atlas doctor
```

Results were: lock and offline sync passed; Ruff formatted-check covered 51 files and lint passed;
mypy passed over 24 source files; **272 tests passed, zero failed, zero skipped**; and doctor passed
with FFmpeg/ffprobe 6.1.1, Tesseract 5.3.4, Leptonica 1.82.0, and English tessdata available. No
network, GPU, cloud service, model download, or training was used by the replay.

Fresh ignored M1, M2A, M2B, M2B.1, M2B.2, and inventory-interrupted/resumed M2B.2 runs validated
with respectively `18 / 32 / 69 / 69 / 69 / 69` artifact hashes and zero errors. Accepted v1 and
v1.1 runs validated read-only with 64 and 68 artifact hashes and zero errors.

Completed first/repeated resume preserved every one of 72 run files and 69 manifest-tracked
artifacts. Their sorted full-map and manifest-map digests were respectively
`26ea7690b24db7c775e238392005b6515b5dcaf5527b893471b58d1a9afff93f` and
`6d7fcfae81203be355c15b9ee376da6a286829f6389885a3f1f0b564ce40ec1f`.
Interrupted completion and both repeated resumes were likewise byte-identical, with digests
`327554fade972edf5714d85f66558008f547215ab720f8074f21eb853ee74d57` and
`d112c327564be1c58a80a318cb8fabf0bf91eadbd5b4891e3f762c54f5c8082e`.

The exact fresh reproduction commands and hash-comparison method are in
`M2B_CONTROLLED_REPRODUCTION.md`. This is a fresh reproducibility replay in the same controlled
environment, not an independent implementation or separate-environment verification.

The exact implementation commit passed main CI at
<https://github.com/belagrf/av-atlas/actions/runs/29486707488> and CodeQL at
<https://github.com/belagrf/av-atlas/actions/runs/29486706995>. Release-preparation PR CI and CodeQL
are reviewed and reported externally so these release notes remain temporally stable.

## Compatibility and immutable predecessors

The original releases remain untouched:

- v1 tag object `8cadd6c8ecda7d0b6f60421f312c199cbad163e1`, tagged commit
  `54d96dc25bdf03ab1e92d22150c5011faf16b7e6`;
- v1.1 tag object `8be328eef2fd10037b56921aff1f401c3ef3a12e`, tagged commit
  `5d016784c6b3d7226a9f6e0f56cca9fb3ef48822`.

The v1 fixture, gold, configuration, raw OCR, evaluation, benchmark, run-manifest, and release-
manifest hashes remain `6d1f79c6…82a8`, `e62e392a…bc1a`, `8f5545df…5c55`,
`f851aef0…6060`, `a1011542…3ad`, `47908700…455`, `67797695…440`, and
`e545855c…9b2`. The v1.1 machine-readable release record remains
`fbdc8e171811794d37bbdb018179ba736647795ed053d01cada4580fe5d29d73`.

## Security, governance, and limitations

The rights-manifest self-hash is an integrity checksum, not an authenticated signature. Rights
declarations remain operator assertions rather than legal determinations. No project license has
been selected: public visibility permits inspection but grants no reuse rights beyond applicable
law. Patent and publication review remain unresolved.

Issue [#17](https://github.com/belagrf/av-atlas/issues/17) remains the security and temporary-root
gate before any authorized real-media pilot. The pilot additionally requires operator-supplied
authorized media and two genuinely independent human annotations; neither is present. Remaining
technical limits include logical-not-secure snapshot deletion, no OS sandbox for native parsers,
same-UID hostility, no retained-frame lifecycle, POSIX-only acquisition primitives, unsupported
non-Matroska and growing/live inputs, and no real-media evidence.

No private media, frame, audio, subtitle, annotation, rights workspace, traineddata, checkpoint,
model weight, run directory, or local archive belongs in this release. No real-media pilot or M2C
work occurred.
