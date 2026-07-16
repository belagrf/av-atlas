# ADR-0007: M2B.3 private pilot storage and sandboxed native execution

- Status: proposed by the accepted issue 17 direction; acceptance requires reviewed merge
- Date: 2026-07-16
- Milestone: M2B.3 pilot-host security; no real-media processing or M2C implementation

## Context

M2B.2 makes authorization and stable byte acquisition precede native parsing, binds controlled
fixture sidecars, and constrains supported FFmpeg protocols and demuxers. That boundary does not
isolate FFprobe, FFmpeg, or Tesseract from the operator account. Its default temporary root can
also be disk-backed, journaled, swapped, snapshotted, indexed, or backed up. Logical unlinking of a
snapshot is not secure erasure. These are blockers for the first authorized real-media pilot even
though they do not invalidate the controlled synthetic releases.

Issue 17 selected a mandatory sandboxed pilot path. An unsandboxed native-parser risk waiver is
not sufficient for the initial pilot. The implementation and tests continue to use only
project-authored synthetic data; this decision does not authorize operator media.

## Decision

M2B.3 uses additive current 1.1 contracts. The local-private
`av-atlas-pilot-security-policy/1.1.0` may contain the explicit transient- and retained-root paths,
their identities, host storage facts, review records, the independent reviewer pseudonym, and
expiry. It is mode `0600`, ignored by Git, and must never be copied into a run, report, release,
annotation package, or log. The public `av-atlas-pilot-security-receipt/1.1.0` contains only
hash-derived identities, measured storage classes and capacities, sandbox identity, enforced
limits, decision linkage, cleanup state, and privacy booleans. It deliberately omits the reviewer
pseudonym as well as absolute paths, user names, hostnames, mount paths, secrets, and raw
environment values. Both contracts are schema-validated and self-hash checked. Those self-hashes
are integrity checksums, not authenticated signatures. The policy is expiry-bound and binds one
exact pilot ID and frozen pilot-spec identity. Historical 1.0 policy and receipt records remain
read-only validation compatible but cannot authorize current pilot execution.

Pilot mode requires two explicit, pre-created, distinct private roots; it never implicitly chooses
the system temporary directory or an arbitrary output location. The transient root contains only
short-lived snapshots and sandbox workspaces. The retained root contains prepared pilot packages,
annotation packages, authenticated OCR output packages, and evaluation reports that the rights and
security policies permit retaining. AV-Atlas opens and retains directory descriptors, rejects a
final symlink, and verifies absolute/canonical identity, device, inode, current-UID ownership,
exact mode `0700`, local filesystem class, and free capacity for the separately declared transient
and aggregate retained ceilings plus reserves. Both roots must be outside the tracked checkout.
Retained directories and files use exact modes `0700` and `0600`, have one owner/link as applicable,
and are created descriptor-relative only after parent and child identity checks. Every production
retained writer uses a pinned direct-child package descriptor, stable descriptor-relative reads,
create-only files, and aggregate/current-capacity admission before each bounded write.
Symlinks, special files, path replacement, ownership or mode drift, unsupported or remote
filesystems, and inadequate current capacity fail closed. Leases and cleanup operate relative to
the pinned descriptors. Marker-aware stale recovery remains bounded and does not follow symlinks;
failed or interrupted partial output is removed while an authenticated successful retained package
remains subject to the policy's aggregate-byte ceiling and operator deletion lifecycle.

The allowed storage decisions apply independently to each root:

- `verified-tmpfs`, which requires a measured `tmpfs` filesystem and an explicit acknowledgement
  that swap can still preserve content unless the host's swap policy prevents it;
- `reviewed-encrypted-volume`, which treats encryption as an independently reviewed operator
  assertion scoped to the pilot and expiry, not as a cryptographic claim made by AV-Atlas; and
- `reviewed-remanence-acceptance`, which requires an independent, pilot-scoped, expiring review,
  compensating controls, and a deletion plan.

Cleanup means logical unlinking and directory removal only. AV-Atlas makes no overwrite-based,
cryptographic-deletion, or secure-erasure claim.

When an independently reviewed decision is selected, the 1.1 private policy persists a nonempty,
pilot-scoped reviewer pseudonym alongside the scope and expiry and revalidates it at each bounded
native-processing boundary. Removing or changing that identity invalidates the policy checksum or
semantic validation. The public receipt does not export it.

