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
descriptor, derives the canonical source ID, and verifies an explicit rights schema, checksum,
source, permission closure, retention, and expiry. No adjacent marker authorizes execution. Only a
validated `synthetic-controlled` rights basis may then open an exact current fixture bundle; all
ordinary bases ignore adjacent markers and sidecars. The same descriptor supplies a
bounded byte-for-byte copy in a unique 0700 directory and 0600 file. Source and temporary ceilings
apply before and during copying. Pre/post descriptor and pathname metadata detect mutation,
replacement, growth, and truncation; copied and independently reread hashes, sizes, and source IDs
must match. Only then may FFprobe or FFmpeg receive the snapshot path. Before parsing, shared
native-input contract `av-atlas-native-input/1.0.0` requires parser-free EBML magic, input protocol
whitelist `file`, format whitelist `matroska`, and forced `matroska` demuxing. Runtime helpers repeat
classification immediately before decode. Text playlists/manifests, HLS, DASH, concat/concatf,
image sequences, Blu-ray navigation, MOV/MP4, unknown formats, and all network protocols are denied
without an unrestricted retry. Generated OCR frames require PNG magic and forced `png_pipe` input.
Tesseract receives snapshot-derived keyframes. Tests use subprocess sentinels to prove zero native-parser calls for missing,
stale, mismatched, denied, retention-denied, expired, mutated, and replaced inputs.

Fixture-manifest 1.1 binds each accepted runtime sidecar—currently at most one observation
sidecar—by canonical basename, type, payload schema, SHA-256, and byte size. The sidecar is opened
with final-component no-follow protection where available, capped at 1 MB, streamed once, and
checked for path/descriptor identity before and after reading. Its digest, size, JSON schema, and
observation IDs are validated before an immutable observation tuple is supplied to adapters.
Adapters perform no later path read. Missing, changed, replaced, symlinked, malformed, oversized,
or unlisted sidecars fail closed. Forged legacy/current markers without explicit rights fail before
parsing; ordinary explicit rights cannot be promoted or receive adjacent observations; and
synthetic-controlled rights fail if the current bundle is missing or mismatched. Legacy 1.0 markers
remain historical-validation data only. The marker checksum is an integrity checksum, not an
authenticated project signature or authorization credential.

The path-free stable-input receipt records the verified method and policy, not original/snapshot
paths. Native error details redact private paths. Run completion occurs only after the snapshot is
removed. Ordinary exceptions, adapter failures, timeouts, and handled interruption execute the same
cleanup. A locked marker supports bounded startup recovery after `SIGKILL` or power loss: only
recognized inactive private entries are removed, via pinned directory descriptors, without
recursive traversal or symlink following. Unrecognized and live entries remain untouched.
`inspect --output` is exclusively created after parsing and never replaces an existing path;
source, hard-link, symlink, and pre-existing-output collisions fail before parser invocation.

Native policy rendering accepts no caller-supplied option list that could override the whitelist or
demuxer. The only input option is a validated nonnegative integer-millisecond seek rendered by the
policy itself. Bounded recovery accepts only the known stable-input 1.0/1.1/1.2 lease-marker versions;
unknown marker contracts remain untouched.

Hostile HLS/local-file and DASH/loopback fixtures prove zero parser starts, zero local-sentinel
access, and zero HTTP requests. The fixed allowlist prevents libavformat default protocol and
demuxer expansion, but FFmpeg remains an attack surface. These budgets are defense-in-depth, not an OS sandbox. Production
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

