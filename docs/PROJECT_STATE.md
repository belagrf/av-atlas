# Project state

Last verified: 2026-07-16 (Europe/Berlin)

## Milestone status

- **M0 — verified complete for its gate.** Reproducible locked setup, versioned schemas,
  typed contracts, safe inventory, deterministic controlled media, provenance, structured logs,
  tests, and architecture/security/governance records remain operational.
- **M1 — independently regression-verified.** The original CPU-only offline fixture is byte-identical
  to the previously reported fixture and sidecar. Its overlapping-chunk, sidecar-adapter, ledger,
  export, validation, interruption, and resume path remains operational under the M2A contracts.
- **M2A — complete.** The repository now has a hash-bound operator rights gate for non-fixtures,
  embedded text-subtitle extraction with track/cue provenance, deterministic structural shot and
  keyframe perception, versioned synthetic gold, machine/human component evaluation, explicit
  adapter degraded states, resource limits, and a dependency/model bill of materials.
- **M2B — controlled-fixture execution complete; real-media pilot pending.** The operator-approved
  packaged Tesseract/English data executed on the unchanged frozen set. Evidence-linked OCR,
  component quality, one/two/four-worker resources, negative rights/security paths, and normal and
  interrupted resume were measured and validated. This is frame OCR only, not semantic vision.
- **M2B.1 — reviewed hardening complete; v1.1 patch record frozen.** Permission closure, strict
  configuration, coherent partial results, actual chunk provenance, immutable raw OCR plus secondary
  temporal tracks, complete derived-artifact validation, path privacy, and clean-checkout CI are
  complete for the synthetic controlled baseline. Real-media evaluation remains pending.
- **M2B.2 — reviewed implementation merged; v1.2 release record frozen.** Supported
  media entry points authorize parser-free, acquire a verified private snapshot, enforce a shared
  fixed native protocol/demuxer policy, and hash/size-bind fixture sidecars before immutable
  adapter delivery. Issues 11, 12, and 14 closed with the reviewed implementation; issue 17 remains
  the security and temporary-root gate before any real-media pilot.
- **M2B.3 — reviewed private-storage and sandboxed pilot-security capability implemented.** A
  versioned local-private storage decision, path-free public receipt, exact Bubblewrap inventory,
  typed sandboxed native runner, bounded resource policy, pilot-manifest linkage, and hostile
  filesystem/network tests are implemented. The approved local Bubblewrap executable actually ran
  project-authored synthetic bytes through FFprobe, FFmpeg, and Tesseract. Final merge, issue, CI,
  and CodeQL identities are verified externally; this is not a real-media pilot-completion claim.
- **M2 — in progress, not complete.** ASR/alignment, diarization, acoustic,
  and semantic visual perception, a human-adjudicated pilot, direct-VLM/loose-baseline comparisons,
  and the full M2 continuation gate in `AV-Atlas_GOAL.md` have not been delivered.

No real-media understanding, model performance, statistical significance, or full-M2 completion is
claimed. No weights were downloaded and no training was run.

## Final environment and quality gates

Observed environment: uv 0.11.28, uv-managed CPython 3.14.3, Linux 6.8.0-134-generic x86_64,
FFmpeg/ffprobe 6.1.1-3ubuntu5, Tesseract 5.3.4, Leptonica 1.82.0, and Bubblewrap
0.9.0-1ubuntu0.1. `doctor` reports optional GPU state, but the pipeline did not use it; PyTorch is
not installed or required.

Commands run from the repository root and exact final results:

```text
uv lock --check
  Resolved 19 packages
uv sync --extra dev --locked --offline
  Resolved 19 packages; checked 18 packages; local package 0.2.3
uv run ruff format --check .
  63 files already formatted
uv run ruff check .
  All checks passed!
uv run mypy src
  Success: no issues found in 28 source files
uv run pytest -q
  405 passed in 137.84 s; zero failed; zero skipped
uv run av-atlas doctor
  passed; required FFmpeg/ffprobe, approved local OCR inventory, and available
  Bubblewrap pilot-sandbox capability reported
```

The final suite covers the M0/M1 behavior plus explicit fixture trust, rights refusal,
permission/hash/expiry/tamper failures, parser/subprocess zero-call sentinels, private snapshot
lifecycle and recovery, hostile mutation, fixed native protocol/demuxer policy, immutable sidecar
delivery, rights-gated inspection, subtitle and shot/keyframe paths, OCR, interruption, repeated
resume, semantic determinism, evaluation, BOM, schemas, revisions, provenance, evidence, and
artifact hashes. M2B.3 adds private-root admission, Bubblewrap identity/profile checks, native
resource limits, sandbox transition enforcement, actual filesystem/network denial probes, bounded
cleanup, and public-artifact path redaction. It requires no external network or GPU.

## Independent M0/M1 verification

The verification did not rely on the previous state report. A new M1 fixture and run were generated:

```text
uv run av-atlas make-fixture --profile m1 --output tests/fixtures/generated/m1
uv run av-atlas inspect tests/fixtures/generated/m1/synthetic.mkv \
  --output tests/fixtures/generated/m1/inventory.json
uv run av-atlas run tests/fixtures/generated/m1/synthetic.mkv \
  --config configs/baseline.yaml --output runs/m1-regression-m2a
uv run av-atlas validate runs/m1-regression-m2a
  valid: true; errors: 0; json_schema: 18; adapter_contracts: 5;
  events: 3; evidence_refs: 9; revision_chains: 3; rights_linkage: 1;
  artifact_hashes: 17; shots/keyframes/subtitle_cues: 0
```

The 6,000 ms media remains 391,222 bytes with SHA-256
`adb97d44f0e819a49473fbd34cc24e52c77f4390d6c09124bc382db7146edea1`; the sidecar
SHA-256 remains `4c1be7d7de62e5066282e7e90ad677aa40dd8cf2bdd2aca13b1c92bbcfc68387`.
The run produced 3 provisional and 3 final events, 9 evidence references, 17 hashed artifacts,
0 retries, and a measured pipeline runtime of 0.038296 s. The former documentation statement that
each observation always becomes its own event was corrected: co-timed observations can merge.

## Offline M2A demonstration

The complete documented command sequence was executed against the project-authored 10,000 ms
fixture:

```text
uv run av-atlas make-fixture --profile m2a --include-edge-fixtures \
  --output tests/fixtures/generated/m2a
uv run av-atlas make-rights tests/fixtures/generated/m2a/m2a_controlled.mkv \
  --output tests/fixtures/generated/m2a/rights.json \
  --operator-id controlled-demo-operator --basis synthetic-controlled \
  --allow analysis --allow evaluation --allow derivative_artifact_retention \
  --notes "Project-authored M2A controlled fixture"
uv run av-atlas inspect tests/fixtures/generated/m2a/m2a_controlled.mkv \
  --output tests/fixtures/generated/m2a/inventory.json
uv run av-atlas inspect-subtitles tests/fixtures/generated/m2a/m2a_controlled.mkv
uv run av-atlas run tests/fixtures/generated/m2a/m2a_controlled.mkv \
  --config configs/m2a.yaml --rights-manifest tests/fixtures/generated/m2a/rights.json \
  --operation analysis --output runs/m2a-demo
uv run av-atlas export runs/m2a-demo
uv run av-atlas validate runs/m2a-demo
uv run av-atlas evaluate runs/m2a-demo tests/gold/m2a-controlled.gold.json \
  --tolerance-ms 200
uv run av-atlas validate runs/m2a-demo
uv run av-atlas resume runs/m2a-demo
```

Pre-evaluation validation was valid with 28 artifact hashes and 41 schema instances. Final
validation was valid with 31 artifact hashes, 43 schema instances, 2 adapter contracts, 8 events,
12 evidence references, 8 revision chains, 1 rights linkage, 4 shots, 4 keyframes, and 4 subtitle
cues; errors were zero. The run directory contains 34 files (59,364 bytes by `du -sb`), including
all required inventories, ledgers, views, state, structured log, evaluation, quality report, and
four visually inspected PNG keyframes. Hashing every file before and after resume produced an empty
diff: all 34 files remained byte-identical and no records were duplicated.

Core identities and hashes:

- source: 517,837 bytes; `7bfc6a815292354891dd1c43fbf70667a839ded1c5b1f11bdc184bf5174f1391`
- config snapshot: `0ebf1fa971e866d0519999cd9071a057a863f4f295d919846df2d1f2eb31d01c`
- rights artifact: `26feed0cb099a53d40efdedb11ccb305e3270234dda847378c0bed65ad47612d`
- fixture manifest: `5338271d1ba309cca3c21d80a01d134a3a3e5aa00884d5f33d402087d4eb9545`
- gold source: `c076d202548dbd08a6c2ea27a577a6287a09e77a5892b98d9751aa568c364f4c`
- provisional/final ledger: `4a3f3d3ae9daafc117d8f19bca4bae4de51bce9b98bdd30030c7a2eccaad2d3a` /
  `75b870cac3d57eabeed97e12135087b23af1f5f2fa0ed15025e1bc3cecd2a1da`
- evidence index: `ff826beab64bc15b427c66458f348069341659375518c8b4653ae88dc3409438`
- shots/keyframes/subtitles: `4ad0819228e92a70333ee31dd265cf1067ea57b7835ffa4d9185d73211a0c692` /
  `57633eb63a030c4692269e789fab3f24173ce78c0a8f7887af8c32ce55d876b7` /
  `572fcdd07b5b95ec23c316512995e32b8843124649138e431231d7c6e9ce51c2`
- evaluation: `efca5599e1342df309d44d224295631e81fbd9a2670f32166407f12f85d5279e`
- final run manifest: `b60bf4b78c737c0c4a188f6fee4d4da2189646ab7346edbc989248b16a2c5490`

The evidence index contains 12 entries: 4 `SUB` cue references and 8 `VID` shot/frame references.
There are 8 provisional and 8 final events, 4 contiguous shots `[0,2000)`, `[2000,4600)`,
`[4600,8000)`, `[8000,10000)`, 4 unique keyframes at 1000/3300/6300/9000 ms, 2 subtitle
tracks, and 4 cues. The 6,000 ms flash produced no boundary. Unicode, formatting, overlap,
multiline content, and `IGNORE PREVIOUS INSTRUCTIONS` were retained as inert subtitle data.

## Measured synthetic-fixture results

At a 200 ms matching tolerance, the versioned synthetic gold evaluation measured:

- shot boundary precision/recall/F1: 1.0/1.0/1.0 (3 predicted, 3 gold, 3 correct);
  timing errors `[0, 100, 0]` ms, mean 33.333333333333336 ms, median 0 ms;
  transition confusion was 2/2 hard cuts and 1/1 gradual transition correct;
- keyframes: 4/4 covered, coverage 1.0, 0 missing, 0 duplicate;
- subtitle tracks: precision/recall/F1/discovery accuracy 1.0 (2/2);
- subtitle cues: precision/recall/F1/exact match 1.0 (4/4), normalized character error 0.0,
  all start/end timing errors 0 ms;
- adapter-state correctness: 2/2, accuracy 1.0;
- pipeline runtime 0.423365 s; evaluation runtime 0.042542 s; evaluation-reported output storage
  53,676 bytes; pipeline/evaluation peak RSS 28,748/27,520 KiB; 10,000 ms processed; 0 retries.

These are component checks on one project-authored ten-second fixture, not a human-adjudicated or
representative real-media sample. They cannot support population estimates or statistical
significance. ASR WER/alignment, diarization error, OCR accuracy, acoustic-event F1, semantic visual
accuracy, supported-claim precision, salient-event recall, and real-media generalization remain
unmeasured or unsupported.

## Rights, dependencies, and security boundaries

Non-fixture runs fail closed without a schema-valid explicit manifest. Validation binds source ID and
SHA-256, requested operation, derivative-retention permission, expiry, and the manifest's own hash.
The demonstrated declaration permits analysis, evaluation, and derivative retention; annotation,
training, and redistribution remain false. The operator is persisted only as pseudonym
`OPR_CF231A2419E4`. Fixture auto-authorization is accepted only with a matching hash-bound fixture
marker. A run-directory scan found no `/home/...` path, operator name, or secret-like value.

`docs/dependency-bom.json` records the local FFmpeg Ubuntu build, ffprobe binary, jsonschema, and
DejaVu Sans font with exact versions/hashes, license and constraint fields. The checkpoint inventory
is empty and weights are absent. FFmpeg's local GPL build is documented; no redistribution decision
is implied. Future ML dependencies remain optional and unapproved.

Media subprocesses use argument arrays without a shell, timeouts, output caps, controlled run-local
paths, dimension/duration/frame/keyframe limits, and explicit corrupt/decode/resource statuses.
Sources are never modified. These controls are not an OS sandbox. Codec parsers still process
untrusted bytes in local FFmpeg, rights declarations are operator assertions rather than legal
determinations, and free-text manifests/subtitles/metadata remain untrusted data. Quality reports are
excluded from their own manifest hash to avoid circular self-hashing.

## Smallest coherent M2B assignment

Implement one real OCR increment without expanding into learned fusion: a replaceable, rights-gated
frame OCR adapter, using a locally packaged Tesseract build and trained-data files only after their
versions, checksums, licenses, language coverage, and redistribution constraints pass BOM review.
Tesseract is not installed in the verified environment, so installation or data acquisition requires
separate authorization; M2B must fail as `unavailable_dependency` until then. Evaluate it on a small
project-authored plus authorized/public-domain, double-annotated pilot with exact/timing/error metrics,
while retaining the current sidecar adapter as the loose baseline.

Estimated execution needs after authorization: 4 CPU cores, under 2 GiB RAM, no GPU, roughly
0.1–0.5 GiB per approved language-data set plus under 1 GiB for fixtures/artifacts, and minutes—not
hours—per small pilot. Do not download weights/data or begin training as part of assignment setup.
ASR/alignment, diarization, acoustic-event, and semantic-visual adapters should remain later bounded
increments, each preceded by the same license/checkpoint/resource review.

## M2B verification — 2026-07-14

The repository, all instructions, the 22-page research paper, ADRs, schemas, configurations, source,
and tests were re-audited before changes. `command -v tesseract`, `dpkg-query -W tesseract-ocr
tesseract-ocr-eng libtesseract5`, and `/usr/share/tesseract-ocr` confirmed that no Tesseract
executable, package, or language data exists. No installation or network command was run. The exact
operator command for the detected Ubuntu system is:

```text
sudo apt-get install tesseract-ocr tesseract-ocr-eng
```

### Exact changed files

Added: `configs/m2b.yaml`; `src/av_atlas/ocr.py`; `src/av_atlas/ocr_evaluation.py`;
`schemas/ocr-observation.schema.json`; `schemas/ocr-gold.schema.json`;
`tests/gold/m2b-ocr-controlled.gold.json`; `tests/unit/test_ocr.py`;
`tests/integration/test_m2b_ocr.py`; `docs/ocr-annotation-guide.md`; and
`docs/decisions/ADR-0003-optional-tesseract-frame-ocr.md`.

Changed: `README.md`, `pyproject.toml`, `uv.lock`, `src/av_atlas/__init__.py`,
`src/av_atlas/cli.py`, `src/av_atlas/config.py`, `src/av_atlas/fixture.py`,
`src/av_atlas/pipeline.py`, `src/av_atlas/schemas.py`, `src/av_atlas/validation.py`,
`schemas/fixture-manifest.schema.json`, `tests/contract/test_schemas.py`,
`docs/architecture.md`, `docs/data-governance.md`, `docs/security.md`, `docs/evaluation.md`,
`docs/dependency-bom.json`, `docs/dependency-bom.md`, and this file.

### Final gates and regressions

