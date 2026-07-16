from __future__ import annotations

import base64
import os
import resource
import signal
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import pytest

from av_atlas import native_exec_helper, native_process
from av_atlas.errors import AtlasError, ResourceLimitError
from av_atlas.native_process import (
    BUBBLEWRAP_INSTALL_COMMAND,
    PROFILE_SHA256,
    PROFILE_VERSION,
    BubblewrapInventory,
    BubblewrapNativeRunner,
    DependencyState,
    NativeInvocation,
    NativeResourceLimits,
    NativeTool,
    ReadOnlyBind,
    WritableDirectory,
    inspect_bubblewrap,
    load_bubblewrap_inventory,
    profile_record,
    run_hostile_sandbox_probes,
)


def _inventory_or_skip() -> BubblewrapInventory:
    inventory = load_bubblewrap_inventory()
    if inventory.state is not DependencyState.AVAILABLE:
        pytest.skip(
            f"approved Bubblewrap capability unavailable; operator command: "
            f"{BUBBLEWRAP_INSTALL_COMMAND}"
        )
    return inventory


def _private_directory(path: Path) -> WritableDirectory:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return WritableDirectory.measure(path)


def _runner(
    path: Path, limits: NativeResourceLimits | None = None
) -> tuple[BubblewrapNativeRunner, WritableDirectory]:
    return (
        BubblewrapNativeRunner(_inventory_or_skip(), limits),
        _private_directory(path),
    )


def test_inventory_is_sanitized_versioned_and_fail_closed() -> None:
    value = inspect_bubblewrap()
    assert value["profile_version"] == PROFILE_VERSION
    assert value["profile_sha256"] == PROFILE_SHA256
    assert value["installation_command"] == BUBBLEWRAP_INSTALL_COMMAND
    assert value["network_accessed"] is False
    assert "resolved_executable_path" not in value
    assert value["executable"]["basename"] == "bwrap"
    assert value["state"] in {"available", "unavailable", "unsupported"}
    if value["state"] == "available":
        assert value["capability_smoke"]["passed"] is True
        assert all(value["capability_smoke"]["namespace_isolation"].values())
        assert value["capability_smoke"]["hostname_sanitized"] is True
        assert (
            value["executable"]["sha256"]
            == ("52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712")
            or len(value["executable"]["sha256"]) == 64
        )
        if value["package"] is not None:
            assert value["package"]["license_id"] != "unknown-not-verified"
    assert profile_record()["whole_host_root_bound"] is False
    assert profile_record()["root_remounted_read_only"] is True
    assert profile_record()["devices"] == ["null", "zero", "random", "urandom"]
    assert profile_record()["hostname"] == "av-atlas-pilot"
    assert native_process._profile_prefix() == profile_record()["argument_prefix"]
    assert native_process._profile_suffix() == profile_record()["argument_suffix"]
    assert {
        tool.value: path for tool, path in native_process._TOOL_PATHS.items()
    } == profile_record()["tool_paths"]


def test_inventory_missing_dependency_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native_process.shutil, "which", lambda _: None)
    value = inspect_bubblewrap()
    assert value["state"] == "unavailable"
    assert value["installation_command"] == "sudo apt-get install bubblewrap"
    assert value["capability_smoke"] is None
    with pytest.raises(AtlasError, match="fails closed|unavailable"):
        BubblewrapNativeRunner(load_bubblewrap_inventory())


def test_measured_hostile_denials_environment_and_capture_cleanup(tmp_path: Path) -> None:
    runner, work = _runner(tmp_path / "work")
    sentinel = tmp_path / "outside-sentinel"
    sentinel.write_text("must remain unavailable", encoding="utf-8")
    result = run_hostile_sandbox_probes(runner, work, sentinel)
    assert all(result.values())
    assert result["outside_write_positive_control"] is True
    assert result["outside_host_write_denied"] is True
    assert result["hostname_sanitized"] is True
    assert not (Path("/") / "escape").exists()
    assert not (Path("/dev") / "escape").exists()
    assert not list(work.source.glob(".av-atlas-native-capture-*"))
    assert not list(tmp_path.glob(".av-atlas-outside-write-probe-*"))
    assert (work.source / "probe-allowed").read_bytes() == b"x"


