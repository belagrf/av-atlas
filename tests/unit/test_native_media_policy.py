from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from av_atlas import media, ocr, ocr_pilot, shots, subtitles
from av_atlas.adapters import AdapterContext
from av_atlas.cli import main
from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError
from av_atlas.io import sha256_file
from av_atlas.native_media import (
    AUTHORIZED_MATROSKA,
    CONTRACT_VERSION,
    GENERATED_PNG,
    PROTOCOL_WHITELIST,
    classify_authorized_source,
    classify_generated_png,
)
from av_atlas.rights import create_rights_manifest

EBML = b"\x1aE\xdf\xa3"
PNG = b"\x89PNG\r\n\x1a\n"


def _rights(source: Path, output: Path) -> Path:
    create_rights_manifest(
        source,
        output,
        "native-policy-test",
        "owned",
        {"analysis", "derivative_artifact_retention"},
    )
    return output


def _config() -> BaselineConfig:
    return BaselineConfig.load(Path(__file__).parents[2] / "configs/m2b2.yaml")


def test_versioned_policy_has_exact_non_configurable_input_arguments(tmp_path: Path) -> None:
    source = tmp_path / "source.snapshot"
    source.write_bytes(EBML + b"controlled")
    assert CONTRACT_VERSION == "av-atlas-native-input/1.0.0"
    assert PROTOCOL_WHITELIST == ("file",)
    assert classify_authorized_source(source) == AUTHORIZED_MATROSKA
    assert AUTHORIZED_MATROSKA.arguments(source) == [
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        "matroska",
        "-f",
        "matroska",
        "-i",
        str(source),
    ]
    assert AUTHORIZED_MATROSKA.as_record()["multi_resource_inputs_permitted"] is False


def test_policy_renderer_does_not_accept_override_options(tmp_path: Path) -> None:
    source = tmp_path / "source.snapshot"
    source.write_bytes(EBML + b"controlled")
    renderer: Any = AUTHORIZED_MATROSKA.arguments
    with pytest.raises(TypeError):
        renderer(source, "-protocol_whitelist", "file,http")
    with pytest.raises(AtlasError, match="nonnegative integer"):
        AUTHORIZED_MATROSKA.arguments(source, seek_ms=True)


def test_generated_png_uses_single_image_demuxer_and_rejects_other_bytes(
    tmp_path: Path,
) -> None:
    frame = tmp_path / "frame.png"
    frame.write_bytes(PNG + b"controlled")
    assert classify_generated_png(frame) == GENERATED_PNG
    assert "png_pipe" in GENERATED_PNG.arguments(frame)
    frame.write_bytes(b"GIF89a")
    with pytest.raises(AtlasError, match="not a stable PNG"):
        classify_generated_png(frame)


@pytest.mark.parametrize(
    "payload",
    [
        b"#EXTM3U\nsegment.ts\n",
        b"<?xml version='1.0'?><MPD><BaseURL>http://127.0.0.1/x</BaseURL></MPD>",
        b"ffconcat version 1.0\nfile outside.mkv\n",
        b"file 'one.mkv'\nfile 'two.mkv'\n",
        b"frame-%04d.png\n",
        b"BDMV\x00index.bdmv",
        b"https://127.0.0.1/video.m3u8\n",
    ],
)
def test_manifest_playlist_sequence_and_navigation_inputs_reject_before_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
) -> None:
    source = tmp_path / "hostile.input"
    source.write_bytes(payload)
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("native parser must not run")

    monkeypatch.setattr(media, "_run", forbidden)
    with pytest.raises(AtlasError, match="unsupported native input format"):
        media.inspect_media(source)
    assert calls == 0


