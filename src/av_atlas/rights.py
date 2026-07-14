"""Fail-closed operator rights declarations bound to exact source bytes."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from av_atlas.errors import AtlasError
from av_atlas.io import canonical_json, sha256_file, write_json
from av_atlas.schemas import validate_instance

OPERATIONS = (
    "analysis",
    "annotation",
    "training",
    "evaluation",
    "derivative_artifact_retention",
    "redistribution",
)


def _manifest_digest(value: dict[str, Any]) -> str:
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
        "source_id": f"SRC_{content_hash[:12].upper()}",
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
    value["manifest_hash"] = _manifest_digest(value)
    validate_instance("rights_manifest", value, output.name)
    write_json(output, value)
    return value


def load_rights_manifest(path: Path) -> dict[str, Any]:
    try:
        value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"invalid rights manifest {path.name}: {exc}") from exc
    validate_instance("rights_manifest", value, path.name)
    if value["manifest_hash"] != _manifest_digest(value):
        raise AtlasError("rights manifest hash is invalid")
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


def controlled_fixture_manifest(media: Path) -> dict[str, Any] | None:
    marker = media.with_suffix(".fixture.json")
    if not marker.is_file():
        return None
    try:
        value: dict[str, Any] = json.loads(marker.read_text(encoding="utf-8"))
        validate_instance("fixture_manifest", value, marker.name)
    except (OSError, json.JSONDecodeError, AtlasError):
        return None
    if value["content_sha256"] != sha256_file(media):
        return None
    return value


def fixture_rights(inventory: dict[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_id": inventory["source_id"],
        "content_sha256": inventory["sha256"],
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
    value["manifest_hash"] = _manifest_digest(value)
    validate_instance("rights_manifest", value, "controlled fixture rights")
    return value