def test_sandbox_hostname_is_fixed_and_host_identity_is_not_exposed(tmp_path: Path) -> None:
    runner, work = _runner(tmp_path / "work")
    host_hostname = os.uname().nodename
    result = runner.run(
        NativeInvocation(
            NativeTool.PYTHON_PROBE,
            ("-c", "import socket; print(socket.gethostname())"),
            work,
        )
    )
    assert result.stdout.strip() == "av-atlas-pilot"
    if host_hostname != "av-atlas-pilot":
        assert host_hostname not in result.stdout


def test_before_run_guard_executes_before_any_native_boundary_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = _inventory_or_skip()
    work = _private_directory(tmp_path / "work")
    events: list[str] = []

    def deny() -> None:
        events.append("guard")
        raise AtlasError("per-unit policy guard denied execution")

    runner = BubblewrapNativeRunner(inventory, before_run=deny)
    monkeypatch.setattr(
        runner,
        "_open_bubblewrap",
        lambda: (_ for _ in ()).throw(AssertionError("guard must run before executable open")),
    )
    with pytest.raises(AtlasError, match="policy guard denied"):
        runner.run(NativeInvocation(NativeTool.PYTHON_PROBE, ("-c", "pass"), work))
    assert events == ["guard"]


def test_descriptor_bound_work_rejects_parent_replacement_without_redirecting_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_root = tmp_path / "private-root"
    private_root.mkdir(mode=0o700)
    work_path = private_root / "work"
    runner, work = _runner(work_path)
    displaced_root = tmp_path / "displaced-root"
    original_open_work = native_process._open_work

    def replace_parent_after_open(value: WritableDirectory) -> int:
        descriptor = original_open_work(value)
        os.rename(private_root, displaced_root)
        private_root.mkdir(mode=0o700)
        replacement = private_root / "work"
        replacement.mkdir(mode=0o700)
        replacement.chmod(0o700)
        return descriptor

    monkeypatch.setattr(native_process, "_open_work", replace_parent_after_open)
    with pytest.raises(AtlasError, match="identity changed during execution"):
        runner.run(
            NativeInvocation(
                NativeTool.PYTHON_PROBE,
                ("-c", "open('/work/pinned-write','wb').write(b'pinned')"),
                work,
            )
        )
    assert (displaced_root / "work" / "pinned-write").read_bytes() == b"pinned"
    assert not (private_root / "work" / "pinned-write").exists()


