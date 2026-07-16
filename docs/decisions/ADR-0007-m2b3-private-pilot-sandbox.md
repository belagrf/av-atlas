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

M2B.3 adds two separate 1.0 contracts. The local-private
`av-atlas-pilot-security-policy/1.0.0` may contain the explicit temporary-root path, root identity,
host storage facts, review records, and expiry. It is mode `0600`, ignored by Git, and must never be
copied into a run, report, release, annotation package, or log. The public
`av-atlas-pilot-security-receipt/1.0.0` contains only hash-derived identities, measured storage
class and capacity, sandbox identity, enforced limits, decision linkage, cleanup state, and privacy
booleans. It contains no absolute path, user name, hostname, mount path, secret, or raw environment
value. Both contracts are schema-validated and self-hash checked. The policy is expiry-bound and
binds one exact pilot ID and frozen pilot-spec identity.

Pilot mode requires an explicit, pre-created private root; it never implicitly chooses the system
temporary directory. AV-Atlas opens and retains a directory descriptor, rejects a final symlink,
and verifies absolute/canonical identity, device, inode, current-UID ownership, exact mode `0700`,
local filesystem class, and free capacity for the declared source ceiling, temporary ceiling, and
reserve. Leases and cleanup operate relative to that pinned descriptor. Marker-aware stale
recovery remains bounded and does not follow symlinks.

The allowed storage decisions are:

- `verified-tmpfs`, which requires a measured `tmpfs` filesystem and an explicit acknowledgement
  that swap can still preserve content unless the host's swap policy prevents it;
- `reviewed-encrypted-volume`, which treats encryption as an independently reviewed operator
  assertion scoped to the pilot and expiry, not as a cryptographic claim made by AV-Atlas; and
- `reviewed-remanence-acceptance`, which requires an independent, pilot-scoped, expiring review,
  compensating controls, and a deletion plan.

Cleanup means logical unlinking and directory removal only. AV-Atlas makes no overwrite-based,
cryptographic-deletion, or secure-erasure claim.

Pilot native execution is mandatory through Bubblewrap profile
`av-atlas-bubblewrap-pilot/1.0.0`. There is no direct-execution fallback. A missing, changed, or
incapable Bubblewrap dependency fails closed before pilot parsing. The profile creates user, PID,
IPC, UTS, mount, and network namespaces; starts a new session; dies with its parent; drops all
capabilities; clears the environment; exposes no operator home; supplies a private tmpfs `/tmp`;
mounts the minimum reviewed system runtime read-only; mounts verified input read-only at `/input`;
and mounts only one verified host-backed output/work directory read-write at `/work`. It does not
bind the whole host root. It replaces the UTS hostname with a fixed non-host value. The sandbox-
local private tmpfs `/tmp` is also writable. The profile
document has SHA-256
`b69562979857a6c33d59d7db88ce8a14a7ceaa46504539284edc86d0d0e07a0a` on the implementation
branch.

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
native execution remains an explicit compatibility path for the accepted controlled synthetic
baseline only. Low-level helpers must reject a pilot context that lacks the runner.

Pilot-manifest 1.1 additively links the policy digest, sanitized receipt digest, frozen pilot/spec
and source set, rights aggregate, root identity digest, storage decision, sandbox dependency and
profile, resource limits, measured denial booleans, privacy booleans, and cleanup outcome.
Preparation and OCR execution require the same still-valid policy. Preparation reacquires a fresh
verified source snapshot for each source; OCR execution hash/size-verifies frozen prepared frames
while copying them into a fresh private workspace. Evaluation-only commands may consume the frozen
sanitized receipt without reopening the private policy or host path.

## Measured dependency state

The current implementation host exposes a system-class `bwrap` basename, version `bubblewrap
0.9.0`, executable size 72,160 bytes, and executable SHA-256
`52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712`. Ubuntu package metadata
reports `bubblewrap` `0.9.0-1ubuntu0.1` for `amd64`, source package/version
`bubblewrap 0.9.0-1ubuntu0.1`, and `LGPL-2+` from installed copyright metadata whose SHA-256 is
`229a402fddba5c81005950f28de162359383cba731f5b859b8f82a03c338bf01`. The sanitized dependency
identity is `85905bce616b6f7327efca1c7196f4758752561a0c41bca23401c1fee4ece3f2`.

The exact static Bubblewrap argument prefix/suffix and fixed native-tool paths are part of the
profile record whose SHA-256 is
`b69562979857a6c33d59d7db88ce8a14a7ceaa46504539284edc86d0d0e07a0a`; the runner derives its
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

No authorized real-media pilot, independent human annotation, M2C adapter, learned model,
checkpoint, GPU, cloud service, training, or license choice is introduced by this decision. M2B.3
completion must not be claimed until the measured synthetic sandbox completion gate and reviewed
merge both succeed. The additive policy, receipt, and pilot-manifest contracts do not rewrite the
immutable M2B v1, v1.1, or v1.2 evidence; their historical schemas remain read-only validation
compatible.
