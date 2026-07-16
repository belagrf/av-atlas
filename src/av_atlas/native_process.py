"""Typed, bounded Bubblewrap execution for native pilot tools.

The controlled baseline can continue to use its existing direct execution path.
This module is the mandatory, no-fallback boundary for pilot-mode native
parsers.  It intentionally exposes only fixed tools, descriptor-backed input
mounts, one descriptor-backed writable directory, and a versioned profile.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from av_atlas.errors import AtlasError, ResourceLimitError

BUBBLEWRAP_INSTALL_COMMAND = "sudo apt-get install bubblewrap"
PROFILE_VERSION = "av-atlas-bubblewrap-pilot/1.1.0"
PROFILE_SCHEMA_VERSION = "1.1.0"
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FIXED_ENVIRONMENT = {
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/bin:/bin",
}
_INVOCATION_ENVIRONMENT_KEYS = frozenset({"OMP_THREAD_LIMIT"})
_SANDBOX_HOSTNAME = "av-atlas-pilot"
_EXPOSED_HOST_SUBTREES = (
    "/usr/bin",
    "/usr/lib",
    "/usr/lib64",
    "/usr/share/tesseract-ocr",
    "/etc/alternatives",
)
_MASKED_HOST_SUBTREES = (
    "/usr/local",
    "/usr/src",
    "/usr/include",
    "/usr/share/doc",
    "/usr/share/man",
)
_MASKED_RUNTIME_SENTINEL_CANDIDATES = (
    Path("/usr/local/bin"),
    Path("/usr/local/lib"),
    Path("/usr/local/share"),
)
_PROFILE_PREFIX_ARGUMENTS = (
    "--unshare-user",
    "--unshare-pid",
    "--unshare-ipc",
    "--unshare-uts",
    "--hostname",
    _SANDBOX_HOSTNAME,
    "--unshare-net",
    "--die-with-parent",
    "--new-session",
    "--cap-drop",
    "ALL",
    "--clearenv",
    "--dir",
    "/usr",
    "--ro-bind",
    "/usr/bin",
    "/usr/bin",
    "--ro-bind",
    "/usr/lib",
    "/usr/lib",
    "--ro-bind-try",
    "/usr/lib64",
    "/usr/lib64",
    "--dir",
    "/usr/share",
    "--ro-bind-try",
    "/usr/share/tesseract-ocr",
    "/usr/share/tesseract-ocr",
    "--dir",
    "/usr/local",
    "--dir",
    "/usr/src",
    "--dir",
    "/usr/include",
    "--dir",
    "/usr/share/doc",
    "--dir",
    "/usr/share/man",
    "--symlink",
    "usr/bin",
    "/bin",
    "--symlink",
    "usr/lib",
    "/lib",
    "--symlink",
    "usr/lib64",
    "/lib64",
    "--dir",
    "/etc",
    "--ro-bind-try",
    "/etc/alternatives",
    "/etc/alternatives",
    "--proc",
    "/proc",
    "--dir",
    "/dev",
    "--dev-bind",
    "/dev/null",
    "/dev/null",
    "--dev-bind",
    "/dev/zero",
    "/dev/zero",
    "--dev-bind",
    "/dev/random",
    "/dev/random",
    "--dev-bind",
    "/dev/urandom",
    "/dev/urandom",
    "--tmpfs",
    "/tmp",
    "--dir",
    "/input",
    "--dir",
    "/work",
    "--setenv",
    "HOME",
    "/nonexistent",
    "--setenv",
    "LANG",
    "C.UTF-8",
    "--setenv",
    "LC_ALL",
    "C.UTF-8",
    "--setenv",
    "PATH",
    "/usr/bin:/bin",
)
_PROFILE_SUFFIX_ARGUMENTS = ("--chdir", "/work", "--remount-ro", "/")
_PROFILE_TOOL_PATHS = {
    "ffprobe": "/usr/bin/ffprobe",
    "ffmpeg": "/usr/bin/ffmpeg",
    "tesseract": "/usr/bin/tesseract",
    "python3-probe": "/usr/bin/python3",
}
_SYSTEM_PROFILE = {
    "schema_version": PROFILE_SCHEMA_VERSION,
    "contract_version": PROFILE_VERSION,
    "namespaces": ["user", "pid", "ipc", "uts", "network", "mount"],
    "session": "new-session",
    "parent_lifecycle": "die-with-parent",
    "capabilities": "drop-all",
    "hostname": _SANDBOX_HOSTNAME,
    "environment": _FIXED_ENVIRONMENT,
    "system_runtime_mounts": [
        {"source": "/usr/bin", "target": "/usr/bin", "mode": "read-only"},
        {"source": "/usr/lib", "target": "/usr/lib", "mode": "read-only"},
        {
            "source": "/usr/lib64",
            "target": "/usr/lib64",
            "mode": "read-only-if-present",
        },
        {
            "source": "/usr/share/tesseract-ocr",
            "target": "/usr/share/tesseract-ocr",
            "mode": "read-only-if-present",
        },
        {
            "source": "/etc/alternatives",
            "target": "/etc/alternatives",
            "mode": "read-only-if-present",
        },
    ],
    "exposed_host_subtrees": list(_EXPOSED_HOST_SUBTREES),
    "masked_host_subtrees": list(_MASKED_HOST_SUBTREES),
    "compatibility_symlinks": {
        "/bin": "usr/bin",
        "/lib": "usr/lib",
        "/lib64": "usr/lib64",
    },
    "devices": ["null", "zero", "random", "urandom"],
    "private_tmpfs": "/tmp",
    "input_root": "/input",
    "writable_root": "/work",
    "root_remounted_read_only": True,
    "whole_host_root_bound": False,
    "argument_prefix": list(_PROFILE_PREFIX_ARGUMENTS),
    "argument_suffix": list(_PROFILE_SUFFIX_ARGUMENTS),
    "tool_paths": _PROFILE_TOOL_PATHS,
}
PROFILE_SHA256 = hashlib.sha256(
    json.dumps(_SYSTEM_PROFILE, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


def reject_exposed_host_path(path: Path, *, label: str = "operator path") -> None:
    """Reject a host path whose bytes are already visible through fixed runtime mounts."""
    if not isinstance(path, Path) or "\x00" in str(path):
        raise AtlasError(f"{label} must be a NUL-free filesystem path")
    if not isinstance(label, str) or not label or any(character in label for character in "\r\n"):
        raise AtlasError("sandbox path label is invalid")
    try:
        candidates = {
            Path(os.path.abspath(path)),
            path.resolve(strict=False),
        }
    except (OSError, RuntimeError, ValueError) as exc:
        raise AtlasError(f"{label} could not be classified against sandbox runtime mounts") from exc
    for candidate in candidates:
        for exposed in map(Path, _EXPOSED_HOST_SUBTREES):
            if candidate.is_relative_to(exposed) or exposed.is_relative_to(candidate):
                raise AtlasError(f"{label} overlaps a sandbox-exposed host runtime subtree")


class NativeTool(StrEnum):
    """The only executables accepted by the pilot runner."""

    FFPROBE = "ffprobe"
    FFMPEG = "ffmpeg"
    TESSERACT = "tesseract"
    PYTHON_PROBE = "python3-probe"


class BindKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"


class DependencyState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


_TOOL_PATHS = {tool: _PROFILE_TOOL_PATHS[tool.value] for tool in NativeTool}


@dataclass(frozen=True)
class NativeResourceLimits:
    """Hard native child limits plus parent-enforced capture and wall limits."""

    wall_seconds: float = 30.0
    cpu_seconds: int = 30
    address_space_bytes: int = 2 * 1024**3
    file_size_bytes: int = 256 * 1024**2
    open_files: int = 64
    # RLIMIT_NPROC is charged against the host real UID before Bubblewrap
    # enters its user namespace.  This remains bounded, but must accommodate
    # the operator's already-running threads on a shared desktop session.
    process_count: int = 8192
    stdout_bytes: int = 8 * 1024**2
    stderr_bytes: int = 8 * 1024**2
    termination_grace_seconds: float = 1.0

    def __post_init__(self) -> None:
        integer_values = {
            "cpu_seconds": self.cpu_seconds,
            "address_space_bytes": self.address_space_bytes,
            "file_size_bytes": self.file_size_bytes,
            "open_files": self.open_files,
            "process_count": self.process_count,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
        }
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in integer_values.values()
        ):
            raise AtlasError("native integer resource limits must be positive integers")
        if (
            not isinstance(self.wall_seconds, (int, float))
            or isinstance(self.wall_seconds, bool)
            or not 0 < self.wall_seconds <= 3600
            or not isinstance(self.termination_grace_seconds, (int, float))
            or isinstance(self.termination_grace_seconds, bool)
            or not 0 < self.termination_grace_seconds <= 10
        ):
            raise AtlasError("native wall and termination limits are outside supported bounds")
        maxima = {
            "cpu_seconds": 3600,
            "address_space_bytes": 16 * 1024**3,
            "file_size_bytes": 8 * 1024**3,
            "open_files": 4096,
            "process_count": 16384,
            "stdout_bytes": 64 * 1024**2,
            "stderr_bytes": 64 * 1024**2,
        }
        for name, maximum in maxima.items():
            if integer_values[name] > maximum:
                raise AtlasError(f"native {name} exceeds the reviewed profile maximum")
        if self.stdout_bytes > self.file_size_bytes or self.stderr_bytes > self.file_size_bytes:
            raise AtlasError("native capture limits cannot exceed the file-size limit")

    def as_record(self) -> dict[str, int | float]:
        return {
            "wall_seconds": self.wall_seconds,
            "cpu_seconds": self.cpu_seconds,
            "address_space_bytes": self.address_space_bytes,
            "file_size_bytes": self.file_size_bytes,
            "open_files": self.open_files,
            "process_count": self.process_count,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "termination_grace_seconds": self.termination_grace_seconds,
        }


def _validate_sandbox_target(value: str) -> PurePosixPath:
    if not isinstance(value, str) or "\x00" in value:
        raise AtlasError("sandbox mount targets must be NUL-free strings")
    target = PurePosixPath(value)
    if not target.is_absolute() or ".." in target.parts or target.parent != PurePosixPath("/input"):
        raise AtlasError("read-only sandbox targets must be direct children of /input")
    if target.name in {"", ".", ".."}:
        raise AtlasError("sandbox mount target is invalid")
    return target


@dataclass(frozen=True)
class ReadOnlyBind:
    """A source identity that is reopened and supplied through an inherited fd."""

    source: Path
    target: str
    kind: BindKind
    expected_device: int
    expected_inode: int
    expected_size: int | None = None
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        _validate_sandbox_target(self.target)
        if (
            not isinstance(self.expected_device, int)
            or isinstance(self.expected_device, bool)
            or self.expected_device < 0
            or not isinstance(self.expected_inode, int)
            or isinstance(self.expected_inode, bool)
            or self.expected_inode <= 0
        ):
            raise AtlasError("bind device and inode identities must be nonnegative integers")
        if self.kind is BindKind.FILE:
            if (
                not isinstance(self.expected_size, int)
                or isinstance(self.expected_size, bool)
                or self.expected_size < 0
                or not isinstance(self.expected_sha256, str)
                or not _HASH_PATTERN.fullmatch(self.expected_sha256)
            ):
                raise AtlasError("file binds require exact size and SHA-256 identities")
        elif self.expected_size is not None or self.expected_sha256 is not None:
            raise AtlasError("directory binds do not accept file size or hash fields")

    @classmethod
    def measure_file(
        cls,
        source: Path,
        target: str,
        *,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
    ) -> ReadOnlyBind:
        reject_exposed_host_path(source, label="native read-only input")
        descriptor, measured = _open_verified_path(source, BindKind.FILE)
        try:
            size = measured.st_size
            digest = _sha256_descriptor(descriptor)
        finally:
            os.close(descriptor)
        if expected_size is not None and expected_size != size:
            raise AtlasError("read-only input size differs from its expected identity")
        if expected_sha256 is not None and expected_sha256 != digest:
            raise AtlasError("read-only input hash differs from its expected identity")
        return cls(source, target, BindKind.FILE, measured.st_dev, measured.st_ino, size, digest)

    @classmethod
    def measure_directory(cls, source: Path, target: str) -> ReadOnlyBind:
        reject_exposed_host_path(source, label="native read-only input")
        descriptor, measured = _open_verified_path(source, BindKind.DIRECTORY)
        os.close(descriptor)
        return cls(source, target, BindKind.DIRECTORY, measured.st_dev, measured.st_ino)


@dataclass(frozen=True)
class WritableDirectory:
    """The sole host directory exposed writable at fixed sandbox path /work."""

    source: Path
    expected_device: int
    expected_inode: int
    expected_parent_device: int
    expected_parent_inode: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.expected_device, int)
            or isinstance(self.expected_device, bool)
            or self.expected_device < 0
            or not isinstance(self.expected_inode, int)
            or isinstance(self.expected_inode, bool)
            or self.expected_inode <= 0
            or not isinstance(self.expected_parent_device, int)
            or isinstance(self.expected_parent_device, bool)
            or self.expected_parent_device < 0
            or not isinstance(self.expected_parent_inode, int)
            or isinstance(self.expected_parent_inode, bool)
            or self.expected_parent_inode <= 0
        ):
            raise AtlasError("writable directory identity is invalid")

    @classmethod
    def measure(cls, source: Path) -> WritableDirectory:
        reject_exposed_host_path(source, label="native writable directory")
        absolute = Path(os.path.abspath(source))
        if absolute.name in {"", ".", ".."}:
            raise AtlasError("native writable directory must have a stable parent entry")
        parent_fd, parent = _open_verified_path(absolute.parent, BindKind.DIRECTORY)
        descriptor: int | None = None
        try:
            descriptor, measured = _open_directory_at(parent_fd, absolute.name)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(parent_fd)
        return cls(
            absolute,
            measured.st_dev,
            measured.st_ino,
            parent.st_dev,
            parent.st_ino,
        )


@dataclass(frozen=True)
class NativeInvocation:
    tool: NativeTool
    arguments: tuple[str, ...]
    writable_directory: WritableDirectory
    read_only_binds: tuple[ReadOnlyBind, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    private_paths: tuple[Path, ...] = ()
    check: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.tool, NativeTool):
            raise AtlasError("native tool must be a supported NativeTool value")
        if not isinstance(self.arguments, tuple) or any(
            not isinstance(item, str) or "\x00" in item for item in self.arguments
        ):
            raise AtlasError("native arguments must be a tuple of NUL-free strings")
        targets = [item.target for item in self.read_only_binds]
        if len(targets) != len(set(targets)):
            raise AtlasError("native read-only mount targets must be unique")
        if not isinstance(self.environment, tuple):
            raise AtlasError("native environment overrides must be a tuple")
        for key, value in self.environment:
            if (
                key not in _INVOCATION_ENVIRONMENT_KEYS
                or not isinstance(value, str)
                or "\x00" in value
                or len(value) > 128
            ):
                raise AtlasError("native environment override is unsupported or unsafe")
        private_values = [str(item) for item in self.private_paths]
        private_values.extend(str(item.source) for item in self.read_only_binds)
        private_values.append(str(self.writable_directory.source))
        if any(
            value and value in argument for value in private_values for argument in self.arguments
        ):
            raise AtlasError("native arguments must use sandbox paths, not private host paths")


@dataclass(frozen=True)
class NativeProcessResult:
    tool: NativeTool
    arguments: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    wall_seconds: float
    stdout_bytes: int
    stderr_bytes: int
    profile_version: str
    profile_sha256: str
    timed_out: bool = False
    output_limit_exceeded: bool = False


@dataclass(frozen=True)
class CapabilitySmoke:
    state: str
    namespace_isolation: dict[str, bool]
    loopback_network_denied: bool
    external_network_denied: bool
    home_directory_exposed: bool
    inherited_environment_exposed: bool
    root_write_denied: bool
    device_directory_write_denied: bool
    hostname_sanitized: bool
    detail: str | None = None

    @property
    def passed(self) -> bool:
        return (
            self.state == "passed"
            and bool(self.namespace_isolation)
            and all(self.namespace_isolation.values())
            and self.loopback_network_denied
            and self.external_network_denied
            and not self.home_directory_exposed
            and not self.inherited_environment_exposed
            and self.root_write_denied
            and self.device_directory_write_denied
            and self.hostname_sanitized
        )

    def as_record(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "passed": self.passed,
            "namespace_isolation": self.namespace_isolation,
            "loopback_network_denied": self.loopback_network_denied,
            "external_network_denied": self.external_network_denied,
            "home_directory_exposed": self.home_directory_exposed,
            "inherited_environment_exposed": self.inherited_environment_exposed,
            "root_write_denied": self.root_write_denied,
            "device_directory_write_denied": self.device_directory_write_denied,
            "hostname_sanitized": self.hostname_sanitized,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BubblewrapInventory:
    state: DependencyState
    basename: str
    path_class: str
    executable_sha256: str | None
    executable_size_bytes: int | None
    version: str | None
    package: dict[str, Any] | None
    capability_smoke: CapabilitySmoke | None
    dependency_identity_sha256: str | None
    executable_path: Path | None = None
    detail: str | None = None

    def as_record(self, *, include_private_path: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "state": self.state.value,
            "provider": "bubblewrap",
            "profile_version": PROFILE_VERSION,
            "profile_sha256": PROFILE_SHA256,
            "exposed_host_subtrees": list(_EXPOSED_HOST_SUBTREES),
            "masked_host_subtrees": list(_MASKED_HOST_SUBTREES),
            "executable": {
                "basename": self.basename,
                "path_class": self.path_class,
                "sha256": self.executable_sha256,
                "size_bytes": self.executable_size_bytes,
            },
            "version": self.version,
            "package": self.package,
            "capability_smoke": (
                self.capability_smoke.as_record() if self.capability_smoke is not None else None
            ),
            "dependency_identity_sha256": self.dependency_identity_sha256,
            "installation_command": BUBBLEWRAP_INSTALL_COMMAND,
            "network_accessed": False,
            "detail": self.detail,
        }
        if include_private_path:
            value["resolved_executable_path"] = (
                str(self.executable_path) if self.executable_path is not None else None
            )
        return value


def _sha256_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    for block in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
        digest.update(block)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def _open_verified_path(path: Path, kind: BindKind) -> tuple[int, os.stat_result]:
    try:
        before = os.lstat(path)
        expected_type = stat.S_ISREG if kind is BindKind.FILE else stat.S_ISDIR
        if not expected_type(before.st_mode):
            raise AtlasError(f"native {kind.value} bind must be a non-symlink {kind.value}")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        if kind is BindKind.DIRECTORY:
            flags |= getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        after = os.lstat(path)
    except AtlasError:
        raise
    except OSError as exc:
        raise AtlasError(f"native {kind.value} bind could not be opened safely") from exc
    identities = {
        (value.st_dev, value.st_ino, value.st_mode, value.st_size)
        for value in (before, opened, after)
    }
    if len(identities) != 1 or not expected_type(opened.st_mode):
        os.close(descriptor)
        raise AtlasError(f"native {kind.value} bind changed while it was opened")
    return descriptor, opened


def _open_directory_at(parent_fd: int, name: str) -> tuple[int, os.stat_result]:
    """Open one direct child directory through an already verified parent fd."""
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise AtlasError("native writable directory entry name is invalid")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(before.st_mode):
            raise AtlasError("native writable directory must be a non-symlink directory")
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        opened = os.fstat(descriptor)
        after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except AtlasError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise AtlasError("native writable directory could not be opened safely") from exc
    identities = {(value.st_dev, value.st_ino, value.st_mode) for value in (before, opened, after)}
    if len(identities) != 1 or not stat.S_ISDIR(opened.st_mode):
        os.close(descriptor)
        raise AtlasError("native writable directory changed while it was opened")
    return descriptor, opened


def _open_bind(value: ReadOnlyBind) -> int:
    descriptor, measured = _open_verified_path(value.source, value.kind)
    try:
        if (measured.st_dev, measured.st_ino) != (
            value.expected_device,
            value.expected_inode,
        ):
            raise AtlasError("native read-only bind identity changed")
        if value.kind is BindKind.FILE and (
            measured.st_size != value.expected_size
            or _sha256_descriptor(descriptor) != value.expected_sha256
        ):
            raise AtlasError("native read-only file content identity changed")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_work(value: WritableDirectory) -> int:
    parent_fd, parent = _open_verified_path(value.source.parent, BindKind.DIRECTORY)
    descriptor: int | None = None
    try:
        if (parent.st_dev, parent.st_ino) != (
            value.expected_parent_device,
            value.expected_parent_inode,
        ):
            raise AtlasError("native writable directory parent identity changed")
        descriptor, measured = _open_directory_at(parent_fd, value.source.name)
        if (measured.st_dev, measured.st_ino) != (
            value.expected_device,
            value.expected_inode,
        ):
            raise AtlasError("native writable directory identity changed")
        uid = os.geteuid() if hasattr(os, "geteuid") else None
        if (uid is not None and measured.st_uid != uid) or stat.S_IMODE(measured.st_mode) != 0o700:
            raise AtlasError("native writable directory must be current-UID owned with mode 0700")
        return descriptor
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        raise
    finally:
        os.close(parent_fd)


def _verify_open_work(value: WritableDirectory, descriptor: int) -> None:
    """Prove the descriptor-backed target still owns its original parent entry."""
    measured = os.fstat(descriptor)
    parent_fd, parent = _open_verified_path(value.source.parent, BindKind.DIRECTORY)
    try:
        current = os.stat(value.source.name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise AtlasError("native writable directory identity changed during execution") from exc
    finally:
        os.close(parent_fd)
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    if (
        (parent.st_dev, parent.st_ino)
        != (value.expected_parent_device, value.expected_parent_inode)
        or (measured.st_dev, measured.st_ino) != (value.expected_device, value.expected_inode)
        or (current.st_dev, current.st_ino) != (value.expected_device, value.expected_inode)
        or not stat.S_ISDIR(measured.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or stat.S_IMODE(measured.st_mode) != 0o700
        or stat.S_IMODE(current.st_mode) != 0o700
        or (uid is not None and (measured.st_uid != uid or current.st_uid != uid))
    ):
        raise AtlasError("native writable directory identity changed during execution")


def _profile_prefix() -> list[str]:
    return list(_PROFILE_PREFIX_ARGUMENTS)


def _profile_suffix() -> list[str]:
    return list(_PROFILE_SUFFIX_ARGUMENTS)


def _path_class(path: Path) -> str:
    return "system" if str(path).startswith(("/usr/", "/bin/", "/opt/")) else "operator-supplied"


def _dependency_identity(
    basename: str,
    executable_sha256: str,
    executable_size_bytes: int,
    version: str,
    package: dict[str, Any] | None,
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "basename": basename,
                "sha256": executable_sha256,
                "size_bytes": executable_size_bytes,
                "version": version,
                "package": package,
                "profile_sha256": PROFILE_SHA256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _package_record(path: Path) -> dict[str, Any] | None:
    query = shutil.which("dpkg-query")
    if query is None:
        return None
    try:
        owner = subprocess.run(
            [query, "-S", str(path)],
            check=True,
            capture_output=True,
            text=True,
            shell=False,
            timeout=5,
        ).stdout.split(":", 1)[0]
        fields = (
            subprocess.run(
                [
                    query,
                    "-W",
                    "-f=${binary:Package}\t${Version}\t${Architecture}\t${source:Package}\t${source:Version}",
                    owner,
                ],
                check=True,
                capture_output=True,
                text=True,
                shell=False,
                timeout=5,
            )
            .stdout.strip()
            .split("\t")
        )
        if len(fields) != 5:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    package = fields[0].split(":", 1)[0]
    copyright_path = Path("/usr/share/doc") / package / "copyright"
    license_id = "unknown-not-verified"
    license_verification = "installed package copyright metadata unavailable"
    license_hash: str | None = None
    if copyright_path.is_file():
        try:
            value = copyright_path.read_text(encoding="utf-8", errors="replace")
            license_hash = hashlib.sha256(value.encode("utf-8")).hexdigest()
            first_license = next(
                (
                    line.split(":", 1)[1].strip()
                    for line in value.splitlines()
                    if line.startswith("License:")
                ),
                None,
            )
            if first_license:
                license_id = first_license
            license_verification = "read installed package copyright metadata"
        except OSError:
            license_verification = "installed package copyright metadata unreadable"
    return {
        "package": fields[0],
        "version": fields[1],
        "architecture": fields[2],
        "source_package": fields[3] or package,
        "source_version": fields[4] or fields[1],
        "license_id": license_id,
        "license_verification": license_verification,
        "license_file_basename": copyright_path.name if copyright_path.is_file() else None,
        "license_file_sha256": license_hash,
    }


_SMOKE_SCRIPT = """import json, os, socket
namespace_names = ('user','pid','ipc','uts','net','mnt')
names = {name: os.readlink('/proc/self/ns/' + name) for name in namespace_names}
def denied(host, port):
    sock = socket.socket(); sock.settimeout(0.2)
    try:
        sock.connect((host, port)); return False
    except OSError:
        return True
    finally:
        sock.close()
