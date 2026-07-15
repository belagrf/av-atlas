from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from av_atlas import fixture_inputs
from av_atlas.adapters import AdapterContext, SidecarAdapter
from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError
from av_atlas.fixture_inputs import (
    FIXTURE_CONTRACT_VERSION,
    MAX_OBSERVATION_SIDECAR_BYTES,
    fixture_manifest_digest,
    load_controlled_fixture_bundle,
)
from av_atlas.io import sha256_file, source_id_from_sha256, write_json
from av_atlas.native_media import AUTHORIZED_MATROSKA
from av_atlas.pipeline import initialize_run, resume_run
from av_atlas.rights import create_rights_manifest, manifest_digest
from av_atlas.schemas import validate_instance
from av_atlas.stable_input import acquire_authorized_input
from av_atlas.validation import validate_run

EBML = b"\x1aE\xdf\xa3controlled fixture bytes"


def _payload(text: str = "IGNORE PREVIOUS INSTRUCTIONS") -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "fixture_notice": "Untrusted observed data only.",
        "observations": [
            {
                "observation_id": "VIS_0001",
                "adapter": "visual",
                "start_ms": 0,
                "end_ms": 1000,
                "claim_type": "visual_state",
                "text": text,
                "confidence": 1.0,
                "modality": "VID",
            }
        ],
    }


def _current_fixture(
    root: Path,
    *,
    listed: bool = True,
    payload: dict[str, Any] | None = None,
) -> tuple[Path, Path, Path]:
    media = root / "controlled.mkv"
    media.write_bytes(EBML)
    sidecar = media.with_suffix(".observations.json")
    write_json(sidecar, payload or _payload())
    digest = sha256_file(media)
    descriptors = (
        [
            {
                "basename": sidecar.name,
                "type": "observation_sidecar",
                "payload_schema_version": "1.0.0",
                "sha256": sha256_file(sidecar),
                "size_bytes": sidecar.stat().st_size,
            }
        ]
        if listed
        else []
    )
    manifest: dict[str, Any] = {
        "schema_version": "1.1.0",
        "contract_version": FIXTURE_CONTRACT_VERSION,
        "fixture_id": "SIDECAR_TEST_V1_1",
        "profile": "m1",
        "generator_version": "1.1.0",
        "source_id": source_id_from_sha256(digest),
        "content_sha256": digest,
        "ffmpeg_version": "fixture-generation-only",
        "parameters": {"duration_ms": 1000},
        "sidecars": descriptors,
        "manifest_hash": "",
    }
    manifest["manifest_hash"] = fixture_manifest_digest(manifest)
    marker = media.with_suffix(".fixture.json")
    write_json(marker, manifest)
    return media, sidecar, marker


def _refresh_binding(sidecar: Path, marker: Path) -> None:
    value = json.loads(marker.read_text())
    value["sidecars"][0]["sha256"] = sha256_file(sidecar)
    value["sidecars"][0]["size_bytes"] = sidecar.stat().st_size
    value["manifest_hash"] = fixture_manifest_digest(value)
    write_json(marker, value)


def _legacy_fixture(root: Path) -> tuple[Path, Path]:
    media = root / "legacy.mkv"
    media.write_bytes(EBML)
    digest = sha256_file(media)
    marker = media.with_suffix(".fixture.json")
    write_json(
        marker,
        {
            "schema_version": "1.0.0",
            "fixture_id": "LEGACY_FIXTURE_V1",
            "profile": "m1",
            "generator_version": "1.0.0",
            "source_id": source_id_from_sha256(digest),
            "content_sha256": digest,
            "ffmpeg_version": "fixture-generation-only",
            "parameters": {},
        },
    )
    return media, marker


def _load(media: Path) -> fixture_inputs.ControlledFixtureBundle | None:
    digest = sha256_file(media)
    return load_controlled_fixture_bundle(media, digest, source_id_from_sha256(digest))


def _run_bytes(run_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }


def _rights(media: Path, path: Path, basis: str = "synthetic-controlled") -> Path:
    create_rights_manifest(
        media,
        path,
        "fixture-sidecar-test",
        basis,
        {"analysis", "derivative_artifact_retention"},
    )
    return path


