import json
import subprocess
from pathlib import Path

import pytest

from av_atlas import media
from av_atlas.errors import AtlasError
from av_atlas.media import enforce_media_limits


def test_corrupt_ffprobe_metadata_is_actionable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.mkv"
    source.write_bytes(b"\x1aE\xdf\xa3not media")
    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        media,
        "_run",
        lambda _, **kwargs: subprocess.CompletedProcess([], 0, stdout="not-json", stderr=""),
    )
    with pytest.raises(AtlasError, match="corrupt JSON"):
        media.inspect_media(source)


def test_missing_streams_are_reported_without_fabrication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"\x1aE\xdf\xa3x")
    payload = {
        "format": {"duration": "1.0", "format_name": "matroska,webm"},
        "streams": [],
    }
    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        media,
        "_run",
        lambda _, **kwargs: subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(payload), stderr=""
        ),
    )
    inventory = media.inspect_media(source)
    assert inventory["streams"] == []
    assert inventory["duration_ms"] == 1000


def test_unsafe_filename_is_passed_as_one_non_shell_argument(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "$(touch SHOULD_NOT_EXIST).mkv"
    source.write_bytes(b"\x1aE\xdf\xa3x")
    captured: list[str] = []
    payload = {"format": {"duration": "1.0", "format_name": "matroska"}, "streams": []}

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.extend(arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(media, "_run", fake_run)
    media.inspect_media(source)
    assert captured[-1] == str(source)
    assert captured[-8:-1] == [
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        "matroska",
        "-f",
        "matroska",
        "-i",
    ]
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


def test_media_limits_fail_closed_for_duration_and_dimensions() -> None:
    inventory = {
        "duration_ms": 10001,
        "streams": [{"width": 9000, "height": 100, "codec_type": "video"}],
    }
    with pytest.raises(AtlasError, match="duration"):
        enforce_media_limits(inventory, 10000, 4096, 4096)
    inventory["duration_ms"] = 1000
    with pytest.raises(AtlasError, match="width"):
        enforce_media_limits(inventory, 10000, 4096, 4096)


def test_native_parser_error_redacts_private_snapshot_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    snapshot = tmp_path / "private/snapshot-secret/source.snapshot"

    def fail(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(
            1,
            ["ffprobe"],
            stderr=f"cannot parse {snapshot} ({snapshot.name})",
        )

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(AtlasError) as error:
        media._run(["ffprobe", str(snapshot)], private_paths=(snapshot,))
    assert str(snapshot) not in str(error.value)
    assert snapshot.name not in str(error.value)
