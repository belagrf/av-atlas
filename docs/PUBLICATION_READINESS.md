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

The candidate adds no media, frame, audio, subtitle, annotation, rights workspace, traineddata,
checkpoint, model, binary, or run directory. Private lease roots, snapshots, verified sidecar
payloads, and residues are ignored and are not release artifacts. Snapshot unlinking is documented
as logical cleanup rather than secure erasure. The final review scan and machine-readable manifest
cover 132 proposed branch paths, and a second independently rendered manifest was byte-identical.
Exact gate counts are recorded in `PROJECT_STATE.md`; the detached manifest hash and clean-checkout
CI/CodeQL results are reported in the PR update to avoid circular tracked claims. This branch
creates no release and does not alter the v1/v1.1 release records. Issues 11, 12, and 14 remain
open.