def test_fixture_schema_accepts_legacy_and_hash_bound_current_contract(tmp_path: Path) -> None:
    legacy, legacy_marker = _legacy_fixture(tmp_path)
    current, sidecar, current_marker = _current_fixture(tmp_path)
    validate_instance("fixture_manifest", json.loads(legacy_marker.read_text()), legacy_marker.name)
    validate_instance(
        "fixture_manifest", json.loads(current_marker.read_text()), current_marker.name
    )
    bundle = _load(current)
    assert bundle is not None
    assert bundle.manifest["schema_version"] == "1.1.0"
    assert bundle.manifest["sidecars"] == [
        {
            "basename": sidecar.name,
            "type": "observation_sidecar",
            "payload_schema_version": "1.0.0",
            "sha256": sha256_file(sidecar),
            "size_bytes": sidecar.stat().st_size,
        }
    ]
    assert _load(legacy) is not None


@pytest.mark.parametrize(
    "mutation",
    ["unknown_manifest_key", "unknown_sidecar_key", "unknown_type", "zero_size", "over_limit"],
)
def test_fixture_schema_rejects_unsafe_current_contract_values(
    tmp_path: Path, mutation: str
) -> None:
    _, _, marker = _current_fixture(tmp_path)
    value = json.loads(marker.read_text())
    if mutation == "unknown_manifest_key":
        value["unexpected"] = True
    elif mutation == "unknown_sidecar_key":
        value["sidecars"][0]["unexpected"] = True
    elif mutation == "unknown_type":
        value["sidecars"][0]["type"] = "arbitrary"
    elif mutation == "zero_size":
        value["sidecars"][0]["size_bytes"] = 0
    else:
        value["sidecars"][0]["size_bytes"] = MAX_OBSERVATION_SIDECAR_BYTES + 1
    value["manifest_hash"] = fixture_manifest_digest(value)
    with pytest.raises(AtlasError, match="schema validation"):
        validate_instance("fixture_manifest", value, "unsafe fixture")


def test_duplicate_observation_ids_are_rejected_after_schema_validation(tmp_path: Path) -> None:
    payload = _payload()
    payload["observations"].append(dict(payload["observations"][0]))
    media, _, _ = _current_fixture(tmp_path, payload=payload)
    with pytest.raises(AtlasError, match="duplicate observation IDs"):
        _load(media)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "hash_mismatch",
        "declared_size_mismatch",
        "symlink",
        "malformed",
        "schema_invalid",
        "oversized_matching_descriptor",
        "oversized_lying_descriptor",
        "unlisted",
        "stale_manifest_hash",
    ],
)
def test_invalid_bound_sidecar_fails_before_parser_or_run_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    media, sidecar, marker = _current_fixture(tmp_path, listed=mutation != "unlisted")
    rights = _rights(media, tmp_path / "rights.json")
    if mutation == "missing":
        sidecar.unlink()
    elif mutation == "hash_mismatch":
        raw = sidecar.read_bytes()
        sidecar.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    elif mutation == "declared_size_mismatch":
        value = json.loads(marker.read_text())
        value["sidecars"][0]["size_bytes"] -= 1
        value["manifest_hash"] = fixture_manifest_digest(value)
        write_json(marker, value)
    elif mutation == "symlink":
        target = tmp_path / "exact-target.json"
        target.write_bytes(sidecar.read_bytes())
        sidecar.unlink()
        sidecar.symlink_to(target)
    elif mutation == "malformed":
        sidecar.write_text("{malformed")
        _refresh_binding(sidecar, marker)
    elif mutation == "schema_invalid":
        write_json(sidecar, {"schema_version": "1.0.0", "observations": []})
        _refresh_binding(sidecar, marker)
    elif mutation.startswith("oversized"):
        sidecar.write_bytes(b"x" * (MAX_OBSERVATION_SIDECAR_BYTES + 1))
        value = json.loads(marker.read_text())
        value["sidecars"][0]["sha256"] = sha256_file(sidecar)
        if mutation == "oversized_matching_descriptor":
            value["sidecars"][0]["size_bytes"] = sidecar.stat().st_size
        value["manifest_hash"] = fixture_manifest_digest(value)
        write_json(marker, value)
    elif mutation == "stale_manifest_hash":
        value = json.loads(marker.read_text())
        value["parameters"]["changed"] = True
        write_json(marker, value)
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("invalid sidecar must fail before parser")

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    run_dir = tmp_path / "run"
    with pytest.raises(AtlasError):
        initialize_run(
            media,
            Path(__file__).parents[2] / "configs/baseline.yaml",
            run_dir,
            rights_manifest=rights,
        )
    assert calls == 0
    assert not run_dir.exists()


