# Evaluation

M0/M1 evaluation is operational, not a model-quality claim. The validator reports counts for schema
instances, event intervals, evidence references, provisional-to-final revision chains, and artifact
hashes. Contract and integration tests exercise failure behavior and deterministic equivalence.

M2A adds fixture-only shot-boundary precision/recall/F1 and timing errors, transition confusion,
keyframe coverage, subtitle track/cue discovery, exact/normalized text error, cue timing, adapter
state correctness, runtime, peak RSS, storage, retries, and processed duration. Machine and Markdown
reports preserve configuration, source/gold hashes, environment, code-state availability, unmeasured
targets, unsupported metrics, and sample-size limitations.

The gold is project-authored synthetic structure, not an independently adjudicated real-media pilot.
No supported-claim precision, salient-event recall, ASR/OCR/diarization/acoustic accuracy,
confidence interval, statistical significance, direct-VLM comparison, or M2 gate has been measured.

M2B evaluates the frozen synthetic OCR set with exact match, normalized CER/WER, frame presence,
evidence/time integrity, duplicate rate, adapter-state correctness, difficulty-stratified results,
and measured CPU/wall/RSS/throughput. The same frozen keyframes and gold run at one, two, and four
workers; canonical OCR bytes must agree. Region precision/recall and IoU remain null because the
frozen gold contains no region annotations, even though predictions retain word boxes. These
synthetic measurements are engineering checks, not real-media or generalized OCR performance.

The authorized-pilot evaluator is gated on two complete independent annotations, adjudicated gold,
and a hash-locked manifest. It supports frame/region exact match, CER/WER, presence P/R/F1,
one-to-one IoU >= 0.5 region P/R/F1 and mean IoU, reading order, evidence/time failures, duplicate
rate, resources, and source/category/difficulty/text-size/confidence strata. Inter-annotator results
remain separate. The path is prepared but unexecuted because no authorized media or human
annotations are present.

M2B.1 separately reports exact-record duplicates, temporal repeated observations, derived-track
compression, and unresolved derived evidence. Prediction-only keyframes participate in text-
presence false positives rather than being mislabeled as timestamp errors. Gold-only frames remain
false negatives, no-text frames remain explicit negatives, and zero-record adapter correctness is
checked from structured state rather than by vacuous `all([])`. The accepted four-frame v1 gold and
historical metrics are unchanged; new metrics belong to the additive hardening report.

M2B.2 adds engineering validation of authorized-byte stability rather than an OCR quality metric.
Tests cover descriptor-bound acquisition, source/snapshot identity, parser zero-call denial,
private modes, cleanup and bounded recovery, interruption/fresh resume, path-free receipts and
exports, and accepted v1/v1.1 run validation. The shared native-input contract is checked at every
runtime ingest decode: exact argument ordering, `file`-only protocol and `matroska`-only format
whitelists, forced demuxing, parser-free EBML selection, reported-format agreement, no unrestricted
fallback, and zero parser/network/local-sentinel access for hostile HLS/DASH/concat/sequence/
navigation inputs. Generated OCR PNG decoding has a separate forced single-image contract.

Fixture-manifest 1.1 regressions cover missing, mismatched, replaced, symlinked, malformed,
oversized, unlisted, and concurrently changed observation sidecars; stale marker checksums;
fabricated adjacent data; immutable adapter delivery; mutation/replacement after acquisition;
resume revalidation; and deterministic regeneration. Fixture 1.0 remains historical-validation
compatible but cannot newly authorize an adjacent observation sidecar. These are security and
evidence-integrity checks, not new OCR metrics. The frozen fixture, gold, normalization, OCR metric
definitions, observations, and accepted quality claims do not change. No M2B.2 result is evidence
of real-media accuracy or semantic perception.

Explicit fixture-trust regressions separately prove that forged legacy and current markers without
rights stop before parsing; ordinary explicit rights neither change fixture status nor admit
adjacent observations; synthetic-controlled rights accept only an exact current bundle; missing or
mismatched bundles fail closed; resume cannot cross between ordinary and controlled trust; and
semantic validation rejects impossible controlled states. Accepted v1/v1.1 artifacts remain
read-only compatible. These tests establish authorization/evidence behavior only and do not alter
the frozen OCR fixture, gold, normalization, or quality metrics.
