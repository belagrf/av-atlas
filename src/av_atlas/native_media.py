"""Versioned, fail-closed native media input policy.

The policy is intentionally fixed in code rather than operator-configurable.  A
top-level snapshot alone does not prevent libavformat demuxers from opening
nested resources, so every supported runtime input is supplied with an explicit
protocol whitelist and forced single-resource demuxer.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av_atlas.errors import AtlasError
from av_atlas.schemas import validate_instance

CONTRACT_VERSION = "av-atlas-native-input/1.0.0"
SCHEMA_VERSION = "1.0.0"
PROTOCOL_WHITELIST = ("file",)
MAGIC_READ_BYTES = 16


@dataclass(frozen=True)
class NativeInputPolicy:
    """One immutable FFmpeg/FFprobe input boundary."""

    role: str
    demuxer: str
    accepted_reported_formats: tuple[str, ...]
    selection: str

    def arguments(self, path: Path, *, seek_ms: int | None = None) -> list[str]:
        """Return fixed input arguments with only a bounded integer seek option."""
        if seek_ms is not None and (
            not isinstance(seek_ms, int) or isinstance(seek_ms, bool) or seek_ms < 0
        ):
            raise AtlasError("native input seek must be a nonnegative integer millisecond value")
        seek_arguments = [] if seek_ms is None else ["-ss", f"{seek_ms / 1000:.3f}"]
        return [
            "-protocol_whitelist",
            ",".join(PROTOCOL_WHITELIST),
            "-format_whitelist",
            self.demuxer,
            "-f",
            self.demuxer,
            *seek_arguments,
            "-i",
            str(path),
        ]

    def as_record(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "role": self.role,
            "selection": self.selection,
            "demuxer": self.demuxer,
            "protocol_whitelist": list(PROTOCOL_WHITELIST),
            "format_whitelist": [self.demuxer],
            "accepted_reported_formats": list(self.accepted_reported_formats),
            "multi_resource_inputs_permitted": False,
        }
        validate_instance("native_input_policy", value, "native input policy")
        return value

    def validate_reported_formats(self, formats: list[str]) -> None:
        reported = {item for item in formats if item}
        if not reported or not reported.issubset(set(self.accepted_reported_formats)):
            raise AtlasError("native parser reported a format outside the forced demuxer policy")


AUTHORIZED_MATROSKA = NativeInputPolicy(
    role="authorized_source",
    demuxer="matroska",
    accepted_reported_formats=("matroska", "webm"),
    selection="parser-free-ebml-magic",
)

GENERATED_PNG = NativeInputPolicy(
    role="generated_single_frame",
    demuxer="png_pipe",
    accepted_reported_formats=("png_pipe",),
    selection="trusted-generated-png-contract",
)


def _stable_prefix(path: Path) -> bytes:
    """Read a bounded prefix without following a final symlink or accepting replacement."""
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("input is not a regular file")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened = os.fstat(descriptor)
            prefix = os.read(descriptor, MAGIC_READ_BYTES)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        final = os.lstat(path)
    except OSError as exc:
        raise AtlasError("native input could not be classified as stable regular bytes") from exc
    identities = [
        (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        for value in (before, opened, after, final)
    ]
    if not stat.S_ISREG(opened.st_mode) or len(set(identities)) != 1:
        raise AtlasError("native input changed during parser-free format classification")
    return prefix


def classify_authorized_source(path: Path) -> NativeInputPolicy:
    """Select only a reviewed self-contained demuxer from parser-free magic bytes."""
    prefix = _stable_prefix(path)
    if prefix.startswith(b"\x1aE\xdf\xa3"):
        return AUTHORIZED_MATROSKA
    raise AtlasError(
        "unsupported native input format: M2B.2 accepts only self-contained Matroska/WebM; "
        "playlist, manifest, image-sequence, Blu-ray, and other multi-resource inputs are denied"
    )


def classify_generated_png(path: Path) -> NativeInputPolicy:
    """Verify a generated frame signature before invoking the single-PNG demuxer."""
    prefix = _stable_prefix(path)
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return GENERATED_PNG
    raise AtlasError("generated OCR frame is not a stable PNG input")


def enforce_path_policy(path: Path, expected: NativeInputPolicy) -> None:
    """Reclassify immediately before decoding and require the recorded fixed policy."""
    if expected.role == "authorized_source":
        measured = classify_authorized_source(path)
    elif expected.role == "generated_single_frame":
        measured = classify_generated_png(path)
    else:  # pragma: no cover - dataclass values are fixed by this module
        raise AtlasError("unsupported native-input policy role")
    if measured != expected:
        raise AtlasError("native input no longer matches its recorded parser policy")


def policy_from_inventory(inventory: dict[str, Any]) -> NativeInputPolicy:
    """Reconstruct and verify the fixed source policy recorded by inventory."""
    value = inventory.get("native_input_policy")
    validate_instance("native_input_policy", value, "inventory native input policy")
    if value != AUTHORIZED_MATROSKA.as_record():
        raise AtlasError("inventory native-input policy is unsupported or was altered")
    return AUTHORIZED_MATROSKA