@pytest.mark.parametrize(
    "basename",
    ["../outside.json", "/absolute.json", "folder\\outside.json", "wrong.json"],
)
def test_fixture_sidecar_basename_must_be_plain_and_canonical(
    tmp_path: Path, basename: str
) -> None:
    media, _, marker = _current_fixture(tmp_path)
    value = json.loads(marker.read_text())
    value["sidecars"][0]["basename"] = basename
    value["manifest_hash"] = fixture_manifest_digest(value)
    write_json(marker, value)
    with pytest.raises(AtlasError):
        _load(media)


def test_legacy_or_nonfixture_adjacent_sidecar_cannot_acquire_fixture_trust(
    tmp_path: Path,
) -> None:
    legacy, _ = _legacy_fixture(tmp_path)
    write_json(legacy.with_suffix(".observations.json"), _payload())
    with pytest.raises(AtlasError, match="legacy fixture manifest cannot authorize"):
        _load(legacy)
    nonfixture = tmp_path / "nonfixture.mkv"
    nonfixture.write_bytes(EBML)
    write_json(nonfixture.with_suffix(".observations.json"), _payload())
    assert _load(nonfixture) is None


def test_fabricated_nonfixture_sidecar_cannot_authorize_a_run_or_start_a_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "nonfixture.mkv"
    media.write_bytes(EBML)
    write_json(media.with_suffix(".observations.json"), _payload())
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("a fabricated sidecar must not reach a native parser")

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    run_dir = tmp_path / "run"
    with pytest.raises(AtlasError, match="requires --rights-manifest"):
        initialize_run(
            media,
            Path(__file__).parents[2] / "configs/baseline.yaml",
            run_dir,
        )
    assert calls == 0
    assert not run_dir.exists()


def test_forged_current_bundle_without_rights_cannot_authorize_or_inject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media, _, _ = _current_fixture(tmp_path)
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("forged bundle must fail before a parser or adapter")

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(
        "av_atlas.rights.load_controlled_fixture_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("no-rights denial must not consult a fixture marker")
        ),
    )
    run_dir = tmp_path / "run"
    with pytest.raises(AtlasError, match="requires --rights-manifest"):
        initialize_run(media, Path(__file__).parents[2] / "configs/baseline.yaml", run_dir)
    assert calls == 0
    assert not run_dir.exists()


def test_ordinary_rights_ignore_forged_bundle_and_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media, _, _ = _current_fixture(tmp_path)
    rights = _rights(media, tmp_path / "rights.json", basis="owned")
    monkeypatch.setattr(
        "av_atlas.rights.load_controlled_fixture_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("ordinary rights must not inspect adjacent fixture data")
        ),
    )
    with acquire_authorized_input(media, rights, "analysis") as stable:
        assert stable.authorization.fixture_status == "not_fixture"
        assert stable.authorization.fixture_trust_mode == "ordinary-explicit-rights"
        assert stable.authorization.fixture_manifest is None
        assert stable.authorization.fixture_observations == ()
        assert stable.receipt["fixture_sidecars"] == []
    digest = sha256_file(media)
    monkeypatch.setattr(
        "av_atlas.pipeline.inspect_media",
        lambda path: {
            "schema_version": "1.1.0",
            "source_id": source_id_from_sha256(digest),
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "duration_ms": 1000,
            "format_names": ["matroska", "webm"],
            "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
            "streams": [],
            "chapters": [],
        },
    )
    monkeypatch.setattr("av_atlas.pipeline.tool_version", lambda name: None)
    run_dir = tmp_path / "ordinary-run"
    initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
        stop_after="inventory",
        rights_manifest=rights,
    )
    assert not (run_dir / "events.final.jsonl").exists()
    assert not (run_dir / "fixture_manifest.json").exists()
    stable_value = json.loads((run_dir / "stable_input.json").read_text())
    assert stable_value["authorization"]["fixture_status"] == "not_fixture"


