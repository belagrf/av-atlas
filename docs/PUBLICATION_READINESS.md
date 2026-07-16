# Publication readiness

## Decision

Ready for public source inspection after the tracked-file manifest and staged-blob scans pass. The
repository is not described as open source because no project license has been selected.

## Audit scope

The audit covers candidate filenames and contents, binary types and sizes, symlinks, generated
media, caches/environments/runs, rights manifests, PDF metadata/text, secret-like patterns, email and
home-path patterns, and staged Git blobs. This directory had no prior Git history. The authenticated
GitHub credential remains in the system keyring and is neither read nor stored by the project.

Included binary: the project concept-paper PDF, whose metadata identifies `OpenAI` as author and
contains no personal email, private path, script, encryption, or embedded operator media. Its reuse
license remains unresolved. The editable DOCX is excluded as an unpublished source document.

Generated synthetic media are excluded even though project-authored; CI regenerates fixtures from
tracked code. Compact synthetic gold and sanitized release hashes remain tracked. Test strings such
as `operator@example.invalid` and `/home/` are non-live negative-test sentinels.

## Publication boundaries

No private/commercial/operator media, extracted derivative, private annotation, private rights
manifest, traineddata, checkpoint, dataset, executable, secret, personal name/email, or absolute
personal path is approved. `runs/`, `reproductions/`, generated fixtures, caches, environments, and
logs are excluded. No M2C implementation is included.

No project license has yet been selected. Public visibility permits inspection of the source but
does not grant reuse rights beyond applicable law.

## Measured local gate

On 2026-07-15, the post-merge source and v1.1 release branch each passed `uv lock --check`, locked
offline sync, Ruff formatting over 44 files, Ruff lint, mypy over 21 source files, and doctor. The
final release-branch suite passed 140/140 tests in 42.39 seconds with the installed Tesseract path
executing. Fresh ignored M1, M2A, M2B, M2B.1, and interrupted/repeated-resume fixtures/runs validated
with zero errors. The accepted v1 run also validated read-only without rewriting its evidence.

Fresh v1.1 OCR retained the accepted 13-observation semantic hash, added 13 deterministic secondary
tracks, and preserved all per-file maps across completed and interrupted repeated resume. Runtime
evaluation and worker measurements remain explicitly separate from content-stable hashes.
Post-merge clean-checkout CI and CodeQL both passed on
`4646f40e3c424a569fc8379c37df2fc67f99b7dd`.

The first v1 public CI failure remains visible in GitHub history: a regression referenced an
intentionally excluded historical M0 run. The subsequent clean-checkout fix and M2B.1 hardening do
not depend on ignored local evidence. Tesseract tests execute in current CI.

## v1.1 final candidate scan

The v1.1 manifest covers all 121 proposed tracked paths. A second independently rendered manifest
was byte-identical and its path set exactly matched the reviewed candidate list. Filename, content,
MIME, size, symlink, Git LFS, credential, home-path, email, media, derivative, rights-workspace,
annotation, dataset, traineddata, checkpoint, weight, archive, and run-directory scans found no
publishable blocker. The only file above 1 MiB is the already approved 1,282,425-byte concept PDF;
it is unencrypted and its author metadata is `OpenAI`. There are no tracked symlinks or LFS objects.

Home-path and email matches are limited to documented scan statements and inert negative-test
sentinels (`/home/operator/...` and `operator@example.invalid`) whose tests prove redaction. No
private media, private derivative, private rights declaration, credential, personal path, or
private annotation is included. The detached publication-manifest hash is computed after this final
record and reported in release verification, avoiding a circular hash claim inside a hashed input.

## M2B.2 pull-request candidate

The M2B.2 candidate adds standard-library stable-input acquisition, stable-input/fixture/inventory
compatibility schemas, a fixed native-input policy schema, one explicit configuration, synthetic
security/regression tests, and documentation. The source-review correction forces self-contained
Matroska/WebM through a `file`-only protocol and `matroska`-only demuxer/format policy, forces
generated PNG decoding through `png_pipe`, and passes only hash/size-bound immutable controlled-
fixture observations to adapters. Hostile local-manifest and loopback-network cases are generated
under pytest temporary directories and produce zero parser calls, local-sentinel access, and HTTP
requests; they are not tracked media or downloaded content.

The follow-up trust correction requires explicit rights for every fresh run and inspection. Only
`synthetic-controlled` plus an exact current fixture bundle admits sidecars; ordinary rights ignore
adjacent marker/sidecar data, and legacy markers are validation-only. Stable-input 1.2 and run-
manifest 1.1 persist and validate this decision. Forged-marker, missing-bundle, ordinary-isolation,
trust-transition, and impossible-state regressions contain only temporary synthetic bytes.

