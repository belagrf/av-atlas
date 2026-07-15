"""Fail-closed operator rights declarations bound to exact source bytes."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from av_atlas.errors import AtlasError
from av_atlas.io import canonical_json, sha256_file, source_id_from_sha256, write_json
from av_atlas.schemas import validate_instance

OPERATIONS = (
    "analysis",
    "annotation",
    "training",
    "evaluation",
    "derivative_artifact_retention",
    "redistribution",
)

RUN_MODES = ("analysis", "evaluation")
RUN_MODE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "analysis": ("analysis", "derivative_artifact_retention"),
    "evaluation": ("analysis", "evaluation", "derivative_artifact_retention"),
}


@dataclass(frozen=True)
class AuthorizationPreflight:
    """Parser-free authorization bound to the bytes presented at preflight."""

    source_sha256: str
    source_id: str
    fixture_status: str
    fixture_manifest: dict[str, Any] | None
    rights_declaration: dict[str, Any]
    requested_run_mode: str
    authorized_at: str


def manifest_digest(value: dict[str, Any]) -> str:
    """Return the declaration integrity checksum (not an authenticated signature)."""
    payload = {key: item for key, item in value.items() if key != "manifest_hash"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def create_rights_manifest(
    media: Path,
    output: Path,
    operator_identity: str,
    rights_basis: str,
    allowed_operations: set[str],
    restrictions: list[str] | None = None,
    expires_at: str | None = None,
    notes: str = "",
    independently_reviewed: bool = False,
    review_record: str | None = None,
) -> dict[str, Any]:
    if not media.is_file():
        raise AtlasError(f"media source is not a regular file: {media}")
    unknown = allowed_operations.difference(OPERATIONS)
    if unknown:
        raise AtlasError(f"unknown rights operations: {', '.join(sorted(unknown))}")
    content_hash = sha256_file(media)
    value: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_id": source_id_from_sha256(content_hash),
        "content_sha256": content_hash,
        "operator_id": "OPR_"
        + hashlib.sha256(operator_identity.encode("utf-8")).hexdigest()[:12].upper(),
        "rights_basis": rights_basis,
        "permissions": {operation: operation in allowed_operations for operation in OPERATIONS},
        "restrictions": restrictions or [],
        "expires_at": expires_at,
        "notes": notes,
        "created_at": datetime.now(UTC).isoformat(),
        "manifest_hash": "",
        "independently_reviewed": independently_reviewed,
        "review_record": review_record,
    }
    value["manifest_hash"] = manifest_digest(value)
    validate_instance("rights_manifest", value, output.name)
    write_json(output, value)
    return value


def load_rights_manifest(path: Path) -> dict[str, Any]:
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 1_000_000:
            raise OSError("rights declaration is not a bounded regular file")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened = os.fstat(descriptor)
            raw = b""
            while len(raw) <= 1_000_000:
                block = os.read(descriptor, min(65_536, 1_000_001 - len(raw)))
                if not block:
                    break
                raw += block
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if (
            len(raw) != before.st_size
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
            )
            or (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        ):
            raise OSError("rights declaration changed while it was read")
        value: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AtlasError(
            "invalid rights manifest: unreadable, unstable, or malformed JSON"
        ) from exc
    validate_instance("rights_manifest", value, "rights manifest")
    if value["manifest_hash"] != manifest_digest(value):
        raise AtlasError("rights manifest hash is invalid")
    return value


def validate_rights_artifact(
    value: dict[str, Any],
    source_hash: str,
    source_id: str,
    run_mode: str,
    *,
    expected_manifest_hash: str | None = None,
    label: str = "rights manifest",
) -> None:
    """Schema-, digest-, linkage-, source-, permission-, and expiry-check one artifact."""
    validate_instance("rights_manifest", value, label)
    actual = manifest_digest(value)
    if value["manifest_hash"] != actual:
        raise AtlasError("rights manifest hash is invalid")
    if expected_manifest_hash is not None and actual != expected_manifest_hash:
        raise AtlasError("expected rights manifest hash does not match rights artifact")
    validate_run_mode_permissions(value, source_hash, source_id, run_mode)


def load_and_validate_rights(
    path: Path,
    source_hash: str,
    source_id: str,
    run_mode: str,
    *,
    expected_manifest_hash: str | None = None,
) -> dict[str, Any]:
    """Authoritative path for loading a persisted rights declaration."""
    value = load_rights_manifest(path)
    validate_rights_artifact(
        value,
        source_hash,
        source_id,
        run_mode,
        expected_manifest_hash=expected_manifest_hash,
        label="rights manifest",
    )
    return value


def validate_rights(
    value: dict[str, Any], source_hash: str, source_id: str, operation: str
) -> None:
    if operation not in OPERATIONS:
        raise AtlasError(f"unsupported requested operation: {operation}")
    if value["content_sha256"] != source_hash or value["source_id"] != source_id:
        raise AtlasError("rights manifest is not bound to the exact source content hash")
    if not value["permissions"].get(operation, False):
        raise AtlasError(f"rights manifest does not permit requested operation: {operation}")
    if value["expires_at"] is not None:
        try:
            expiry = datetime.fromisoformat(str(value["expires_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise AtlasError("rights manifest expiration is malformed") from exc
        if expiry.tzinfo is None:
            raise AtlasError("rights manifest expiration must include a timezone")
        if expiry <= datetime.now(UTC):
            raise AtlasError("rights manifest authorization has expired")


def required_permissions_for_run_mode(run_mode: str) -> tuple[str, ...]:
    """Return the complete permission closure for one executable run mode."""
    permissions = RUN_MODE_PERMISSIONS.get(run_mode)
    if permissions is None:
        raise AtlasError(
            f"unsupported run mode: {run_mode}; supported modes are {', '.join(RUN_MODES)}"
        )
    return permissions


def validate_run_mode_permissions(
    value: dict[str, Any], source_hash: str, source_id: str, run_mode: str
) -> None:
    """Require every permission implied by actual processing for a supported run mode."""
    for permission in required_permissions_for_run_mode(run_mode):
        validate_rights(value, source_hash, source_id, permission)


def controlled_fixture_manifest(
    media: Path,
    source_hash: str | None = None,
    source_id: str | None = None,
) -> dict[str, Any] | None:
    """Return a marker only when it is schema-valid and bound to these exact bytes."""
    marker = media.with_suffix(".fixture.json")
    try:
        marker_stat = os.lstat(marker)
    except OSError:
        return None
    if not stat.S_ISREG(marker_stat.st_mode) or marker_stat.st_size > 1_000_000:
        return None
    try:
        descriptor = os.open(
            marker,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened = os.fstat(descriptor)
            raw = os.read(descriptor, marker_stat.st_size + 1)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if (
            (marker_stat.st_dev, marker_stat.st_ino, marker_stat.st_size)
            != (opened.st_dev, opened.st_ino, opened.st_size)
            or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or len(raw) != marker_stat.st_size
        ):
            return None
        value: dict[str, Any] = json.loads(raw.decode("utf-8"))
        validate_instance("fixture_manifest", value, marker.name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AtlasError):
        return None
    exact_hash = source_hash if source_hash is not None else sha256_file(media)
    exact_source_id = source_id if source_id is not None else source_id_from_sha256(exact_hash)
    if value["content_sha256"] != exact_hash or value["source_id"] != exact_source_id:
        return None
    return value


def authorize_source_identity(
    media: Path,
    source_hash: str,
    source_id: str,
    rights_manifest: Path | None,
    run_mode: str,
    *,
    expected_manifest_hash: str | None = None,
    additional_permissions: tuple[str, ...] = (),
) -> AuthorizationPreflight:
    """Authorize a parser-free, independently measured source identity.

    The caller owns the file-descriptor and mutation checks that established
    ``source_hash`` and ``source_id``. This function never opens the media bytes.
    """
    required_permissions_for_run_mode(run_mode)
    fixture_marker = controlled_fixture_manifest(media, source_hash, source_id)
    if rights_manifest is None:
        if fixture_marker is None:
            raise AtlasError(
                "non-fixture media requires --rights-manifest bound to the exact source hash"
            )
        rights = fixture_rights(source_hash, source_id)
        fixture_status = "authorized_controlled_fixture"
    else:
        rights = load_and_validate_rights(
            rights_manifest,
            source_hash,
            source_id,
            run_mode,
            expected_manifest_hash=expected_manifest_hash,
        )
        fixture_status = (
            "authorized_controlled_fixture" if fixture_marker is not None else "not_fixture"
        )
    validate_rights_artifact(
        rights,
        source_hash,
        source_id,
        run_mode,
        expected_manifest_hash=expected_manifest_hash,
    )
    for permission in additional_permissions:
        validate_rights(rights, source_hash, source_id, permission)
    return AuthorizationPreflight(
        source_sha256=source_hash,
        source_id=source_id,
        fixture_status=fixture_status,
        fixture_manifest=fixture_marker,
        rights_declaration=rights,
        requested_run_mode=run_mode,
        authorized_at=datetime.now(UTC).isoformat(),
    )


def fixture_rights(source_hash: str, source_id: str) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_id": source_id,
        "content_sha256": source_hash,
        "operator_id": "OPR_000000000001",
        "rights_basis": "synthetic-controlled",
        "permissions": {operation: True for operation in OPERATIONS},
        "restrictions": [],
        "expires_at": None,
        "notes": "Automatically declared for a hash-bound AV-Atlas controlled fixture.",
        "created_at": "2026-07-13T00:00:00+00:00",
        "manifest_hash": "",
        "independently_reviewed": False,
        "review_record": None,
    }
    value["manifest_hash"] = manifest_digest(value)
    validate_instance("rights_manifest", value, "controlled fixture rights")
    return value


def authorize_media_preflight(
    media: Path,
    rights_manifest: Path | None,
    run_mode: str,
) -> AuthorizationPreflight:
    """Legacy parser-free authorization wrapper; processing uses ``stable_input``."""
    try:
        before = os.lstat(media)
    except OSError as exc:
        raise AtlasError("media source is unavailable") from exc
    if not stat.S_ISREG(before.st_mode):
        raise AtlasError("media source must be a regular non-symlink file")
    source_hash = sha256_file(media)
    try:
        after = os.lstat(media)
    except OSError as exc:
        raise AtlasError("media source changed during authorization") from exc
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise AtlasError("media source changed during authorization")
    source_id = source_id_from_sha256(source_hash)
    return authorize_source_identity(media, source_hash, source_id, rights_manifest, run_mode)
