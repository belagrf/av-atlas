"""Project-specific errors surfaced by the CLI."""


class AtlasError(Exception):
    """Actionable user-facing error."""


class ResourceLimitError(AtlasError):
    """A configured local decode or output budget was exceeded."""