```text
uv lock --check
  Resolved 19 packages
uv sync --extra dev --locked --offline
  Resolved 19 packages; checked 18 packages
uv run ruff format --check .
  31 files already formatted
uv run ruff check .
  All checks passed!
uv run mypy src
  Success: no issues found in 19 source files
uv run pytest -q
  42 passed, 1 skipped in 10.13s
  skip: approved local Tesseract absent; actionable Ubuntu installation command reported
uv run av-atlas doctor
  FFmpeg/ffprobe present; no GPU or model dependency used
```

Fresh M1 regeneration validated with zero errors: 17 artifact hashes, 18 schema instances, 5
adapter contracts, 3 events, 9 evidence references, and 3 revision chains. Its source hash remains
`adb97d44f0e819a49473fbd34cc24e52c77f4390d6c09124bc382db7146edea1`.

Fresh M2A regeneration/evaluation validated with zero errors: 31 hashes, 43 schema instances, 2
adapter contracts, 8 events, 12 evidence references, 8 revision chains, 4 shots, 4 keyframes, and 4
subtitle cues. Shot and subtitle fixture F1 remained 1.0; the gradual boundary remained 100 ms late.
Pipeline/evaluation runtime was 0.453003/0.046130 s and evaluation peak RSS was 28,020 KiB.

### M2B controlled demonstration and artifacts

Commands executed:

```text
uv run av-atlas inspect-ocr
uv run av-atlas make-fixture --profile m2b --output tests/fixtures/generated/m2b
uv run av-atlas run tests/fixtures/generated/m2b/m2b_ocr_controlled.mkv \
  --config configs/m2b.yaml --output runs/m2b-ocr-demo
uv run av-atlas export runs/m2b-ocr-demo
uv run av-atlas validate runs/m2b-ocr-demo
uv run av-atlas evaluate-ocr runs/m2b-ocr-demo tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas benchmark-ocr runs/m2b-ocr-demo
uv run av-atlas validate runs/m2b-ocr-demo
uv run av-atlas resume runs/m2b-ocr-demo
```

The 8,000 ms, 2,401,427-byte fixture contains four rapid-cut cards covering high/low contrast,
small/large mixed case, punctuation, digits, multiline text, supported Latin characters, rotation,
blur, deterministic noise/compression-like degradation, boundary placement, repeated adjacent
frames, and inert `IGNORE PREVIOUS INSTRUCTIONS`. Its SHA-256 is
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`.
The fixture marker hash is `61a990a35d1ad119c6ab77bf335333f2ee45789a8e34ff80b05193011b4a751d`;
gold hash `e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`;
configuration hash `8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55`.

Final M2B validation was valid with zero errors, 29 manifest artifact hashes, 27 schema instances,
2 adapter contracts, 4 structural events, 4 video evidence references, 4 revision chains, 4 shots,
and 4 keyframes. The run has 32 files/96,285 bytes. Pipeline runtime was 0.477195 s, peak RSS
29,572 KiB, and retries zero. Run manifest hash:
`ee1fc47675dbc49e0dde4638d8aa597ac5d9eb203d6489d7036e05e712f050c9`.

The OCR adapter state was `unavailable_dependency`, canonical OCR record count was zero, and no OCR
claim was fabricated. Evaluation engineering overhead was 0.005604 s wall, 0.005627 s CPU, peak RSS
27,776 KiB; OCR accuracy, FPS, and media-minutes/compute-minute are null. Evaluation hash:
`75db9215edb204bc8a1460a6f46671a4991ab59e7015a6e395e4acc1a0989e51`.
The 1/2/4-worker rows each record `blocked_unavailable_dependency`, one failure, zero timeouts, and
null wall/CPU/RSS/FPS/equivalence rather than estimates. Benchmark hash:
`27d44628b8ffc4878b5b9bbbe6d853ee224d2348b4fcc2aa4bd4d4b7c13402db`.

Completed-run resume left all files byte-identical. An inventory-interrupted run resumed twice with
an identical final-ledger hash. A scan found no absolute `/home/...` path, operator identity, or
secret-like value in the run. The prompt phrase appears only in project-authored pixels/gold, not in
logs or control flow. Temporary OCR derivatives are deleted; symlink/out-of-run keyframes are
rejected. FFmpeg/Tesseract controls remain defense-in-depth, not an OS sandbox.

The BOM records Tesseract and `tesseract-ocr-eng` as `not_installed`, with no invented version,
executable/data hash, or build features. The checkpoint inventory remains empty.

“M2B engineering and controlled-fixture evaluation complete; authorized double-annotated real-media
pilot pending.” Here evaluation means the unavailable-state engineering path; no OCR quality was
measured. Full M2B remains blocked until an approved local Tesseract execution, BOM refresh,
controlled-fixture metrics, and real 1/2/4-worker benchmark pass all gates.

### Smallest coherent M2C proposal

After M2B is genuinely completed, add one replaceable CPU-only acoustic-event baseline using only an
already installed or separately authorized distribution component. Begin with dependency/license
inventory and explicit unavailable states, then a project-authored tone/impulse/ambience fixture,
evidence-linked intervals, and component F1/onset timing evaluation. Do not download a checkpoint or
train. ASR/alignment, diarization, semantic visual perception, direct-VLM comparison, the real pilot,
and full M2 remain incomplete.

## M2B installed-engine closure — 2026-07-14

This section supersedes the earlier unavailable-dependency execution report. That report verified
the fail-closed adapter boundary only; it was not OCR quality evaluation. Before this closure, the
frozen fixture, gold, and configuration were re-hashed and matched their reported values exactly:

- fixture: `6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`
- gold: `e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`
- configuration: `8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55`

None of those frozen files, their timing/categories/transcriptions/regions, normalization, tolerance,
or metric definitions was changed. The gold's `source_sha256` field remains null; evaluation reports
that limitation instead of pretending an in-gold source match, while the fixture hash is checked
directly before execution. Three implementation defects were recorded before correction: the
benchmark emitted hard-coded unavailable rows even with an installed engine; configured workers did
not execute concurrently; and the component report omitted required evidence, presence-F1,
adapter-state, resource, and per-category quality fields. Poor recognition was not treated as a
defect.

### Exact dependency identity

`/usr/bin/tesseract` is a 39,320-byte Ubuntu `tesseract-ocr` 5.3.4-1build5 amd64 executable (source
`tesseract` 5.3.4-1build5), SHA-256
`9f831cab7525c3dab04af41bda35182af7ea1df9dceeaaa2f3bf207ac45c06a5`, Apache-2.0 per
`/usr/share/doc/tesseract-ocr/copyright` (SHA-256
`2442a6ad56b34fc1e0ec4b13509e22d4e428c856e488b2a709456ce4e9f0ab4e`). The runtime package is
`libtesseract5:amd64` 5.3.4-1build5; `/usr/lib/x86_64-linux-gnu/libtesseract.so.5.0.3` SHA-256 is
`0d3b71cd757860c6639918c1b2d9407c8652ee22babc8d5c5f18cc35dde6334b`.

Tesseract reports Leptonica 1.82.0, AVX512BW/F/VNNI, AVX2, AVX, FMA, SSE4.1, OpenMP 201511,
libarchive 3.7.2, and libcurl 8.5.0. `TESSDATA_PREFIX` and `OMP_THREAD_LIMIT` were unset in the parent
environment; distribution-default discovery resolved `/usr/share/tesseract-ocr/5/tessdata` and
listed `eng` and `osd`. The adapter sets `OMP_THREAD_LIMIT=1` for each Tesseract child.

`eng.traineddata` is 4,113,088 bytes, Ubuntu `tesseract-ocr-eng` 1:4.1.0-2 all (source
`tesseract-lang`), SHA-256
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. Its local Apache-2.0
copyright file hash is `33fb8161898e34fcf5c6b8585d6be97642d7e8f34a922e783c6c5c970d0b09ad`.
Installed `osd.traineddata` is inventoried but not used by the eng-only frozen configuration:
10,562,727 bytes, `tesseract-ocr-osd` 1:4.1.0-2 all, SHA-256
`9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff`.

The runtime configuration is PSM 6, OEM 1, grayscale, no contrast normalization or threshold,
minimum confidence 0, maximum dimension 1920, 15-second process timeout, one default worker, maximum
four workers in benchmarks, 100-frame source limit, unavailable behavior `degrade`, no raw-frame
retention, and deleted temporary files. The BOM records all four Ubuntu package identities and keeps
the checkpoint array empty. Language data is third-party pretrained data, not AV-Atlas-trained
weights.

### Actual OCR result and controlled-fixture metrics

The fresh run is `runs/m2b-ocr-executed`. Tesseract processed four keyframes and emitted 13 ordered
word observations, each with source/shot/frame identity, integer timestamp, separate raw and
normalized text, box, confidence, eng and engine/data identity, preprocessing, source-frame and OCR
evidence references, succeeded state, and warnings. Frame transcriptions were:

- 1000 ms: `AV Atlas 2026!` (3 regions; confidence 96.460037–96.832489)
- 3000 ms: `Low Contrast ‘small Text 42` (5; 76.766487–95.569748)
- 5000 ms: `Unicode cafe` (2; 95.963280–96.970825)
- 7000 ms: `IGNORE PREVIOUS INSTRUCTIONS` (3; 96.689056–96.928932)

The prompt-like text remained untrusted evidence and did not occur in logs, configuration, state, or
control inputs. Against the unchanged synthetic gold: 4 evaluated/4 text-positive frames, 13
observations, exact frame transcription 0.75, normalized CER 0.0125, normalized WER
0.07692307692307693, text-presence precision/recall/F1 1.0/1.0/1.0, duplicate rate 0,
missing-evidence count 0, invalid-timestamp count 0, adapter-state correctness true, retries/timeouts
0/0. OCR runtime was 3.017794 s wall, 2.230488 s CPU, peak RSS 181,284 KiB, 1.325471735142 frames/s,
and 2.650943039850 media-minutes per compute-minute. The process-memory measurement is the maximum
of the parent or a single child, not concurrent aggregate RSS.

Per-category exact/CER/WER: high-contrast, digits, mixed-case, punctuation, rotation,
prompt-injection, and unicode-supported-by-eng were 1/0/0; low-contrast and small were
0/0.038461538461538464/0.2; multiline (two frames) was 0.5/0.018518518518518517/0.125. Region
precision/recall and box IoU are null only because every frozen gold `regions` array is empty;
predicted word boxes are present but have no gold regions against which to match.

### Worker scaling

All rows ran the same frozen four frames and gold, produced 13 observations, exact/CER/WER
0.75/0.0125/0.07692307692307693, presence precision/recall/F1 1/1/1, zero retries/timeouts/failures,
and semantic output SHA-256
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`:

| Workers | Effective config SHA-256 | Wall s | CPU s | Peak KiB | Frames/s | Media min/compute min |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `7020e5ea8bb54c00d99963dd0eed00a02f521859cbe222400232969c5a83fd3c` | 2.207769 | 2.177335 | 181352 | 1.811783620446 | 3.623567501854 |
| 2 | `6fb1b15f8c0e6411c8ef9d10493d2f0654f20aaea9007f1e2e1be385bf48b33e` | 1.842121 | 2.096001 | 181352 | 2.171409541629 | 4.342820042766 |
| 4 | `cdd9168fdf983922ed0233f8b2d81d865ee49e98a5f1096a920e707181a5c08d` | 1.838363 | 2.364020 | 181352 | 2.175848547082 | 4.351697678859 |

The semantic outputs are identical across worker counts. Peak single-process RSS stayed below the
2 GiB target; no network or GPU was used.

### Regression, rights, security, and resume

Fresh M1 validation: zero errors, 17 artifacts, 18 schemas, 5 adapter contracts, 3 events, 9 evidence
references, and 3 revision chains. Fresh M2A evaluation retained shot/subtitle F1 1.0 and zero
subtitle CER; validation had zero errors, 31 artifacts, 43 schemas, 2 contracts, 8 events, 12
evidence references, 4 shots/keyframes/cues. M2B validation had zero errors, 64 manifest artifacts,
53 schema instances, 2 contracts, 8 events, 17 evidence references, 4 shots/keyframes, and 8 revision
chains.

Every directory under `runs/` validates with zero errors. The preserved AV-Atlas 0.1.0 run is
checked through an explicit legacy contract (JSON readability, duration/evidence integrity, and 12
recorded artifact hashes) without retroactively asserting rights/config/adapter artifacts that did
not exist in 0.1.0. The preserved pre-schema M2B unavailable report is likewise recognized as
legacy rather than rewritten; current M2B reports use the new versioned schemas.

Tests exercised both successful and unavailable dependencies; unsupported/nonexistent language;
malformed/corrupt, empty/no-text, oversized, hash-mismatched frames; timeout; shell metacharacters;
symlink/path escape; temporary cleanup; prompt isolation; exact-source mismatch; separately denied
analysis/evaluation/derivative retention; expired/tampered rights; corrupt media; and offline M1/M2A
regressions. Rights validation occurs before frame extraction and fails closed. Operator assertions
remain declarations, not legal conclusions. A scan of the final run found no `/home/`, `/tmp/`, raw
operator identifier, common secret-like assignment, or prompt phrase in logs/config/state.

Completed-run resume preserved all 67 files byte-for-byte (aggregate digest
`08539c8632cdf0a452892b7f558ae54f8b1026958d0710ec678ba87f492da3f0`) and all 64 tracked artifacts
(`e10bec548cd486d969cdc9f169928ee2e02a8d19958f0dfc58350808a4722e97`). A process-group SIGTERM
during the OCR temporary-directory stage exited 143 with manifest `processing`, stage `inventory`,
and zero tracked artifacts. Resume removed the stale bounded temporary directory, completed,
evaluated, benchmarked, and validated the run; repeated resume then preserved all files digest
`1108667aa3f7057b450c4c9ed69ad9e63f0d6f9d141cccb6f6f3bdc4ac1ffcf1` and tracked digest
`b07e1b5e716a77d05a33d8a6b6254fdb35cfa69f7ba6a7eaedd5d69e4bdf36e1`. Runtime timestamps and
resource measurements differ between independently started runs, as expected; canonical OCR bytes
remain identical.

