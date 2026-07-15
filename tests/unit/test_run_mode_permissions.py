import subprocess
from pathlib import Path

import pytest

from av_atlas.cli import main
from av_atlas.errors import AtlasError
from av_atlas.rights import (
    RUN_MODE_PERMISSIONS,
    create_rights_manifest,
    load_and_validate_rights,
    required_permissions_for_run_mode,
)


def _manifest(tmp_path: Path, allowed: set[str]) -> tuple[Path, dict[str, object]]:
    media = tmp_path / "source.bin"
    media.write_bytes(b"permission closure source")
    path = tmp_path / "rights.json"
    value = create_rights_manifest(media, path, "operator", "owned", allowed)
    return path, value


def test_run_mode_permission_matrix_is_explicit() -> None:
    assert RUN_MODE_PERMISSIONS == {
        "analysis": ("analysis", "derivative_artifact_retention"),
        "evaluation": ("analysis", "evaluation", "derivative_artifact_retention"),
    }
    assert required_permissions_for_run_mode("analysis") == RUN_MODE_PERMISSIONS["analysis"]
    assert required_permissions_for_run_mode("evaluation") == RUN_MODE_PERMISSIONS["evaluation"]
    for unsupported in (
        "annotation",
        "training",
        "derivative_artifact_retention",
        "redistribution",
    ):
        with pytest.raises(AtlasError, match="unsupported run mode"):
            required_permissions_for_run_mode(unsupported)


@pytest.mark.parametrize(
    ("mode", "allowed", "expected"),
    [
        ("analysis", {"analysis", "derivative_artifact_retention"}, None),
        ("analysis", {"analysis", "evaluation", "derivative_artifact_retention"}, None),
        ("evaluation", {"analysis", "evaluation", "derivative_artifact_retention"}, None),
        ("evaluation", {"evaluation", "derivative_artifact_retention"}, "analysis"),
        ("evaluation", {"analysis", "derivative_artifact_retention"}, "evaluation"),
        ("analysis", {"analysis"}, "derivative_artifact_retention"),
    ],
)
def test_persisted_loader_enforces_complete_permission_closure(
    tmp_path: Path, mode: str, allowed: set[str], expected: str | None
) -> None:
    path, value = _manifest(tmp_path, allowed)
    if expected is None:
        loaded = load_and_validate_rights(
            path, str(value["content_sha256"]), str(value["source_id"]), mode
        )
        assert loaded == value
    else:
        with pytest.raises(AtlasError, match=expected):
            load_and_validate_rights(
                path, str(value["content_sha256"]), str(value["source_id"]), mode
            )


@pytest.mark.parametrize(
    "run_mode",
    ["annotation", "training", "derivative_artifact_retention", "redistribution"],
)
def test_public_cli_rejects_unsupported_run_modes_before_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_mode: str,
) -> None:
    invoked: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        invoked.append("subprocess")
        raise AssertionError("unsupported run mode must fail during CLI parsing")

    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "run",
                str(tmp_path / "media.bin"),
                "--config",
                str(tmp_path / "config.json"),
                "--output",
                str(tmp_path / "run"),
                "--operation",
                run_mode,
            ]
        )
    assert exc.value.code == 2
    assert invoked == []
