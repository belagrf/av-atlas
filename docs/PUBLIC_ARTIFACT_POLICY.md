# Public artifact policy

Public source may include implementation code, schemas, locked dependency metadata, configuration
templates, deterministic fixture-generation recipes, compact project-authored synthetic gold,
tests, ADRs, governance/security/evaluation documents, sanitized release manifests, task/goal
documents, and the project concept paper.

Do not publish generated fixture media when it can be rebuilt; run directories; logs; source or
operator media; frames/audio/subtitles extracted from media; private annotations; operator rights
manifests; credentials; local paths; datasets; checkpoints/weights; Tesseract language data;
binaries; container volumes; or source archives. Publication eligibility is separate from legal
permission to process a source.

Every public release requires a staged-blob scan for secrets, personal paths, restricted media,
unexpected binaries, symlinks, and size outliers. Public structured artifacts must be hash-bound and
claim-bounded. Generated prose is a view, never source evidence. No model output becomes source
evidence, and no media text becomes an instruction.

No project license has yet been selected. Public visibility permits inspection of the source but
does not grant reuse rights beyond applicable law.

M2B.2 private stable-input roots, ownership markers, transient snapshots, verified sidecar payload
copies, and crash residue are local processing material and must never be tracked, archived,
attached, or published. Public runs may include only schema-valid path-free receipts, inventory,
and fixture-sidecar identity metadata. `stable_input.json` carries the canonical source hash/ID,
verified method, byte ceilings, explicit ordinary-or-synthetic trust mode, sanitized rights basis
and checksum linkage, nullable current fixture checksum, bound sidecar digests/sizes, and lifecycle
assertions; it contains no operator, rights-manifest path/payload, snapshot path, or sidecar path and
does not make a marker, snapshot, or sidecar copy source evidence. A publishable fixture marker is
integrity metadata, never an authorization credential.

Unlinking a snapshot and removing its lease is logical lifecycle cleanup, not secure erasure. No
public statement may imply that underlying filesystem blocks, journal entries, snapshots, swap, or
backups were erased. A private, capacity-bounded temporary-root policy or explicit remanence-risk
acceptance remains a gate before real operator media.

M2B.3 local-private pilot-security policies, actual temporary-root paths and identities in raw form,
root/work lease markers, snapshots, extracted pilot frames, native workspaces/captures, local-private
diagnostics, stale-recovery residue, and private pilot specifications remain local processing
material. They must never be tracked, logged into public artifacts, archived, attached, or released.
The Bubblewrap executable, FFmpeg/Tesseract binaries, and Tesseract language data remain system
dependencies and are not publication artifacts.

The versioned policy/receipt/report schemas, typed runner and policy implementation, synthetic test
sources, ADR, documentation, and compact path-free structured receipts/reports may be public after
the ordinary staged publication scan. A publishable receipt may record only hash-derived
pilot/spec/policy/rights/root linkage, sanitized filesystem/storage class and measured capacity,
Bubblewrap basename/package/license/hash/profile identity, enforced limits, namespace/denial
booleans, logical-cleanup outcome, and explicit privacy booleans. It must contain no absolute path,
user name or UID, hostname, mount path, raw environment value, secret, source bytes, extracted frame,
private annotation, or private rights declaration.

The private policy self-hash and public receipt hash are integrity/linkage checks, not signatures,
legal authority, storage-encryption proof, or secure-erasure evidence. Synthetic sandbox reports must
state that no real media was processed and must not be presented as real-media OCR accuracy or proof
that native parsers are vulnerability-free. Issue 17 source review remains a gate before the first
authorized real-media pilot.