Pilot native execution is mandatory through Bubblewrap profile
`av-atlas-bubblewrap-pilot/1.1.0`. There is no direct-execution fallback. A missing, changed, or
incapable Bubblewrap dependency fails closed before pilot parsing. The profile creates user, PID,
IPC, UTS, mount, and network namespaces; starts a new session; dies with its parent; drops all
capabilities; clears the environment; exposes no operator home; supplies a private tmpfs `/tmp`;
mounts only `/usr/bin`, `/usr/lib`, optional `/usr/lib64`, Tesseract data under
`/usr/share/tesseract-ocr`, and optional `/etc/alternatives` read-only; mounts verified input
read-only at `/input`; and mounts only one verified host-backed output/work directory read-write at
`/work`. `/usr/local`, `/usr/src`, `/usr/include`, `/usr/share/doc`, and `/usr/share/man` are
explicitly represented as masked or unexposed profile subtrees. The profile does not bind the whole
host root or all of `/usr`, and policy, source, transient-root, retained-root, and output paths that
overlap an exposed runtime subtree are rejected before execution. A measured sentinel check must
prove that a masked mutable runtime subtree is unavailable while the required FFprobe, FFmpeg,
Tesseract, and Python probes remain usable. It replaces the UTS hostname with a fixed non-host
value. The sandbox-local private tmpfs `/tmp` is also writable. The profile document has SHA-256
`18ba5b8e06291138310fa45d040c5930bcbc5c705ac4c2a7018398114b0be2ad` on the implementation
branch. That digest binds the declarative argument sequence, mount list, masks, and fixed tool paths;
it does not independently bind the Python overlap checks or runner logic, which are identified by
the reviewed source commit and covered by zero-native-call regressions.

For a policy-approved dependency reload, AV-Atlas opens the Bubblewrap candidate without following
its final path component and checks its exact size and SHA-256 before executing that candidate for
version inventory or namespace smoke. A mismatch executes no candidate subprocess.

One typed native-process runner is the pilot boundary for FFprobe, FFmpeg, and Tesseract. It opens
and rechecks descriptor-backed executables and binds. Writable parent/child identity is checked
before the `/work` descriptor bind and after execution; hostile testing includes a parent-proven
host-writable outside positive control. Policy/reviewer expiry and root identity are rechecked by a
runner callback before every native unit and again before success output. The runner invokes with an argument array and
`shell=False`, bounds stdout/stderr capture, uses a new process group, and terminates the group on
timeout or handled interruption. A small helper sets `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_FSIZE`,
`RLIMIT_NOFILE`, `RLIMIT_NPROC`, and a zero core-dump limit before `exec` of Bubblewrap; it avoids
Python `preexec_fn` in concurrent OCR workers. The policy records wall timeout and cleanup grace as
well as every kernel resource limit.

`RLIMIT_NPROC` is charged against the host real UID before Bubblewrap enters its user namespace.
The reviewed default ceiling therefore accommodates the operator's existing desktop processes and
is not a precise per-sandbox process counter. The PID namespace, wall/CPU/memory/file/descriptor
limits, process-group termination, and hostile capability tests remain required defense in depth.

Every native pilot operation—including source inventory, subtitle extraction, frame/keyframe
decode, OCR preprocessing, and Tesseract recognition—must use the selected sandbox mode. Direct
native execution remains an explicit compatibility path for accepted controlled non-pilot
baselines only; no pilot command accepts it. Low-level helpers must reject a pilot context that
lacks the runner. The M2B.3 synthetic check also requires exact source-bound
`synthetic-controlled` rights, evaluation-mode permission closure, and the current fixture bundle
before FFprobe or FFmpeg can execute. The security policy supplements rather than replaces source
authorization.

Pilot-manifest 1.2 additively extends the validation-compatible 1.1 contract and links the policy
digest, sanitized receipt digest, frozen pilot/spec
and source set, rights aggregate, root identity digest, storage decision, sandbox dependency and
profile, resource limits, measured denial booleans, privacy booleans, and cleanup outcome.
Preparation and OCR execution require the same still-valid policy. Preparation reacquires a fresh
verified source snapshot for each source; OCR execution hash/size-verifies frozen prepared frames
while copying them into a fresh private workspace.

