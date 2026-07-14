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

On 2026-07-14, `uv lock --check`, locked offline sync, Ruff formatting/lint, mypy over 20 source
files, and doctor passed. Pytest passed 52/52 in 63.40 seconds with the installed Tesseract tests
executing. Fresh ignored M1, M2A, and M2B fixtures/runs validated with zero errors. M2A retained
shot/subtitle F1 1.0. M2B produced the accepted 13-observation semantic hash and quality metrics;
the fresh resource timings were treated as runtime metadata. Two completed resumes preserved all 64
M2B manifest-tracked artifacts, with comparison digest
`308e6943ae828b4e12e9a30b21a332bde8f707ccf4408a202b9ba6ac1b2018c7` before and after.
