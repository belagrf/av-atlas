from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from av_atlas.errors import AtlasError
from av_atlas.fixture_inputs import FIXTURE_CONTRACT_VERSION, fixture_manifest_digest
from av_atlas.io import sha256_file, source_id_from_sha256, write_json
from av_atlas.pipeline import initialize_run
from av_atlas.rights import create_rights_manifest, manifest_digest


def _rights(media: Path, path: Path) -> dict[str, Any]:
    return create_rights_manifest(
        media,
        path,
        "test-operator",
        "owned",
        {"analysis", "derivative_artifact_retention"},
    )


def _inventory(media: Path) -> dict[str, Any]:
    digest = sha256_file(media)
    return {
        "schema_version": "1.0.0",
        "source_id": source_id_from_sha256(digest),
        "sha256": digest,
        "size_bytes": media.stat().st_size,
        "duration_ms": 1000,
        "format_names": ["test"],
        "streams": [],
        "chapters": [],
    }


def _fixture_marker(media: Path) -> None:
    digest = sha256_file(media)
    write_json(
        media.with_suffix(".fixture.json"),
        {
            "schema_version": "1.0.0",
            "fixture_id": "PREFLIGHT_TEST_V1",
            "profile": "m1",
            "generator_version": "1.0.0",
            "source_id": source_id_from_sha256(digest),
            "content_sha256": digest,
            "ffmpeg_version": "fixture-generation-only",
            "parameters": {},
        },
    )


def _current_fixture_marker(media: Path) -> None:
    digest = sha256_file(media)
    value: dict[str, Any] = {
        "schema_version": "1.1.0",
        "contract_version": FIXTURE_CONTRACT_VERSION,
        "fixture_id": "PREFLIGHT_TEST_V1_1",
        "profile": "m1",
        "generator_version": "1.1.0",
        "source_id": source_id_from_sha256(digest),
        "content_sha256": digest,
        "ffmpeg_version": "fixture-generation-only",
        "parameters": {},
        "sidecars": [],
        "manifest_hash": "",
    }
    value["manifest_hash"] = fixture_manifest_digest(value)
    write_json(media.with_suffix(".fixture.json"), value)


def _synthetic_rights(media: Path, path: Path) -> dict[str, Any]:
    return create_rights_manifest(
        media,
        path,
        "test-operator",
        "synthetic-controlled",
        {"analysis", "derivative_artifact_retention"},
    )


def _forbid_parsers(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        calls.append("external")
        raise AssertionError("external parser or adapter must not run before authorization")

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    return calls


def test_non_fixture_without_rights_fails_before_parser_or_run_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "untrusted.bin"
    media.write_bytes(b"not authorized")
    calls = _forbid_parsers(monkeypatch)
    run_dir = tmp_path / "run"
    with pytest.raises(AtlasError, match="requires --rights-manifest"):
        initialize_run(media, Path(__file__).parents[2] / "configs/baseline.yaml", run_dir)
    assert calls == []
    assert not run_dir.exists()


def test_forged_legacy_fixture_marker_without_rights_fails_before_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "forged.mkv"
    media.write_bytes(b"\x1aE\xdf\xa3forged legacy fixture")
    _fixture_marker(media)
    calls = _forbid_parsers(monkeypatch)
    run_dir = tmp_path / "run"
    with pytest.raises(AtlasError, match="requires --rights-manifest"):
        initialize_run(media, Path(__file__).parents[2] / "configs/baseline.yaml", run_dir)
    assert calls == []
    assert not run_dir.exists()


@pytest.mark.parametrize(
    ("mutation", "operation", "expected"),
    [
        ("stale_digest", "analysis", "hash is invalid"),
        ("source_hash", "analysis", "exact source"),
        ("source_id", "analysis", "exact source"),
        ("analysis_denied", "analysis", "requested operation"),
        ("evaluation_without_analysis", "evaluation", "requested operation: analysis"),
        ("retention_denied", "analysis", "derivative_artifact_retention"),
        ("expired", "analysis", "expired"),
        ("operation_denied", "evaluation", "requested operation"),
    ],
)
def test_invalid_explicit_rights_fail_before_every_parser_and_derivative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    operation: str,
    expected: str,
) -> None:
    media = tmp_path / "operator.bin"
    media.write_bytes(b"authorized bytes")
    rights_path = tmp_path / "rights.json"
    value = _rights(media, rights_path)
    if mutation == "stale_digest":
        value["notes"] = "altered without updating checksum"
    elif mutation == "source_hash":
        value["content_sha256"] = "0" * 64
    elif mutation == "source_id":
        value["source_id"] = "SRC_000000000000"
    elif mutation == "analysis_denied":
        value["permissions"]["analysis"] = False
    elif mutation == "evaluation_without_analysis":
        value["permissions"]["analysis"] = False
        value["permissions"]["evaluation"] = True
    elif mutation == "retention_denied":
        value["permissions"]["derivative_artifact_retention"] = False
    elif mutation == "expired":
        value["expires_at"] = "2000-01-01T00:00:00+00:00"
    if mutation != "stale_digest":
        value["manifest_hash"] = manifest_digest(value)
    rights_path.write_text(json.dumps(value), encoding="utf-8")
    calls = _forbid_parsers(monkeypatch)
    run_dir = tmp_path / "run"
    with pytest.raises(AtlasError, match=expected):
        initialize_run(
            media,
            Path(__file__).parents[2] / "configs/baseline.yaml",
            run_dir,
            rights_manifest=rights_path,
            operation=operation,
        )
    assert calls == []
    assert not run_dir.exists()


