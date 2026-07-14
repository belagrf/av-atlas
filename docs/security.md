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
rejects out-of-range or duplicate timestamps, invokes FFmpeg with an argument array and timeout,
and removes a partial output package on failure. Pilot OCR rechecks rights, frame hashes, and the
frozen configuration. Media paths appear only in the operator's local input specification; tracked
manifests export hash-derived source IDs. Separate annotator packages prevent accidental disclosure
of the other submission, but their operational delivery remains the operator's responsibility.

Resume and validation recompute the persisted rights checksum and compare it with the run link
before processing. Permission edits with either a stale checksum or a new checksum but stale run
linkage fail closed before FFmpeg, Tesseract, or an adapter is called. This checksum is not a
signature, identity proof, or legal determination.

Ordinary OCR dependency artifacts contain hashes, basenames, and path classes, not custom
operator-home paths or a raw `TESSDATA_PREFIX`. Full paths require the explicitly local/private
diagnostic option. Package licenses are identified only when installed metadata was actually read;
unknown status remains explicit.