def cannot_write(path):
    try:
        open(path, 'wb').write(b'x'); return False
    except OSError:
        return True
print(json.dumps({'namespaces': names,
 'loopback_denied': denied('127.0.0.1', 9),
 'external_denied': denied('192.0.2.1', 9),
 'home_exposed': os.path.exists(os.environ.get('HOME','')),
 'environment_exposed': 'AV_ATLAS_HOST_SENTINEL' in os.environ,
 'root_write_denied': cannot_write('/escape'),
 'device_write_denied': cannot_write('/dev/escape'),
 'hostname_sanitized': socket.gethostname() == 'av-atlas-pilot'}))
"""


def _capability_smoke(executable_fd: int) -> CapabilitySmoke:
    host_namespaces = {
        name: os.readlink(f"/proc/self/ns/{name}")
        for name in ("user", "pid", "ipc", "uts", "net", "mnt")
    }
    command = [
        f"/proc/self/fd/{executable_fd}",
        *_profile_prefix(),
        *_profile_suffix(),
        "--",
        "/usr/bin/python3",
        "-c",
        _SMOKE_SCRIPT,
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
            timeout=5,
            pass_fds=(executable_fd,),
            env={
                "AV_ATLAS_HOST_SENTINEL": "must-not-cross",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
            },
        )
        if len(completed.stdout.encode("utf-8")) > 16_384:
            raise ValueError("smoke output exceeded its fixed bound")
        value = json.loads(completed.stdout)
        sandbox_namespaces = value["namespaces"]
        isolation = {
            name: sandbox_namespaces[name] != host_namespaces[name] for name in host_namespaces
        }
        smoke = CapabilitySmoke(
            "passed",
            isolation,
            bool(value["loopback_denied"]),
            bool(value["external_denied"]),
            bool(value["home_exposed"]),
            bool(value["environment_exposed"]),
            bool(value["root_write_denied"]),
            bool(value["device_write_denied"]),
            bool(value["hostname_sanitized"]),
        )
        if not smoke.passed:
            return CapabilitySmoke(
                "failed",
                isolation,
                smoke.loopback_network_denied,
                smoke.external_network_denied,
                smoke.home_directory_exposed,
                smoke.inherited_environment_exposed,
                smoke.root_write_denied,
                smoke.device_directory_write_denied,
                smoke.hostname_sanitized,
                "one or more required isolation properties failed",
            )
        return smoke
    except (
        OSError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        return CapabilitySmoke(
            "failed",
            {},
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            f"capability smoke failed safely: {type(exc).__name__}",
        )


def inspect_bubblewrap(
    *,
    include_private_path: bool = False,
    expected_executable_sha256: str | None = None,
    expected_executable_size_bytes: int | None = None,
) -> dict[str, Any]:
    """Return a sanitized dependency inventory and measured namespace smoke result."""
    if (expected_executable_sha256 is None) != (expected_executable_size_bytes is None):
        raise AtlasError("Bubblewrap expected hash and size must be supplied together")
    if expected_executable_sha256 is not None and not _HASH_PATTERN.fullmatch(
        expected_executable_sha256
    ):
        raise AtlasError("Bubblewrap expected executable hash is invalid")
    if expected_executable_size_bytes is not None and (
        not isinstance(expected_executable_size_bytes, int)
        or isinstance(expected_executable_size_bytes, bool)
        or expected_executable_size_bytes <= 0
    ):
        raise AtlasError("Bubblewrap expected executable size is invalid")
    candidate = shutil.which("bwrap")
    if candidate is None:
        return BubblewrapInventory(
            DependencyState.UNAVAILABLE,
            "bwrap",
            "unavailable",
            None,
            None,
            None,
            None,
            None,
            None,
            detail="Bubblewrap is unavailable; the pilot sandbox fails closed",
        ).as_record(include_private_path=include_private_path)
    resolved = Path(candidate).resolve()
    descriptor: int | None = None
    try:
        descriptor, measured = _open_verified_path(resolved, BindKind.FILE)
        digest = _sha256_descriptor(descriptor)
        if expected_executable_sha256 is not None and (
            digest != expected_executable_sha256
            or measured.st_size != expected_executable_size_bytes
        ):
            return BubblewrapInventory(
                DependencyState.UNSUPPORTED,
                resolved.name,
                _path_class(resolved),
                digest,
                measured.st_size,
                None,
                None,
                None,
                None,
                resolved,
                "Bubblewrap candidate differs from the policy-approved executable; "
                "no candidate code was executed",
            ).as_record(include_private_path=include_private_path)
        version_result = subprocess.run(
            [f"/proc/self/fd/{descriptor}", "--version"],
            check=True,
            capture_output=True,
            text=True,
            shell=False,
            timeout=5,
            pass_fds=(descriptor,),
        )
        version = (version_result.stdout or version_result.stderr).strip().splitlines()[0]
        smoke = _capability_smoke(descriptor)
        state = DependencyState.AVAILABLE if smoke.passed else DependencyState.UNSUPPORTED
        package = _package_record(resolved)
        identity = _dependency_identity(
            resolved.name,
            digest,
            measured.st_size,
            version,
            package,
        )
        inventory = BubblewrapInventory(
            state,
            resolved.name,
            _path_class(resolved),
            digest,
            measured.st_size,
            version,
            package,
            smoke,
            identity,
            resolved,
            None if smoke.passed else "required Bubblewrap capability smoke failed",
        )
    except (AtlasError, OSError, subprocess.SubprocessError, IndexError) as exc:
        inventory = BubblewrapInventory(
            DependencyState.UNSUPPORTED,
            resolved.name,
            _path_class(resolved),
            None,
            None,
            None,
            None,
            None,
            None,
            resolved,
            f"Bubblewrap inventory failed safely: {type(exc).__name__}",
        )
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return inventory.as_record(include_private_path=include_private_path)


def load_bubblewrap_inventory(
    *,
    expected_executable_sha256: str | None = None,
    expected_executable_size_bytes: int | None = None,
) -> BubblewrapInventory:
    """Load the private executable identity required by the runner."""
    public = inspect_bubblewrap(
        include_private_path=True,
        expected_executable_sha256=expected_executable_sha256,
        expected_executable_size_bytes=expected_executable_size_bytes,
    )
    state = DependencyState(public["state"])
    executable = public["executable"]
    smoke_value = public.get("capability_smoke")
    smoke = (
        CapabilitySmoke(
            smoke_value["state"],
            smoke_value["namespace_isolation"],
            smoke_value["loopback_network_denied"],
            smoke_value["external_network_denied"],
            smoke_value["home_directory_exposed"],
            smoke_value["inherited_environment_exposed"],
            smoke_value["root_write_denied"],
            smoke_value["device_directory_write_denied"],
            smoke_value["hostname_sanitized"],
            smoke_value["detail"],
        )
        if isinstance(smoke_value, dict)
        else None
    )
    return BubblewrapInventory(
        state,
        executable["basename"],
        executable["path_class"],
        executable["sha256"],
        executable["size_bytes"],
        public["version"],
        public["package"],
        smoke,
        public["dependency_identity_sha256"],
        Path(public["resolved_executable_path"])
        if public.get("resolved_executable_path")
        else None,
        public["detail"],
    )


def _anonymous_capture(directory_fd: int) -> BinaryIO:
    name = f".av-atlas-native-capture-{secrets.token_hex(16)}"
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        os.fchmod(descriptor, 0o600)
        os.unlink(name, dir_fd=directory_fd)
    except BaseException:
        os.close(descriptor)
        raise
    return os.fdopen(descriptor, "w+b")


def _terminate_process_group(process: subprocess.Popen[bytes], grace_seconds: float) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=grace_seconds)
        # The OS still owns cleanup; callers receive a controlled failure.


def _capture_value(handle: BinaryIO, maximum: int) -> tuple[str, int]:
    size = os.fstat(handle.fileno()).st_size
    handle.seek(0)
    value = handle.read(maximum + 1)
    return value[:maximum].decode("utf-8", errors="replace"), size


def _redact_native_paths(value: str, paths: tuple[Path, ...]) -> str:
    """Redact exact private host paths without corrupting ordinary words/JSON keys."""
    sanitized = value
    for path in sorted({str(item) for item in paths if str(item)}, key=len, reverse=True):
        sanitized = sanitized.replace(path, "<private-host-path>")
    return sanitized


class BubblewrapNativeRunner:
    """No-fallback pilot runner bound to one measured Bubblewrap identity."""

    def __init__(
        self,
        inventory: BubblewrapInventory,
        limits: NativeResourceLimits | None = None,
        before_run: Callable[[], None] | None = None,
    ) -> None:
        if (
            inventory.state is not DependencyState.AVAILABLE
            or inventory.executable_path is None
            or inventory.executable_sha256 is None
            or inventory.executable_size_bytes is None
            or inventory.capability_smoke is None
            or not inventory.capability_smoke.passed
        ):
            raise AtlasError(
                "Bubblewrap pilot sandbox is unavailable or unsupported; "
                f"install/verify with: {BUBBLEWRAP_INSTALL_COMMAND}"
            )
        if inventory.version is None or inventory.dependency_identity_sha256 != (
            _dependency_identity(
                inventory.basename,
                inventory.executable_sha256,
                inventory.executable_size_bytes,
                inventory.version,
                inventory.package,
            )
        ):
            raise AtlasError("Bubblewrap dependency or sandbox profile identity is inconsistent")
        self.inventory = inventory
        self.limits = limits or NativeResourceLimits()
        self.before_run = before_run

    @classmethod
    def from_current_host(
        cls, limits: NativeResourceLimits | None = None
    ) -> BubblewrapNativeRunner:
        return cls(load_bubblewrap_inventory(), limits)

    def _open_bubblewrap(self) -> int:
        assert self.inventory.executable_path is not None
        descriptor, measured = _open_verified_path(
            self.inventory.executable_path,
            BindKind.FILE,
        )
        try:
            if (
                measured.st_size != self.inventory.executable_size_bytes
                or _sha256_descriptor(descriptor) != self.inventory.executable_sha256
            ):
                raise AtlasError("Bubblewrap executable changed after dependency approval")
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def run(self, invocation: NativeInvocation) -> NativeProcessResult:
        """Run one fixed native tool with bounded captures and guaranteed teardown."""
        if self.before_run is not None:
            self.before_run()
        limits = self.limits
        bind_descriptors: list[int] = []
        work_fd: int | None = None
        bubblewrap_fd: int | None = None
        stdout_handle: BinaryIO | None = None
        stderr_handle: BinaryIO | None = None
        process: subprocess.Popen[bytes] | None = None
        private_paths = (
            *invocation.private_paths,
            invocation.writable_directory.source,
            *(item.source for item in invocation.read_only_binds),
        )
        started = time.monotonic()
        try:
            bubblewrap_fd = self._open_bubblewrap()
            work_fd = _open_work(invocation.writable_directory)
            for item in invocation.read_only_binds:
                bind_descriptors.append(_open_bind(item))
            inherited_count = 4 + len(bind_descriptors)
            if inherited_count >= limits.open_files:
                raise ResourceLimitError("native input bind count exceeds the open-file limit")
            stdout_handle = _anonymous_capture(work_fd)
            stderr_handle = _anonymous_capture(work_fd)
            sandbox_arguments = _profile_prefix()
            for item, descriptor in zip(invocation.read_only_binds, bind_descriptors, strict=True):
                sandbox_arguments.extend(["--ro-bind", f"/proc/self/fd/{descriptor}", item.target])
            sandbox_arguments.extend(["--bind", f"/proc/self/fd/{work_fd}", "/work"])
            for key, value in sorted(invocation.environment):
                sandbox_arguments.extend(["--setenv", key, value])
            sandbox_arguments.extend(_profile_suffix())
            sandbox_arguments.extend(["--", _TOOL_PATHS[invocation.tool], *invocation.arguments])
            helper = [
                sys.executable,
                "-m",
                "av_atlas.native_exec_helper",
                "--bwrap-fd",
                str(bubblewrap_fd),
                "--cpu-seconds",
                str(limits.cpu_seconds),
                "--address-space-bytes",
                str(limits.address_space_bytes),
                "--file-size-bytes",
                str(limits.file_size_bytes),
                "--open-files",
                str(limits.open_files),
                "--process-count",
                str(limits.process_count),
                "--",
                *sandbox_arguments,
            ]
            pass_fds = (bubblewrap_fd, work_fd, *bind_descriptors)
            process = subprocess.Popen(
                helper,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                shell=False,
                close_fds=True,
                pass_fds=pass_fds,
                start_new_session=True,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            )
            deadline = started + limits.wall_seconds
            output_limit = False
            timed_out = False
            while process.poll() is None:
                stdout_size = os.fstat(stdout_handle.fileno()).st_size
                stderr_size = os.fstat(stderr_handle.fileno()).st_size
                if stdout_size > limits.stdout_bytes or stderr_size > limits.stderr_bytes:
                    output_limit = True
                    _terminate_process_group(process, limits.termination_grace_seconds)
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    _terminate_process_group(process, limits.termination_grace_seconds)
                    break
                with suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=min(0.02, remaining))
            returncode = process.wait()
            _verify_open_work(invocation.writable_directory, work_fd)
            stdout, stdout_size = _capture_value(stdout_handle, limits.stdout_bytes)
            stderr, stderr_size = _capture_value(stderr_handle, limits.stderr_bytes)
            stdout = _redact_native_paths(stdout, private_paths)
            stderr = _redact_native_paths(stderr, private_paths)
            output_limit = output_limit or stdout_size > limits.stdout_bytes
            output_limit = output_limit or stderr_size > limits.stderr_bytes
            result = NativeProcessResult(
                invocation.tool,
                invocation.arguments,
                returncode,
                stdout,
                stderr,
                time.monotonic() - started,
                stdout_size,
                stderr_size,
                PROFILE_VERSION,
                PROFILE_SHA256,
                timed_out,
                output_limit,
            )
            if timed_out:
                raise ResourceLimitError(
                    f"sandboxed {invocation.tool.value} exceeded the wall-time limit"
                )
            if output_limit:
                raise ResourceLimitError(
                    f"sandboxed {invocation.tool.value} exceeded a capture-size limit"
                )
            if invocation.check and returncode != 0:
                detail = (stderr or stdout or f"exit status {returncode}").strip().splitlines()[-1]
                raise AtlasError(
                    f"sandboxed {invocation.tool.value} failed: "
                    f"{_redact_native_paths(detail, private_paths)}"
                )
            return result
        except (KeyboardInterrupt, SystemExit):
            if process is not None:
                _terminate_process_group(process, limits.termination_grace_seconds)
            raise
        except (AtlasError, ResourceLimitError):
            if process is not None:
                _terminate_process_group(process, limits.termination_grace_seconds)
            raise
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, OverflowError) as exc:
            if process is not None:
                _terminate_process_group(process, limits.termination_grace_seconds)
            raise AtlasError("sandboxed native process failed safely") from exc
        finally:
            if stdout_handle is not None:
                stdout_handle.close()
            if stderr_handle is not None:
                stderr_handle.close()
            for descriptor in bind_descriptors:
                os.close(descriptor)
            if work_fd is not None:
                os.close(work_fd)
            if bubblewrap_fd is not None:
                os.close(bubblewrap_fd)


def _masked_runtime_sentinel() -> Path:
    """Select one readable file whose bytes a whole-/usr bind would expose."""
    scanned = 0
    for candidate in _MASKED_RUNTIME_SENTINEL_CANDIDATES:
        try:
            measured = os.lstat(candidate)
        except OSError:
            continue
        if stat.S_ISREG(measured.st_mode):
            return candidate
        if not stat.S_ISDIR(measured.st_mode):
            continue
        pending: list[tuple[Path, int]] = [(candidate, 0)]
        while pending:
            current, depth = pending.pop(0)
            try:
                entries = sorted(os.scandir(current), key=lambda entry: entry.name)
            except OSError:
                continue
            for entry in entries:
                scanned += 1
                if scanned > 512:
                    raise AtlasError("sandbox masked-runtime sentinel scan exceeded its bound")
                try:
                    value = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                path = current / entry.name
                if stat.S_ISREG(value.st_mode) and os.access(path, os.R_OK):
                    return path
                if stat.S_ISDIR(value.st_mode) and depth < 3:
                    pending.append((path, depth + 1))
    raise AtlasError("sandbox masked-runtime sentinel is unavailable on this host")


def run_hostile_sandbox_probes(
    runner: BubblewrapNativeRunner,
    writable_directory: WritableDirectory,
    outside_sentinel: Path,
) -> dict[str, bool]:
    """Measure the fixed sandbox denials with project-authored probe code."""
    sentinel = Path(os.path.abspath(outside_sentinel))
    work = writable_directory.source
    if sentinel == work or sentinel.is_relative_to(work):
        raise AtlasError("sandbox hostile sentinel must be outside the writable sandbox mount")
    try:
        sentinel_stat = os.lstat(sentinel)
    except OSError as exc:
        raise AtlasError("sandbox hostile sentinel is unavailable") from exc
    if not stat.S_ISREG(sentinel_stat.st_mode):
        raise AtlasError("sandbox hostile sentinel must be a regular non-symlink file")
    masked_runtime_sentinel = _masked_runtime_sentinel()
    parent_fd, _ = _open_verified_path(sentinel.parent, BindKind.DIRECTORY)
    positive_name: str | None = None
    positive_fd: int | None = None
    positive_payload = b"av-atlas-host-writable-positive-control\n"
    for _ in range(8):
        candidate = f".av-atlas-outside-write-probe-{secrets.token_hex(16)}"
        try:
            positive_fd = os.open(
                candidate,
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
        except FileExistsError:
            continue
        positive_name = candidate
        break
    if positive_fd is None or positive_name is None:
        os.close(parent_fd)
        raise AtlasError("sandbox outside-write positive control could not be allocated")
    positive_path = sentinel.parent / positive_name
    try:
        os.fchmod(positive_fd, 0o600)
        if os.write(positive_fd, positive_payload) != len(positive_payload):
            raise AtlasError("sandbox outside-write positive control write was incomplete")
        os.fsync(positive_fd)
        os.lseek(positive_fd, 0, os.SEEK_SET)
        host_write_positive = os.read(positive_fd, len(positive_payload) + 1) == positive_payload
    except BaseException:
        os.close(positive_fd)
        os.unlink(positive_name, dir_fd=parent_fd)
        os.close(parent_fd)
        raise
    sentinel_encoded = base64.b64encode(str(sentinel).encode("utf-8")).decode("ascii")
    masked_runtime_encoded = base64.b64encode(str(masked_runtime_sentinel).encode("utf-8")).decode(
        "ascii"
    )
    positive_encoded = base64.b64encode(str(positive_path).encode("utf-8")).decode("ascii")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
    except BaseException:
        listener.close()
        os.close(positive_fd)
        os.unlink(positive_name, dir_fd=parent_fd)
        os.close(parent_fd)
        raise
    loopback_port = int(listener.getsockname()[1])
    script = f"""import base64, json, os, socket