Stable-input receipt 1.2 and run-manifest 1.1 persist the explicit trust mode, rights basis and
checksum, and current fixture checksum when controlled. Resume rejects ordinary-to-controlled or
controlled-to-ordinary transitions before rewriting the receipt or invoking an adapter. Validation
recomputes the relationship and reports impossible controlled states as actionable errors while
retaining read-only support for accepted historical contracts. Runs declaring AV-Atlas 0.2.2 or
later must use the current run-manifest 1.1 and stable-input 1.2 pair; declaring an older schema pair
does not bypass these semantic checks.

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
files that share its account. Runtime helpers require the fixed policy even though their internal
API still accepts a `Path`; no arbitrary internal caller receives a capability-enforced filesystem
view. Acquisition fails closed on platforms without the
required POSIX directory-descriptor and `flock` primitives. A growing live source and a retained-
frame lifecycle outside the policy-bound pilot path remain unsupported. Pilot derivatives instead
use the private retained-root contract below. Issues [#11](https://github.com/belagrf/av-atlas/issues/11),
[#12](https://github.com/belagrf/av-atlas/issues/12), and
[#14](https://github.com/belagrf/av-atlas/issues/14) closed after review and merge of this
implementation. Issue [#17](https://github.com/belagrf/av-atlas/issues/17) remains the security and
temporary-root/source-review gate before any real-media pilot; no authorized real-media pilot has
begun.

Snapshot cleanup unlinks the private file and removes its lease directory. This is logical
lifecycle cleanup, not cryptographic or secure erasure; AV-Atlas does not claim filesystem blocks
are erased. The default OS temporary root may be disk-backed, journaled, snapshotted, swapped, or
backed up. Before real operator media, the operator must select and document an appropriately
private, capacity-bounded temporary root—for example an encrypted local volume or suitably
configured tmpfs—or obtain an independently reviewed, pilot-scoped, expiring residual-remanence
acceptance with compensating controls and a deletion plan. A tmpfs may still swap unless configured
appropriately. This storage decision never waives the mandatory native-process sandbox.

M2B.3 makes transient and retained storage selections machine-checkable for pilot mode. The
current local-private policy contract is `av-atlas-pilot-security-policy/1.1.0`; historical 1.0
policies remain read-only validation data. A current policy binds an exact pilot/spec, expires,
self-hashes, names distinct pre-created transient and retained roots, and records expected
device/inode/current-UID ownership/exact `0700` modes, local filesystem identities, separate
storage decisions, source/temporary/aggregate-retained ceilings, and reserves. Its self-hash is an
integrity checksum, not an authenticated signature. AV-Atlas pins each root with a directory
descriptor and performs transient lease, retained package, and cleanup operations relative to the
corresponding descriptor. Both roots must be outside the tracked checkout. It rejects repository-
local transient or retained roots, symlinks, special files,
identity/ownership/permission drift, parent or child replacement, unsupported or remote
filesystems, inadequate current capacity, and aggregate retained bytes above the policy ceiling.
Retained directories and files must have exact modes `0700` and `0600` and one hard link for each
file. Every production retained writer uses a pinned direct-child package descriptor, create-only
files, stable retained-input reads, and bounded aggregate/capacity checks before each write. Failed
or handled-interruption partial packages are removed; successful retained derivatives remain under
the declared policy and operator deletion lifecycle. Logical deletion remains distinct from secure
erasure.

All cooperating retained mutations share one advisory-lock transaction on the verified root. The
lock spans root/output/ancestor verification, aggregate and free-capacity admission,
descriptor-relative direct or nested creation/copy, source and destination identity/content
verification, the post-write aggregate check, fsync, and exact-created-inode rollback. Prepared
frames and both annotation packages use the same typed transaction as JSON, OCR, freeze, and
evaluation outputs; there is no unlocked hard-link placement step. This prevents two cooperating
AV-Atlas processes with separate root descriptors from both committing against the same remaining
capacity. It does not constrain a malicious same-UID process that ignores the advisory lock.

For an independently reviewed storage decision, policy 1.1 stores a nonempty reviewer pseudonym
with its pilot scope and expiry and revalidates that identity at each bounded processing boundary.
Removing or changing the pseudonym invalidates either the policy checksum or its semantic
validation. The private policy is never exported. Its path-free public counterpart,
`av-atlas-pilot-security-receipt/1.1.0`, deliberately omits the reviewer pseudonym and publishes
only sanitized, hash-linked storage identities/classes/capacities, facts, and booleans. Receipt 1.0
remains historical-validation compatible but cannot authorize current execution.

Current prepared-pilot and OCR-package validation also compares the receipt's retained-root
identity digest, filesystem type, byte ceiling, reserve, and decision with the live verified root
and policy. Recomputing ordinary JSON self-hashes after falsifying one of those fields does not make
the claim valid.

Pilot mode has no native-parser waiver or direct fallback. Bubblewrap profile
`av-atlas-bubblewrap-pilot/1.1.0` must match the policy by executable hash/size/version and must pass
the kernel namespace capability smoke test. It creates user, PID, IPC, UTS, mount, and network
namespaces; drops capabilities; clears the environment; supplies no operator home; remounts the
sandbox root read-only; and exposes only `/usr/bin`, `/usr/lib`, optional `/usr/lib64`, Tesseract
data under `/usr/share/tesseract-ocr`, and optional `/etc/alternatives` as read-only host runtime.
It does not bind all of `/usr`; `/usr/local`, `/usr/src`, `/usr/include`, `/usr/share/doc`, and
`/usr/share/man` are masked or unexposed. Source, policy, transient-root, retained-root, and output
paths that overlap an exposed runtime subtree are rejected before execution. Descriptor-backed
input is read-only, and only `/work` plus a private tmpfs `/tmp` are writable. The UTS hostname is
replaced by a fixed non-host value. Hostile probes must measure denial of loopback/external
network, an out-of-mount local sentinel, a sentinel under a masked mutable runtime subtree, a
parent-proven host-writable outside target, root/device writes, home, hostname, and inherited
environment while confirming that required native tools remain usable before a receipt can claim
success.
When a policy pins an approved Bubblewrap hash and size, AV-Atlas opens the candidate without
following its final path component and verifies those bytes before invoking that candidate for
`--version` or the namespace smoke test. A mismatch produces an unsupported state with zero
candidate subprocesses.

The profile SHA-256 covers the declarative argument sequence, mount set, masks, and fixed tool
paths. It does not separately authenticate the Python overlap checks or runner implementation;
those controls are bound by the reviewed source commit and verified by path-overlap and zero-
subprocess tests.

A central typed runner is the only pilot interface to FFprobe, FFmpeg, and Tesseract. It does not
accept an arbitrary executable or mount profile. Descriptor identity and content hashes are
rechecked at use. The `/work` parent and child identities are checked before descriptor binding and
again after execution so persistent or mid-invocation replacement cannot silently redirect output.
Policy/reviewer identity, scope, and expiry and both private roots are rechecked before every native
invocation and before a success receipt or final artifact is emitted. Commands use argument arrays and
`shell=False`; capture is bounded; and timeout or handled interruption terminates the process group
before private-workspace cleanup. A minimal
helper sets `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_FSIZE`, `RLIMIT_NOFILE`, `RLIMIT_NPROC`, and
`RLIMIT_CORE=0` before `exec`, avoiding unsafe `preexec_fn` behavior with OCR workers.

There is no direct-native compatibility mode for a pilot command. Direct execution remains only
for historical controlled non-pilot baseline paths. The M2B.3 synthetic check also requires exact
source-bound `synthetic-controlled` rights, evaluation-mode permission closure, and the current
fixture bundle before FFprobe or FFmpeg is invoked. Security-policy approval alone cannot authorize
the media parser.

`RLIMIT_NPROC` applies to the host real UID before Bubblewrap enters the user namespace. Its ceiling
must accommodate processes already owned by that UID and is not a precise per-sandbox process
count. PID isolation, CPU/memory/file/descriptor limits, wall timeout, process-group termination,
and measured hostile probes remain necessary additional controls. Bubblewrap and its minimum
read-only runtime are still part of the trusted computing base; a sandbox does not prove native
parsers free of vulnerabilities.

Cleanup is deliberately described as logical deletion. AV-Atlas does not claim overwrite-based or
cryptographic erasure; encrypted-volume status is a reviewed operator assertion, and tmpfs may
swap. The sanitized receipt must say `secure_erasure_claimed=false` and
`private_paths_exported=false`.

Pilot OCR output is accepted only as the complete, versioned
`av-atlas-pilot-ocr-output/1.0.0` package. It is emitted after all component schemas validate and
native-work cleanup completes. The manifest binds the exact frozen pilot manifest file and
embedded hash, pilot/spec/source set, rights aggregate, policy digest, prepared and
`ocr-complete` receipt file and embedded hashes plus stages, frozen OCR configuration, sanitized
Tesseract identity, each dependency/observation/evidence/runtime file hash and size, record counts,
and semantic output hash. Evaluation recomputes those relationships before reading metrics and
rejects missing, modified, swapped, cross-pilot, or cross-policy components. A receipt or manifest
self-hash provides corruption evidence, not signer authentication.

Current synthetic security output uses `av-atlas-m2b3-synthetic-pilot/1.1.0`. The validator keeps
1.0 reports readable as historical evidence, but a 1.0 report cannot authorize or represent a new
pilot execution.

No M2B.3 completion or real-media safety claim follows from schema or dependency availability
alone: the project-authored synthetic pilot must actually exercise FFprobe, FFmpeg, and Tesseract,
denial tests, cleanup/interruption, immutable-baseline validation, all local/CI/CodeQL gates, and
source review. No authorized real-media pilot has been processed by these corrections.