Major final artifact hashes for `runs/m2b-ocr-executed`: run manifest
`6779769594db6a7457ee30b7d9ffbdacc8ec345120433125e7e846978359b440`; dependency inventory
`cbe5ba1f556c3b290322016332b9400418dccd0d4396c3bc1de2373e888f5440`; observations
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`; evidence
`35a7dd62e34124f9446137c7043f208f9c7c39c731346f9402dad090d47d4c09`; final ledger
`10af6563a220d3d8948211f89e0b7ba972bc4c22a697db5a8d2880247a135787`; evaluation
`a1011542165e3b8974857aaee68bbaa8185987cbb3ca0353ad4afecda38803ad`; benchmark
`479087002a126b1d442ca2e4d768bafd3e266e9f542dba92a01ea075a3280455`; BOM snapshot
`5239dcff7fcff70f1c917f64b4ade983fdf497cd930bbe1084cce1c30b484643`; quality report
`a5333b9e95234fff4d020379ba00eafd84ad4deda62f8f015d6c55392a25475a`.

### Commands and changed files

Executed commands included the required `uv lock --check`, locked offline sync, Ruff format/check,
mypy, full and marked Tesseract pytest, doctor, `inspect-ocr`, fresh M1/M2A generation/run/evaluation/
validation, frozen M2B run/export/evaluation/benchmark/validation, normal resume, process-group
interruption during OCR, first/repeated resume, file/artifact hashing, package queries, and privacy/
prompt scans. No network, installer, sudo, cloud, GPU, API, upload, checkpoint download, or training
command was used.

Source/test/schema files changed: `src/av_atlas/ocr.py`, `src/av_atlas/ocr_evaluation.py`,
`src/av_atlas/cli.py`, `src/av_atlas/schemas.py`, `src/av_atlas/validation.py`;
`schemas/ocr-dependency.schema.json`, `schemas/ocr-frame-results.schema.json`,
`schemas/ocr-runtime.schema.json`, `schemas/ocr-evaluation.schema.json`,
`schemas/ocr-benchmark.schema.json`; `tests/unit/test_ocr.py`, `tests/unit/test_rights.py`,
`tests/integration/test_end_to_end.py`, `tests/integration/test_m2b_ocr.py`, and
`tests/integration/test_m2b_execution.py`. Documentation
changed: `README.md`, `docs/architecture.md`, `docs/data-governance.md`, `docs/security.md`,
`docs/evaluation.md`, `docs/dependency-bom.json`, `docs/dependency-bom.md`, and this file. Fresh
generated evidence is under `tests/fixtures/generated/m1-m2b-executed`,
`tests/fixtures/generated/m2a-m2b-executed`, `runs/m1-regression-m2b-executed`,
`runs/m2a-regression-m2b-executed`, `runs/m2b-ocr-executed`, and
`runs/m2b-ocr-interruption-proof`. Two completed timing attempts that finished before a signal could
land are preserved at `runs/m2b-ocr-interrupted-executed` and
`runs/m2b-ocr-mid-interruption-executed`; they also validate. Exact run files are enumerated and
hashed by each run manifest.

### Decision and limitations

“M2B controlled-fixture engineering, OCR execution, evaluation, and resource benchmark complete;
authorized double-annotated real-media pilot pending.” No real-media accuracy, semantic visual
understanding, audiovisual reasoning, learned AV-Atlas capability, or full M2 completion is claimed.
Full M2 remains incomplete because ASR/alignment, diarization, acoustic-event recognition, semantic
visual perception, the adjudicated real-media pilot, and direct-VLM comparison remain incomplete.

## 2026-07-14 — M2B controlled-baseline v1 freeze and pilot-package preparation

The accepted status remains: “M2B controlled-fixture engineering, OCR execution, evaluation, and
resource benchmark complete; authorized double-annotated real-media pilot pending.” This applies
only to four project-authored synthetic frames. No real-media accuracy, semantic visual
understanding, audiovisual reasoning, learned model, or full-M2 claim is made.

### Release verification and fresh replay

Before changes, the accepted fixture/gold/configuration hashes were independently re-read as
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`,
`e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`, and
`8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55`. Accepted observations,
evaluation, benchmark, and run-manifest hashes also matched:
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`,
`a1011542165e3b8974857aaee68bbaa8185987cbb3ca0353ad4afecda38803ad`,
`479087002a126b1d442ca2e4d768bafd3e266e9f542dba92a01ea075a3280455`, and
`6779769594db6a7457ee30b7d9ffbdacc8ec345120433125e7e846978359b440`.

The dependency remained operator-installed Ubuntu `tesseract-ocr` 5.3.4-1build5 amd64, Tesseract
5.3.4/Leptonica 1.82.0, executable hash
`9f831cab7525c3dab04af41bda35182af7ea1df9dceeaaa2f3bf207ac45c06a5`; English data remained
`tesseract-ocr-eng` 1:4.1.0-2, 4,113,088 bytes, hash
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.
Codex installed nothing during this replay. No network, GPU, cloud, API, upload, checkpoint, or
training was used.

A new same-host fresh reproducibility replay generated
`reproductions/m2b-controlled-baseline-v1/fixtures` and `runs/m2b-controlled-replay-v1`. The rebuilt
fixture and OCR semantic output matched exactly. Replay evaluation preserved 4 frames, 13
observations, exact match 0.75, CER 0.0125, WER 0.07692307692307693, presence P/R/F1 1/1/1, zero
duplicates/evidence failures/invalid timestamps/retries/timeouts, and correct adapter states. Its
nondeterministic main runtime was wall 3.640003 s, CPU 2.299175 s, peak RSS 180,556 KiB, and
1.098900113513 frames/s. Replay worker wall times were 2.751924/2.388375/2.338480 s for 1/2/4
workers, with identical semantic output and quality. Replay evaluation/benchmark/run-manifest file
hashes were `86bc464e8c462ae98a67e1241860ddf3e2ba55ec2d4243eeb633c25f471f468c`,
`af8a6cfc0990c8c50746e5c1b65222122f6ef25080152b8caff53c354c884288`, and
`4dad1363871629af6f3c0edb6af94e74c8ae4545d4e401d39d19a0c8b54c8832`. These runtime-bearing
hashes are not expected to equal the accepted run. Validation reported zero errors and 64 artifact
hashes. First and repeated completed-run resume preserved all manifest-tracked bytes; the replay
tracked-list digest remained `316e6a9d3e20ee760d9ef76cf1e620531c230d5a33ef1e8cc8d8c68b5bc921cc`
under the replay comparison procedure. Accepted interrupted-resume evidence was rechecked from the
preserved run and remains documented in the release record.

A container runtime and cached Python image existed, but the image lacked uv, FFmpeg, and Tesseract.
No image pull or package installation was authorized, so this is explicitly a fresh same-host
reproducibility replay, not an independent second-environment or second-implementation verification.

The frozen benchmark supports a provisional two-worker recommendation: measured accepted wall time
improved 16.56% from one to two workers (reasonably approximately 20%), while four workers improved
only another 0.20%; every worker count had the identical semantic hash. The frozen one-worker
configuration was not changed.

### Release, pilot tooling, and blocked state

Release records are `docs/releases/M2B_CONTROLLED_BASELINE_V1.md` and `.json`; the fully offline
procedure is `docs/releases/M2B_CONTROLLED_REPRODUCTION.md`. The record states that the operator
installed Tesseract before execution and contains no absolute home path or username.

New fail-closed commands prepare the authorized pilot without fabricating data:
`pilot-prepare`, `pilot-annotation-packages`, `pilot-compare-annotations`, `pilot-freeze`,
`pilot-run-ocr`, and `pilot-evaluate`. They enforce at least three distinct sources, exactly 20
calibration and 60 locked evaluation frames, all four required rights permissions, exact hashes,
bounded safe extraction, separate blank packages, distinct completed human submissions,
adjudication, frozen configuration/gold/rules, unchanged local OCR, evidence linking, region and
text metrics, and source/category/difficulty/size/confidence strata. Pilot media and work directories
remain untracked and local. The prepared path is covered by new schemas and fail-closed unit tests.

No operator-supplied pilot media and no two independent human annotations were present. Therefore
no pilot composition, inter-annotator score, real-media OCR metric, region metric, or error taxonomy
was measured. Current pilot status: “M2B controlled baseline frozen and real-media pilot package
ready; operator-supplied authorized media and two independent human annotations pending.”

### Files and commands

Files added: `src/av_atlas/ocr_pilot.py`; `schemas/ocr-pilot-manifest.schema.json`;
`schemas/ocr-human-annotation.schema.json`; `tests/unit/test_ocr_pilot.py`;
`docs/releases/M2B_CONTROLLED_BASELINE_V1.md`; its `.json` manifest;
`docs/releases/M2B_CONTROLLED_REPRODUCTION.md`; `docs/templates/ocr-pilot-spec-v1.json`;
`docs/decisions/ADR-0004-frozen-ocr-pilot-protocol.md`; and
`docs/research/M2C_DECISION_MEMO.md`. Files updated: `src/av_atlas/cli.py`,
`src/av_atlas/schemas.py`, `README.md`, this file, architecture, data governance, security,
evaluation, dependency-BOM Markdown, OCR annotation guide, and ADR-0003. Generated fresh evidence is
in the reproduction fixture and replay run directories above. Frozen fixture, gold, normalization,
metrics, and M2B configuration were not changed.

Executed commands included complete file/PDF inspection; `sha256sum`; Tesseract/package inventory;
cached-container inspection with networking disabled; fresh `make-fixture`, `run`, `evaluate-ocr`,
`benchmark-ocr`, `validate`, and repeated `resume`; schema/test discovery; Ruff format/check; mypy;
pytest; and the final locked/offline and doctor gates recorded below. No privileged or network
command was run.

### M2C decision, not implementation

The earlier acoustic-event-only proposal is superseded by the decision memo, not by implementation.
The strategically preferred smallest M2C is a separately authorized replaceable local ASR adapter
with word-level integer-millisecond alignment, controlled English fixtures, evidence/provenance,
rights and prompt-injection controls, offline CPU measurement, and an explicit unavailable state.
Exact runtime/checkpoint license, hash, size, memory, and CPU feasibility must be audited before any
installation or download. A compact acoustic-event adapter remains the lower-complexity alternative
when CPU-only incremental delivery is explicitly prioritized. Diarization is third because of
voice-privacy, overlap, multi-stage dependency, and CPU risks. No M2C model was downloaded or run.

Full M2 remains incomplete: ASR/alignment, diarization, acoustic-event recognition, semantic visual
perception, the adjudicated real-media pilot, and direct-VLM comparison are still absent.

## 2026-07-14 — public-source publication preparation

The operator authorized publication without selecting a reuse license. The public tree therefore
states: “No project license has yet been selected. Public visibility permits inspection of the
source but does not grant reuse rights beyond applicable law.” It is not described as open source.

Publication controls add comprehensive Git exclusions, attributes, security/contribution/citation
files, least-privilege CI, Dependabot configuration, pull-request controls, publication/license/
artifact/release decisions, and a per-file machine-readable publication manifest. Generated media,
runs, reproduction outputs, caches, environments, logs, operator/private media or derivatives,
rights workspaces, annotations, datasets, checkpoints, traineddata, binaries, editable research
source, archives, and secrets are excluded. The project concept PDF, source, schemas, configs,
tests, compact synthetic gold, locked dependencies, governance, task/goal records, and sanitized
release records are included under explicit public-disclosure authorization with reuse licensing
unresolved.

Pre-publication local gates passed: locked offline sync, Ruff formatting/lint, mypy over 20 source
files, doctor, and 52/52 tests in 63.40 seconds with real Tesseract execution. Fresh ignored M1,
M2A, and M2B runs validated with zero errors. The fresh M2B semantic output remained
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`; completed and repeated
resume preserved all 64 tracked artifacts with comparison digest
`308e6943ae828b4e12e9a30b21a332bde8f707ccf4408a202b9ba6ac1b2018c7`.

The filename/content/PDF/binary/size/symlink scan found no live credential, personal email/home
path, restricted media, private derivative, private rights declaration, checkpoint, dataset,
traineddata, executable, or escaping symlink among publication candidates. Negative-test sentinels
such as `operator@example.invalid` and `/home/` assertions are inert test data. The authenticated
GitHub credential remains in the system keyring and is not stored in the repository. M2C was not
implemented.

The first public CI run exposed one publication-only regression: a test directly referenced the
intentionally untracked `runs/m0-m1-validation-v3` directory. The test now executes when that local
historical evidence exists and otherwise skips with an explicit policy reason. It does not skip any
Tesseract path or weaken the legacy validator. The failed Actions run remains visible.

Final gates passed: lock check; locked offline sync (18 packages checked); Ruff formatting (34
files); Ruff lint; mypy (20 source files); doctor; and pytest (52 passed in 69.52 s, no skips or
failures). Every one of the 13 run directories with a manifest validated at zero errors. A
host-wide disk-full condition briefly prevented validation from atomically rewriting a quality
report; only this assignment's `pytest-67` scratch directory was removed, after which the complete
validation sweep passed. No repository evidence or unrelated cache/temp work was removed. Final
release JSON/Markdown and M2C memo hashes are
`e545855c11ee23542939a35aecf03d00c6f12bbd056d6d4bcae43df139b7c9b2`,
`f4a48d534707b56bf1d21ccfa69c8e8dafa4544e163893c7da6411c26fa331ef`, and
`f6aed849967a1cf3185dc9de21138a4fdc117c18240c5597984d6de87d74f547`
respectively.

## 2026-07-14 — M2B.1 source-audit hardening branch

Branch `audit/m2b1-hardening` addresses confirmed source-integrity and correctness findings without
implementing M2C, processing real media, or changing the immutable `m2b-controlled-v1` tag/release.
Public findings are tracked in issues 7, 8, and 9.

Confirmed on pre-change `main` (`2545fcf4da8e7b62cb57ad1196f802226059c03e`): resume and
validation bypassed the rights self-digest loader; resume omitted retention and run-link checks;
configuration coerced wrong JSON types and missed nested unknown keys; OCR/subtitle partial output
had contradictory status semantics; prediction-only OCR frames were excluded from presence false
positives; empty-record state correctness was vacuous; event chunk provenance hardcoded 2,000 ms;
ordinary OCR dependency reports exposed full paths; and the clean-checkout CI fix postdated v1.
No requested finding was rejected as non-reproducible.

The additive contracts are adapter-results 1.1 (`partial_success` plus balanced unit counts), event
ledger 1.1 (all overlapping generated chunk IDs), OCR frame-results 1.1, OCR dependency 1.1,
dependency BOM 1.1, strict configuration schema 1.1, and derived OCR text tracks 1.0. Legacy 1.0
adapter, event, frame, dependency, and BOM artifacts remain accepted. Rights validation now uses one
schema/digest/source/operation/retention/expiry/run-link path before resume processing. The rights
self-hash is explicitly only an integrity checksum, not an authenticated signature.

Raw OCR observations remain byte-identical to v1; a separate association artifact preserves every
member observation/frame reference and uses normalized text, same-shot, bounded-gap, and spatial
compatibility policy `ocr-temporal-association/1.0.0`. Evaluation now separates exact duplicates,
temporal repetition, track compression, and unresolved evidence and includes prediction-only and
gold-only frames. Raw-frame retention remains false-only.

Exact local gates:

```text
uv lock --check
  Resolved 19 packages
uv sync --extra dev --locked --offline
  Resolved 19 packages; checked 18 packages
uv run ruff format --check .
  41 files already formatted
uv run ruff check .
  All checks passed!
uv run mypy src
  Success: no issues found in 21 source files
uv run pytest -q
  86 passed in 40.12s
uv run av-atlas doctor
  exit 0; FFmpeg/ffprobe 6.1.1-3ubuntu5, Python 3.14.3, Tesseract 5.3.4 available;
  ordinary OCR inventory path-sanitized; no GPU/model dependency used
```

