from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from av_atlas import media, stable_input
from av_atlas.cli import main
from av_atlas.io import sha256_file, source_id_from_sha256, write_json
from av_atlas.rights import create_rights_manifest, manifest_digest


def _rights(source: Path, path: Path) -> Path:
    create_rights_manifest(
        source,
        path,
        "inspection-test",
        "owned",
        {"analysis", "derivative_artifact_retention"},
    )
    return path


def _ffprobe_payload(subtitle: bool = False) -> dict[str, Any]:
    streams = []
    if subtitle:
        streams.append(
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "duration": "1.0",
                "tags": {"language": "eng"},
                "disposition": {},
            }
        )
    return {
        "format": {"duration": "1.0", "format_name": "matroska,webm"},
        "streams": streams,
    }


def _fixture_marker(source: Path) -> None:
    digest = sha256_file(source)
    write_json(
        source.with_suffix(".fixture.json"),
        {
            "schema_version": "1.0.0",
            "fixture_id": "INSPECTION_FIXTURE_V1",
            "profile": "m1",
            "generator_version": "1.0.0",
            "source_id": source_id_from_sha256(digest),
            "content_sha256": digest,
            "ffmpeg_version": "fixture-generation-only",
            "parameters": {},
        },
    )


@pytest.mark.parametrize("command", ["inspect", "inspect-subtitles"])
def test_nonfixture_inspection_is_rights_gated_and_parser_sees_only_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    source = tmp_path / "operator;$(never-run).mkv"
    source.write_bytes(b"\x1aE\xdf\xa3authorized fake media")
    rights = _rights(source, tmp_path / "rights.json")
    parser_inputs: list[Path] = []

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        parser_inputs.append(Path(arguments[-1]))
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout=json.dumps(_ffprobe_payload(command == "inspect-subtitles")),
            stderr="",
        )

    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(media, "_run", fake_run)
    assert main([command, str(source), "--rights-manifest", str(rights)]) == 0
    assert len(parser_inputs) == 1
    snapshot = parser_inputs[0]
    assert snapshot != source
    assert snapshot.name == "source.snapshot"
    assert not snapshot.exists()
    assert not (tmp_path / "never-run").exists()


@pytest.mark.parametrize(
    "mutation",
    ["missing", "stale_hash", "analysis_denied", "retention_denied", "expired", "mismatch"],
)
@pytest.mark.parametrize("command", ["inspect", "inspect-subtitles"])
def test_inspection_denial_invokes_no_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    command: str,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    rights = _rights(source, tmp_path / "rights.json")
    value = json.loads(rights.read_text())
    rights_argument: list[str] = ["--rights-manifest", str(rights)]
    if mutation == "missing":
        rights_argument = []
    elif mutation == "stale_hash":
        value["notes"] = "changed without digest"
    elif mutation == "analysis_denied":
        value["permissions"]["analysis"] = False
        value["manifest_hash"] = manifest_digest(value)
    elif mutation == "retention_denied":
        value["permissions"]["derivative_artifact_retention"] = False
        value["manifest_hash"] = manifest_digest(value)
    elif mutation == "expired":
        value["expires_at"] = "2000-01-01T00:00:00+00:00"
        value["manifest_hash"] = manifest_digest(value)
    else:
        value["content_sha256"] = "0" * 64
        value["source_id"] = source_id_from_sha256("0" * 64)
        value["manifest_hash"] = manifest_digest(value)
    rights.write_text(json.dumps(value))
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("parser must not be called")

    monkeypatch.setattr(media, "inspect_media", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert main([command, str(source), *rights_argument]) == 2
    assert calls == 0


@pytest.mark.parametrize("command", ["inspect", "inspect-subtitles"])
def test_controlled_fixture_inspection_auto_authorizes_exact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    source = tmp_path / "controlled.bin"
    source.write_bytes(b"\x1aE\xdf\xa3controlled inspection bytes")
    _fixture_marker(source)
    parser_inputs: list[Path] = []

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        parser_inputs.append(Path(arguments[-1]))
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout=json.dumps(_ffprobe_payload(command == "inspect-subtitles")),
            stderr="",
        )

    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(media, "_run", fake_run)
    assert main([command, str(source)]) == 0
    assert len(parser_inputs) == 1
    assert parser_inputs[0] != source
    assert not parser_inputs[0].exists()


