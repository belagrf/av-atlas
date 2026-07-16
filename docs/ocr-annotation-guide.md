# Authorized real-media OCR pilot

No authorized real-media pilot is present and no human annotation has occurred. The commands below
prepare the package but fail closed until the operator supplies at least three local sources, exact
hash-bound rights declarations, and a valid local-private pilot-security policy. AV-Atlas validates
operator and reviewer assertions; it does not make a legal or storage-encryption determination.

## Intake and pre-registration

Keep source media and working pilot directories outside version control. For each source, record provenance, acquisition basis, privacy review, deletion owner/date, and restrictions. Generate a rights manifest permitting all four operations:

```sh
uv run av-atlas make-rights LOCAL_MEDIA --output LOCAL_RIGHTS \
  --operator-id OPERATOR_PSEUDONYM --basis owned \
  --allow analysis --allow annotation --allow evaluation \
  --allow derivative_artifact_retention
```

`owned` is an operator assertion, not a legal conclusion. Use the correct basis. Expiration and restrictions must reflect the actual authorization.

Copy [the pilot specification template](templates/ocr-pilot-spec-v1.json) outside the repository and
fill it before inspecting any Tesseract output. It requires source and rights paths only in this
local input, at least three content-distinct sources, an explicit selection method, seed where
randomized, inclusion/exclusion rules, duplicate policy, categories, and exactly 20 calibration plus
60 evaluation timestamps. Select across subtitles/captions, title cards, credits, signs, screens,
lower-thirds, text sizes/difficulties, multiple regions, repeated text, and no-text frames where
available. Do not select for known OCR success.

Pilot mode also requires an explicit, pre-created current-UID-owned local directory with exact mode
`0700`; it never selects the operating-system default temporary directory. The root and policy
must be outside the checkout, and the policy basename must be `pilot-security-policy.local.json`
or end in `.pilot-security-policy.local.json`. Keep both private paths outside version control.
Inventory the approved local Bubblewrap
dependency, then create and validate a policy bound to the exact pilot ID, specification bytes,
root identity, storage decision, expiry, capacity, Bubblewrap identity/profile, and resource limits:

```sh
uv run av-atlas inspect-bubblewrap
uv run av-atlas pilot-security-create \
  --root LOCAL_PRIVATE_ROOT --pilot-id PILOT_ID --pilot-spec LOCAL_SPEC \
  --output PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json \
  --expires-at EXPIRY_RFC3339 \
  --storage-decision verified-tmpfs
uv run av-atlas pilot-security-inspect \
  PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json \
  --pilot-id PILOT_ID --pilot-spec LOCAL_SPEC
uv run av-atlas pilot-security-validate \
  PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json \
  --pilot-id PILOT_ID --pilot-spec LOCAL_SPEC
```

`verified-tmpfs` requires a root actually measured as tmpfs and does not prove that swap is disabled.
The alternative `reviewed-encrypted-volume` and `reviewed-remanence-acceptance` decisions require
the corresponding independent, pilot-scoped, expiring review fields; encryption remains a reviewed
assertion, not a cryptographic finding by AV-Atlas. If approved Bubblewrap or the required Linux
namespace capability is unavailable, pilot native processing fails closed. AV-Atlas does not
install Bubblewrap automatically.

```sh
uv run av-atlas pilot-prepare LOCAL_SPEC \
  --security-policy PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json \
  --output NEW_LOCAL_PILOT_DIR
uv run av-atlas pilot-security-validate-artifacts NEW_LOCAL_PILOT_DIR \
  --security-policy PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json
```

Preparation verifies every exact source hash and all four permissions before parsing any source,
validates timestamp bounds, rejects duplicates, and exports only hash-derived source IDs. It does
not run OCR. The original source is never copied into the pilot package: FFprobe and FFmpeg operate
on a verified private transient snapshot through the mandatory Bubblewrap profile, which is deleted
after each source. If authorization, sandboxing, extraction, timeout, or handled interruption fails,
the private workspace and incomplete package are removed or left only for bounded marker-aware
recovery. The pilot manifest records exact frame hashes, the pre-registered split, security-policy/
receipt linkage, sandbox identity, enforced limits, measured denial state, and cleanup outcome.

Current native-input policy accepts only parser-free-classified, self-contained Matroska/WebM.
MOV/MP4, HLS, DASH, concat/concatf, image sequences, Blu-ray navigation, and other unreviewed or
multi-resource inputs fail before parsing; operators must not use AV-Atlas to fetch or silently
transcode them. Pilot FFprobe, FFmpeg, OCR preprocessing, and Tesseract use the one reviewed
Bubblewrap profile with no unsandboxed fallback. It denies network and ambient home access, exposes
verified inputs read-only, exposes only the private work directory as host-backed writable storage,
and provides a separate sandbox-local tmpfs `/tmp`. Snapshot/workspace unlinking and lease removal
are logical cleanup, not secure erasure; storage internals, backups, journals, snapshots, and swap
remain outside that claim.