The candidate adds no media, frame, audio, subtitle, annotation, rights workspace, traineddata,
checkpoint, model, binary, or run directory. Private lease roots, snapshots, verified sidecar
payloads, and residues are ignored and are not release artifacts. Snapshot unlinking is documented
as logical cleanup rather than secure erasure. The final review scan and machine-readable manifest
cover 132 proposed branch paths, and a second independently rendered manifest was byte-identical.
Exact gate counts are recorded in `PROJECT_STATE.md`; the detached manifest hash and clean-checkout
CI/CodeQL results were reported in the PR review to avoid circular tracked claims. The reviewed
implementation merged without altering the v1/v1.1 release records. Issues 11, 12, and 14 closed
with that implementation; issue 17 is the remaining security and temporary-root gate before a
real-media pilot.

## v1.2 release-preparation candidate

The v1.2 candidate contains release, state, reproduction, publication, governance, security, and
ADR metadata only. It preserves the reviewed implementation commit
`2555a297153c9b5ff059b7d8dc7e49de5d93c43b` and package 0.2.2 without changing source, schemas,
configuration, tests, locks, workflows, fixtures, or accepted evidence. The two new release records
bring the reviewed candidate inventory to 134 files. A fresh deterministic render must exactly
match that candidate path set; its detached SHA-256 is reported in the release-preparation PR,
because embedding it in a file that it hashes would be circular.

The complete local gate passed 272 tests with zero failures/skips, Ruff format over 51 files, Ruff
lint, mypy over 24 source files, locked offline sync, and doctor. Fresh ignored
M1/M2A/M2B/M2B.1/M2B.2/interrupted-resumed M2B.2 runs validated with zero errors; accepted v1/v1.1
runs validated read-only. The exact implementation source passed main CI and CodeQL. Completed and
interrupted first/repeated resume comparisons were byte-identical across all 72 run files and all
69 manifest artifacts.

The candidate scan covers filenames, content, staged blobs, JSON, MIME/magic, sizes, symlinks, Git
LFS, credentials, personal paths/emails, media/derivatives, rights workspaces, annotations,
traineddata, checkpoints/weights, datasets, archives, runs, caches, and private snapshot leases. No
publication blocker was found. The only object above 1 MiB remains the approved 1,282,425-byte
concept PDF; it is unencrypted and has no JavaScript or embedded file. There are no tracked
symlinks or LFS objects. Inert `.invalid`, `/home/operator`, and documented negative-test strings
are not live personal data or credentials.

No tag or release is created from this branch before source review. No private media, derivative,
rights declaration, annotation, traineddata, checkpoint, model, run directory, or archive is
included. No project license has been selected. Issue 17 and the operator-supplied authorized
double-annotated pilot remain pending; full M2 is incomplete and M2C is unimplemented.

## M2B.3 pull-request candidate

Issue 17 authorizes a synthetic-only implementation branch and an unmerged public pull request for
the sandboxed local pilot path. It does not authorize a tag, release, merge before source review,
operator-media processing, model/checkpoint acquisition, GPU, cloud inference, paid API, training,
M2C, or a project-license decision. The immutable v1, v1.1, and v1.2 tags, releases, fixtures, gold,
configuration, and accepted evidence remain outside this change.

The candidate adds versioned local-private policy, sanitized receipt, and synthetic-security-report
schemas; a Linux Bubblewrap profile and typed native-process runner; descriptor-relative private
root/workspace handling; an additive pilot-manifest security block; synthetic hostile/lifecycle/
compatibility tests; ADR-0007; and current operator/security/governance documentation. The approved
locally installed Bubblewrap executable is inventoried and exercised, not copied or redistributed.
All executable tests use only project-authored synthetic bytes.

The actual private-root path, local-private policy, private pilot specification, rights manifests,
stable-input snapshots, extracted frames, private workspaces, structured run outputs, local
diagnostics, and recovery residue are excluded from the tracked candidate. Eligible structured
records contain only hash-derived linkage, sanitized storage/sandbox identity, measured limits and
denial booleans, and logical-cleanup/privacy state. The final working-tree candidate scan covered
147 paths and found no absolute personal/root path, user/host identity, raw environment value,
credential, media, derivative, traineddata, checkpoint, weight, executable, archive, or unexpected
large object. There are no symlinks, executable tracked files, or Git LFS pointers. The only object
above 1 MiB is the previously approved 1,282,425-byte concept PDF. Inert `.invalid` addresses and
`/home/operator` negative-test sentinels are not live personal data. The staged-blob scan is repeated
after explicit staging. `docs/publication-manifest.json` covers the exact 147-path set using its
established normalized self-entry convention; its detached hash is reported in the pull request to
avoid a circular tracked claim.

The local synthetic sandbox check is host-security engineering evidence only. It establishes no
real-media safety or OCR accuracy, secure erasure, native-parser correctness, trained-model
capability, M2B.3 final acceptance, or full-M2 completion. Issue 17 remains open and the pull request
remains unmerged pending CI, CodeQL, and source review; no authorized real-media pilot has begun.
