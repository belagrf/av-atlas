# Project state

Last verified: 2026-07-14 (Europe/Berlin)

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
- **M2 — in progress, not complete.** ASR/alignment, diarization, acoustic,
  and semantic visual perception, a human-adjudicated pilot, direct-VLM/loose-baseline comparisons,
  and the full M2 continuation gate in `AV-Atlas_GOAL.md` have not been delivered.

No real-media understanding, model performance, statistical significance, or full-M2 completion is
claimed. No weights were downloaded and no training was run.

## Final environment and quality gates

Observed environment: uv 0.11.28, uv-managed CPython 3.14.3, Linux 6.8.0-134-generic x86_64,
FFmpeg/ffprobe 6.1.1-3ubuntu5, Tesseract 5.3.4, and Leptonica 1.82.0. `doctor` reports optional GPU state, but the pipeline did not use it; PyTorch is not
installed or required.

Commands run from the repository root and exact final results:

```text
uv lock --offline
  Resolved 19 packages
uv lock --check
  Resolved 19 packages
uv sync --extra dev --locked --offline
  Resolved 19 packages; checked 18 packages
uv run ruff format --check .
  32 files already formatted
uv run ruff check .
  All checks passed!
uv run mypy src
  Success: no issues found in 19 source files
uv run pytest -q
  48 passed in 36.31s; no skips
uv run pytest -q -m tesseract
  4 passed, 44 deselected in 28.61s
uv run av-atlas doctor
  required FFmpeg/ffprobe and optional local OCR inventory reported
```

The final suite covers the M0/M1 behavior plus rights refusal, permission/hash/expiry/tamper failures,
valid non-fixture authorization, subtitle metadata and cue edge cases, unsupported bitmap subtitles,
hard/gradual/flash shot behavior, keyframe evidence, absent streams, corrupt input, media limits,
inert prompt text, interruption, repeated resume, semantic determinism, evaluation, BOM, schemas,
revisions, provenance, evidence, and artifact hashes. It requires no network or GPU.

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
rights checksums, native FFmpeg/Tesseract parser exposure without an OS sandbox, no retained-frame
lifecycle, synthetic-only OCR quality, and an unexecuted authorized double-annotated pilot. Full M2
and M2C remain unimplemented.

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