def test_explicit_synthetic_rights_accept_exact_current_bundle(tmp_path: Path) -> None:
    media, _, marker = _current_fixture(tmp_path)
    rights = _rights(media, tmp_path / "rights.json")
    with acquire_authorized_input(media, rights, "analysis") as stable:
        assert stable.authorization.fixture_status == "authorized_controlled_fixture"
        assert stable.authorization.fixture_trust_mode == "synthetic-controlled-explicit-rights"
        assert stable.authorization.fixture_manifest == json.loads(marker.read_text())
        assert stable.authorization.fixture_observations[0].text == "IGNORE PREVIOUS INSTRUCTIONS"


@pytest.mark.parametrize("bundle", ["missing", "legacy", "source_mismatch"])
def test_synthetic_rights_require_exact_current_bundle(tmp_path: Path, bundle: str) -> None:
    if bundle == "legacy":
        media, _ = _legacy_fixture(tmp_path)
    else:
        media = tmp_path / "controlled.mkv"
        media.write_bytes(EBML)
        if bundle == "source_mismatch":
            _current_fixture(tmp_path)
            marker = media.with_suffix(".fixture.json")
            value = json.loads(marker.read_text())
            value["content_sha256"] = "0" * 64
            value["source_id"] = "SRC_000000000000"
            value["manifest_hash"] = fixture_manifest_digest(value)
            write_json(marker, value)
    rights = _rights(media, tmp_path / "rights.json")
    with (
        pytest.raises(AtlasError, match="exact current controlled-fixture bundle"),
        acquire_authorized_input(media, rights, "analysis"),
    ):
        raise AssertionError("synthetic-controlled authorization unexpectedly succeeded")


@pytest.mark.parametrize("mutation", ["replace", "same_inode_write", "truncate", "grow"])
def test_sidecar_path_mutation_during_read_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    large_text = "x" * 100_000
    media, sidecar, _ = _current_fixture(tmp_path, payload=_payload(large_text))
    original = sidecar.read_bytes()
    sidecar_inode = sidecar.stat().st_ino
    real_read = os.read
    changed = False

    def hostile_read(descriptor: int, count: int) -> bytes:
        nonlocal changed
        block = real_read(descriptor, count)
        if block and not changed and os.fstat(descriptor).st_ino == sidecar_inode:
            changed = True
            if mutation == "replace":
                replacement = tmp_path / "replacement.json"
                replacement.write_bytes(original)
                replacement.replace(sidecar)
            elif mutation == "same_inode_write":
                sidecar.write_bytes(original)
            elif mutation == "truncate":
                sidecar.write_bytes(original[:100])
            else:
                sidecar.write_bytes(original + b" ")
        return block

    monkeypatch.setattr(fixture_inputs.os, "read", hostile_read)
    with pytest.raises(AtlasError, match="changed|replaced|bounded"):
        _load(media)


def test_verified_sidecar_is_immutable_and_never_reread_by_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media, sidecar, _ = _current_fixture(tmp_path)
    rights = _rights(media, tmp_path / "rights.json")
    config = BaselineConfig.load(Path(__file__).parents[2] / "configs/baseline.yaml")
    with acquire_authorized_input(media, rights, "analysis") as stable:
        verified = stable.authorization.fixture_observations
        sidecar.unlink()

        def forbidden(*args: object, **kwargs: object) -> str:
            raise AssertionError("adapter must not reread a fixture path")

        monkeypatch.setattr(Path, "read_text", forbidden)
        context = AdapterContext(
            stable.snapshot_path,
            {"duration_ms": 1000},
            tmp_path / "run",
            config,
            verified,
        )
        result = SidecarAdapter("visual").run(context)
    assert result.result.observations[0].text == "IGNORE PREVIOUS INSTRUCTIONS"
    assert result.result.status == "success"


