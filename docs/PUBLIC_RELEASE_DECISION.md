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

Security issue 11 and standalone-inspection governance issue 12 remain open pilot gates. Native
parser isolation and retained-frame lifecycle also remain unresolved. Full M2 is incomplete, and
M2C is unimplemented.

## M2B.2 pull-request boundary

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
[#14](https://github.com/belagrf/av-atlas/issues/14) stay open until review and merge. The local and
loopback hostile-input regressions generate only temporary synthetic bytes and publish neither
media nor network-fetched content.
