"""Hash-bound, stable, immutable controlled-fixture sidecar loading."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av_atlas.contracts import Observation
from av_atlas.errors import AtlasError, ResourceLimitError
from av_atlas.io import canonical_json
from av_atlas.schemas import validate_instance

FIXTURE_CONTRACT_VERSION = "av-atlas-controlled-fixture/1.1.0"
FIXTURE_SCHEMA_VERSION = "1.1.0"
LEGACY_FIXTURE_SCHEMA_VERSION = "1.0.0"
OBSERVATION_SIDECAR_TYPE = "observation_sidecar"
MAX_FIXTURE_MANIFEST_BYTES = 1_000_000
MAX_OBSERVATION_SIDECAR_BYTES = 1_000_000
READ_BLOCK_BYTES = 65_536


@dataclass(frozen=True)
class VerifiedFixtureSidecar:
    """One verified sidecar represented only by immutable values."""

    basename: str
    sidecar_type: str
    payload_schema_version: str
    sha256: str
    size_bytes: int
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class ControlledFixtureBundle:
    """Exact source-bound fixture marker plus immutable accepted sidecars."""

    manifest: dict[str, Any]
    sidecars: tuple[VerifiedFixtureSidecar, ...]

    @property
    def observations(self) -> tuple[Observation, ...]:
        return tuple(observation for item in self.sidecars for observation in item.observations)


def fixture_manifest_digest(value: dict[str, Any]) -> str:
    """Return the fixture integrity checksum; it is not an authenticated signature."""
    payload = {key: item for key, item in value.items() if key != "manifest_hash"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_nlink,
    )


def _read_stable_regular(path: Path, maximum_bytes: int, label: str) -> tuple[bytes, str]:
    """Read and hash one bounded file through a stable no-follow descriptor."""
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("not a regular file")
        if before.st_size <= 0 or before.st_size > maximum_bytes:
            raise ResourceLimitError(f"{label} exceeds its bounded byte-size contract")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened = os.fstat(descriptor)
            digest = hashlib.sha256()
            chunks: list[bytes] = []
            total = 0
            while True:
                block = os.read(descriptor, min(READ_BLOCK_BYTES, maximum_bytes + 1 - total))
                if not block:
                    break
                chunks.append(block)
                digest.update(block)
                total += len(block)
                if total > maximum_bytes or total > before.st_size:
                    raise ResourceLimitError(f"{label} grew beyond its bounded byte-size contract")
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        final = os.lstat(path)
    except ResourceLimitError:
        raise
    except OSError as exc:
        raise AtlasError(f"{label} is missing, unsafe, or could not be read stably") from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or len({_identity(value) for value in (before, opened, after, final)}) != 1
        or total != before.st_size
    ):
        raise AtlasError(f"{label} changed or was replaced while it was read")
    return b"".join(chunks), digest.hexdigest()


def _canonical_observation_basename(media: Path) -> str:
    return media.with_suffix(".observations.json").name


def _adjacent_observation_exists(media: Path) -> bool:
    return os.path.lexists(media.with_suffix(".observations.json"))


def _load_observation_sidecar(media: Path, descriptor: dict[str, Any]) -> VerifiedFixtureSidecar:
    basename = str(descriptor["basename"])
    if (
        Path(basename).name != basename
        or "/" in basename
        or "\\" in basename
        or basename in {".", ".."}
        or basename != _canonical_observation_basename(media)
    ):
        raise AtlasError("fixture sidecar basename is not the canonical adjacent filename")
    declared_size = descriptor["size_bytes"]
    if (
        not isinstance(declared_size, int)
        or isinstance(declared_size, bool)
        or not 1 <= declared_size <= MAX_OBSERVATION_SIDECAR_BYTES
    ):
        raise ResourceLimitError("fixture sidecar declared size is outside the bounded contract")
    path = media.parent / basename
    raw, digest = _read_stable_regular(
        path, MAX_OBSERVATION_SIDECAR_BYTES, "controlled fixture observation sidecar"
    )
    if len(raw) != declared_size:
        raise AtlasError("fixture sidecar byte size does not match its manifest binding")
    if digest != descriptor["sha256"]:
        raise AtlasError("fixture sidecar SHA-256 does not match its manifest binding")
    try:
        value: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise AtlasError("controlled fixture observation sidecar is malformed JSON") from exc
    validate_instance("observation_sidecar", value, basename)
    if value["schema_version"] != descriptor["payload_schema_version"]:
        raise AtlasError("fixture sidecar payload schema version does not match its binding")
    observations = tuple(Observation.from_dict(item) for item in value["observations"])
    identifiers = [item.observation_id for item in observations]
    if len(identifiers) != len(set(identifiers)):
        raise AtlasError("fixture sidecar contains duplicate observation IDs")
    return VerifiedFixtureSidecar(
        basename,
        str(descriptor["type"]),
        str(descriptor["payload_schema_version"]),
        digest,
        len(raw),
        observations,
    )


def load_controlled_fixture_bundle(
    media: Path,
    source_hash: str,
    source_id: str,
) -> ControlledFixtureBundle | None:
    """Load an exact-byte marker and every current-version accepted sidecar."""
    marker = media.with_suffix(".fixture.json")
    if not os.path.lexists(marker):
        return None
    raw, _ = _read_stable_regular(marker, MAX_FIXTURE_MANIFEST_BYTES, "controlled fixture manifest")
    try:
        value: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise AtlasError("controlled fixture manifest is malformed JSON") from exc
    validate_instance("fixture_manifest", value, marker.name)
    if value["content_sha256"] != source_hash or value["source_id"] != source_id:
        return None
    if value["schema_version"] == LEGACY_FIXTURE_SCHEMA_VERSION:
        if _adjacent_observation_exists(media):
            raise AtlasError(
                "legacy fixture manifest cannot authorize adjacent observations; regenerate "
                "the controlled fixture with the 1.1 sidecar-binding contract"
            )
        return ControlledFixtureBundle(value, ())
    if value["manifest_hash"] != fixture_manifest_digest(value):
        raise AtlasError("controlled fixture manifest integrity checksum is invalid")
    descriptors = value["sidecars"]
    if len(descriptors) != len({item["basename"] for item in descriptors}):
        raise AtlasError("controlled fixture manifest contains duplicate sidecar basenames")
    listed_observation = any(item["type"] == OBSERVATION_SIDECAR_TYPE for item in descriptors)
    if _adjacent_observation_exists(media) and not listed_observation:
        raise AtlasError("adjacent fixture observation sidecar is not listed in the manifest")
    sidecars: list[VerifiedFixtureSidecar] = []
    for descriptor in descriptors:
        if descriptor["type"] != OBSERVATION_SIDECAR_TYPE:
            raise AtlasError("controlled fixture manifest lists an unsupported sidecar type")
        sidecars.append(_load_observation_sidecar(media, descriptor))
    return ControlledFixtureBundle(value, tuple(sidecars))