@pytest.mark.parametrize("mutation", ["rewrite", "replace"])
def test_sidecar_mutation_after_snapshot_acquisition_cannot_change_ledger_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    media, sidecar, _ = _current_fixture(tmp_path)
    rights = _rights(media, tmp_path / "rights.json")
    original_hash = sha256_file(media)

    def inspect(path: Path) -> dict[str, Any]:
        # Acquisition and sidecar verification have completed before inventory.
        if mutation == "rewrite":
            sidecar.write_text("replacement must never become evidence")
        else:
            replacement = tmp_path / "replacement.json"
            write_json(replacement, _payload("replacement must never become evidence"))
            replacement.replace(sidecar)
        return {
            "schema_version": "1.1.0",
            "source_id": source_id_from_sha256(original_hash),
            "sha256": original_hash,
            "size_bytes": path.stat().st_size,
            "duration_ms": 1000,
            "format_names": ["matroska", "webm"],
            "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
            "streams": [],
            "chapters": [],
        }

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.pipeline.tool_version", lambda name: None)
    run_dir = tmp_path / "run"
    initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
        rights_manifest=rights,
    )
    ledger = (run_dir / "events.final.jsonl").read_text()
    assert "IGNORE PREVIOUS INSTRUCTIONS" in ledger
    assert "replacement must never become evidence" not in ledger


@pytest.mark.parametrize("binding", ["stale", "validly_rehashed"])
def test_changed_sidecar_before_resume_fails_before_adapter_and_preserves_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, binding: str
) -> None:
    media, sidecar, _ = _current_fixture(tmp_path)
    rights = _rights(media, tmp_path / "rights.json")
    digest = sha256_file(media)

    def inspect(path: Path) -> dict[str, Any]:
        return {
            "schema_version": "1.1.0",
            "source_id": source_id_from_sha256(digest),
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "duration_ms": 1000,
            "format_names": ["matroska", "webm"],
            "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
            "streams": [],
            "chapters": [],
        }

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.pipeline.tool_version", lambda name: None)
    run_dir = tmp_path / "run"
    initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
        stop_after="inventory",
        rights_manifest=rights,
    )
    before = _run_bytes(run_dir)
    if binding == "validly_rehashed":
        write_json(sidecar, _payload("changed after interruption"))
        _refresh_binding(sidecar, media.with_suffix(".fixture.json"))
    else:
        sidecar.write_text("changed after interruption")
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("resume must fail before adapter or parser")

    monkeypatch.setattr("av_atlas.pipeline._complete", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(AtlasError, match="sidecar|fixture"):
        resume_run(run_dir, media)
    after = _run_bytes(run_dir)
    assert calls == 0
    assert after == before


def test_controlled_bundle_removal_before_resume_fails_without_run_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media, _, marker = _current_fixture(tmp_path)
    rights = _rights(media, tmp_path / "rights.json")
    digest = sha256_file(media)

    def inspect(path: Path) -> dict[str, Any]:
        return {
            "schema_version": "1.1.0",
            "source_id": source_id_from_sha256(digest),
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "duration_ms": 1000,
            "format_names": ["matroska", "webm"],
            "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
            "streams": [],
            "chapters": [],
        }

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.pipeline.tool_version", lambda name: None)
    run_dir = tmp_path / "run"
    initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
        stop_after="inventory",
        rights_manifest=rights,
    )
    before = _run_bytes(run_dir)
    marker.unlink()
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("fixture transition must not reach an adapter or parser")

    monkeypatch.setattr("av_atlas.pipeline._complete", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(AtlasError, match="fixture"):
        resume_run(run_dir, media)
    assert calls == 0
    assert _run_bytes(run_dir) == before


def test_ordinary_resume_ignores_new_adjacent_fixture_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "controlled.mkv"
    media.write_bytes(EBML)
    rights = _rights(media, tmp_path / "rights.json", basis="owned")
    digest = sha256_file(media)

    def inspect(path: Path) -> dict[str, Any]:
        return {
            "schema_version": "1.1.0",
            "source_id": source_id_from_sha256(digest),
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "duration_ms": 1000,
            "format_names": ["matroska", "webm"],
            "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
            "streams": [],
            "chapters": [],
        }

    monkeypatch.setattr("av_atlas.pipeline.inspect_media", inspect)
    monkeypatch.setattr("av_atlas.pipeline.tool_version", lambda name: None)
    run_dir = tmp_path / "run"
    initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
        stop_after="inventory",
        rights_manifest=rights,
    )
    _current_fixture(tmp_path)

    def complete(*args: object, **kwargs: object) -> None:
        assert kwargs["sidecar_observations"] == ()
        return None

    monkeypatch.setattr("av_atlas.pipeline._complete", complete)
    resume_run(run_dir, media)
    stable = json.loads((run_dir / "stable_input.json").read_text())
    assert stable["authorization"]["fixture_status"] == "not_fixture"
    assert stable["authorization"]["fixture_trust_mode"] == "ordinary-explicit-rights"
    assert not (run_dir / "fixture_manifest.json").exists()


