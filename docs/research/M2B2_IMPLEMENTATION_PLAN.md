# M2B.2 implementation plan — stable authorized input

Status: design and implementation contract. No real operator media is authorized by this document.

This plan implements ADR-0006 and issue #14. It must not begin M2C, training, cloud inference, model
or checkpoint acquisition, or the authorized real-media pilot.

## 1. Deliverable

Introduce one reusable stable-input subsystem and route every applicable native-media entry point
through it:

```text
operator source
  -> parser-free regular-file checks
  -> source SHA-256 and source ID
  -> fixture or explicit rights authorization
  -> bounded private verified snapshot
  -> FFprobe / FFmpeg / Tesseract consume snapshot only
  -> canonical artifacts retain original source identity
  -> snapshot cleanup
```

Applicable entry points:

- `av-atlas run`
- `av-atlas resume`
- `av-atlas inspect`
- `av-atlas inspect-subtitles`
- OCR pilot source preparation and frame extraction

Evaluation and validation commands that operate only on existing structured run artifacts do not
need a media snapshot unless they independently reopen source media.

## 2. Proposed module boundary

Add a module such as `src/av_atlas/stable_input.py` with narrowly scoped types and functions.

Suggested public API:

```python
@dataclass(frozen=True)
class StableInputRecord:
    source_sha256: str
    source_id: str
    size_bytes: int
    method: str
    snapshot_path: Path

@contextmanager
def authorized_stable_input(
    source: Path,
    rights_manifest: Path | None,
    run_mode: str,
    *,
    expected_manifest_hash: str | None = None,
    max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
) -> Iterator[tuple[AuthorizationPreflight, StableInputRecord]]:
    ...
```

The snapshot path is private runtime state. It must never be serialized by ordinary callers.

A helper may combine snapshot acquisition and FFprobe inventory, but source authorization, stable
copying, and media inspection must remain separately testable.

## 3. Source-open and copy rules

### 3.1 Pre-open checks

- Use `lstat` or equivalent no-follow inspection.
- Reject symlinks, directories, devices, FIFOs, sockets, and non-regular files.
- Open read-only and use `O_CLOEXEC` and `O_NOFOLLOW` where available.
- Compare pre-open path identity with `fstat` identity to reduce path-switch ambiguity.

### 3.2 Authorization

- Compute the parser-free source SHA-256.
- Derive the canonical source ID through the existing shared helper.
- Reuse `authorize_media_preflight`; extend it only when necessary for persisted manifest linkage.
- Do not duplicate rights vocabulary or permission-closure logic.

### 3.3 Resource bound

The first implementation must have an explicit byte ceiling. A default in the low-single-digit GiB
range is adequate for the small pilot, but the exact value must be documented and tested. Oversize
input fails before a snapshot file is allocated or a parser is called.

If the ceiling becomes configurable, add it as an optional strict configuration field without
changing accepted frozen configuration files or their hashes.

### 3.4 Copy and verification

- Create a mode-0700 temporary directory.
- Create the destination exclusively with mode 0600.
- Copy in bounded chunks and handle partial writes.
- Compute the destination hash while copying.
- `fsync` the destination before parser use where supported.
- Compare copied byte count, authorized hash, descriptor identity, size, mtime/ctime metadata where
  available, and final path identity.
- Reject any mismatch before parser execution.
- Preserve a safe suffix only if useful for parser probing; never reuse an unsafe original basename.

## 4. Pipeline integration

### 4.1 Initial run

- Load and strictly validate configuration.
- Refuse a nonempty run directory before creating a snapshot.
- Authorize source.
- Acquire verified snapshot.
- Run FFprobe against snapshot.
- Verify inventory source identity equals authorization.
- Create run directory and canonical records using original content identity.
- Keep the snapshot context alive through all configured adapters.
- Pass original source only to explicitly non-parser sidecar lookup when required for controlled
  fixtures; native adapters receive snapshot only.
- Delete snapshot after completion or ordinary failure.

Consider extending `AdapterContext` with explicit fields such as:

```python
media: Path          # verified snapshot used by native adapters
source_media: Path | None  # original location only for controlled sidecar discovery
```

Do not let native adapters choose the original path.

### 4.2 Resume

- Validate run manifest, inventory, persisted rights digest/linkage, operation, and configuration.
- Require `--media` when the original path was intentionally not retained.
- Reauthorize exact current bytes.
- Acquire a new snapshot.
- Verify source identity against the run manifest.
- Resume adapters against snapshot only.
- Repeated resume of a complete run remains a no-op and should not create a snapshot.

### 4.3 Stop-after-inventory

`--stop-after inventory` may delete its transient snapshot on exit. Resume reacquires a new one.
The snapshot is not a resumable artifact.

## 5. Standalone inspection

Add `--rights-manifest` to both commands:

```text
av-atlas inspect MEDIA --rights-manifest RIGHTS [--output PATH]
av-atlas inspect-subtitles MEDIA --rights-manifest RIGHTS
```

For controlled fixtures, omission remains permitted only when the exact hash-bound fixture marker
validates.

Both commands:

