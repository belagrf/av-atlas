from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from av_atlas.adapters import AdapterContext
from av_atlas.config import BaselineConfig
from av_atlas.errors import AtlasError
from av_atlas.io import sha256_file, source_id_from_sha256
from av_atlas.native_media import AUTHORIZED_MATROSKA
from av_atlas.native_process import NativeInvocation, NativeProcessResult, NativeTool
from av_atlas.ocr_pilot import _extract_frame as _extract_pilot_frame
from av_atlas.shots import FRAME_BYTES, ShotAdapter, _extract_keyframe
from av_atlas.subtitles import SubtitleAdapter

EBML = b"\x1aE\xdf\xa3"
PNG = b"\x89PNG\r\n\x1a\n"


class RecordingRunner:
    def __init__(self) -> None:
        self.invocations: list[NativeInvocation] = []

    def run(self, invocation: NativeInvocation) -> NativeProcessResult:
        self.invocations.append(invocation)
        arguments = invocation.arguments
        stdout = ""
        if arguments[-1] == "pipe:1":
            stdout = "WEBVTT\n\n00:00.100 --> 00:00.900\nprivate pilot text\n"
        elif arguments[-1].endswith(".rgb"):
            relative = arguments[-1].removeprefix("/work/")
            (invocation.writable_directory.source / relative).write_bytes(
                bytes([17]) * (10 * FRAME_BYTES)
            )
        elif arguments[-1].endswith(".png"):
            relative = arguments[-1].removeprefix("/work/")
            output = invocation.writable_directory.source / relative
            output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            output.write_bytes(PNG + b"sandboxed-keyframe")
        else:  # pragma: no cover - protects the fixed test protocol
            raise AssertionError(f"unexpected sandbox invocation: {arguments}")
        return NativeProcessResult(
            invocation.tool,
            invocation.arguments,
            0,
            stdout,
            "",
            0.01,
            len(stdout.encode("utf-8")),
            0,
            "av-atlas-bubblewrap-pilot/1.0.0",
            "0" * 64,
        )


def _source_and_inventory(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    source = tmp_path / "authorized.snapshot"
    source.write_bytes(EBML + b"stable-controlled-pilot-input")
    source_hash = sha256_file(source)
    inventory: dict[str, Any] = {
        "schema_version": "1.1.0",
        "source_id": source_id_from_sha256(source_hash),
        "sha256": source_hash,
        "size_bytes": source.stat().st_size,
        "duration_ms": 1000,
        "native_input_policy": AUTHORIZED_MATROSKA.as_record(),
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264"},
            {
                "index": 1,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "language": "eng",
                "title": "English",
                "time_base": "1/1000",
                "disposition": {},
            },
        ],
    }
    return source, inventory


def _pilot_context(
    tmp_path: Path,
    source: Path,
    inventory: dict[str, Any],
    runner: RecordingRunner,
) -> AdapterContext:
    run_dir = tmp_path / "private-work"
    run_dir.mkdir(mode=0o700)
    return AdapterContext(
        source,
        inventory,
        run_dir,
        BaselineConfig.load(Path(__file__).parents[2] / "configs/m2a.yaml"),
        native_execution_mode="pilot_bubblewrap",
        native_runner=runner,  # type: ignore[arg-type]
    )


def _forbid_direct_subprocess(*args: object, **kwargs: object) -> None:
    raise AssertionError("pilot adapter reached the unsandboxed subprocess path")


def test_pilot_subtitle_and_shot_adapters_use_only_typed_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, inventory = _source_and_inventory(tmp_path)
    runner = RecordingRunner()
    context = _pilot_context(tmp_path, source, inventory, runner)
    monkeypatch.setattr(subprocess, "run", _forbid_direct_subprocess)

    subtitle = SubtitleAdapter().run(context)
    shot = ShotAdapter().run(context)

    assert subtitle.result.status == "success"
    assert shot.result.status == "success"
    assert len(runner.invocations) == 3
    assert all(invocation.tool is NativeTool.FFMPEG for invocation in runner.invocations)
    for invocation in runner.invocations:
        assert invocation.writable_directory.source == context.run_dir
        assert len(invocation.read_only_binds) == 1
        source_bind = invocation.read_only_binds[0]
        assert source_bind.target == "/input/source"
        assert source_bind.expected_sha256 == inventory["sha256"]
        assert source_bind.expected_size == inventory["size_bytes"]
        assert str(source) not in invocation.arguments
        assert "/input/source" in invocation.arguments
    assert not (context.run_dir / ".av-atlas-shot-samples.rgb").exists()


@pytest.mark.parametrize("adapter", ["subtitle", "shot"])
def test_pilot_source_mutation_fails_before_native_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    adapter: str,
) -> None:
    source, inventory = _source_and_inventory(tmp_path)
    runner = RecordingRunner()
    context = _pilot_context(tmp_path, source, inventory, runner)
    source.write_bytes(source.read_bytes() + b"mutation")
    monkeypatch.setattr(subprocess, "run", _forbid_direct_subprocess)

    output = SubtitleAdapter().run(context) if adapter == "subtitle" else ShotAdapter().run(context)

    assert output.result.status == "decode_failure"
    assert runner.invocations == []


def test_pilot_keyframe_output_outside_work_is_rejected_before_spawn(tmp_path: Path) -> None:
    source, inventory = _source_and_inventory(tmp_path)
    runner = RecordingRunner()
    work = tmp_path / "private-work"
    work.mkdir(mode=0o700)
    outside = tmp_path / "outside" / "frame.png"

    with pytest.raises(AtlasError, match="inside the private work directory"):
        _extract_keyframe(
            source,
            outside,
            500,
            5,
            AUTHORIZED_MATROSKA,
            native_runner=runner,  # type: ignore[arg-type]
            sandbox_work_directory=work,
            expected_source_sha256=str(inventory["sha256"]),
            expected_source_size=int(inventory["size_bytes"]),
        )
    assert runner.invocations == []


def test_pilot_frame_low_level_helper_has_no_unsandboxed_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, inventory = _source_and_inventory(tmp_path)
    output = tmp_path / "private-work" / "frame.png"
    output.parent.mkdir(mode=0o700)
    direct_calls = 0

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal direct_calls
        direct_calls += 1
        raise AssertionError("pilot low-level helper attempted direct subprocess execution")

    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(AtlasError, match="mandatory sandbox runner"):
        _extract_pilot_frame(
            source,
            500,
            output,
            AUTHORIZED_MATROSKA,
            expected_source_sha256=str(inventory["sha256"]),
            expected_source_size=int(inventory["size_bytes"]),
        )

    assert direct_calls == 0
    assert not output.exists()
