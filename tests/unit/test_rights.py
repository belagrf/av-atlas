from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from av_atlas.errors import AtlasError
from av_atlas.rights import (
    create_rights_manifest,
    load_and_validate_rights,
    load_rights_manifest,
    manifest_digest,
    validate_rights,
)


def test_rights_manifest_is_hashed_private_and_source_bound(tmp_path: Path) -> None:
    media = tmp_path / "source.bin"
    media.write_bytes(b"authorized controlled bytes")
    path = tmp_path / "rights.json"
    value = create_rights_manifest(
        media,
        path,
        "operator@example.invalid",
        "owned",
        {"analysis", "derivative_artifact_retention"},
    )
    assert value["operator_id"].startswith("OPR_")
    assert "operator@example.invalid" not in path.read_text(encoding="utf-8")
    loaded = load_rights_manifest(path)
    validate_rights(loaded, value["content_sha256"], value["source_id"], "analysis")
    with pytest.raises(AtlasError, match="exact source"):
        validate_rights(loaded, "0" * 64, value["source_id"], "analysis")
    with pytest.raises(AtlasError, match="does not permit"):
        validate_rights(loaded, value["content_sha256"], value["source_id"], "training")


def test_expired_and_tampered_rights_fail_closed(tmp_path: Path) -> None:
    media = tmp_path / "source.bin"
    media.write_bytes(b"x")
    expired = tmp_path / "expired.json"
    value = create_rights_manifest(
        media,
        expired,
        "operator",
        "licensed",
        {"analysis"},
        expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
    )
    with pytest.raises(AtlasError, match="expired"):
        validate_rights(value, value["content_sha256"], value["source_id"], "analysis")
    text = expired.read_text(encoding="utf-8").replace('"notes": ""', '"notes": "tampered"')
    expired.write_text(text, encoding="utf-8")
    with pytest.raises(AtlasError, match="manifest hash"):
        load_rights_manifest(expired)


def test_ocr_analysis_evaluation_and_retention_permissions_are_independent(
    tmp_path: Path,
) -> None:
    media = tmp_path / "source.bin"
    media.write_bytes(b"rights-gated OCR")
    value = create_rights_manifest(
        media,
        tmp_path / "rights.json",
        "operator",
        "owned",
        {"analysis"},
    )
    validate_rights(value, value["content_sha256"], value["source_id"], "analysis")
    for operation in ("evaluation", "derivative_artifact_retention"):
        with pytest.raises(AtlasError, match="does not permit"):
            validate_rights(value, value["content_sha256"], value["source_id"], operation)


def test_authoritative_loader_rejects_stale_digest_and_stale_run_linkage(tmp_path: Path) -> None:
    media = tmp_path / "source.bin"
    media.write_bytes(b"source")
    path = tmp_path / "rights.json"
    value = create_rights_manifest(
        media,
        path,
        "operator",
        "owned",
        {"analysis", "derivative_artifact_retention"},
    )
    accepted_hash = value["manifest_hash"]
    value["permissions"]["analysis"] = False
    path.write_text(__import__("json").dumps(value))
    with pytest.raises(AtlasError, match="hash is invalid"):
        load_and_validate_rights(path, value["content_sha256"], value["source_id"], "analysis")
    value["manifest_hash"] = manifest_digest(value)
    path.write_text(__import__("json").dumps(value))
    with pytest.raises(AtlasError, match="run manifest rights hash"):
        load_and_validate_rights(
            path,
            value["content_sha256"],
            value["source_id"],
            "analysis",
            expected_manifest_hash=accepted_hash,
        )