def test_inspection_inventory_preserves_original_identity_without_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "private-name.mkv"
    source.write_bytes(b"\x1aE\xdf\xa3authorized fake media")
    rights = _rights(source, tmp_path / "rights.json")

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            arguments, 0, stdout=json.dumps(_ffprobe_payload()), stderr=""
        )

    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(media, "_run", fake_run)
    assert main(["inspect", str(source), "--rights-manifest", str(rights)]) == 0
    output = capsys.readouterr().out
    value = json.loads(output)
    assert value["sha256"] == sha256_file(source)
    assert value["source_id"] == source_id_from_sha256(value["sha256"])
    assert str(source) not in output
    assert source.name not in output
    assert "source.snapshot" not in output


def test_parser_reads_frozen_snapshot_when_original_changes_after_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "operator.bin"
    original = b"\x1aE\xdf\xa3authorized parser bytes"
    source.write_bytes(original)
    expected_hash = sha256_file(source)
    rights = _rights(source, tmp_path / "rights.json")

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        source.write_bytes(b"changed after acquisition")
        assert Path(arguments[-1]).read_bytes() == original
        return subprocess.CompletedProcess(
            arguments, 0, stdout=json.dumps(_ffprobe_payload()), stderr=""
        )

    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(media, "_run", fake_run)
    output = tmp_path / "inventory.json"
    assert (
        main(
            [
                "inspect",
                str(source),
                "--rights-manifest",
                str(rights),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text())["sha256"] == expected_hash


@pytest.mark.parametrize("mutation", ["mutate", "replace"])
def test_hostile_source_change_during_acquisition_invokes_no_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    source = tmp_path / "operator.bin"
    source.write_bytes(b"authorized")
    rights = _rights(source, tmp_path / "rights.json")
    real_copy = stable_input._copy_snapshot
    parser_calls = 0

    def hostile_copy(*args: object, **kwargs: object) -> tuple[str, int]:
        result = real_copy(*args, **kwargs)  # type: ignore[arg-type]
        if mutation == "mutate":
            source.write_bytes(b"unauthoriz")
        else:
            replacement = tmp_path / "replacement.bin"
            replacement.write_bytes(b"unauthoriz")
            replacement.replace(source)
        return result

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal parser_calls
        parser_calls += 1
        raise AssertionError("parser must not see a source changed during acquisition")

    monkeypatch.setattr(stable_input, "_copy_snapshot", hostile_copy)
    monkeypatch.setattr(media, "inspect_media", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert main(["inspect", str(source), "--rights-manifest", str(rights)]) == 2
    assert parser_calls == 0


@pytest.mark.parametrize("collision", ["exact", "hardlink", "symlink", "existing"])
def test_inspection_output_collision_never_parses_or_modifies_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collision: str,
) -> None:
    source = tmp_path / "operator.bin"
    original = b"authorized source bytes"
    source.write_bytes(original)
    rights = _rights(source, tmp_path / "rights.json")
    output = source
    if collision == "hardlink":
        output = tmp_path / "hardlink.json"
        output.hardlink_to(source)
    elif collision == "symlink":
        output = tmp_path / "symlink.json"
        output.symlink_to(source)
    elif collision == "existing":
        output = tmp_path / "existing.json"
        output.write_text("keep")
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("unsafe output collision must fail before parsing")

    monkeypatch.setattr(media, "inspect_media", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert (
        main(
            [
                "inspect",
                str(source),
                "--rights-manifest",
                str(rights),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert calls == 0
    assert source.read_bytes() == original
    if collision == "existing":
        assert output.read_text() == "keep"
