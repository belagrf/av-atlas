# Public release decision — M2B controlled baseline v1

The operator explicitly authorized public repository creation, the `m2b-controlled-v1` annotated
tag, and a release containing notes only after the publication scan passes. This does not authorize
publication of operator media, derivatives, private annotations/rights declarations, datasets,
weights, Tesseract data, credentials, or local paths.

Accepted wording: “M2B controlled-fixture engineering, OCR execution, evaluation, and resource
benchmark complete; authorized double-annotated real-media pilot pending.” The fixture contains four
synthetic frames and produced thirteen OCR observations. No real-media OCR accuracy is established;
region metrics are unsupported by the frozen gold; no AV-Atlas model has been trained; no semantic
audiovisual understanding is claimed; and full M2 remains incomplete.

The GitHub release contains the sanitized Markdown release notes only. GitHub-generated source
archives contain tracked source; the locally created review archive is not committed or attached.

## Separately authorized v1.1 patch

After PR 10 passed source review, the operator separately authorized squash merge and an immutable
`m2b-controlled-v1.1` patch release. That authorization covers the reviewed M2B.1 hardening source,
sanitized release records, and ordinary GitHub-generated source archives. It does not broaden the
media, model, training, cloud, pilot, license-selection, patent, or private-data authorization.

Accepted wording: “M2B.1 rights, configuration, partial-result, provenance, temporal-track,
validation, privacy, and clean-checkout hardening complete for the controlled synthetic baseline.
Authorized real-media evaluation remains pending.” The patch remains four synthetic frames and 13
OCR observations. It establishes no real-media accuracy or semantic understanding, and neither an
AV-Atlas model nor a foundation model was trained.

The original `m2b-controlled-v1` tag, release, and records remain immutable. The v1.1 release uses a
new reviewed documentation commit and tag, carries no manually uploaded asset, and records detached
manifest hashes after final rendering. No project license has been selected; public visibility
permits inspection but grants no reuse rights beyond applicable law. Patent/publication review
remains unresolved rather than inferred from release authorization.

At v1.1 release time, security issue 11 and standalone-inspection governance issue 12 remained open
pilot gates; both later closed with the reviewed M2B.2 implementation. Native parser isolation and
retained-frame lifecycle remain unresolved. Full M2 is incomplete, and M2C is unimplemented.

## Historical M2B.2 pull-request boundary

The operator authorized public implementation of issue 14 on
`feat/m2b2-stable-input` and an unmerged review pull request. This authorizes publication of the
source, schemas, synthetic tests, ADR, and sanitized engineering documentation only. It does not
authorize a tag or release, closure of issues 11/12 before review and merge, real-media processing,
M2C, license selection, model/checkpoint use, or any private snapshot/run artifact. The immutable
v1 and v1.1 tags, releases, fixtures, gold, configuration, and accepted artifacts are unchanged.

The source-review follow-up adds a fixed versioned FFmpeg/FFprobe protocol, format, and demuxer
policy plus hash/size-bound immutable controlled-fixture sidecar delivery. It remains within PR 16:
no tag or release is authorized, and issues
[#11](https://github.com/belagrf/av-atlas/issues/11),
[#12](https://github.com/belagrf/av-atlas/issues/12), and
[#14](https://github.com/belagrf/av-atlas/issues/14) stayed open until review and merge. The local and
loopback hostile-input regressions generate only temporary synthetic bytes and publish neither
media nor network-fetched content.

The final authorization correction also remains inside PR 16. It removes automatic marker trust,
requires an explicit declaration for every fresh run/inspection, admits fixture data only for an
explicit `synthetic-controlled` basis plus an exact current bundle, and persists the decision in
stable-input 1.2/run-manifest 1.1. Ordinary rights ignore adjacent fixture data; historical markers
remain validation-only. This correction authorizes no release, tag movement, issue closure, real
media, M2C work, or license choice.

## Separately authorized v1.2 release preparation

Issue 18 authorizes a documentation/manifests-only preparation branch and public pull request for a
future immutable `m2b-controlled-v1.2` patch release. The reviewed M2B.2 runtime source is exactly
`2555a297153c9b5ff059b7d8dc7e49de5d93c43b`, package version 0.2.2. This preparation does not
authorize creating the tag or publishing the release before the pull request receives source
review and is merged. The future release commit is therefore intentionally not predicted in the
tracked record.

The proposed release freezes explicit source-bound rights, stable-input 1.2, run-manifest 1.1,
private transient snapshots, fixed native-input policy 1.0, fixture 1.1 immutable sidecar bindings,
declaration-derived trust modes, rights-gated inspection, fresh-snapshot resume, and accepted
v1/v1.1 validation compatibility. It remains a four-frame synthetic fixture with 13 OCR
observations. It establishes no real-media OCR accuracy, semantic visual understanding, trained
AV-Atlas/foundation-model capability, M2C, or full-M2 completion.

The v1 and v1.1 tags, releases, records, and accepted evidence remain immutable. No manually
attached media, derivative, private rights declaration, annotation, Tesseract traineddata,
checkpoint, weight, run, or archive is authorized. Issue 17 remains the security and temporary-root
gate before any real-media pilot. Logical-not-secure snapshot deletion, absence of an OS native-
parser sandbox, non-Matroska/live/non-POSIX limits, retained-frame lifecycle, project-license
selection, and patent/publication review remain unresolved.

No project license has been selected. Public visibility permits inspection of the source but does
not grant reuse rights beyond applicable law.

## Issue 17 M2B.3 implementation pull-request boundary

The operator authorized implementation of issue 17 on `feat/m2b3-pilot-security` and an unmerged
public pull request titled `Implement M2B.3 private storage and sandboxed pilot execution`. This
authorization covers the versioned local-private-policy and sanitized-receipt/report contracts,
typed Bubblewrap native runner, additive pilot-manifest linkage, project-authored hostile tests,
ADR, dependency inventory, and sanitized engineering documentation. It does not authorize a merge
before source review, a new tag or release, modification of v1/v1.1/v1.2 identities, operator-media
processing, M2C, model/checkpoint acquisition, GPU, cloud inference, paid API, training, or license
selection.

The approved locally installed Bubblewrap dependency may execute only project-authored synthetic
fixtures during this assignment. No Bubblewrap binary, FFmpeg/Tesseract binary, traineddata, source
media, extracted frame/audio/subtitle, run directory, private policy/root/specification, rights
manifest, annotation, archive, or local diagnostic is authorized for publication. Sanitized
path-free receipts and synthetic security reports are eligible only after schema validation and the
ordinary secret/path/media/staged-blob scan.

Issue 17 and its pull request remain open and unmerged until CI, CodeQL, and source review accept the
implementation. The local synthetic sandbox measurement does not establish real-media OCR accuracy,
native-parser correctness, secure erasure, semantic visual understanding, learned-model capability,
or full-M2 completion. The authorized double-annotated real-media pilot remains pending, M2C remains
unimplemented, and no project license has been selected.