Fresh ignored M1, M2A, M2B, and interruption/resume runs all validated with zero errors. M1 had 17
artifact hashes/3 events/9 evidence references. M2A had 31 hashes/8 events/12 references/4 shots/4
keyframes/4 cues and retained shot/subtitle F1 1.0. M2B had 68 hashes/8 events/17 references/4
shots/4 keyframes and 13 OCR observations. The accepted OCR semantic hash remained
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`.

New synthetic hardening evaluation retained exact match 0.75, CER 0.0125, WER
0.07692307692307693, presence P/R/F1 1/1/1, 0 exact duplicates, 0 temporal repeats, 13 derived
tracks, compression 0, 0 prediction-only/gold-only frames, 0 unresolved evidence/invalid
timestamps/timeouts/retries, and correct adapter state. Measured OCR wall/CPU/peak RSS/FPS were
2.408453 s/1.909924 s/180,556 KiB/1.6608173544469151. Worker 1/2/4 measurements were respectively
1.870963/1.651128/1.510803 wall seconds, 1.855986/1.888869/1.900421 CPU seconds, 180,556 KiB peak,
and 2.1379358942689217/2.422586835739302/2.6475993620845615 FPS. All emitted the accepted semantic
hash with zero failures/timeouts.

New artifact hashes: OCR tracks
`f27d60f51c06cead4d0b6159b47865fd635a010e2faba9902057ae1c9cd4b9c2`; evaluation
`4787b5acadea251e9b9930b3bccfda3c4f11238643639547c7efc39bd2b4968c`; benchmark
`8b6b5838c8372456f7a561c598734a42707d97672569bc33226f4a36aa385baa`; sanitized OCR dependency
`5ab8663ce63b7d6303ce84e3ec62ab3a9dd1ec55283e8f0c6852dd88740d5cce`; BOM snapshot
`abca366e47275ef2d5ff2825b53b0d47436e03a56e29a696f903cb194d188868`; M2B run manifest
`65b6919d4cdda23acfdd87e4292fb91488866113b494ff94a94a5fa773e77a8f`.
Completed-run tracked digest remained
`0fdda6b09a2de87d7a0bcf22c85dc36258bf246cbc246521713207f6bea14c86` across two resumes;
interrupted/completed digest remained
`06879f45963ae06f06bb6e62f9607ce2fcaed47f90ace7e75029dcbc933fe5be` on repeated resume.

The accepted fixture, gold, configuration, OCR output, evaluation, benchmark, run manifest, and
release manifest hashes remain exactly
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`,
`e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`,
`8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55`,
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`,
`a1011542165e3b8974857aaee68bbaa8185987cbb3ca0353ad4afecda38803ad`,
`479087002a126b1d442ca2e4d768bafd3e266e9f542dba92a01ea075a3280455`,
`6779769594db6a7457ee30b7d9ffbdacc8ec345120433125e7e846978359b440`, and
`e545855c11ee23542939a35aecf03d00c6f12bbd056d6d4bcae43df139b7c9b2`. The old 64-artifact M2B
run validates under backward compatibility. No authorized real-media result or full-M2 completion
is claimed.

Changed tracked files are README and project architecture/governance/security/evaluation/BOM/
reproduction documentation; ADR-0005; configuration, adapter-results, event, OCR dependency/frame/
track, and BOM schemas; adapter/config/contract/rights/pipeline/OCR/evaluation/subtitle/shot/
validation/CLI source; and contract/unit/integration regressions for each finding. Generated runs
remain ignored. The checkpoint inventory remains empty. Remaining risks include unauthenticated
rights checksums, native FFmpeg/Tesseract parser exposure without an OS sandbox, no non-pilot
retained-frame lifecycle, synthetic-only OCR quality, and an unexecuted authorized double-annotated
pilot. Full M2 and M2C remain unimplemented.

## 2026-07-14 — M2B.1 review follow-up: initial preflight and OCR-track relations

Review of PR 10 confirmed two additional defects. Initial `initialize_run()` called FFprobe before
checking a fixture marker or explicit rights declaration, so denied non-fixture bytes could reach a
native parser. OCR text-track validation used strict `zip` over unchecked parallel arrays and could
raise `ValueError`; it also did not recompute the complete derived relationship from raw OCR
observations.

Initial execution now uses a frozen parser-free authorization record containing the directly
computed source SHA-256, canonical hash-derived source ID, controlled-fixture status and validated
marker, validated rights declaration, requested operation, and authorization timestamp. Regular
file, fixture marker, rights schema/self-checksum, exact source, operation, derivative retention,
and expiry checks complete before media inspection. FFprobe inventory must reproduce the preflight
hash and source ID; a changed source aborts before run-directory creation. Fixture generation,
rights creation, media inventory, and preflight all use one canonical source-ID helper.

Track validation now checks equal member/evidence/box/confidence lengths before iteration and
recomputes member uniqueness/existence, source, shot, normalized text, evidence, boxes, confidence,
timestamp bounds, ordering, arithmetic mean (`1e-9` absolute/relative tolerance), policy version,
configured temporal gap, shot boundary, and spatial compatibility from immutable raw OCR records.
Malformed artifacts return controlled validation errors and write actionable quality-report
entries; raw OCR remains canonical and tracks remain secondary.

Regression coverage includes zero-call parser/subprocess sentinels for missing rights, stale
self-checksum, wrong source hash/ID, analysis denial, retention denial, expiry, and requested
operation denial; stale persisted-run linkage; valid explicit and fixture authorization ordering;
post-preflight source change; marker/source-byte mismatch; all requested track relational
mutations; nonzero CLI validation without traceback; and a valid generated track.

The focused set passed 49 tests in 14.67 seconds, and the final complete suite passed 118 tests in
66.35 seconds. Lock checking, locked offline sync (18 packages checked), Ruff formatting (43
files), Ruff lint, mypy over 21 source files, and doctor also passed. Fresh ignored M1, M2A, and M2B runs validated with 17,
31, and 68 artifact hashes respectively and zero errors. The M2B report checked 13 temporal tracks.
Fresh interrupted completion and repeated resume validated with 28 artifact hashes and zero errors.
Completed and interrupted tracked-artifact comparison digests stayed byte-identical across resume:
`99b71bc94243a7e84fba13ee8cad92b5e7a205086f262a9f0d2fa686f5dcfdc1` and
`693ae04efcde94ce271e24fd6ebf09cbc645993ee8766b52339db6d7225a6212`.

The fresh M2B observation and temporal-track hashes remain
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060` and
`f27d60f51c06cead4d0b6159b47865fd635a010e2faba9902057ae1c9cd4b9c2`.
Runtime-bearing evaluation, benchmark, and run-manifest hashes for this replay are
`9ccce73311dca7146f1ff837b83dde27fcb89ac8d45b512175dac427e8fc8cb4`,
`748b174a197bc35b5da616bd4710cc84d9343ca703a800f478a0c2e1ab2c1f82`, and
`a0e62a3eb3278c121c441d00c69a0c29207dec87b068b9697c1cef7e09b45cb7`.
The sanitized dependency and BOM hashes remain
`5ab8663ce63b7d6303ce84e3ec62ab3a9dd1ec55283e8f0c6852dd88740d5cce` and
`abca366e47275ef2d5ff2825b53b0d47436e03a56e29a696f903cb194d188868`.

The accepted M2B v1 fixture, gold, configuration, OCR, evaluation, benchmark, run-manifest, and
release hashes remain unchanged. Its 64-artifact run and the prior 68-artifact M2B.1 run both
validate without rewriting their reports. No schema version or valid hardening output changed; the
new work strengthens initial ordering and validation semantics only. PR 10 remains the delivery
vehicle. No tag, release, real-media processing, M2C implementation, or full-M2 claim occurred.

## 2026-07-15 — M2B.1 review follow-up: permission closure and complete track derivation

Review of PR 10 confirmed that rights permission names were still accepted indiscriminately as
executable run modes. Because every run enters the perception pipeline, an evaluation-only or
downstream-use permission could otherwise trigger analysis without the complete authorization
needed by the actual behavior. Executable modes are now distinct from the unchanged rights-manifest
1.0 vocabulary: `analysis` requires `analysis` plus `derivative_artifact_retention`; `evaluation`
requires `analysis`, `evaluation`, and `derivative_artifact_retention`. `annotation`, `training`,
`derivative_artifact_retention`, and `redistribution` are rejected as run modes rather than being
silently treated as analysis. One canonical closure helper is used by CLI validation, parser-free
initial authorization, persisted-rights loading, resume, and run validation. Regression sentinels
prove denied modes and incomplete permission closures invoke no FFprobe, FFmpeg, Tesseract, or
adapter subprocess.

OCR temporal tracks are now validated as the complete deterministic secondary derivation of all
immutable raw OCR observations. Validation recomputes the expected payload with
`associate_temporal_text` and the configured maximum gap, canonicalizes both payloads, and compares
them in full. It also reports field-level errors for track/member uniqueness and order, exactly-once
raw-observation coverage, nonempty equal-length parallel arrays, ordered unique raw-text variants,
source/shot/text/evidence/box/confidence relations, timestamps, mean confidence, policy, spatial
compatibility, and temporal gaps. Empty member arrays and other malformed values are guarded before
indexing, extrema, or arithmetic, so the public validation CLI returns a controlled nonzero result
and writes an actionable quality report without a traceback. Empty tracks are accepted only when
there are no raw OCR observations. No schema version changed: these are semantic invariants of the
existing M2B.1 derived artifact, while accepted M2B v1 runs without that optional artifact retain
backward compatibility.

