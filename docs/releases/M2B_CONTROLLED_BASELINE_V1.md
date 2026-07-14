# M2B controlled baseline v1

Status: “M2B controlled-fixture engineering, OCR execution, evaluation, and resource benchmark complete; authorized double-annotated real-media pilot pending.”

This release freezes only four project-authored synthetic frames. It establishes neither real-media OCR accuracy nor semantic visual understanding. Full M2 remains incomplete.

## Frozen identity

The operator installed the distribution-packaged Tesseract executable and English language data before the measured execution. Codex performed no installation during that continuation or this release replay.

| Item | Identity / SHA-256 |
|---|---|
| Tesseract | 5.3.4, Leptonica 1.82.0; executable `9f831cab7525c3dab04af41bda35182af7ea1df9dceeaaa2f3bf207ac45c06a5` |
| English data | `tesseract-ocr-eng` 1:4.1.0-2, 4,113,088 bytes; `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2` |
| Fixture | `6d1f79c6a63b6a8d5510bcd67a74e522096fe97b6c2bba68587f0213ccc682a8` |
| Gold | `e62e392aa45406f939edc1f2093d07f1dcf175c0c4ea9085cbeae3edde50bc1a` |
| Configuration | `8f5545df1c78e5845e19e3ae0299a86cc7c950cb9c3ba7e7b5fee217f1a45c55` |
| OCR observations / semantic output | `f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060` |
| Evaluation | `a1011542165e3b8974857aaee68bbaa8185987cbb3ca0353ad4afecda38803ad` |
| Benchmark | `479087002a126b1d442ca2e4d768bafd3e266e9f542dba92a01ea075a3280455` |
| Run manifest | `6779769594db6a7457ee30b7d9ffbdacc8ec345120433125e7e846978359b440` |

Frozen schema hashes are OCR observation `8e70e97e07df18374d986691c34da1311115a11af8659eae07148555e96e21f3`,
OCR gold `01189133b7185d3cf0d17dbaf7c34cb9700e7d17ae5d98fede470f747070efc3`,
OCR evaluation `28c639314fdc4bdbd5789e68251e3003071861df276564589c123074a53b9d4a`,
OCR benchmark `f07e1519a937b1d6408ee92249185bc4ba263c1d50f3cef15f305128078a87e5`,
and run manifest `59053ec2bcdf0752f32889bc00b9322da6d98831ce83120208237225a3cc5b4d`.

The executable is the Ubuntu `tesseract-ocr` 5.3.4-1build5 amd64 package (Apache-2.0). The default M2B path uses `eng` only; installed `osd` was inventoried but not used. `TESSDATA_PREFIX` was unset, so the distribution default data directory was used. Tracked documentation deliberately omits absolute host paths.

## Frozen synthetic measurements

Four frames containing expected text produced 13 observations. Exact frame match was 0.75, normalized CER 0.0125, normalized WER 0.07692307692307693, and text-presence precision/recall/F1 were all 1.0. Duplicate rate was 0; missing evidence references, invalid timestamps, retries, and timeouts were all 0. Adapter-state correctness was true. Main-run wall time was 3.017794 s, CPU time 2.230488 s, peak RSS 181,284 KiB, throughput 1.325471735142 frames/s, and media-minutes per compute-minute 2.650943470284.

Region precision, region recall, and box/polygon IoU are unsupported for this frozen version because its gold region arrays are empty. Predicted boxes remain preserved. This limitation is not hidden with a fabricated zero.

Difficulty results are exact/CER/WER: high-contrast 1/0/0; digits 1/0/0; mixed-case 1/0/0; punctuation 1/0/0; prompt-injection 1/0/0; rotation 1/0/0; Unicode supported by `eng` 1/0/0; low-contrast 0/0.038461538461538464/0.2; small 0/0.038461538461538464/0.2; multiline 0.5/0.018518518518518517/0.125.

## Worker benchmark and recommendation

| Workers | Wall s | CPU s | Peak RSS KiB | Frames/s | Media min/compute min |
|---:|---:|---:|---:|---:|---:|
| 1 | 2.207769 | 2.177335 | 181352 | 1.811783620446 | 3.623567501854 |
| 2 | 1.842121 | 2.096001 | 181352 | 2.171409541629 | 4.342820042766 |
| 4 | 1.838363 | 2.364020 | 181352 | 2.175848547082 | 4.351697678859 |

All produced the semantic hash `f851aef0d8a1c215023cd71b38120a2f317a10be3dd24567f2f023449acd6060`, identical metrics, 13 observations, and no failures or timeouts. Two workers reduced wall time by 16.56% versus one (approximately 20%); four improved only another 0.20%. Two workers are therefore the provisional recommendation. The frozen one-worker configuration and its hash are unchanged; a future versioned configuration may adopt two.

## Gates, rights, security, and resume

The accepted run passed the locked dependency, format, lint, type, full test, and doctor gates, and all M1/M2A/M2B run validation reports had zero unexplained errors. Negative tests cover missing executables/languages, malformed/corrupt/empty/no-text/oversized frames, timeout, metacharacter paths, symlinks, cleanup, rights hash/operation/expiry/retention failures, prompt-injection isolation, offline behavior, path leakage, secret-like values, interruption, and resume.

Release-freeze gates: `uv lock --check` pass; `uv sync --extra dev --locked --offline` pass (18
packages checked); Ruff format pass (34 files), Ruff lint pass, mypy pass (20 source files), pytest
pass (52 tests, including actual Tesseract), and doctor pass. All 13 preserved/generated run
directories validated with zero errors.

Completed-run first and repeated resume preserved every manifest-tracked byte. Accepted completed tracked digest: `e10bec548cd486d969cdc9f169928ee2e02a8d19958f0dfc58350808a4722e97`; interrupted-run first/repeated resume tracked digest: `b07e1b5e716a77d05a33d8a6b6254fdb35cfa69f7ba6a7eaedd5d69e4bdf36e1`. Runtime measurements and creation timestamps are nondeterministic across fresh executions; semantic OCR output is deterministic.

## Reproduction

Follow [M2B controlled reproduction](M2B_CONTROLLED_REPRODUCTION.md). The current verification is a fresh same-host reproducibility replay, not independent verification by a second implementation or environment. The exact commands and machine-readable values are in [the release manifest](M2B_CONTROLLED_BASELINE_V1.json).

## Limitations

No external media or human annotations were used. No generalized performance, real-media accuracy, learned AV-Atlas capability, audiovisual reasoning, or semantic-vision claim is made. ASR/alignment, diarization, acoustic-event recognition, semantic visual perception, a real adjudicated pilot, and direct-VLM comparison remain incomplete.