## Independent annotation

```sh
uv run av-atlas pilot-annotation-packages LOCAL_PILOT_DIR
```

Deliver `annotator_A` and `annotator_B` separately. Do not give either person OCR output or the other annotation. Each person directly fills every field: exact visible text; separately normalized text; one box `[x,y,width,height]` or polygon per region; region reading order; English language; legibility and uncertainty; ignore regions; occlusion/truncation; pseudonym; timestamp; notes; and the independence attestation. Do not infer hidden text. Codex must not fill or impersonate either package.

After both completed packages return:

```sh
uv run av-atlas pilot-compare-annotations LOCAL_PILOT_DIR ANNOTATION_A ANNOTATION_B \
  --output DISAGREEMENTS.json
```

Record inter-annotator exact agreement, transcription distance, and region agreement separately from OCR quality. An adjudicator reviews every disagreement against the frames and produces a completed adjudicated annotation while preserving both originals. The command reports differences; it never auto-adjudicates.

## Freeze, unchanged-adapter run, and evaluation

Freeze before the first quality evaluation:

```sh
uv run av-atlas pilot-freeze LOCAL_PILOT_DIR ANNOTATION_A ANNOTATION_B ADJUDICATED.json \
  --output PILOT_FROZEN_V1.json
uv run av-atlas pilot-run-ocr LOCAL_PILOT_DIR PILOT_FROZEN_V1.json \
  --security-policy PRIVATE_POLICY_DIR/PILOT_ID.pilot-security-policy.local.json \
  --output NEW_OCR_OUTPUT
uv run av-atlas pilot-security-validate-artifacts LOCAL_PILOT_DIR \
  --manifest PILOT_FROZEN_V1.json --security-policy LOCAL_PRIVATE_POLICY
uv run av-atlas pilot-evaluate LOCAL_PILOT_DIR PILOT_FROZEN_V1.json ADJUDICATED.json \
  NEW_OCR_OUTPUT/ocr_observations.jsonl NEW_OCR_OUTPUT/ocr_runtime.json \
  --output PILOT_EVALUATION_V1.json
```

Freeze locks frame, two-annotation, adjudicated-gold, normalization implementation, unchanged
`configs/m2b.yaml`, region rule, and metric identities. Any later modification requires a new
version. `pilot-run-ocr` rechecks analysis, evaluation, and derivative-retention rights, frame
hashes, the frozen configuration, and the still-current policy/root/sandbox/spec linkage. It copies
each hash/size-verified frozen frame into a fresh private workspace and uses the existing local CPU
adapter only through the sandboxed runner. Recognized commands remain inert untrusted data.

The evaluation reports frame/region text accuracy, CER/WER, presence, IoU-based region detection, reading order where measurable, duplicates, evidence/timestamp failures, retries/timeouts, and resources. Reports from the synthetic baseline and real-media pilot remain separate. A 60-frame pilot cannot establish accuracy for all films, episodes, or livestreams.

After evaluation, create an evidence-linked error table with one row per error and assign at least
one reviewed primary cause: missed text region; false-positive region; character substitution;
insertion; deletion; word segmentation; punctuation; reading order; rotation; perspective; blur;
low contrast; compression; occlusion; boundary truncation; unsupported character/language;
frame-selection failure; preprocessing failure; or evidence/provenance failure. Do not infer causes
automatically. Representative examples must cite retained evidence and must not embed source images
unless redistribution/retention explicitly permits it.

## Privacy, interruption, and deletion

Keep all media and the local-private policy/root outside version control and scan exports for
absolute paths, usernames, hostnames, secret-like strings, raw environment values, and unnecessary
personal data. Pseudonymize annotators. Resume or retry only from hash-validated frames, current
rights declarations, and the same valid security decision; a changed or expired declaration or
policy requires a new authorized package or policy version. Retain source frames, annotations,
reports, and evidence examples only as the manifest permits. At expiry, delete source derivatives,
both packages, adjudication material, OCR outputs, and reports using the operator-recorded deletion
owner and verify logical cleanup. Do not claim secure erasure and do not redistribute representative
images unless redistribution is separately permitted.

Current status: “M2B controlled baseline frozen and real-media pilot package ready; operator-supplied authorized media and two independent human annotations pending.”