Current synthetic security output uses `av-atlas-m2b3-synthetic-pilot/1.1.0`; historical 1.0
reports remain read-only validation compatible and cannot authorize new execution.

An OCR completion is not represented by a loose collection of output files. Versioned
`av-atlas-pilot-ocr-output/1.0.0` authenticates the complete package only after every native unit
has terminated and private work cleanup has succeeded. It binds the exact frozen pilot manifest
file and embedded hash, pilot/spec/source-set and rights aggregate, private-policy digest, prepared
and `ocr-complete` receipt file and embedded hashes plus stages, frozen OCR configuration,
sanitized Tesseract dependency identity, hashes and sizes of dependency, observation, evidence, and
runtime artifacts, record/frame/evidence counts, and one semantic-output digest. All component
schemas are validated before the manifest is finalized. `pilot-evaluate` accepts this
authenticated output manifest, revalidates every binding and component, and rejects loose,
swapped, modified, cross-pilot, or cross-policy files before computing metrics. Evaluation invokes
no native parser and consumes only policy-bound retained packages; it does not accept arbitrary
loose host files as OCR results.

## Measured dependency state

The current implementation host exposes a system-class `bwrap` basename, version `bubblewrap
0.9.0`, executable size 72,160 bytes, and executable SHA-256
`52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712`. Ubuntu package metadata
reports `bubblewrap` `0.9.0-1ubuntu0.1` for `amd64`, source package/version
`bubblewrap 0.9.0-1ubuntu0.1`, and `LGPL-2+` from installed copyright metadata whose SHA-256 is
`229a402fddba5c81005950f28de162359383cba731f5b859b8f82a03c338bf01`. The sanitized dependency
identity under profile 1.1 is
`f75d9e08d32eaad33de98592ee0f603a19539768f3e5381b8a0b31e3c1f6c94e`.

The exact static Bubblewrap argument prefix/suffix and fixed native-tool paths are part of the
profile record whose SHA-256 is
`18ba5b8e06291138310fa45d040c5930bcbc5c705ac4c2a7018398114b0be2ad`; the runner derives its
command from that record rather than from a second unbound implementation.

The local namespace capability smoke test passed for the required user, PID, IPC, UTS, mount, and
network namespaces and measured loopback/external-network, host-root write, device-directory
write, home, fixed-hostname, and inherited-environment isolation. The synthetic hostile check also
proved a host-writable outside target before confirming the sandbox could not alter it. That
dependency smoke result does not by itself
complete M2B.3: completion additionally requires the project-authored synthetic pilot to execute
FFprobe, FFmpeg, and Tesseract through this exact path and all hostile, lifecycle, compatibility,
local, CI, CodeQL, and source-review gates to pass.

## Consequences and limitations

Pilot execution is Linux/Bubblewrap-specific in this contract. Unsupported systems fail closed;
AV-Atlas does not install Bubblewrap automatically. The Ubuntu operator installation command is
`sudo apt-get install bubblewrap`, but running it remains an operator action. Shared libraries and
the minimum read-only system runtime remain part of the trusted computing base. Kernel namespace
isolation and rlimits reduce impact but do not prove that native parsers are defect-free.

Private-root storage assertions do not establish media ownership or legal authority. A rights
manifest, pilot specification, and policy each serve separate purposes and remain required.
`verified-tmpfs` does not prove swap is disabled; reviewed encryption is an assertion; and logical
cleanup cannot guarantee removal from storage internals, backups, journals, swap, or snapshots.

The retained-root contract reduces accidental persistence and substitution risk but cannot prove
that host storage, backups, snapshots, or same-UID processes are trustworthy. Policy-bound
retention is not consent to redistribution and does not replace the media rights declaration.

No authorized real-media pilot, independent human annotation, M2C adapter, learned model,
checkpoint, GPU, cloud service, training, or license choice is introduced by this decision. M2B.3
completion must not be claimed until the corrected synthetic sandbox completion gate, local and
remote quality gates, and reviewed merge all succeed. The additive policy, receipt, OCR-package,
and pilot-manifest contracts do not rewrite the immutable M2B v1, v1.1, or v1.2 evidence; their
historical schemas remain read-only validation compatible.
