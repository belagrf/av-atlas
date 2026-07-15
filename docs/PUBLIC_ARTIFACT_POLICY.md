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

M2B.2 private stable-input roots, ownership markers, transient snapshots, and crash residue are
local processing material and must never be tracked, archived, attached, or published. Public runs
may include only the schema-valid path-free `stable_input.json` receipt. That receipt carries the
canonical source hash/ID, verified method, byte ceilings, and lifecycle assertions; it contains no
operator or snapshot path and does not make the snapshot source evidence.
