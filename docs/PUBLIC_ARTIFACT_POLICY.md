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