@pytest.mark.parametrize(
    "run_mode",
    ["annotation", "training", "redistribution", "derivative_artifact_retention"],
)
def test_unsupported_run_modes_fail_before_every_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run_mode: str
) -> None:
    media = tmp_path / "operator.bin"
    media.write_bytes(b"authorized bytes")
    rights_path = tmp_path / "rights.json"
    create_rights_manifest(
        media,
        rights_path,
        "test-operator",
        "owned",
        {
            "analysis",
            "annotation",
            "training",
            "evaluation",
            "derivative_artifact_retention",
            "redistribution",
        },
    )
    calls = _forbid_parsers(monkeypatch)
    run_dir = tmp_path / "run"
    with pytest.raises(AtlasError, match="unsupported run mode"):
        initialize_run(
            media,
            Path(__file__).parents[2] / "configs/baseline.yaml",
            run_dir,
            rights_manifest=rights_path,
            operation=run_mode,
        )
    assert calls == []
    assert not run_dir.exists()


def test_valid_non_fixture_is_inspected_once_after_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "operator.bin"
    media.write_bytes(b"authorized bytes")
    rights_path = tmp_path / "rights.json"
    _rights(media, rights_path)
    calls = 0
    snapshot_path: Path | None = None

    def inspect(path: Path) -> dict[str, Any]:
        nonlocal calls, snapshot_path
        calls += 1
        snapshot_path = path
        assert path != media
        assert path.read_bytes() == media.read_bytes()
        return _inventory(path)

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.pipeline.tool_version", lambda name: None)
    run_dir = tmp_path / "run"
    initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
        stop_after="inventory",
        rights_manifest=rights_path,
    )
    assert calls == 1
    assert snapshot_path is not None and not snapshot_path.exists()
    assert (run_dir / "inventory.json").is_file()


def test_valid_evaluation_mode_requires_and_records_complete_permission_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "operator.bin"
    media.write_bytes(b"authorized evaluation bytes")
    rights_path = tmp_path / "rights.json"
    create_rights_manifest(
        media,
        rights_path,
        "test-operator",
        "owned",
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    calls = 0

    def inspect(path: Path) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _inventory(path)

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.pipeline.tool_version", lambda name: None)
    run_dir = tmp_path / "run"
    initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
        stop_after="inventory",
        rights_manifest=rights_path,
        operation="evaluation",
    )
    assert calls == 1
    assert json.loads((run_dir / "run_manifest.json").read_text())["operation"] == "evaluation"


def test_valid_fixture_is_inspected_only_after_fixture_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "controlled.bin"
    media.write_bytes(b"controlled fixture bytes")
    _current_fixture_marker(media)
    rights = tmp_path / "rights.json"
    _synthetic_rights(media, rights)
    authorized = False
    calls = 0
    from av_atlas import stable_input

    original = stable_input.authorize_source_identity

    def authorize(*args: Any, **kwargs: Any) -> Any:
        nonlocal authorized
        result = original(*args, **kwargs)
        authorized = result.fixture_status == "authorized_controlled_fixture"
        return result

    def inspect(path: Path) -> dict[str, Any]:
        nonlocal calls
        assert authorized is True
        calls += 1
        return _inventory(path)

    monkeypatch.setattr(stable_input, "authorize_source_identity", authorize)
    monkeypatch.setattr("av_atlas.pipeline.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.pipeline.tool_version", lambda name: None)
    initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        tmp_path / "run",
        stop_after="inventory",
        rights_manifest=rights,
    )
    assert calls == 1


def test_changed_source_inventory_is_rejected_before_run_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "controlled.bin"
    media.write_bytes(b"controlled fixture bytes")
    rights = tmp_path / "rights.json"
    _rights(media, rights)
    changed = _inventory(media)
    changed["sha256"] = "f" * 64
    changed["source_id"] = source_id_from_sha256(changed["sha256"])
    calls = 0

    def inspect(path: Path) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return changed

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", inspect)
    run_dir = tmp_path / "run"
    with pytest.raises(AtlasError, match="snapshot identity disagrees"):
        initialize_run(
            media,
            Path(__file__).parents[2] / "configs/baseline.yaml",
            run_dir,
            rights_manifest=rights,
        )
    assert calls == 1
    assert not run_dir.exists()


def test_fixture_marker_for_other_bytes_does_not_authorize_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "controlled.bin"
    media.write_bytes(b"first bytes")
    _fixture_marker(media)
    media.write_bytes(b"changed bytes")
    rights = tmp_path / "rights.json"
    _synthetic_rights(media, rights)
    calls = _forbid_parsers(monkeypatch)
    with pytest.raises(AtlasError, match="exact current controlled-fixture bundle"):
        initialize_run(
            media,
            Path(__file__).parents[2] / "configs/baseline.yaml",
            tmp_path / "run",
            rights_manifest=rights,
        )
    assert calls == []
