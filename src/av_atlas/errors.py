"""Project-specific errors surfaced by the CLI."""

from pathlib import Path


class AtlasError(Exception):
    """Actionable user-facing error."""


class ResourceLimitError(AtlasError):
    """A configured local decode or output budget was exceeded."""


def redact_private_paths(detail: str, *paths: Path) -> str:
    """Remove private transient path values from native-tool diagnostics."""
    sanitized = detail
    for path in paths:
        value = str(path)
        sanitized = sanitized.replace(value, "<authorized-input>")
        sanitized = sanitized.replace(str(path.parent), "<private-input-directory>")
        sanitized = sanitized.replace(path.name, "<authorized-input>")
    return sanitized
