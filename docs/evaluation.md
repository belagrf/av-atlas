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