Authorization still hashes and authorizes the source before FFprobe and verifies identity again
after inspection, but this does not provide an absolute exact-byte parser guarantee against a
concurrent same-path mutation. The documented property is: “Authorization completes before parser
invocation, and post-inspection identity verification detects source changes. A concurrent
same-path modification race remains until a stable-input mechanism is implemented.” Public issue
[#11](https://github.com/belagrf/av-atlas/issues/11) evaluates an authorized immutable copy,
copy-on-write/reflink snapshot, stable file-descriptor design, and operator-enforced immutable
storage. The authorized real-media pilot remains pending until a design is accepted or the residual
risk is explicitly accepted.

The focused permission, preflight-sentinel, resume/validation closure, malformed-track, complete
recomputation, valid-track, CLI failure-report, and M2B v1 compatibility tests passed: 75 tests in
13.24 seconds. The complete local gate results were:

```text
uv lock --check
  Resolved 19 packages
uv sync --extra dev --locked --offline
  Resolved 19 packages; checked 18 packages
uv run ruff format --check .
  44 files already formatted
uv run ruff check .
  All checks passed!
uv run mypy src
  Success: no issues found in 21 source files
uv run pytest -q
  140 passed in 61.01s
uv run av-atlas doctor
  exit 0; required CPU/offline dependencies and approved Tesseract 5.3.4 available
```

Fresh ignored M1, M2A, and M2B runs validated with 17, 31, and 68 tracked artifact hashes and zero
errors. The fresh M2B run emitted 13 raw OCR observations and 13 derived temporal tracks. A fresh
interrupted M2B.1 run completed on resume, validated with 28 tracked artifact hashes, and remained
byte-identical on repeated resume. Completed-run and interrupted/repeated-resume aggregate tracked
digests remained respectively
`760bbc33a8ff3883d38d87a4577ea1bf513503154a2318e3e488c2994910b4ea` and
`2760fa06c7e795d7b51f2074430eb40fb511f578556574beeb734d7625656b9f`.
The accepted 64-artifact M2B v1 run, the prior 68-artifact M2B.1 run, and the current 68-artifact
M2B.1 run all validate without rewriting their reports.

Stable hardening hashes remain: raw OCR observations
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`, temporal tracks
`f27d60f51c06cead4d0b6159b47865fd635a010e2faba9902057ae1c9cd4b9c2`, sanitized OCR dependency
inventory `5ab8663ce63b7d6303ce84e3ec62ab3a9dd1ec55283e8f0c6852dd88740d5cce`, and BOM snapshot
`abca366e47275ef2d5ff2825b53b0d47436e03a56e29a696f903cb194d188868`. Runtime-bearing replay
hashes are evaluation `dc228c0d4d844b4e0a8303e55c70aeb787e2e4a36807d8bd06aaf2d5ab04924b`, benchmark
`52207face378c24f1634deb382d5a9f9f7fe774e9955cb2f00c98f536d15a4af`, and run manifest
`b6f2f098a939e177f7126f8f141248da03f313f0b9c750627196e17dcd360792`.

The accepted M2B v1 fixture, gold, configuration, OCR, evaluation, benchmark, run-manifest, and
release-manifest hashes remain exactly
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`,
`e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`,
`8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55`,
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`,
`a1011542165e3b8974857aaee68bbaa8185987cbb3ca0353ad4afecda38803ad`,
`479087002a126b1d442ca2e4d768bafd3e266e9f542dba92a01ea075a3280455`,
`6779769594db6a7457ee30b7d9ffbdacc8ec345120433125e7e846978359b440`, and
`e545855c11ee23542939a35aecf03d00c6f12bbd056d6d4bcae43df139b7c9b2`.

Changed tracked files for this follow-up are README, project state, architecture, governance and
security documentation; CLI, rights, and validation source; and unit/integration regressions for
run-mode closure, parser/subprocess non-invocation, resume/validation closure, and complete OCR-track
derivation. Generated runs remain ignored. No accepted artifact, schema, tag, release, real-media
input, or raw OCR observation changed; no M2C work occurred.

## 2026-07-15 — Post-merge M2B.1 and controlled patch release preparation

PR 10 was squash-merged only after its head was pinned to
`ff6449f0d1d05ab67b622200a3679b1329971616` and CI/CodeQL passed. The reviewed hardening source on
`main` is `4646f40e3c424a569fc8379c37df2fc67f99b7dd`. Issues 7, 8, and 9 closed through the PR;
stable-input security issue 11 remains open. Standalone-inspection governance issue 12 was opened
without choosing between a rights-gated preflight and a narrow read-only exemption. Both issues are
gates for the authorized real-media pilot.

The post-merge local gate passed: lock check (19 packages), locked offline sync (18 checked), Ruff
format over 44 files, Ruff lint, mypy over 21 source files, 140 tests in 55.04 seconds, and doctor.
Fresh ignored M1, M2A, M2B, M2B.1, and inventory-interrupted M2B.1 runs all validated with zero
errors. M1/M2A/M2B validation recorded 17/31/68 artifact hashes; current M2B.1 emitted 13 raw OCR
observations and 13 secondary tracks. Post-merge public clean-checkout CI
`https://github.com/belagrf/av-atlas/actions/runs/29434632938` and CodeQL
`https://github.com/belagrf/av-atlas/actions/runs/29434632160` both succeeded.

The accepted 64-artifact v1 run validates read-only with no report rewrite. Its fixture, gold,
configuration, OCR, evaluation, benchmark, run-manifest, and release-manifest hashes remain
respectively
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`,
`e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`,
`8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55`,
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`,
`a1011542165e3b8974857aaee68bbaa8185987cbb3ca0353ad4afecda38803ad`,
`479087002a126b1d442ca2e4d768bafd3e266e9f542dba92a01ea075a3280455`,
`6779769594db6a7457ee30b7d9ffbdacc8ec345120433125e7e846978359b440`, and
`e545855c11ee23542939a35aecf03d00c6f12bbd056d6d4bcae43df139b7c9b2`.

A separate fresh release-branch replay retained the fixture, gold, configuration, and raw OCR
hashes and added content-stable tracks
`f27d60f51c06cead4d0b6159b47865fd635a010e2faba9902057ae1c9cd4b9c2` and sanitized OCR inventory
`5ab8663ce63b7d6303ce84e3ec62ab3a9dd1ec55283e8f0c6852dd88740d5cce`.
Runtime/software-bearing hashes are evaluation
`b2bc510bfffcda2792bec62069cde2f1701e513e837f1c808525331bcf3bd1f5`, benchmark
`5b5c753ebe93b652f7d29b8f1afcd82911916f16196ebbfef47fe4c16697bea7`, BOM
`abca366e47275ef2d5ff2825b53b0d47436e03a56e29a696f903cb194d188868`, and run manifest
`633c4ed36e477179cd513c8270fc28275b64c6046e6ec2a44645e8a191661781`.
Completed and interrupted/repeated resume comparison digests are
`7b754c8808e578e54905f223569f1a06c410642968ecdab72cfe1ac68980a428` and
`1f22e6ffc956d074a50939c199fbe3a0b55c64b11d26feed503c10a0c5aa754c`;
the corresponding per-file maps remained identical.

The release-branch replay measured exact match 0.75, CER 0.0125, WER
0.07692307692307693, text-presence precision/recall/F1 1/1/1, 13 observations, 13 tracks, zero
unresolved evidence, invalid timestamps, retries, timeouts, or adapter-state errors, 2.584538 wall
seconds, 1.941979 CPU seconds, 180,556 KiB peak single-process RSS, and 1.5476651249747477 frames/s.
The 1/2/4-worker wall times were 1.912063/1.714091/1.557332 seconds and all outputs were semantically
identical. These are four-frame synthetic measurements, not real-media accuracy.

The v1.1 machine-readable release record SHA-256 is
`fbdc8e171811794d37bbdb018179ba736647795ed053d01cada4580fe5d29d73`. The publication manifest
uses a normalized self-entry and its detached final file hash is reported after final rendering to
avoid circular self-reference. The package version remains 0.2.1. No project or data license was
selected; patent/publication review, native-parser sandboxing, stable input, standalone inspection,
non-pilot retained-frame lifecycle, and the double-annotated pilot remain unresolved. No real media was
processed, no model or foundation model was trained, full M2 remains incomplete, and M2C was not
implemented.

The release branch then repeated all prescribed gates on its documentation and release-tooling
tree: 19 packages resolved, 18 checked offline, 44 files formatted, Ruff and mypy clean, 140 tests
passed in 42.39 seconds, and doctor passed. Publication metadata changes do not alter production
processing behavior.

## 2026-07-15 — M2B.2 pre-correction review head (superseded, not accepted)

Issue [#14](https://github.com/belagrf/av-atlas/issues/14) and its approved design review were
implemented on `feat/m2b2-stable-input` at commit
`e60a815ea3214ca403781cd229964a0d67fb17ee`. A later source review rejected this head because native
libavformat transitive resource access was not constrained and controlled-fixture observation
sidecars were not hash/size-bound or read stably. The measurements and hashes in this section are
preserved as evidence of that unaccepted review head and are superseded by the correction section
below; they are not accepted M2B.2 identities. This is an unmerged review increment. Issues 11 and 12
remain open until review and merge; neither accepted tag or release changed. Package version 0.2.2
adds stable-input contract `av-atlas-stable-input/1.0.0`, receipt schema 1.0.0, configuration schema
ID 1.2.0, and `configs/m2b2.yaml`. Rights-manifest schema/vocabulary remains 1.0.0.

The shared service opens a regular non-symlink source, uses `O_NOFOLLOW` where available, streams
SHA-256 through one file descriptor, derives the canonical source ID, and completes fixture or
explicit-rights permission closure before a parser call. It then copies from that descriptor into a
unique 0700 directory/0600 regular file, enforces the configured source and temporary byte ceilings
before and during copying, handles partial writes, hashes while writing, fsyncs, independently
rehashes, and verifies size/hash/source ID plus pre/post descriptor/path identity. It never uses a
hard link. Defaults are 8 GiB for each ceiling and the schema cap is 64 GiB. Unsupported non-POSIX
directory-descriptor/`flock` platforms fail closed.

`run`, `resume`, `inspect`, `inspect-subtitles`, and pilot preparation use that service. FFprobe and
FFmpeg receive only `source.snapshot`; Tesseract receives only snapshot-derived keyframes. Original
source identity remains canonical. Non-fixture inspection requires analysis plus derivative
retention; controlled fixtures auto-authorize only through an exact hash-bound marker. Pilot
preflight authorizes all three sources and pins each rights-manifest checksum before parsing any
source. Source-adjacent sidecars are fixture-only. `inspect --output` is create-only and rejects a
source, hard link, symlink, or existing target before parser invocation.

`stable_input.json` is path-free, manifest-tracked metadata; the snapshot is not an artifact or
evidence. Successful completion is written only after cleanup. Failure, timeout, and handled
interruption clean the lease. Bounded recovery inspects at most 64 candidate names and removes at
most 16 recognized inactive, locked-marker leases per invocation through pinned directory file
descriptors, with deletion fsync ordering and no recursive traversal/symlink following. Resume runs
recovery before persisted-rights failure, then reacquires a fresh snapshot from required `--media`;
one invocation performs only one recovery pass.

Final local gates on the completed source were:

```text
uv lock --check
  Resolved 19 packages
uv sync --extra dev --locked --offline
  Resolved 19 packages; checked 18 packages
uv run ruff format --check .
  47 files already formatted
uv run ruff check .
  All checks passed
uv run mypy src
  Success: no issues found in 22 source files
uv run pytest -q
  199 passed in 66.81s; no skips or failures
uv run av-atlas doctor
  exit 0; FFmpeg/ffprobe and operator-installed Tesseract/English data available
```

Focused authorization, hostile-mutation, stable-input, pilot, inspection, M1/M2A, cleanup,
compatibility, and privacy suites also passed (100 tests in the independent source audit; the final
complete suite above is authoritative). Regressions cover absent/stale/mismatched/expired or
insufficient rights; parser/subprocess zero calls; source mutation/replacement/growth/truncation;
symlinks; byte limits; partial writes; hash mismatch; shell metacharacters; private modes; success,
failure, timeout, and `KeyboardInterrupt` cleanup; live/malformed/unknown/symlink stale entries;
scan/removal bounds; descriptor leaks; crash-consistent deletion order; parent replacement;
unsupported platforms; fresh resume; cleanup failure preventing completion; output collisions;
pilot all-source and checksum linkage; snapshot-only parser arguments; full-run path privacy; and
pre-0.2.2 stable-receipt compatibility.

Fresh ignored controlled commands used new `tests/fixtures/generated/m2b2-final-20260715` and
`runs/m2b2-final-20260715` paths. They regenerated M1, M2A (including edge fixtures, explicit
synthetic rights, inspection, subtitle inspection, and component evaluation), M2B, M2B.1, and
M2B.2; ran OCR evaluation and 1/2/4-worker benchmarks for each OCR baseline; and validated every
run. M1/M2A/M2B/M2B.1/M2B.2 recorded respectively 18/32/69/69/69 artifact hashes and zero errors.
M2B/M2B.1/M2B.2 each emitted 13 immutable raw OCR observations and 13 secondary temporal tracks.
The accepted v1 and v1.1 ignored runs validated read-only with 64 and 68 artifact hashes and zero
errors.

The M2B.2 controlled evaluation measured exact match 0.75, normalized CER 0.0125, normalized WER
0.07692307692307693, text-presence precision/recall/F1 1/1/1, 13 observations, 13 tracks, zero
exact duplicates, temporal repeats, unresolved track evidence, prediction-only/gold-only frames,
invalid timestamps, retries, or timeouts. Wall/CPU/peak RSS/throughput were 1.951492 s, 1.931623 s,
180,556 KiB, and 2.0497142805419646 frames/s. Region precision/recall/IoU remain unsupported because
the frozen gold regions are empty. These are four-frame synthetic engineering measurements, not
real-media OCR accuracy.

The M2B.2 1/2/4-worker wall times were 1.939312/1.695935/1.607338 s; CPU times were
1.919016/1.955704/2.043362 s; peak RSS was 180,556 KiB for each; and throughput was
2.062587553793115/2.35858031584715/2.4885864574906273 frames/s. Every run produced 13 observations,
zero failures/timeouts/retries, identical quality metrics, and accepted semantic output
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`.

Fresh content and artifact hashes are:

- fixture `6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`;
- gold `e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`;
- M2B.2 configuration `9c0d2b71c928912671f10cee3c0b2e0676f2b5e81de7ca68962832ebfb99313b`;
- stable-input schema `f224a23a375d607c2f1afd65693d5af7f5ed3bea4675ac1d6e99f0e30adfc265`;
- configuration schema `142c27bbcc47feb56b736b2e4896725f5dfd676dd2f2d0b25f2a3004fe529ae5`;
- stable-input receipt `206358e83b8dd57de60714fd059aa68f27eb7654e3edc32306f693f715d06232`;
- raw OCR `f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`;
- temporal tracks `f27d60f51c06cead4d0b6159b47865fd635a010e2faba9902057ae1c9cd4b9c2`;
- runtime-bearing evaluation `6c8ce51e4e19591de1798abb29a1888dab9c4ae9d4ec18f8f1a35e9c1a74b06d`;
- runtime-bearing benchmark `29721b2b3d943bdbcaee9fb205c3d1693d804dd80df7fcfe4a34741e5dea221a`;
- sanitized OCR dependency `5ab8663ce63b7d6303ce84e3ec62ab3a9dd1ec55283e8f0c6852dd88740d5cce`;
- unchanged BOM snapshot `abca366e47275ef2d5ff2825b53b0d47436e03a56e29a696f903cb194d188868`;
- runtime-bearing run manifest `a02fe06c14932ba985f9da2cdc61a148617d87a4126941b0f01dd0ea01a72341`;
- quality report `ee0936365cb0574518918e5a9d73826f039519c32a31ca9f709bdeae260b3b9d`.

All files in completed and interrupted runs remained byte-identical after resume and repeated
resume. SHA-256 over the sorted `sha256sum` map of every run file was respectively
`fe480dc540df360147e3b6e62a0560e2ed73961dce4e821e07a77c85c78f585f` and
`2c586d4910eca431afd915414912200d73983c21e82802b92690454b8a6cf2b4`.
A binary-safe scan of every fresh run found no original absolute path, snapshot path/name, private-
root prefix, or private residue. No real operator media was read.

Accepted v1 identities remain fixture/gold/configuration/raw OCR/evaluation/benchmark/run manifest/
release manifest
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`,
`e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`,
`8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55`,
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`,
`a1011542165e3b8974857aaee68bbaa8185987cbb3ca0353ad4afecda38803ad`,
`479087002a126b1d442ca2e4d768bafd3e266e9f542dba92a01ea075a3280455`,
`6779769594db6a7457ee30b7d9ffbdacc8ec345120433125e7e846978359b440`, and
`e545855c11ee23542939a35aecf03d00c6f12bbd056d6d4bcae43df139b7c9b2`.
The v1/v1.1 annotated tag objects and commits remain respectively
`8cadd6c8ecda7d0b6f60421f312c199cbad163e1` /
`54d96dc25bdf03ab1e92d22150c5011faf16b7e6` and
`8be328eef2fd10037b56921aff1f401c3ef3a12e` /
`5d016784c6b3d7226a9f6e0f56cca9fb3ef48822`; v1.1 release-record SHA-256 remains
`fbdc8e171811794d37bbdb018179ba736647795ed053d01cada4580fe5d29d73`.

Changed tracked paths are `.gitignore`, `README.md`, `configs/m2b2.yaml`,
`docs/PROJECT_STATE.md`, `docs/PUBLICATION_READINESS.md`, `docs/PUBLIC_ARTIFACT_POLICY.md`,
`docs/PUBLIC_RELEASE_DECISION.md`, `docs/architecture.md`, `docs/data-governance.md`,
`docs/decisions/ADR-0006-m2b2-stable-authorized-input.md`, `docs/dependency-bom.md`,
`docs/evaluation.md`, `docs/ocr-annotation-guide.md`, `docs/publication-manifest.json`,
`docs/releases/M2B_CONTROLLED_REPRODUCTION.md`, `docs/security.md`, `pyproject.toml`,
`schemas/config.schema.json`, `schemas/stable-input.schema.json`, `src/av_atlas/__init__.py`,
`src/av_atlas/adapters.py`, `src/av_atlas/cli.py`, `src/av_atlas/config.py`,
`src/av_atlas/errors.py`, `src/av_atlas/io.py`, `src/av_atlas/media.py`,
`src/av_atlas/ocr_pilot.py`, `src/av_atlas/pipeline.py`, `src/av_atlas/rights.py`,
`src/av_atlas/schemas.py`, `src/av_atlas/shots.py`, `src/av_atlas/stable_input.py`,
`src/av_atlas/subtitles.py`, `src/av_atlas/validation.py`,
`tests/integration/test_end_to_end.py`, `tests/integration/test_m2a_end_to_end.py`,
`tests/unit/test_initial_authorization.py`, `tests/unit/test_media.py`,
`tests/unit/test_ocr_pilot.py`, `tests/unit/test_rights.py`,
`tests/unit/test_rights_gated_inspection.py`, `tests/unit/test_stable_input.py`, and `uv.lock`.

Remaining limitations are the lack of an OS/native-parser sandbox, protection from a hostile
same-UID process, support for growing/live input and non-POSIX directory-descriptor platforms,
non-pilot retained-frame lifecycle, authenticated rights signatures, trusted fixture-marker
authorship, authorized double-annotated real-media evaluation, and project-license/patent/
publication decisions.
Low-level parser helpers accept ordinary paths; snapshot routing is enforced by supported
orchestration entry points. M2B.2 does not close issues 11/12 on this branch. No pilot, model or
checkpoint download, GPU use, cloud/paid API, training, M2C work, semantic-vision claim, or full-M2
completion occurred.

## 2026-07-15 — M2B.2 source-review correction

PR [#16](https://github.com/belagrf/av-atlas/pull/16) source review found two merge blockers in the
unaccepted `e60a815ea3214ca403781cd229964a0d67fb17ee` head: a verified top-level snapshot did not
prevent libavformat from opening transitive resources, and controlled-fixture observations were
reread from an unbound adjacent path after authorization. Both are corrected on the same unmerged
branch; no prior commit was amended or force-pushed.

Native-input contract `av-atlas-native-input/1.0.0` is fixed in code and recorded by media-
inventory 1.1. Parser-free EBML classification admits only self-contained Matroska/WebM source
snapshots. Every ingest FFprobe/FFmpeg call uses protocol whitelist `file`, format whitelist
`matroska`, and forced `matroska` demuxing; reported formats must be `matroska`/`webm`. Runtime
decode helpers in media inspection, shot sampling/keyframes, subtitle extraction, and pilot frame
extraction reclassify immediately before invocation. Generated OCR frames require PNG magic and a
separate forced/whitelisted `png_pipe` policy. The renderer accepts no arbitrary input options that
could override the policy; its only optional input is a validated nonnegative integer-millisecond
seek. There is no unrestricted retry. HLS, DASH, concat/concatf, image sequences, Blu-ray
navigation, MOV/MP4, unknown formats, and network protocols are rejected before parser start.

Controlled-fixture contract `av-atlas-controlled-fixture/1.1.0` binds the currently supported
observation sidecar by canonical basename, type, payload schema, SHA-256, and size. Marker and
sidecar reads are bounded to 1,000,000 bytes, require a regular final component, use `O_NOFOLLOW`
where available, and compare descriptor/path identity before and after streaming. Hash, declared
size, JSON schema, payload schema, and unique observation IDs are checked before the payload is
converted to immutable `Observation` values. Adapters receive that tuple and have no sidecar path
to reread. Missing, mismatched, replaced, symlinked, malformed, oversized, unlisted, and
concurrently changed data fail closed. Legacy fixture 1.0 remains validation-readable but cannot
authorize fresh adjacent observations.

Stable-input/receipt 1.1 records only path-free sidecar identities. Resume compares the prior
receipt fixture status and persisted fixture manifest with freshly verified authorization before
rewriting the receipt or invoking an adapter. Validly rehashed sidecar changes, marker removal, and
marker addition are rejected with zero run-byte mutation. Bounded recovery accepts known 1.0 and
1.1 lease markers so a pre-correction crash residue is not stranded; unknown versions remain
untouched. Media inventory 1.0, stable-input 1.0, fixture 1.0, and accepted runs without a receipt
remain supported for historical validation.

Exact final local gates were:

```text
uv lock --check
  Resolved 19 packages
uv sync --extra dev --locked --offline
  Resolved 19 packages; checked 18 packages
uv run ruff format --check .
  51 files already formatted
uv run ruff check .
  All checks passed
uv run mypy src
  Success: no issues found in 24 source files
uv run pytest -q
  257 passed in 78.32 seconds; no failures or skips
uv run av-atlas doctor
  exit 0; FFmpeg/ffprobe and operator-installed Tesseract/English data available
```

The focused native-policy, fixture-sidecar, stable-input, media, and rights-gated-inspection suite
passed 108 tests in 13.58 seconds. It includes exact policy arguments and override rejection;
hostile HLS/local-sentinel and DASH/loopback inputs with zero parser calls, zero local access, and
zero HTTP requests; reported-format rejection; no fallback; all decode helpers; PNG preprocessing;
marker/descriptor/hash/size/schema validation; final-symlink and replacement rejection; bounded
reads; mutation/replacement after acquisition; fabricated nonfixture and legacy adjacent sidecars;
resume with stale and validly rehashed changes; fixture linkage appearance/disappearance; and known
legacy lease-marker recovery. All tests used project-authored synthetic bytes and no external
network, GPU, cloud, paid API, checkpoint, or training.

Fresh ignored paths `tests/fixtures/generated/m2b2-source-review-20260715` and
`runs/m2b2-source-review-20260715` regenerated and validated M1, M2A, M2B, M2B.1, M2B.2, and an
interrupted/resumed M2B.2 run. Their validation artifact counts were respectively 18, 32, 69, 69,
69, and 69, with zero errors. The accepted v1 and v1.1 run directories validated read-only with
64/68 artifact hashes and zero errors. Completed resume and interrupted first/repeated resume were
byte-identical; sorted per-file map hashes were
`35ddd603a1ebb41f434b1ad1909159c72cc6d9a7c4149f00a0a9405ef77b5267` and
`45655a65a04b1d1cedd0904c272621c845647d18f0d397e5f19e283a7b84c0fd`.

The corrected four-frame synthetic M2B.2 replay produced 13 raw OCR observations and 13 secondary
tracks. Exact match was 0.75, normalized CER 0.0125, normalized WER
0.07692307692307693, presence precision/recall/F1 1/1/1, and adapter-state correctness true, with
zero exact duplicates, temporal repeats, unresolved evidence, prediction-only/gold-only frames,
invalid timestamps, retries, or timeouts. Wall/CPU/peak RSS/throughput were 2.274976 s, 2.158811 s,
180,800 KiB, and 1.7582600163170818 frames/s. Region metrics remain unsupported because the frozen
gold has empty regions. These are synthetic engineering measurements, not real-media accuracy.

Worker measurements used identical semantic output
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`:

| workers | wall s | CPU s | peak RSS KiB | frames/s | config SHA-256 |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 2.306239 | 2.215062 | 180800 | 1.7344253994287655 | `180266786c33110b4fa2b166fcddcb222f88740638bb932b97bf5e8fbb26b107` |
| 2 | 2.083069 | 2.397710 | 180812 | 1.9202438774254889 | `9edd7622e421e846ed634382034c58aa97c5ed150f91900616c5e3b255de1980` |
| 4 | 1.855219 | 2.302810 | 180812 | 2.1560799980084380 | `c16d806cc51a1dfc0722bd29dba004132026eba0e08011e8475ddbf72c2b0040` |

Fresh corrected content/artifact hashes are:

- frozen fixture `6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`;
- frozen gold `e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`;
- frozen M2B config `8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55`;
- M2B.2 config `9c0d2b71c928912671f10cee3c0b2e0676f2b5e81de7ca68962832ebfb99313b`;
- fixture marker file `4186ed28525803033e4131275d2217c401ef12ab5c16e623f2fdff25c2a373d5`;
- fixture/stable/inventory/native-policy schemas
  `46739bbf84a9eb6ef132e03a6f9c5db8cf85fda61cc4a1869247d10a0e97b7d1`,
  `ea3e581f1095ed48973395802fa88b7208541fd56c5f499be9af5aee7f5a00b1`,
  `7314902422c45448e21662c88190a8d0290e1072856fc5c1306e8cbb694be3b9`, and
  `0a8465c8cba176bbd252ee6d579f3043a21777b1236e6cc4bf38b7fdbeb22834`;
- stable receipt `0af6399765ebe38e982a25bc4af8e1f15b2e2a291d045850420c3a8f39153947`;
- media inventory `91ada0947d3da15c53b8a99076fa3f9841ebad026fcf96ec91da87cde5e7d6d5`;
- raw OCR `f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`;
- temporal tracks `f27d60f51c06cead4d0b6159b47865fd635a010e2faba9902057ae1c9cd4b9c2`;
- runtime-bearing evaluation `2513a30fe0ecb05eb9f2e2912d1e05b43101bfefa5b208d203e95b1f7f0cd998`;
- runtime-bearing benchmark `ec24a0f6707e52ca9a930e84e627f747182e651f673f3030ebe60dd6092ce039`;
- OCR dependency `5ab8663ce63b7d6303ce84e3ec62ab3a9dd1ec55283e8f0c6852dd88740d5cce`;
- BOM `abca366e47275ef2d5ff2825b53b0d47436e03a56e29a696f903cb194d188868`;
- runtime-bearing run manifest `db827b8e53dd548326eae1e00c670ab6e5354ed4bfa00fe374215acd5eee0ad5`;
- quality report `ee0936365cb0574518918e5a9d73826f039519c32a31ca9f709bdeae260b3b9d`.

The nonempty M1 sidecar path separately measured media/sidecar/fixture-marker hashes
`adb97d44f0e819a49473fbd34cc24e52c77f4390d6c09124bc382db7146edea1`,
`4c1be7d7de62e5066282e7e90ad677aa40dd8cf2bdd2aca13b1c92bbcfc68387`, and
`a3910126d279803f2cd78ba52fd2c5f7ee8a7a64604481753d9b541a66d7374b`.
Its stable receipt repeats the descriptor and hashes to
`87e89652efcd3f5acb68d5a5a9d8a923f9c626053a7e417298e799d36d0aaf40`;
its unchanged eight-observation final ledger hashes to
`23882d0c1078b2da9f43098d3d487878111b8a92e58e6efd6b532ea9db477d25`.

The immutable accepted v1 fixture/gold/config/raw OCR/evaluation/benchmark/run/release hashes remain
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`,
`e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`,
`8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55`,
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`,
`a1011542165e3b8974857aaee68bbaa8185987cbb3ca0353ad4afecda38803ad`,
`479087002a126b1d442ca2e4d768bafd3e266e9f542dba92a01ea075a3280455`,
`6779769594db6a7457ee30b7d9ffbdacc8ec345120433125e7e846978359b440`, and
`e545855c11ee23542939a35aecf03d00c6f12bbd056d6d4bcae43df139b7c9b2`.
The v1/v1.1 tag objects and commits remain
`8cadd6c8ecda7d0b6f60421f312c199cbad163e1` / `54d96dc25bdf03ab1e92d22150c5011faf16b7e6`
and `8be328eef2fd10037b56921aff1f401c3ef3a12e` /
`5d016784c6b3d7226a9f6e0f56cca9fb3ef48822`; the v1.1 release-record hash remains
`fbdc8e171811794d37bbdb018179ba736647795ed053d01cada4580fe5d29d73`.

The follow-up changes 42 tracked paths after the publication manifest is regenerated: README and
12 engineering/governance/reproduction/state documents; fixture, inventory, stable-input, and new
native-policy schemas; 14 source modules including new `fixture_inputs.py` and `native_media.py`;
and 10 integration/unit test modules including new fixture-sidecar and native-policy suites. The
machine-readable manifest is rendered last to avoid circular content claims; its detached file
hash is reported in the PR update rather than embedded in a file that it hashes.

A binary-safe fresh-run scan found zero original home path, snapshot name, private-root prefix,
credential pattern, symlink, or residual lease. No real media was read. Snapshot unlink and lease
removal are logical lifecycle cleanup, not secure erasure; the default temporary root can be disk-
backed, journaled, snapshotted, swapped, or backed up. Before real media, an operator-selected
private capacity-bounded encrypted volume or suitably configured tmpfs, or explicit remanence-risk
acceptance, remains required. The strict allowlist is not an OS/native-parser sandbox. Same-UID
hostility, authenticated fixture/rights signatures, non-pilot retained-frame lifecycle, growing/
live and non-Matroska input, non-POSIX support, project license/patent/publication decisions, and the
double-annotated pilot remain unresolved. Issues 11, 12, and 14 stay open. No pilot, M2C, model,
checkpoint, GPU, cloud/paid API, training, tag, release, or merge occurred.

## 2026-07-16 — M2B.2 explicit fixture-trust correction (PR #16 follow-up)

Source review confirmed one remaining authorization bypass at review head
`c94280b3cbbfc6bff68388c4bebd419e173bdb71`: `authorize_source_identity()` treated a
caller-constructed adjacent fixture marker as a rights-free credential and also admitted its bound
observations under ordinary explicit rights. A controlled reproduction used only temporary
synthetic EBML-prefixed bytes and produced `authorized_controlled_fixture` plus the forged
observation. No native parser or real media was needed to demonstrate the defect.

Fresh execution now always requires an explicit source-bound rights manifest. Trust is derived only
from the validated rights basis: `synthetic-controlled-explicit-rights` requires an exact current
fixture 1.1 bundle, while `ordinary-explicit-rights` covers owned, licensed, public-domain, and
other documented authorization and never opens adjacent fixture metadata. Legacy fixture 1.0
markers remain validation-only. Marker and rights self-hashes remain integrity checks, not
authenticated signatures or legal determinations.

The new additive contracts are stable-input `av-atlas-stable-input/1.2.0` / schema 1.2.0 and
run-manifest schema 1.1.0. They persist rights basis/checksum, explicit trust mode, nullable exact
fixture checksum/contract, fixture status, and sidecar bindings. Resume re-derives and compares the
same decision before receipt replacement or adapter work. Validation rejects impossible ordinary/
controlled combinations while retaining read-only support for stable-input 1.0/1.1 and run-
manifest 1.0. The rights-manifest 1.0 and fixture-manifest 1.1 vocabularies did not change.

Regression coverage includes forged 1.0 marker/no rights, forged 1.1 marker+sidecar/no rights,
ordinary-rights bundle isolation with zero admitted observations, explicit synthetic exact-bundle
success, missing/legacy/mismatched bundle denial, parser/subprocess zero-call assertions, ordinary
and controlled resume transition denial, ordinary resume ignoring newly adjacent fixture data,
impossible-state validation, current-software schema-downgrade denial, and historical run-manifest/
read-only compatibility. Current controlled inspection also requires explicit synthetic rights. The
complete local suite measured **272 passed,
zero failed, zero skipped**. Locked offline sync, lock check, Ruff formatting/lint, mypy over 24
source files, schema checks, and doctor passed. No dependency was installed or downloaded.

A fresh ignored offline replay was created at
`tests/fixtures/generated/m2b2-explicit-trust-20260716` and
`runs/m2b2-explicit-trust-20260716`. M1, M2A, M2B, M2B.1, M2B.2, and interrupted/resumed M2B.2
validated with 18/32/69/69/69/69 artifact hashes and zero errors. The accepted v1 and v1.1 local
runs validated read-only with 64 and 68 artifact hashes and zero errors. Completed resume and
interrupted-then-repeated resume were byte-identical across all run files; their sorted hash-map
SHA-256 values were `bfb50494993782df1503819cbc14f809a63daad8a8538e14cbfbafdb06f291a0`
and `d41ee232884427d7fe48392bf87cf74241cdf06067705ca70536294789628539`.

The fresh four-frame M2B.2 replay preserved fixture/gold/raw OCR identities and produced 13 raw OCR
observations plus 13 secondary temporal tracks. Measured synthetic-only results were exact match
0.75, normalized CER 0.0125, normalized WER 0.07692307692307693, text-presence precision/recall/F1
1.0/1.0/1.0, zero duplicates, zero missing evidence, zero invalid timestamps, zero retries/timeouts,
wall 3.986374 s, CPU 2.982820 s, peak RSS 180544 KiB, and 1.003418 frames/s. Region metrics remain
unsupported because the frozen gold has no regions. Worker 1/2/4 measurements were respectively:
wall 1.991857/1.683649/1.547342 s; CPU 1.944992/1.937929/1.939354 s; peak RSS
180668/180668/180672 KiB; and 2.008176/2.375792/2.585078 frames/s. Every worker produced 13
observations, identical semantic hash
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`, and zero failures,
retries, or timeouts. These are synthetic engineering measurements, not real-media accuracy.

Fresh content/runtime identities are:

- fixture media `6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`;
- fixture marker file `4186ed28525803033e4131275d2217c401ef12ab5c16e623f2fdff25c2a373d5`
  and bound manifest checksum `001dd0b0a755a780434ea621616392a18abbadf9085317dda6d5915f644205ad`;
- frozen gold `e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`;
- M2B.2 configuration `9c0d2b71c928912671f10cee3c0b2e0676f2b5e81de7ca68962832ebfb99313b`;
- fixture/stable/run/native schema files
  `46739bbf84a9eb6ef132e03a6f9c5db8cf85fda61cc4a1869247d10a0e97b7d1`,
  `4e2fa84f9ae59602a85cd00cbc7b03884abd8b24f9aae3827a80ce77cc739252`,
  `b2df807a219837f9f27ff9a916c9c5356ce78be25c81a4fe548eafeda21c171d`, and
  `0a8465c8cba176bbd252ee6d579f3043a21777b1236e6cc4bf38b7fdbeb22834`;
- stable receipt `d05948457f0fac0159f5273b264d583abda41e7b37a2c03cf1e33a990733a0c0`;
- inventory `91ada0947d3da15c53b8a99076fa3f9841ebad026fcf96ec91da87cde5e7d6d5`;
- raw OCR `f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`;
- temporal tracks `f27d60f51c06cead4d0b6159b47865fd635a010e2faba9902057ae1c9cd4b9c2`;
- runtime-bearing evaluation/benchmark
  `914063061ee4195cc25f4b36f0f33c2e7151a54eb188fe269b95de7f1ebaefce` and
  `bcd31fd6ceb8816dee455681c89c0e6bc60c212347d18766cf8900fb5d3e57ff`;
- OCR dependency/BOM `5ab8663ce63b7d6303ce84e3ec62ab3a9dd1ec55283e8f0c6852dd88740d5cce`
  and `abca366e47275ef2d5ff2825b53b0d47436e03a56e29a696f903cb194d188868`;
- runtime-bearing run manifest `fe112702883b2dcc693c4c5a6d4a38190bdfa3b96cc90b8cf162eee94822aab8`;
- quality report `ee0936365cb0574518918e5a9d73826f039519c32a31ca9f709bdeae260b3b9d`.

The immutable accepted v1 fixture/gold/config/raw OCR/evaluation/benchmark/run/release hashes remain
`6d1f79c6…82a8`, `e62e392a…bc1a`, `8f5545df…5c55`, `f851aef0…6060`,
`a1011542…3ad`, `47908700…455`, `67797695…440`, and `e545855c…9b2`. Tag objects/commits remain
`8cadd6c8ecda7d0b6f60421f312c199cbad163e1` /
`54d96dc25bdf03ab1e92d22150c5011faf16b7e6` and
`8be328eef2fd10037b56921aff1f401c3ef3a12e` /
`5d016784c6b3d7226a9f6e0f56cca9fb3ef48822`. No accepted fixture, gold, configuration, artifact,
tag, or release changed.

Issues 11, 12, and 14 remain open and PR 16 remains unmerged with `needs-work` pending source
review. Residual limitations remain the strict allowlist without an OS/native-parser sandbox,
same-UID hostility, logical-not-secure erasure, temporary-root policy, authenticated rights/
fixture signatures, non-pilot retained-frame lifecycle, non-Matroska/live input, the authorized
real-media pilot, and project license/patent/publication decisions. No real media, M2C, model/
checkpoint, GPU, cloud/paid API, training, tag, release, or merge occurred.

## 2026-07-16 — M2B.2 controlled baseline v1.2 release record

The reviewed M2B.2 implementation merged at source commit
`2555a297153c9b5ff059b7d8dc7e49de5d93c43b`, tree
`f8ca95eab8c1988cee00ab774a2bf30f5cad1776`, package version `0.2.2`. This documentation/manifests-
only commit is the intended immutable v1.2 release record and changes no runtime, schema,
configuration, test, lock, workflow, fixture, or accepted evidence bytes. It adds
`docs/releases/M2B_CONTROLLED_BASELINE_V1_2.md` and `.json` and updates `README.md`, this state
record, the controlled reproduction guide, publication readiness/release-decision records, data
governance, security, ADR-0006 status, and the publication manifest. Final annotated-tag, GitHub-
release, and post-merge check identities are recorded externally rather than predicted here.

The frozen scope is four synthetic frames, 13 immutable raw OCR observations, and 13 secondary
temporal tracks. Every fresh source and inspection now requires explicit source-bound rights.
Stable-input 1.2 creates a verified bounded private `0600` copy under a unique `0700` lease,
exports neither source nor snapshot path, and removes the snapshot before successful completion.
Run-manifest 1.1 persists rights basis/checksum and declaration-derived
`ordinary-explicit-rights` or `synthetic-controlled-explicit-rights` linkage. Only the latter plus
the exact current fixture 1.1 bundle admits hash/size-bound immutable observation sidecars.
Legacy markers remain validation-compatible but authorize no fresh execution. The rights and
marker self-hashes are integrity checks, not authenticated signatures.

Native-input contract `av-atlas-native-input/1.0.0` accepts parser-free-classified,
self-contained Matroska/WebM only; it forces the `matroska` demuxer, `matroska` format whitelist,
and `file` protocol whitelist and denies manifest/multi-resource and network-capable formats before
native parsing. Generated keyframes use the separate forced `png_pipe` policy. The policy limits
transitive access but is not an OS sandbox.

### Exact release-record verification

Commands executed from the repository root were:

```text
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c release/m2b-controlled-v1.2
uv lock --check
uv sync --extra dev --locked --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run av-atlas doctor
uv run av-atlas make-fixture --profile m1 --output FRESH_M1_FIXTURES
uv run av-atlas make-fixture --profile m2a --include-edge-fixtures --output FRESH_M2A_FIXTURES
uv run av-atlas make-fixture --profile m2b --output FRESH_M2B_FIXTURES
uv run av-atlas make-rights MEDIA --output RIGHTS --operator-id controlled-v12-replay \
  --basis synthetic-controlled --allow analysis --allow evaluation \
  --allow derivative_artifact_retention
uv run av-atlas inspect MEDIA --rights-manifest RIGHTS --output INVENTORY
uv run av-atlas inspect-subtitles MEDIA --rights-manifest RIGHTS
uv run av-atlas run MEDIA --config CONFIG --rights-manifest RIGHTS \
  --operation analysis --output FRESH_RUN
uv run av-atlas export FRESH_RUN
uv run av-atlas evaluate FRESH_M2A_RUN tests/gold/m2a-controlled.gold.json --tolerance-ms 200
uv run av-atlas evaluate-ocr FRESH_OCR_RUN tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas benchmark-ocr FRESH_OCR_RUN tests/gold/m2b-ocr-controlled.gold.json
uv run av-atlas validate FRESH_RUN
uv run av-atlas run MEDIA --config configs/m2b2.yaml --rights-manifest RIGHTS \
  --operation analysis --output INTERRUPTED_RUN --stop-after inventory
uv run av-atlas resume RUN --media MEDIA
```

The last resume and validation commands were repeated twice for both completed and interrupted
M2B.2. The final full test gate passed 272/272 with zero failures and zero skips; Ruff format checked 51
files, Ruff lint passed, mypy passed over 24 source files, and doctor passed. Locked offline sync
resolved 19 and checked 18 packages. The installed controlled host reported uv 0.11.28, CPython
3.14.3, Linux 6.8.0-134-generic x86_64, FFmpeg/ffprobe 6.1.1-3ubuntu5, Tesseract 5.3.4,
Leptonica 1.82.0, and approved English tessdata hash
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. The replay used no
network, GPU, cloud inference, paid API, model/checkpoint download, or training.

Fresh ignored M1, M2A, M2B, M2B.1, M2B.2, and inventory-interrupted/resumed M2B.2 runs validated
with `18 / 32 / 69 / 69 / 69 / 69` artifact hashes and zero errors. Accepted v1 and v1.1 evidence
validated read-only with 64 and 68 artifact hashes and zero errors. Completed first/repeated resume
preserved all 72 run files and all 69 manifest artifacts; the full and manifest map hashes were
`26ea7690b24db7c775e238392005b6515b5dcaf5527b893471b58d1a9afff93f` and
`6d7fcfae81203be355c15b9ee376da6a286829f6389885a3f1f0b564ce40ec1f`.
Interrupted completion and repeated resume were also byte-identical. The interrupted all-files map
hash was `327554fade972edf5714d85f66558008f547215ab720f8074f21eb853ee74d57`;
the interrupted manifest-artifact map hash was
`d112c327564be1c58a80a318cb8fabf0bf91eadbd5b4891e3f762c54f5c8082e`.

### Fresh replay hashes and measurements

Frozen input/contract identities are fixture
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`, fixture marker
`4186ed28525803033e4131275d2217c401ef12ab5c16e623f2fdff25c2a373d5` with inner checksum
`001dd0b0a755a780434ea621616392a18abbadf9085317dda6d5915f644205ad`, gold
`e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`, M2B.2 config
`9c0d2b71c928912671f10cee3c0b2e0676f2b5e81de7ca68962832ebfb99313b`. Raw OCR
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060` and temporal tracks
`f27d60f51c06cead4d0b6159b47865fd635a010e2faba9902057ae1c9cd4b9c2` are stable on the recorded
software/dependency set. The FFprobe/software-bound inventory is
`91ada0947d3da15c53b8a99076fa3f9841ebad026fcf96ec91da87cde5e7d6d5`; the sanitized host/package
OCR dependency inventory is `5ab8663ce63b7d6303ce84e3ec62ab3a9dd1ec55283e8f0c6852dd88740d5cce`.

Fresh runtime/execution-bearing identities are stable receipt
`5f7019bf07b012e87ff44c7f9368b24ae04c49f905307388729955f1c5b07a3c`, evaluation
`d82c56376cdcbd8c2eaeb273aac63af4706500530d393d0711f028019fe0c3e2`, benchmark
`27f1e68189ed5ba06f1d30cf406f0c61be4c17701e75270e7721edab4aa9053c`, BOM
`abca366e47275ef2d5ff2825b53b0d47436e03a56e29a696f903cb194d188868`, run manifest
`543f7ba9fe4a9f20f0301b04a675d55bfa22c061700658e4b3577e0d23fa4f77`, and quality report
`ee0936365cb0574518918e5a9d73826f039519c32a31ca9f709bdeae260b3b9d`.

Measured synthetic-only OCR remained exact match 0.75, normalized CER 0.0125, normalized WER
0.07692307692307693, text-presence precision/recall/F1 1.0/1.0/1.0, zero duplicate/missing-
evidence/invalid-timestamp/retry/timeout counts, wall 2.104130 s, CPU 2.057794 s, peak RSS 180796
KiB, and 1.9010231661 frames/s. Region metrics remain unsupported because the frozen gold has no
regions. Worker 1/2/4 wall times were 2.094113/1.816275/1.756431 s; CPU
2.068903/2.091952/2.187848 s; peak RSS 180800 KiB each; and throughput
1.9101169485/2.2023091970/2.2773452216 frames/s. All produced the identical 13-observation semantic
hash and zero failures/retries/timeouts.

The exact implementation commit passed main CI at
`https://github.com/belagrf/av-atlas/actions/runs/29486707488` and CodeQL at
`https://github.com/belagrf/av-atlas/actions/runs/29486706995`. Release-PR and post-merge check
identities are recorded externally. Publication-manifest and release-record detached hashes are
rendered and reported only after every tracked record is final, avoiding circular claims.

### Compatibility, publication, and remaining limits

Immutable v1/v1.1 tag object and commit pairs remain
`8cadd6c8ecda7d0b6f60421f312c199cbad163e1` /
`54d96dc25bdf03ab1e92d22150c5011faf16b7e6` and
`8be328eef2fd10037b56921aff1f401c3ef3a12e` /
`5d016784c6b3d7226a9f6e0f56cca9fb3ef48822`. The accepted v1
fixture/gold/config/raw-OCR/evaluation/benchmark/run/release hashes remain
`6d1f79c6…82a8`, `e62e392a…bc1a`, `8f5545df…5c55`, `f851aef0…6060`,
`a1011542…3ad`, `47908700…455`, `67797695…440`, and `e545855c…9b2`; the v1.1 release JSON remains
`fbdc8e171811794d37bbdb018179ba736647795ed053d01cada4580fe5d29d73`.

The release candidate includes no generated fixture media, run, source/snapshot path, private
rights declaration, annotation, traineddata, checkpoint, weight, archive, or credential. Issue 17
remains the security/temporary-root gate before real media. Snapshot deletion is logical rather
than secure; native parsers lack an OS sandbox; same-UID hostility, non-Matroska and live input,
non-POSIX support, non-pilot retained-frame lifecycle, authenticated rights signatures, license
selection, patent/publication review, the double-annotated pilot, full M2, and M2C remain
unresolved. No real media, pilot, M2C, model, checkpoint, training, tag, or release was processed or
created.

## 2026-07-16 — M2B.3 private storage and sandboxed pilot execution

**Historical pre-source-review record; superseded by “M2B.3 source-review boundary corrections”
below.** The 1.0 contracts, original profile, test count, replay measurements, and hashes in this
section document the earlier review head and are not the current PR result. They are retained for
review history and must not be used as current reproduction targets.

Implementation branch `feat/m2b3-pilot-security` adds the local-private policy and mandatory
Bubblewrap execution boundary accepted in issue 17. Package version is `0.2.3`. The engineering
implementation and actual project-authored synthetic execution passed locally; at that historical
review head, issue 17 was open and M2B.3 acceptance awaited source review. No real or
operator-supplied media was processed.

### Contracts, policy, and lifecycle

The new contracts are:

- local-private policy schema/contract `1.0.0` /
  `av-atlas-pilot-security-policy/1.0.0`;
- sanitized receipt schema/contract `1.0.0` /
  `av-atlas-pilot-security-receipt/1.0.0`;
- synthetic security report schema/contract `1.0.0` /
  `av-atlas-m2b3-synthetic-pilot/1.0.0`;
- Bubblewrap profile `av-atlas-bubblewrap-pilot/1.0.0`; and
- additive OCR pilot-manifest `1.1.0`, while historical manifest `1.0.0` remains validation-only.

The private policy is self-hash checked, mode `0600`, expiry bound, and linked to an exact pilot ID
and pilot-spec hash/size. It alone contains the private root path and must use the ignored
`*.pilot-security-policy.local.json` name. The root must be an explicitly selected pre-created
absolute directory outside the tracked checkout, current-UID-owned, a real non-symlink local
directory with mode `0700`, and identical in device/inode/filesystem identity to the policy. The
admission check verifies adequate capacity for source and temporary ceilings plus reserve before
new work. Root identity is retained by descriptor; lease creation, bounded marker-aware recovery,
and cleanup are relative to it. Cleanup remains available when free capacity later drops. Cleanup
is logical unlink and directory removal, not cryptographic erasure; tmpfs may swap. Reviewed
encrypted-volume and remanence-acceptance choices are explicit expiring reviewer assertions, not
cryptographic claims by AV-Atlas.

The supported pilot path has no unsandboxed fallback. A changed or unavailable Bubblewrap binary,
failed namespace smoke test, changed profile, invalid root or policy, linkage failure, or resource
admission failure stops before FFprobe, FFmpeg, Tesseract, or another native adapter starts. Policy
scope/expiry and root identity are rechecked at source-unit boundaries. Pilot resume reacquires a
fresh stable snapshot. Success, handled failure, timeout, and handled interruption clean the
private work lease; bounded stale recovery never follows symlinks or recursively removes an
unrecognized directory. `SIGKILL`, power loss, and same-UID hostile processes remain limitations.

The typed native runner verifies the exact executable file descriptor, hash, size, dependency
identity, and profile before use. It creates user/PID/IPC/UTS/network/mount namespaces, a new
session, parent-death behavior, drops all capabilities, clears the environment, exposes no home,
read-only binds only reviewed runtime/input paths, makes only `/work` host-backed and writable,
uses a private tmpfs `/tmp`, and never binds the whole host root. A helper sets `umask(077)` and
resource limits before `exec`, without multithreaded `preexec_fn`. The recorded bounds were wall
30 s, CPU 30 s, address space 2 GiB, output file 256 MiB, 64 open descriptors, 4,096 processes,
8 MiB each for stdout/stderr capture, core dump zero, and one-second cleanup escalation. Process-
group termination covers timeout and handled interruption.

The sanitized receipt contains no original/snapshot/root path, user, hostname, secret, or raw
environment value. Pilot manifest `1.1.0` binds policy and receipt digests, storage decision,
sandbox identity/profile, limits, source/spec linkage, denial/privacy booleans, and cleanup outcome.
Rights records and frames remain local-private. The public metadata validator rejects absolute
paths and secret-like values. Raw media text remains inert untrusted data.

### Measured approved dependency and synthetic execution

The locally packaged executable was installed by the operator before this work. Codex installed
nothing. Measured inventory:

- basename/version/package/source: `bwrap`, `bubblewrap 0.9.0`,
  `bubblewrap:amd64 0.9.0-1ubuntu0.1`, source `bubblewrap 0.9.0-1ubuntu0.1`;
- executable SHA-256/size:
  `52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712`, 72,160 bytes;
- installed-package license metadata: `LGPL-2+`, read from the installed copyright record whose
  SHA-256 is `229a402fddba5c81005950f28de162359383cba731f5b859b8f82a03c338bf01`;
- profile SHA-256:
  `b69562979857a6c33d59d7db88ce8a14a7ceaa46504539284edc86d0d0e07a0a`;
- dependency identity SHA-256:
  `85905bce616b6f7327efca1c7196f4758752561a0c41bca23401c1fee4ece3f2`; and
- Linux namespace/capability smoke test: passed. If absent on this detected Ubuntu family, the
  operator command is `sudo apt-get install bubblewrap`; it was not run.

The fresh ignored synthetic check used the unchanged four-frame M2B source hash
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`
and a 224-byte pilot spec with SHA-256
`e315d7ff3d881e37aba46166e2264570fa3fd4763c2ffaff7e0d10f727fcccac`.
An explicitly selected verified tmpfs root passed identity, ownership, mode, local-filesystem and
capacity checks; its path is intentionally absent from public records. The private policy hash was
`e20fd210dc342dc278342901a4b93af069de2368a1b15c2dc209c1b87d720ba1`.
The exact sandbox path ran FFprobe, FFmpeg, and Tesseract. It processed one extracted synthetic
frame and emitted three OCR observations. Measured wall time was 2.9919315020088106 s, CPU time
2.184933 s, peak child RSS 180,672 KiB, source/frame sizes 2,401,427/5,250 bytes, and retries/
timeouts were 0/0.

Actual hostile probes measured `network_denied=true`, including loopback against a reachable local
listener; `external_sentinel_denied=true`; and `outside_write_denied=true`. The parent first created
and wrote a host-writable outside positive-control file; the sandbox could not alter it and cleanup
removed it. Root/device and other host-backed writes outside `/work` failed, while only the private
sandbox-local `/tmp` remained writable as designed. The UTS hostname was fixed to the reviewed
non-host value. The private root was empty after completion. Public-artifact scans found no private
path, source/frame derivative, raw environment, username, hostname, or secret.

Fresh M2B.3 artifact identities are:

- policy/receipt/report schemas:
  `c4d64903f8627c19796b38e945e95dfb20f6d61d29ad62a46457cb9a47636e28`,
  `fd70d41ea55e49d9467e3bcbf30d5bb8e9412210fa0d73ddded4f1a97f88ea64`, and
  `f94bbc9c3bc4e425ce2b815d70fdf877e1993bd37bc934fe79dfe70a61084e38`;
- pilot manifest schema:
  `6822218a7e67d72b0aaab41035d3dbac84d5939d9be50836efe6c7c613afd164`;
- sanitized receipt detached/embedded hashes:
  `183417dfe996e23b3a937320850cc2f82bfe814fa5d4a90ceef0790b18326a33` /
  `9b922948c2fc776370794c888911f1013d06564160a44d74b03feb053168a3ef`;
- synthetic security report detached/embedded hashes:
  `31476516be06d60a30e85d56927cab44ff7609d0b90ff78dde2ba5e8a7710cd2` /
  `d7bfe3e84f04ff54f32ff8e1752bf49d7a92a13b85680e7abe95f4bb5e77af6b`;
- sandboxed OCR dependency inventory:
  `ab20ef53a2039d191460b0b19fe306c710107735cc5370c0edee7c07b7ffdb12`; and
- sandboxed raw OCR observations:
  `7f3c10085a9e3e80289e925b0121d4aa673eaeab495517e8f2879b1627da805e`.

The policy, receipt and report carry timestamps/capacity/runtime measurements and are fresh-run
identities, not cross-host byte-stability promises. The source, pilot spec, schema, executable and
profile identities are content-stable for the measured inputs and implementation.

### Commands, regressions, and compatibility

The exact final gate commands were the six commands in “Final environment and quality gates”
above. Additional execution included `inspect-bubblewrap`, `pilot-security-create`,
`pilot-security-inspect`, `pilot-security-validate`, `pilot-security-synthetic-check`, schema and
artifact validation, fresh `make-fixture`/`make-rights`/`run`/`evaluate`/`evaluate-ocr`/
`benchmark-ocr`/`validate` sequences for M1, M2A, M2B, M2B.1 and M2B.2, interruption, resume, and
repeated resume. All fresh controlled runs validated with zero errors: artifact-hash counts were
18 (M1), 32 (M2A), and 69 each for M2B, M2B.1, M2B.2, and interrupted/resumed M2B.2. Completed and
interrupted/repeated-resume full-file maps remained byte-identical; their final canonical map
SHA-256 values were `0252a38707d10081e7749f6e6a2dbd7af2805fc1beffe1dd2474a7fd26f1b7ee`
and `8f4b1ca22169e1745b809ad4038267ff92936ac8f9eaf63ed7f6754f14e8127d`.

Read-only validation of accepted v1, v1.1, and v1.2 evidence passed with zero errors and 64, 68,
and 69 artifact hashes. Immutable tag object/commit pairs remain:

- v1: `8cadd6c8ecda7d0b6f60421f312c199cbad163e1` /
  `54d96dc25bdf03ab1e92d22150c5011faf16b7e6`;
- v1.1: `8be328eef2fd10037b56921aff1f401c3ef3a12e` /
  `5d016784c6b3d7226a9f6e0f56cca9fb3ef48822`; and
- v1.2: `5427bb4639d94f0311d49f5ef8be9337fdcad167` /
  `c24ff0c9dacb1d3e42cfe8e48e31ec866ab9a882`.

The accepted v1 fixture/gold/config/raw-OCR/evaluation/benchmark/run/release hashes remain
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`,
`e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a`,
`8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55`,
`f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`,
`a1011542165e3b8974857aaee68bbaa8185987cbb3ca0353ad4afecda38803ad`,
`479087002a126b1d442ca2e4d768bafd3e266e9f542dba92a01ea075a3280455`,
`6779769594db6a7457ee30b7d9ffbdacc8ec345120433125e7e846978359b440`, and
`e545855c11ee23542939a35aecf03d00c6f12bbd056d6d4bcae43df139b7c9b2`.
The v1.1/v1.2 release-record JSON hashes remain
`fbdc8e171811794d37bbdb018179ba736647795ed053d01cada4580fe5d29d73` and
`da8ef265124bded29c389fe0eb35d16b0c08aa67d778eea3ebf8465c8a5b71bd`.

Changed tracked files comprise the version bump/lock; three policy/receipt/report schemas and the
additive pilot-manifest schema; the schema registry; central native helper/runner and pilot-
security modules; pilot, media, stable-input, shot, subtitle, OCR and adapter integration; CLI;
README, architecture, governance, security, evaluation, OCR guide, BOM, publication controls,
ADR-0007, project state and publication manifest; plus contract, unit and integration regressions.
Generated fixtures, private policies, rights files, run directories and measured media derivatives
remain ignored and are not publication candidates.

The 337-test local suite includes missing/stale/wrong-link policy zero-native-call paths; root
symlink/replacement/owner/mode/device/inode/remote/capacity cases; changed/unavailable Bubblewrap
and failed namespace/profile checks; host-writable positive-control, sentinel/read/write/network/
environment/home/hostname isolation; replacement after work-fd acquisition; per-native-unit policy,
review-expiry and root checks; CPU, memory, file-size, process, descriptor, capture, core and wall-
time limits; timeout/interruption/process-tree cleanup; stale recovery; policy/prepare/run
transitions; sandbox bypass prevention; strict pilot-manifest linkage; absolute-path/secret scans;
and accepted-release compatibility.

Remaining limits at that superseded review head were source review and merge, same-UID host
hostility, `SIGKILL`/power-loss recovery, logical rather than secure deletion, possible tmpfs swap,
operator-asserted encrypted storage, Linux/Bubblewrap portability, native-parser residual
vulnerability, non-pilot retained-frame lifecycle, authenticated rights signatures, real
independent annotations and adjudication, license
selection, patent/publication review, ASR/alignment, diarization, acoustic events, semantic visual
perception, direct-VLM comparison, full M2, and M2C. No model/checkpoint was downloaded, no GPU,
cloud or paid API was used, no training occurred, no tag/release was created or moved, and no real-
media pilot or M2C work began.

## 2026-07-16 — M2B.3 source-review boundary corrections

The `feat/m2b3-pilot-security` correction implements the four reviewed private-storage and
sandboxed pilot-security boundaries. It processed only the unchanged
project-authored synthetic M2B fixture. No real media, independent human annotation, M2C work,
model/checkpoint, GPU, cloud inference, paid API, training, license decision, tag, or release was
introduced.

The measurements, test count, and runtime-bearing hashes in this correction section are measured
local replay values. Final merge, issue, CI, and CodeQL identities are verified externally; these
local values are not a real-media pilot-completion claim.

### Corrected contracts

- Policy and sanitized receipt are additive schema/contract `1.1.0`; their historical 1.0 forms
  remain read-only validation compatible. The private policy now binds distinct transient and
  retained roots, separately bounded capacity decisions, and a required pilot-scoped, expiring
  reviewer pseudonym for every reviewed storage decision. The public receipt deliberately omits
  the pseudonym and all absolute private paths. A policy or receipt self-hash is an integrity
  checksum, not an authenticated signature.
- Pilot manifest `1.2.0` adds retained-storage identity and Bubblewrap profile 1.1 facts while
  preserving validation of manifests 1.0 and 1.1. New execution requires the current contract.
- Synthetic security reports are current contract
  `av-atlas-m2b3-synthetic-pilot/1.1.0`; report 1.0 remains read-only validation compatible and
  cannot authorize current execution.
- Bubblewrap profile `av-atlas-bubblewrap-pilot/1.1.0` has SHA-256
  `18ba5b8e06291138310fa45d040c5930bcbc5c705ac4c2a7018398114b0be2ad`. It exposes only
  `/usr/bin`, `/usr/lib`, optional `/usr/lib64`, `/usr/share/tesseract-ocr`, and optional
  `/etc/alternatives`; `/usr/local`, `/usr/src`, `/usr/include`, `/usr/share/doc`, and
  `/usr/share/man` are masked or unexposed. Inputs, policies, transient/retained roots, and outputs
  that overlap exposed host runtime mounts fail before native execution. The profile-bound
  Bubblewrap dependency identity is
  `f75d9e08d32eaad33de98592ee0f603a19539768f3e5381b8a0b31e3c1f6c94e`.
  The profile SHA-256 binds its declarative arguments, mounts, masks, and fixed tool paths; it does
  not independently bind the Python overlap-check or runner-enforcement code, which is covered by
  the reviewed source commit and regressions.
- OCR output package `av-atlas-pilot-ocr-output/1.0.0` is a fixed six-file package. Its manifest
  binds the frozen pilot file and embedded hash, pilot/spec/source-set and rights identities,
  policy, prepared and `ocr-complete` receipts, OCR configuration, sanitized dependency,
  observations, evidence index, runtime, counts, and semantic output. The completion receipt binds
  the pre-receipt output digest and the manifest is written last. Evaluation accepts this package,
  recomputes every relationship, and rejects missing, modified, swapped, wrong-stage,
  cross-policy, or cross-pilot content before metrics.
- Retained prepared pilots, annotation packages, OCR packages, and evaluation outputs are direct
  descriptor-created children of the exact policy retained root; both transient and retained roots
  must be outside the tracked checkout. Root and child device/inode, current UID, modes
  `0700`/`0600`, one-link files, local filesystem, parent identity, current capacity, and the
  aggregate retained-byte ceiling are rechecked. Every production writer uses pinned package
  descriptors, stable retained-input reads, create-only files, and pre-write bounded capacity
  admission. Repository-local or arbitrary output,
  replacement, symlink, special file, remote filesystem, capacity failure, and partial interrupted
  output fail closed. Logical deletion is not secure erasure.
- One retained-root transaction is the sole advisory-lock owner for cooperating AV-Atlas writers.
  It covers root/output/ancestor verification, aggregate and free-capacity admission, direct or
  nested byte creation and immutable file copy, source/destination content and identity checks,
  post-write aggregate verification, fsync, and exact-created-inode rollback. Prepared frames and
  both annotation packages use the same transaction; the former post-lock hard-link placement is
  removed. This is cooperative serialization, not protection from a malicious same-UID process.
- For current execution, prepared-pilot linkage and authenticated OCR-package validation recompute
  the retained root identity digest, filesystem type, byte ceiling, reserve, and decision from the
  live verified root and policy. Tests alter each field and recompute ordinary receipt and manifest
  checksums; the internally consistent false claims remain invalid.

The M2B.3 synthetic check requires explicit source-bound `synthetic-controlled` rights,
evaluation-mode permission closure, and the exact current fixture bundle before FFprobe or FFmpeg
can run. Pilot security policy is an additional execution boundary, not media authorization. Direct
native compatibility remains limited to accepted controlled non-pilot baselines; no pilot command
accepts it. `pilot-evaluate` takes the complete authenticated OCR package and validates all six
fixed components and cross-bindings before metrics rather than accepting loose OCR output files.

The current schema file SHA-256 values are:

- private policy: `46470353fa45e6dc16dd55449ac8806986a466ef0c918020c9d1ed04bda52ccc`;
- sanitized receipt: `07e6f81724597a8a53a20bf6a2c05d6c45d3966146f13cee6af823fb04dd19fa`;
- synthetic security report: `23df35b1444c3c6ce494689e99df99c35ddb21876c7c220ceadac2c3567b3172`;
- pilot manifest: `5aa3f901bb3b61244c36b4adcd1e8d948a4b8b56c704ba3543f112fef96dc1c5`;
- pilot OCR output manifest: `9bf13a7864d4a31405180d5be1a7273234eb3a9bb4fa58e14161ecdade39356f`;
  and
- pilot OCR observation: `6a68b863ebd3215015d222709a556e6c3e2e04bbd0bfebc5fdb45e80aa8fa552`.

### Corrected synthetic execution and gates

A fresh ignored private-policy replay used verified, distinct tmpfs roots with separate 64 MiB
temporary and retained ceilings and 16 MiB reserves. The private policy file SHA-256 was
`9468675b9bd6a35422b6b9103d259e70837676a45b40696f7e73b7986cc197cc`; its embedded checksum was
`47342c85b5ddd434564aa2ccc96d2a3405d679ac1d85e69a64e83d1d445d4897`. Its path and root
identities remain untracked and undisclosed. `RLIMIT_NPROC` was set to 8,192 because Linux charges
that limit against the host real UID before Bubblewrap enters its user namespace and the measured
desktop UID already had more than 4,096 threads. The reviewed maximum remains 16,384; this is a
bounded host-UID ceiling, not a precise per-sandbox process count.

The unchanged 2,401,427-byte synthetic source retained SHA-256
`6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8`; the fresh 204-byte synthetic
pilot specification had SHA-256
`e3bde15abcf766ef3b56d7cf2ade2f4366c41a0b562d4f7c40833686f760c0b0`. Approved local FFprobe,
FFmpeg, and Tesseract all executed through Bubblewrap profile 1.1. One 5,250-byte frame produced
three OCR observations with zero retries and zero timeouts. Measured wall time was
2.8674427649821155 seconds, child CPU time 2.151135 seconds, and peak child RSS 180,672 KiB.

Hostile measurements were all true: namespace smoke, loopback/external network denial,
out-of-mount sentinel denial, masked mutable-runtime sentinel denial, and denial of writes outside
the one descriptor-bound work directory. The transient root was empty after completion. Retained
files and directory had exact private modes; a scan found no private path, source/frame export,
user/host identity, environment value, or secret-like value in the public receipt/report.

Fresh runtime-bearing artifact identities are:

- sanitized receipt file / embedded receipt hash:
  `2445c882fa2936f99ce238bf0296ce3286a7c3a5fca64cd3940077eea91fa26e` /
  `4c5cbec555c576e7764b10d4a1b1df3da32d10e67076b49c866c138c09bb02a1`;
- synthetic report file / embedded report hash:
  `aa1d87402bdd61f76f2edbd1cc4c578aa40cfa7c7394f3d6bc5be32e4e379999` /
  `70bfb2c3089a7abc828472b20f830edd3f7bf0448615b005ddcb352bb7ed413a`;
- sandboxed dependency inventory:
  `ab20ef53a2039d191460b0b19fe306c710107735cc5370c0edee7c07b7ffdb12`; and
- sandboxed raw OCR observations:
  `7f3c10085a9e3e80289e925b0121d4aa673eaeab495517e8f2879b1627da805e`.

The receipt reported retained-root identity
`e46782deb61f384916286a1dfb833c0793a1bdc2579969adde873357d4a87059`, filesystem `tmpfs`,
67,108,864-byte ceiling, 16,777,216-byte reserve, `verified-tmpfs` decision, and a 6,459-byte
aggregate. The public receipt/report contained no absolute private path, local user name, or
secret-like value, and the transient root was empty after completion.

The exact local correction gates passed: locked/offline sync; Ruff format and lint; Mypy over 28
source files; 417 tests in 113.69 seconds with zero failures and zero skips; doctor with FFmpeg,
FFprobe, Tesseract, and Bubblewrap available; policy inspect/validation; and the actual synthetic
sandbox check. The new regressions cover all OCR package substitutions, wrong/missing completion
receipt, policy/pilot crossing, retained output placement/replacement/capacity/interruption,
separate-process nested frame-versus-annotation admission, post-create rollback failures,
masked-runtime access, reviewer creation/removal/tampering/expiry/redaction, schema compatibility,
and valid unchanged paths. In the synchronized two-process regression, either 1,024-byte payload
fit a 1,500-byte ceiling but both did not: exactly one committed, the other received capacity
denial before creation, one private inode remained, no pending/partial inode remained, and the
final aggregate was exactly 1,024 bytes.

Immutable tag object/commit pairs remain v1
`8cadd6c8ecda7d0b6f60421f312c199cbad163e1` /
`54d96dc25bdf03ab1e92d22150c5011faf16b7e6`, v1.1
`8be328eef2fd10037b56921aff1f401c3ef3a12e` /
`5d016784c6b3d7226a9f6e0f56cca9fb3ef48822`, and v1.2
`5427bb4639d94f0311d49f5ef8be9337fdcad167` /
`c24ff0c9dacb1d3e42cfe8e48e31ec866ab9a882`. Accepted v1 fixture, gold, configuration, raw OCR,
evaluation, benchmark, run-manifest, and release-manifest hashes remain unchanged. Final issue,
pull-request, CI, and CodeQL identities are verified externally. Same-UID host
processes, kernel/native-parser vulnerabilities, swap/backups/snapshots/remanence, crash/power-loss
cleanup, reviewed-storage assertions, authenticated signatures, Linux portability, real human
annotations, the authorized real-media pilot, license/patent decisions, full M2, and M2C remain
open limitations.
