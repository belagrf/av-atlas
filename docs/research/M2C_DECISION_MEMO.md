# M2C decision memo — preparation only

Decision state: no M2C implementation, model execution, checkpoint download, training, or dependency installation occurred in this assignment.

## Recommendation

Prefer a local ASR adapter with word-level timestamp alignment as the next capability, subject to a separate dependency, license, dataset, privacy, CPU, and checkpoint authorization. Spoken dialogue is a primary information channel in films, episodes, and livestreams, and aligned words provide the strongest immediate evidence substrate for later speaker attribution, audiovisual fusion, retrieval, and long-form memory work.

This is a strategic recommendation, not measured feasibility. Candidate versions, package/model licenses, hashes, sizes, RAM, and throughput must be frozen and measured before M2C begins. This offline memo does not claim that any candidate license or download remains current.

## Comparison

| Criterion | ASR + word alignment | Speaker diarization | General acoustic events |
|---|---|---|---|
| Importance | Highest: recovers spoken lexical content and timings | High after ASR: answers who spoke when, but not what was said | Moderate: captures non-speech context absent from transcripts |
| Evidence/timestamps | Word intervals can resolve directly to audio evidence | Speaker turns resolve to audio intervals; identity remains pseudonymous unless separately authorized | Event intervals resolve to audio evidence; labels may be coarse |
| Later fusion/memory benefit | Highest: searchable language, quotations, entity/event cues | Strong: structures dialogue and conversational memory | Useful context and scene-state cues, less lexical information |
| CPU feasibility | Plausible for small/local models but expected slower than real time for alignment; must measure | Often computationally demanding and sensitive to recording conditions | A small bounded classifier may be the easiest CPU increment |
| GPU need | Not logically required for inference, but larger models/alignment may be impractical on CPU | Common pipelines benefit materially from GPU; CPU target is risky | Small classifiers may fit CPU; larger audio encoders may not |
| Expected memory | Model-size dependent; plan for hundreds of MiB to several GiB, then measure | Often multiple stages/models; potentially several GiB | Potentially hundreds of MiB to low GiB for a compact candidate |
| Expected throughput | Unknown until measured on frozen audio durations and hardware | Unknown and likely below ASR-only throughput | Likely best of the three for a compact classifier, unmeasured |
| Dependency complexity | Decoder, audio frontend, tokenizer, timestamp/alignment path, model runtime | Segmentation, embeddings, clustering, overlap handling, optional VAD | Audio frontend, label ontology, classifier runtime |
| Privacy | Speech content may be sensitive; local-only processing and strict retention are required | Voice embeddings can be biometric/sensitive; highest identity/privacy risk | May infer private settings/activities even without speech text |
| Security | Treat transcripts as untrusted; bound decode/model resources and checkpoint formats | Same, plus hostile audio and embedding leakage risks | Same, plus label/ontology provenance and adversarial audio risk |
| Integration risk | Medium-high, but aligns naturally with the canonical evidence ledger | High: overlap, anonymous speaker stability, and evaluation complexity | Medium: simpler records, but ontology mismatch can limit value |

## Lawful data and license review gates

ASR evaluation should prioritize redistributable, explicitly licensed speech corpora or operator-authorized media with transcription rights. Public availability alone is insufficient. Alignment gold needs word-level timestamps or a separately lawful annotation process. Candidate Whisper-family code/checkpoints and alignment components have historically used different licenses and distribution mechanisms; audit the exact selected files rather than inheriting a family-level assumption.

Diarization needs speech recordings with speaker-turn gold and permission for voice processing. Candidate pyannote-class pipelines commonly combine multiple components and may use gated distribution or separate terms. Treat voice embeddings as sensitive derivatives. Do not acquire a token, accept model terms, or download a pipeline under this memo.

Acoustic-event evaluation needs audio clips with lawful redistribution/evaluation rights and a stable ontology. Common web-video-derived datasets can have availability, consent, link-rot, and redistribution problems even when annotations are published. Prefer project-authored controlled audio plus a separately reviewed lawful evaluation corpus. Candidate BEATs/CLAP/PANN-class checkpoints can differ in code, weight, training-data, and commercial-use terms; review each artifact independently.

## Candidate gate before implementation

A separate M2C authorization should identify one exact runtime and checkpoint, then record source, version, license texts and hashes, checkpoint size/hash/format, transitive dependencies, CPU instruction needs, memory and timeout ceilings, offline installation plan, and security review. Run a tiny controlled fixture before any external corpus. Freeze metrics for WER/CER and timestamp error for ASR; DER/JER and overlap handling for diarization; and macro/micro F1, average precision, calibration, and event-boundary error for acoustic events.

For ASR, the smallest coherent assignment is: replaceable local adapter; speech/no-speech and short English controlled fixtures; raw and normalized transcript separation; word-level integer-millisecond evidence intervals; rights gating; prompt-injection isolation; CPU/offline resource benchmark; and unavailable-dependency behavior. It must not include diarization, semantic fusion, training, or generalized real-media claims.

If the project explicitly prioritizes the lowest-risk CPU-only increment instead of dialogue coverage, a compact acoustic-event adapter is the fallback. Diarization should follow reliable ASR/alignment unless a speaker-centric use case and a lawfully evaluable, CPU-feasible pipeline are demonstrated first.
