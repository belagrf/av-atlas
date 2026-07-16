"""Set native-process resource limits, then replace this process with bubblewrap.

This module is deliberately small and standard-library-only.  The parent process
starts it in a new session and passes already-open descriptors.  Keeping limit
setup here avoids ``preexec_fn`` in the multithreaded OCR process.
"""

from __future__ import annotations

import argparse
import os
import resource
from collections.abc import Sequence


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("resource limits must be positive integers")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--bwrap-fd", type=_positive_integer, required=True)
    parser.add_argument("--cpu-seconds", type=_positive_integer, required=True)
    parser.add_argument("--address-space-bytes", type=_positive_integer, required=True)
    parser.add_argument("--file-size-bytes", type=_positive_integer, required=True)
    parser.add_argument("--open-files", type=_positive_integer, required=True)
    parser.add_argument("--process-count", type=_positive_integer, required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def _set_limits(
    *,
    cpu_seconds: int,
    address_space_bytes: int,
    file_size_bytes: int,
    open_files: int,
    process_count: int,
) -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(
        resource.RLIMIT_AS,
        (address_space_bytes, address_space_bytes),
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_size_bytes, file_size_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (open_files, open_files))
    resource.setrlimit(resource.RLIMIT_NPROC, (process_count, process_count))


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    command = list(args.arguments)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        _parser().error("a bubblewrap argument array is required after --")
    os.umask(0o077)
    _set_limits(
        cpu_seconds=args.cpu_seconds,
        address_space_bytes=args.address_space_bytes,
        file_size_bytes=args.file_size_bytes,
        open_files=args.open_files,
        process_count=args.process_count,
    )
    executable = f"/proc/self/fd/{args.bwrap_fd}"
    environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }
    os.execve(executable, ["bwrap", *command], environment)
    return 127  # pragma: no cover - a successful exec never returns


if __name__ == "__main__":  # pragma: no cover - exercised through the runner
    raise SystemExit(main())