- use analysis-mode permission closure;
- acquire a verified snapshot;
- call FFprobe against snapshot;
- serialize only original source identity and normalized inventory;
- delete snapshot before returning.

No absolute source or snapshot path is printed or written.

## 6. OCR pilot preparation

Refactor pilot preparation so each source is authorized before FFprobe and frame extraction.

For every pilot source:

- require analysis, annotation, evaluation, and derivative-retention permissions;
- acquire one verified snapshot for inventory and all pre-registered frame extractions;
- execute FFmpeg only against snapshot;
- copy only the rights record and selected permitted frame derivatives into the pilot workspace;
- delete the source snapshot before advancing to the next source;
- preserve original source ID/hash in the pilot manifest.

Failure at any point removes the incomplete pilot output according to current fail-closed behavior.

## 7. Cleanup and stale-private-directory policy

Ordinary `finally` cleanup is mandatory.

Use a unique, recognizable prefix and private root. On later invocations, stale cleanup may remove
only directories that satisfy all of these checks:

- expected prefix;
- owned by the current user where the platform exposes ownership;
- not a symlink;
- private directory permissions where applicable;
- older than the configured stale threshold;
- contained under the selected temporary root.

Never recursively delete a path solely because its name has a prefix.

Handled SIGINT/SIGTERM paths should exit through cleanup. SIGKILL and power loss are documented as
stale-cleanup cases.

## 8. Structured runtime record

If a runtime record is added, it must be path-free and schema-versioned. Suggested fields:

```json
{
  "schema_version": "1.0.0",
  "method": "verified-private-copy",
  "source_id": "SRC_...",
  "source_sha256": "...",
  "size_bytes": 123,
  "hash_verified": true,
  "parser_used_snapshot": true,
  "snapshot_retained": false
}
```

Do not record a temporary directory, filename, inode, device number, or absolute source path in an
exported artifact.

The record is optional for the first code increment if tests prove the invariant directly. Avoid
creating a runtime-bearing artifact merely for documentation aesthetics.

## 9. Tests

### 9.1 Stable-input unit tests

- regular source copied and hash-verified;
- snapshot differs in path but equals source bytes;
- snapshot directory/file permissions are private where supported;
- parser callback sees snapshot, never original;
- missing source;
- source symlink;
- directory, FIFO/device where safely testable;
- oversize source;
- source replacement before open;
- source replacement during copy;
- in-place mutation during copy;
- partial-write simulation;
- snapshot hash mismatch;
- cleanup after success;
- cleanup after callback failure;
- cleanup after acquisition failure;
- stale cleanup refuses unverified or escaping paths.

### 9.2 Rights and CLI tests

- non-fixture `inspect` without rights fails before FFprobe;
- stale, expired, mismatched, analysis-denied, or retention-denied rights fail before FFprobe;
- controlled fixture inspection succeeds without explicit rights;
- authorized non-fixture inspection succeeds using snapshot;
- `inspect-subtitles` follows the same matrix;
- output contains no original or snapshot absolute path;
- unsafe source names remain inert.

### 9.3 Pipeline tests

- initial run native adapters receive snapshot;
- controlled fixture sidecar lookup remains functional;
- source mutation during acquisition prevents run creation;
- run manifest retains original identity;
- stop-after-inventory deletes snapshot;
- resume reacquires snapshot and never uses original in a parser;
- complete-run resume creates no snapshot;
- interruption and repeated resume remain deterministic;
- accepted v1/v1.1 baselines validate unchanged.

### 9.4 Pilot tests

- pilot authorization occurs before FFprobe;
- pilot FFmpeg extraction uses snapshot only;
- rights matrix remains analysis + annotation + evaluation + retention;
- all selected frames preserve original source identity;
- snapshot is removed between sources and on failure;
- incomplete pilot output is removed after snapshot/extraction errors.

## 10. Documentation updates

Update only after behavior exists:

- `README.md`
- `docs/architecture.md`
- `docs/security.md`
- `docs/data-governance.md`
- `docs/PROJECT_STATE.md`
- dependency/release records only when a new release is separately authorized

State precisely:

> AV-Atlas authorizes source bytes before creating a private verified processing copy. Native media
> parsers consume the verified copy, not the operator path. This reduces concurrent path-mutation
> risk but does not sandbox native parsers.

## 11. Quality gates

Run at minimum:

```text
uv lock --check
uv sync --extra dev --locked --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run av-atlas doctor
```

Regenerate fresh ignored M1, M2A, M2B, and M2B.1 runs. Validate accepted v1 and v1.1 evidence
without rewriting it.

CI and CodeQL must pass on the pull request. The PR remains unmerged until source review confirms
that every native parser path is snapshot-only.

## 12. Completion wording

Use only after implementation and review:

> M2B.2 stable authorized input and rights-gated standalone inspection complete for the controlled
> engineering baseline. Native parsers consume bounded verified transient snapshots. Authorized
> double-annotated real-media evaluation remains pending.

Do not claim real-media accuracy, a trained AV-Atlas model, a foundation model, semantic audiovisual
understanding, or full M2 completion.