def readable(path):
    try: open(path, 'rb').read(1); return True
    except OSError: return False
def writable(path):
    try: open(path, 'wb').write(b'x'); return True
    except OSError: return False
def denied(host, port):
    sock=socket.socket(); sock.settimeout(0.2)
    try: sock.connect((host,port)); return False
    except OSError: return True
    finally: sock.close()
masked_runtime_sentinel=base64.b64decode('{masked_runtime_encoded}').decode()
value={{
 'outside_sentinel_denied': not readable(base64.b64decode('{sentinel_encoded}').decode()),
 'masked_runtime_sentinel_denied': not os.path.exists(masked_runtime_sentinel),
 'outside_host_write_denied': not writable(base64.b64decode('{positive_encoded}').decode()),
 'outside_root_write_denied': not writable('/escape'),
 'device_directory_write_denied': not writable('/dev/escape'),
 'work_write_allowed': writable('/work/probe-allowed'),
 'tmp_write_allowed': writable('/tmp/probe-allowed'),
 'loopback_network_denied': denied('127.0.0.1',{loopback_port}),
 'external_network_denied': denied('192.0.2.1',9),
 'home_directory_denied': not os.path.exists(os.environ.get('HOME','')),
 'inherited_environment_denied': 'AV_ATLAS_HOST_SENTINEL' not in os.environ,
 'hostname_sanitized': socket.gethostname() == '{_SANDBOX_HOSTNAME}',
}}
print(json.dumps(value))
"""
    try:
        try:
            result = runner.run(
                NativeInvocation(
                    NativeTool.PYTHON_PROBE,
                    ("-c", script),
                    writable_directory,
                    private_paths=(sentinel, positive_path, masked_runtime_sentinel),
                )
            )
            os.lseek(positive_fd, 0, os.SEEK_SET)
            positive_unchanged = os.read(positive_fd, len(positive_payload) + 1) == positive_payload
        finally:
            os.close(positive_fd)
            os.unlink(positive_name, dir_fd=parent_fd)
            os.fsync(parent_fd)
            os.close(parent_fd)
    finally:
        listener.close()
    try:
        value = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AtlasError("sandbox hostile probe returned invalid bounded output") from exc
    expected = {
        "outside_sentinel_denied",
        "masked_runtime_sentinel_denied",
        "outside_host_write_denied",
        "outside_root_write_denied",
        "device_directory_write_denied",
        "work_write_allowed",
        "tmp_write_allowed",
        "loopback_network_denied",
        "external_network_denied",
        "home_directory_denied",
        "inherited_environment_denied",
        "hostname_sanitized",
    }
    if set(value) != expected or not all(isinstance(item, bool) for item in value.values()):
        raise AtlasError("sandbox hostile probe returned an unexpected result contract")
    return {
        **{key: bool(value[key]) for key in sorted(expected)},
        "outside_write_positive_control": host_write_positive and positive_unchanged,
    }


def profile_record() -> dict[str, Any]:
    return {**_SYSTEM_PROFILE, "profile_sha256": PROFILE_SHA256}