def test_descriptor_bound_file_is_exact_and_source_replacement_fails_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, work = _runner(tmp_path / "work")
    source = tmp_path / "source;$(inert).txt"
    source.write_text("descriptor-bound bytes", encoding="utf-8")
    binding = ReadOnlyBind.measure_file(source, "/input/source")
    result = runner.run(
        NativeInvocation(
            NativeTool.PYTHON_PROBE,
            ("-c", "print(open('/input/source').read())"),
            work,
            (binding,),
        )
    )
    assert result.stdout.strip() == "descriptor-bound bytes"
    replacement = tmp_path / "replacement"
    replacement.write_text("changed bytes", encoding="utf-8")
    os.replace(replacement, source)

    def forbidden(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        raise AssertionError("identity failure must occur before native process creation")

    monkeypatch.setattr(native_process.subprocess, "Popen", forbidden)
    with pytest.raises(AtlasError, match="identity changed"):
        runner.run(
            NativeInvocation(
                NativeTool.PYTHON_PROBE,
                ("-c", "print('must not execute')"),
                work,
                (binding,),
            )
        )
    assert not (tmp_path / "inert").exists()


def test_changed_bubblewrap_identity_fails_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = _inventory_or_skip()
    fake = tmp_path / "bwrap"
    fake.write_bytes(b"project-authored fake executable bytes")
    fake.chmod(0o755)
    changed = replace(inventory, executable_path=fake)
    runner = BubblewrapNativeRunner(changed)
    work = _private_directory(tmp_path / "work")

    def forbidden(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        raise AssertionError("changed executable must fail before process creation")

    monkeypatch.setattr(native_process.subprocess, "Popen", forbidden)
    with pytest.raises(AtlasError, match="executable changed"):
        runner.run(NativeInvocation(NativeTool.PYTHON_PROBE, ("-c", "pass"), work))
    with pytest.raises(AtlasError, match="profile identity"):
        BubblewrapNativeRunner(replace(inventory, dependency_identity_sha256="0" * 64))


def test_changed_bubblewrap_candidate_is_never_executed_during_policy_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved = _inventory_or_skip()
    candidate = tmp_path / "bwrap"
    candidate.write_bytes(b"changed project-authored candidate")
    candidate.chmod(0o755)
    monkeypatch.setattr(native_process.shutil, "which", lambda _: str(candidate))
    calls = 0

    def forbidden(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise AssertionError("changed Bubblewrap candidate must not execute")

    monkeypatch.setattr(native_process.subprocess, "run", forbidden)
    measured = load_bubblewrap_inventory(
        expected_executable_sha256=approved.executable_sha256,
        expected_executable_size_bytes=approved.executable_size_bytes,
    )
    assert measured.state is DependencyState.UNSUPPORTED
    assert "no candidate code was executed" in str(measured.detail)
    assert calls == 0


def test_strict_invocation_and_work_directory_contracts(tmp_path: Path) -> None:
    work_path = tmp_path / "work"
    work = _private_directory(work_path)
    with pytest.raises(AtlasError, match="environment override"):
        NativeInvocation(
            NativeTool.PYTHON_PROBE,
            ("-c", "pass"),
            work,
            environment=(("PATH", "/host/path"),),
        )
    source = tmp_path / "source"
    source.write_bytes(b"bytes")
    binding = ReadOnlyBind.measure_file(source, "/input/source")
    with pytest.raises(AtlasError, match="sandbox paths"):
        NativeInvocation(
            NativeTool.PYTHON_PROBE,
            ("-c", f"open({str(source)!r})"),
            work,
            (binding,),
        )
    work_path.chmod(0o755)
    runner = BubblewrapNativeRunner(_inventory_or_skip())
    with pytest.raises(AtlasError, match="mode 0700"):
        runner.run(NativeInvocation(NativeTool.PYTHON_PROBE, ("-c", "pass"), work))


def test_output_capture_limit_is_controlled_and_file_backed(tmp_path: Path) -> None:
    limits = NativeResourceLimits(
        stdout_bytes=1024,
        stderr_bytes=1024,
        file_size_bytes=4096,
    )
    runner, work = _runner(tmp_path / "work", limits)
    with pytest.raises(ResourceLimitError, match="capture-size"):
        runner.run(
            NativeInvocation(
                NativeTool.PYTHON_PROBE,
                ("-c", "import sys; sys.stdout.write('x'*8192)"),
                work,
            )
        )
    assert not list(work.source.glob(".av-atlas-native-capture-*"))


def test_wall_timeout_terminates_sandbox_process_tree(tmp_path: Path) -> None:
    limits = NativeResourceLimits(wall_seconds=0.2, termination_grace_seconds=0.1)
    runner, work = _runner(tmp_path / "work", limits)
    script = """import os, time
if os.fork() == 0:
    time.sleep(0.6)
    open('/work/survivor', 'w').write('process tree survived')
    os._exit(0)
time.sleep(10)
"""
    with pytest.raises(ResourceLimitError, match="wall-time"):
        runner.run(NativeInvocation(NativeTool.PYTHON_PROBE, ("-c", script), work))
    time.sleep(0.7)
    assert not (work.source / "survivor").exists()


def test_handled_interruption_terminates_group_and_removes_capture_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, work = _runner(tmp_path / "work")
    signals: list[int] = []

    class InterruptedProcess:
        pid = 424242
        returncode: int | None = None
        waits = 0

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            self.waits += 1
            if self.waits == 1:
                raise KeyboardInterrupt
            self.returncode = -signal.SIGTERM
            return self.returncode

    process = InterruptedProcess()
    monkeypatch.setattr(native_process.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(os, "killpg", lambda pid, value: signals.append(value))
    with pytest.raises(KeyboardInterrupt):
        runner.run(NativeInvocation(NativeTool.PYTHON_PROBE, ("-c", "pass"), work))
    assert signals == [signal.SIGTERM]
    assert not list(work.source.glob(".av-atlas-native-capture-*"))


def test_cpu_memory_file_descriptor_and_process_limits_are_enforced(tmp_path: Path) -> None:
    cpu_runner, cpu_work = _runner(
        tmp_path / "cpu",
        NativeResourceLimits(wall_seconds=4, cpu_seconds=1),
    )
    cpu = cpu_runner.run(
        NativeInvocation(
            NativeTool.PYTHON_PROBE,
            ("-c", "while True: pass"),
            cpu_work,
            check=False,
        )
    )
    assert cpu.returncode != 0
    assert cpu.wall_seconds < 4

    memory_runner, memory_work = _runner(
        tmp_path / "memory",
        NativeResourceLimits(address_space_bytes=128 * 1024**2),
    )
    memory = memory_runner.run(
        NativeInvocation(
            NativeTool.PYTHON_PROBE,
            (
                "-c",
                "import sys\ntry: bytearray(512*1024*1024)\nexcept MemoryError: sys.exit(23)",
            ),
            memory_work,
            check=False,
        )
    )
    assert memory.returncode == 23

    file_runner, file_work = _runner(
        tmp_path / "file",
        NativeResourceLimits(file_size_bytes=1024, stdout_bytes=512, stderr_bytes=512),
    )
    file_result = file_runner.run(
        NativeInvocation(
            NativeTool.PYTHON_PROBE,
            (
                "-c",
                "with open('/work/big','wb') as handle:\n handle.write(b'x'*4096)\n handle.flush()",
            ),
            file_work,
            check=False,
        )
    )
    assert file_result.returncode != 0
    assert (file_work.source / "big").stat().st_size <= 1024

    descriptor_runner, descriptor_work = _runner(
        tmp_path / "descriptor",
        NativeResourceLimits(open_files=32),
    )
    descriptor_result = descriptor_runner.run(
        NativeInvocation(
            NativeTool.PYTHON_PROBE,
            (
                "-c",
                "files=[]\n"
                "try:\n while True: files.append(open('/dev/null','rb'))\n"
                "except OSError: print(len(files))",
            ),
            descriptor_work,
        )
    )
    assert int(descriptor_result.stdout) < 32

    process_runner, process_work = _runner(
        tmp_path / "process",
        NativeResourceLimits(process_count=1),
    )
    process_result = process_runner.run(
        NativeInvocation(
            NativeTool.PYTHON_PROBE,
            ("-c", "print('must not start after namespace clone')"),
            process_work,
            check=False,
        )
    )
    assert process_result.returncode != 0


def test_private_paths_are_redacted_from_results(tmp_path: Path) -> None:
    runner, work = _runner(tmp_path / "work")
    private = tmp_path / "private operator path"
    encoded = base64.b64encode(str(private).encode()).decode()
    result = runner.run(
        NativeInvocation(
            NativeTool.PYTHON_PROBE,
            ("-c", f"import base64,sys;sys.stderr.write(base64.b64decode('{encoded}').decode())"),
            work,
            private_paths=(private,),
        )
    )
    assert str(private) not in result.stderr
    assert "<private-host-path>" in result.stderr


def test_limit_helper_sets_every_rlimit_before_exact_fd_exec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, tuple[int, int]]] = []
    executed: list[tuple[str, list[str], dict[str, str]]] = []
    umasks: list[int] = []
    monkeypatch.setattr(resource, "setrlimit", lambda kind, value: calls.append((kind, value)))
    monkeypatch.setattr(os, "umask", lambda value: umasks.append(value) or 0o022)

    def fake_exec(path: str, arguments: list[str], environment: dict[str, str]) -> None:
        executed.append((path, arguments, environment))
        raise RuntimeError("exec intercepted")

    monkeypatch.setattr(os, "execve", fake_exec)
    with pytest.raises(RuntimeError, match="intercepted"):
        native_exec_helper.main(
            [
                "--bwrap-fd",
                "19",
                "--cpu-seconds",
                "2",
                "--address-space-bytes",
                "1048576",
                "--file-size-bytes",
                "4096",
                "--open-files",
                "32",
                "--process-count",
                "8",
                "--",
                "--unshare-net",
                "--",
                "/usr/bin/true",
            ]
        )
    assert {kind for kind, _ in calls} == {
        resource.RLIMIT_CORE,
        resource.RLIMIT_CPU,
        resource.RLIMIT_AS,
        resource.RLIMIT_FSIZE,
        resource.RLIMIT_NOFILE,
        resource.RLIMIT_NPROC,
    }
    assert (resource.RLIMIT_CORE, (0, 0)) in calls
    assert umasks == [0o077]
    assert executed == [
        (
            "/proc/self/fd/19",
            ["bwrap", "--unshare-net", "--", "/usr/bin/true"],
            {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"},
        )
    ]
