# Security

Media, subtitles, OCR, transcripts, metadata, filenames, and sidecars are untrusted data. They never
become CLI arguments beyond a path supplied by the operator, configuration keys, prompts, or agent
instructions. The fixture includes the visible phrase “IGNORE PREVIOUS INSTRUCTIONS”; the pipeline
records it as an OCR claim and performs no action from it.

Subprocesses use explicit argument arrays with `shell=False` and no interpolation. Inspection is read-only,
source content is hashed, output directories are never silently overwritten, and resume verifies
the source hash. Logs omit raw paths and media text. The baseline makes no network calls, uploads no
media, loads no model files, and requires no secrets. Operator identities are hashed before storage;
structured logs contain no media text or source/config path.

M2A adds ffprobe output/time limits, source duration/dimension limits, bounded low-resolution frame
counts, subprocess timeouts, keyframe count/size limits, run-controlled output paths, and partial
keyframe cleanup. Source files are never modified. Media-borne subtitle and prompt-injection text is
copied only into evidence fields and cannot select tools, permissions, configuration, or commands.

M2B.2 performs parser-free authorization and stable acquisition before FFprobe. It rejects a
non-regular or symlink source, opens with `O_NOFOLLOW` where available, hashes through one
descriptor, derives the canonical source ID, and verifies the fixture marker or explicit rights
schema, checksum, source, permission closure, retention, and expiry. The same descriptor supplies a
bounded byte-for-byte copy in a unique 0700 directory and 0600 file. Source and temporary ceilings
apply before and during copying. Pre/post descriptor and pathname metadata detect mutation,
replacement, growth, and truncation; copied and independently reread hashes, sizes, and source IDs
must match. Only then may FFprobe or FFmpeg receive the snapshot path. Tesseract receives snapshot-
derived keyframes. Tests use subprocess sentinels to prove zero native-parser calls for missing,
stale, mismatched, denied, retention-denied, expired, mutated, and replaced inputs.

The path-free stable-input receipt records the verified method and policy, not original/snapshot
paths. Native error details redact private paths. Run completion occurs only after the snapshot is
removed. Ordinary exceptions, adapter failures, timeouts, and handled interruption execute the same
cleanup. A locked marker supports bounded startup recovery after `SIGKILL` or power loss: only
recognized inactive private entries are removed, via pinned directory descriptors, without
recursive traversal or symlink following. Unrecognized and live entries remain untouched.
`inspect --output` is exclusively created after parsing and never replaces an existing path;
source, hard-link, symlink, and pre-existing-output collisions fail before parser invocation.

FFmpeg remains an attack surface. These budgets are defense-in-depth, not an OS sandbox. Production
processing of adversarial media still requires operating-system isolation, CPU/memory/file quotas,
decoder patch management, and access controls. DRM, authentication, and paywalls are never bypassed.

Tesseract is an optional native parser attack surface. OCR preprocessing is bounded, temporary
files are run-local and deleted, symlink/out-of-run keyframes are rejected, worker counts are capped
at four, keyframe bytes are re-hashed before decoding, and each process receives one OpenMP thread.
Resume removes only stale run-root temporary directories bearing the adapter's fixed prefix after a
hard interruption. Tests cover missing executables/languages, corrupt/empty/oversized frames,
timeouts, shell metacharacters, symlinks, prompt isolation, and cleanup. These controls are not an
OS sandbox. OCR text—including prompt-like text—remains inert evidence.

Pilot preparation rechecks exact source hashes and four permissions before frame extraction,
authorizes every source before parsing any source, rejects out-of-range or duplicate timestamps,
and invokes FFprobe/FFmpeg only on one verified private snapshot at a time. It removes both the
snapshot and a partial output package on failure. Pilot OCR rechecks rights, frame hashes, and the
frozen configuration. Media paths appear only in the operator's local input specification; tracked
manifests export hash-derived source IDs. Separate annotator packages prevent accidental disclosure
of the other submission, but their operational delivery remains the operator's responsibility.

Resume and validation recompute the persisted rights checksum and compare it with the run link
before processing. Permission edits with either a stale checksum or a new checksum but stale run
linkage fail closed before FFmpeg, Tesseract, or an adapter is called. This checksum is not a
signature, identity proof, or legal determination.

OCR temporal tracks are untrusted derived artifacts. Validation checks equal member/evidence/box/
confidence array lengths before iteration and relationally recomputes all member linkage, ordering,
timestamp bounds, confidence mean, policy version, shot boundary, configured gap, and spatial
compatibility from raw OCR observations. Malformed track data is reported through controlled
validation errors and the quality report; it cannot escape as an uncaught collection/type error.
The complete supplied track payload must also equal the canonical deterministic recomputation from
all immutable raw OCR observations, preventing omitted, duplicated, split, merged, reordered, or
fabricated derived evidence.

Ordinary OCR dependency artifacts contain hashes, basenames, and path classes, not custom
operator-home paths or a raw `TESSDATA_PREFIX`. Full paths require the explicitly local/private
diagnostic option. Package licenses are identified only when installed metadata was actually read;
unknown status remains explicit.

Stable input is risk reduction, not a native-parser sandbox. A same-UID hostile process can modify
files that share its account, and low-level parser helpers still accept plain paths even though all
supported entry points route verified snapshots. Acquisition fails closed on platforms without the
required POSIX directory-descriptor and `flock` primitives. A growing live source and a retained-frame
lifecycle remain unsupported. Issues [#11](https://github.com/belagrf/av-atlas/issues/11) and
[#12](https://github.com/belagrf/av-atlas/issues/12) remain open until this implementation is
reviewed and merged; the real-media pilot has not begun.