@pytest.mark.parametrize("transition", ["ordinary_to_controlled", "controlled_to_ordinary"])
def test_resume_cannot_transition_between_ordinary_and_controlled_trust(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transition: str
) -> None:
    if transition == "controlled_to_ordinary":
        media, _, _ = _current_fixture(tmp_path)
        rights = _rights(media, tmp_path / "rights.json")
    else:
        media = tmp_path / "controlled.mkv"
        media.write_bytes(EBML)
        rights = _rights(media, tmp_path / "rights.json", basis="owned")
    digest = sha256_file(media)

    monkeypatch.setattr(
        "av_atlas.pipeline.inspect_media",
        lambda path: {
            "schema_version": "1.1.0",
            "source_id": source_id_from_sha256(digest),
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "duration_ms": 1000,
            "format_names": ["matroska", "webm"],
            "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
            "streams": [],
            "chapters": [],
        },
    )
    monkeypatch.setattr("av_atlas.pipeline.tool_version", lambda name: None)
    run_dir = tmp_path / "run"
    initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
        stop_after="inventory",
        rights_manifest=rights,
    )
    if transition == "ordinary_to_controlled":
        _, _, marker = _current_fixture(tmp_path)
        basis = "synthetic-controlled"
        trust_mode = "synthetic-controlled-explicit-rights"
        fixture_hash: str | None = json.loads(marker.read_text())["manifest_hash"]
    else:
        basis = "owned"
        trust_mode = "ordinary-explicit-rights"
        fixture_hash = None
    rights_value = json.loads((run_dir / "rights_manifest.json").read_text())
    rights_value["rights_basis"] = basis
    rights_value["manifest_hash"] = manifest_digest(rights_value)
    write_json(run_dir / "rights_manifest.json", rights_value)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    manifest["rights"].update(
        {
            "manifest_hash": rights_value["manifest_hash"],
            "basis": basis,
            "fixture_trust_mode": trust_mode,
            "fixture_manifest_hash": fixture_hash,
        }
    )
    write_json(run_dir / "run_manifest.json", manifest)
    before = _run_bytes(run_dir)
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("trust transition must fail before parser or adapter")

    monkeypatch.setattr("av_atlas.pipeline._complete", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(AtlasError, match="fixture trust|fixture trust state"):
        resume_run(run_dir, media)
    assert calls == 0
    assert _run_bytes(run_dir) == before


def test_validation_rejects_impossible_controlled_fixture_trust_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media, _, _ = _current_fixture(tmp_path)
    rights = _rights(media, tmp_path / "rights.json")
    digest = sha256_file(media)
    monkeypatch.setattr(
        "av_atlas.pipeline.inspect_media",
        lambda path: {
            "schema_version": "1.1.0",
            "source_id": source_id_from_sha256(digest),
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "duration_ms": 1000,
            "format_names": ["matroska", "webm"],
            "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
            "streams": [],
            "chapters": [],
        },
    )
    monkeypatch.setattr("av_atlas.pipeline.tool_version", lambda name: None)
    run_dir = tmp_path / "run"
    initialize_run(
        media,
        Path(__file__).parents[2] / "configs/baseline.yaml",
        run_dir,
        rights_manifest=rights,
    )
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    manifest["rights"].update(
        {
            "basis": "owned",
            "fixture_trust_mode": "ordinary-explicit-rights",
            "fixture_manifest_hash": None,
        }
    )
    write_json(run_dir / "run_manifest.json", manifest)
    with pytest.raises(AtlasError, match="validation failed"):
        validate_run(run_dir)
    report = json.loads((run_dir / "quality_report.json").read_text())
    assert any("impossible fixture trust state" in error for error in report["errors"])