def test_local_playlist_reference_is_rejected_without_external_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "outside-sentinel.ts"
    sentinel.write_bytes(b"DO NOT READ")
    source = tmp_path / "local.m3u8"
    source.write_text(f"#EXTM3U\n#EXTINF:1,\nfile://{sentinel}\n")
    rights = _rights(source, tmp_path / "rights.json")
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("FFprobe/FFmpeg must not run for a playlist")

    monkeypatch.setattr(media, "_run", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert main(["inspect", str(source), "--rights-manifest", str(rights)]) == 2
    assert calls == 0
    assert sentinel.read_bytes() == b"DO NOT READ"


def test_loopback_manifest_reference_makes_zero_requests_and_starts_no_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            requests.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        source = tmp_path / "network.m3u8"
        source.write_text(
            f"#EXTM3U\n#EXTINF:1,\nhttp://127.0.0.1:{server.server_port}/sentinel.ts\n"
        )
        rights = _rights(source, tmp_path / "rights.json")
        calls = 0

        def forbidden(*args: object, **kwargs: object) -> None:
            nonlocal calls
            calls += 1
            raise AssertionError("FFprobe/FFmpeg must not run for a manifest")

        monkeypatch.setattr(media, "_run", forbidden)
        monkeypatch.setattr(subprocess, "run", forbidden)
        assert main(["inspect", str(source), "--rights-manifest", str(rights)]) == 2
        assert calls == 0
        assert requests == []
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.parametrize(
    ("format_name", "accepted"),
    [
        ("matroska", True),
        ("matroska,webm", True),
        ("hls", False),
        ("dash", False),
        ("matroska,hls", False),
        (None, False),
        (7, False),
    ],
)
def test_ffprobe_reported_format_must_match_forced_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    format_name: object,
    accepted: bool,
) -> None:
    source = tmp_path / "source.mkv"
    source.write_bytes(EBML + b"controlled")
    payload: dict[str, Any] = {
        "format": {"duration": "1.0", "format_name": format_name},
        "streams": [],
    }
    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        media,
        "_run",
        lambda arguments, **kwargs: subprocess.CompletedProcess(
            arguments, 0, stdout=json.dumps(payload), stderr=""
        ),
    )
    if accepted:
        inventory = media.inspect_media(source)
        assert inventory["native_input_policy"] == AUTHORIZED_MATROSKA.as_record()
    else:
        with pytest.raises(AtlasError, match="format"):
            media.inspect_media(source)


def test_policy_option_failure_is_controlled_without_unrestricted_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mkv"
    source.write_bytes(EBML + b"controlled")
    calls = 0

    def fail(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise AtlasError("ffprobe failed: unrecognized protocol_whitelist")

    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(media, "_run", fail)
    with pytest.raises(AtlasError, match="protocol_whitelist"):
        media.inspect_media(source)
    assert calls == 1


def test_every_runtime_decode_helper_rejects_manifest_before_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "hostile.m3u8"
    source.write_text("#EXTM3U\nfile:///outside.ts\n")
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("decode helper must reject before subprocess")

    monkeypatch.setattr(shots.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(subtitles.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ocr_pilot.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(AtlasError, match="unsupported native input format"):
        shots._decode_frames(source, _config(), 1000, AUTHORIZED_MATROSKA)
    with pytest.raises(AtlasError, match="unsupported native input format"):
        shots._extract_keyframe(source, tmp_path / "frame.png", 0, 1, AUTHORIZED_MATROSKA)
    with pytest.raises(AtlasError, match="unsupported native input format"):
        subtitles._extract_track(source, 0, 1, AUTHORIZED_MATROSKA)
    with pytest.raises(AtlasError, match="unsupported native input format"):
        ocr_pilot._extract_frame(source, 0, tmp_path / "pilot.png", AUTHORIZED_MATROSKA)
    assert calls == 0


def test_ocr_preprocessing_uses_forced_single_png_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "run"
    keyframes = run_dir / "keyframes"
    keyframes.mkdir(parents=True)
    source = keyframes / "KEY_0001.png"
    source.write_bytes(PNG + b"controlled")
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    config = BaselineConfig.load(Path(__file__).parents[2] / "configs/m2b.yaml")
    context = AdapterContext(
        Path("unused"),
        {"source_id": "SRC_000000000000", "duration_ms": 1000},
        run_dir,
        config,
    )
    keyframe = {
        "keyframe_id": "KEY_0001",
        "shot_id": "SHOT_0001",
        "timestamp_ms": 500,
        "evidence_ref": "VID:SRC_000000000000:frame:500",
        "path": "keyframes/KEY_0001.png",
        "sha256": sha256_file(source),
    }
    captured: list[str] = []

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if Path(arguments[0]).name == "ffmpeg":
            captured.extend(arguments)
            Path(arguments[-1]).write_bytes(PNG + b"prepared")
            return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout="level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n",
            stderr="",
        )

    monkeypatch.setattr(ocr.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ocr.subprocess, "run", fake_run)
    frame_number, rows, state = ocr._process_frame(
        context,
        {"resolved_executable_path": "/usr/bin/tesseract"},
        temporary,
        1,
        keyframe,
    )
    assert frame_number == 1 and rows == [] and state["state"] == "succeeded"
    input_index = captured.index("-i")
    assert captured[input_index - 6 : input_index + 1] == [
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        "png_pipe",
        "-f",
        "png_pipe",
        "-i",
    ]
