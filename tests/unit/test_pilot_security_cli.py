from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

from av_atlas import cli
from av_atlas.errors import AtlasError
from av_atlas.native_process import BUBBLEWRAP_INSTALL_COMMAND


def _policy(private_root: str = "/home/operator/private-pilot") -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "contract_version": "av-atlas-pilot-security-policy/1.0.0",
        "pilot_id": "PILOT_SYNTHETIC",
        "pilot_spec_sha256": "1" * 64,
        "pilot_spec_size_bytes": 512,
        "created_at": "2030-01-01T00:00:00+00:00",
        "expires_at": "2030-01-02T00:00:00+00:00",
        "private_root": {
            "path": private_root,
            "expected_device": 1,
            "expected_inode": 2,
            "expected_uid": 1000,
            "expected_mode": "0700",
            "mount_identity_sha256": "2" * 64,
        },
        "storage": {
            "decision": "verified-tmpfs",
            "expected_filesystem_type": "tmpfs",
            "independently_reviewed": False,
            "review_record": None,
            "review_scope": None,
            "review_expires_at": None,
            "compensating_controls": [],
            "deletion_plan": None,
            "tmpfs_swap_warning_acknowledged": True,
            "secure_erasure_claimed": False,
        },
        "capacity": {
            "source_byte_ceiling": 1024,
            "temporary_byte_ceiling": 2048,
            "reserve_bytes": 0,
        },
        "sandbox": {
            "provider": "bubblewrap",
            "profile_contract_version": "av-atlas-bubblewrap-pilot/1.0.0",
            "profile_sha256": "3" * 64,
            "executable_basename": "bwrap",
            "executable_sha256": "4" * 64,
            "executable_size_bytes": 100,
            "version": "bubblewrap test",
            "capability_state": "passed",
        },
        "resource_limits": {
            "wall_timeout_seconds": 30,
            "cpu_time_seconds": 30,
            "address_space_bytes": 2 * 1024**3,
            "output_file_size_bytes": 256 * 1024**2,
            "open_files": 64,
            "process_count": 4096,
            "core_dump_bytes": 0,
            "capture_bytes": 8 * 1024**2,
            "cleanup_timeout_seconds": 1,
        },
        "policy_hash": "5" * 64,
    }


def _unavailable_bubblewrap() -> dict[str, Any]:
    return {
        "state": "unavailable",
        "profile_sha256": "0" * 64,
        "executable": {
            "basename": "bwrap",
            "path_class": "unavailable",
            "sha256": None,
            "size_bytes": None,
        },
        "version": None,
    }


def test_policy_creation_fails_closed_when_bubblewrap_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "inspect_bubblewrap", lambda **_: _unavailable_bubblewrap())
    monkeypatch.setattr(cli, "preflight_pilot_security_root", lambda *_: {})

    def reject(**kwargs: object) -> dict[str, Any]:
        inventory = kwargs["bubblewrap_inventory"]
        assert isinstance(inventory, dict)
        assert inventory["state"] == "unavailable"
        raise AtlasError("Bubblewrap is unavailable; pilot policy creation fails closed")

    monkeypatch.setattr(cli, "create_pilot_security_policy", reject)
    result = cli.main(
        [
            "pilot-security-create",
            "--root",
            str(tmp_path / "root"),
            "--pilot-id",
            "PILOT_SYNTHETIC",
            "--pilot-spec",
            str(tmp_path / "spec.json"),
            "--output",
            str(tmp_path / "pilot-security-policy.local.json"),
            "--expires-at",
            "2030-01-01T00:00:00Z",
            "--storage-decision",
            "verified-tmpfs",
        ]
    )
    assert result == 2
    assert "fails closed" in capsys.readouterr().err


def test_policy_inspection_never_prints_private_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_root = "/home/operator/secret pilot root"
    monkeypatch.setattr(cli, "load_pilot_security_policy", lambda *_, **__: _policy(private_root))
    assert cli.main(["pilot-security-inspect", str(tmp_path / "policy.json")]) == 0
    output = capsys.readouterr().out
    assert private_root not in output
    assert "/home/operator" not in output
    value = json.loads(output)
    assert value["contains_private_paths"] is False
    assert value["private_root"] == {
        "expected_mode": "0700",
        "identity_bound": True,
        "path_redacted": True,
        "root_validation": "not-requested",
    }


def test_policy_validation_rechecks_current_sandbox_after_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    monkeypatch.setattr(cli, "load_pilot_security_policy", lambda *_, **__: _policy())
    monkeypatch.setattr(
        cli,
        "open_verified_pilot_root",
        lambda _policy: nullcontext(events.append("root") or object()),
    )
    monkeypatch.setattr(
        cli,
        "validate_current_pilot_sandbox",
        lambda _policy: events.append("sandbox") or {},
    )
    assert cli.main(["pilot-security-validate", str(tmp_path / "policy")]) == 0
    assert events == ["root", "sandbox"]
    value = json.loads(capsys.readouterr().out)
    assert value["private_root"]["root_validation"] == "passed-with-current-sandbox"


def test_policy_create_forwards_capacity_review_and_resource_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(cli, "inspect_bubblewrap", lambda **_: {"state": "available"})
    monkeypatch.setattr(cli, "preflight_pilot_security_root", lambda *_: {})

    def create(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return _policy(str(kwargs["root"]))

    monkeypatch.setattr(cli, "create_pilot_security_policy", create)
    assert (
        cli.main(
            [
                "pilot-security-create",
                "--root",
                str(tmp_path / "root"),
                "--pilot-id",
                "PILOT_SYNTHETIC",
                "--pilot-spec",
                str(tmp_path / "spec.json"),
                "--output",
                str(tmp_path / "test.pilot-security-policy.local.json"),
                "--expires-at",
                "2030-01-01T00:00:00Z",
                "--storage-decision",
                "reviewed-remanence-acceptance",
                "--source-byte-ceiling",
                "1000",
                "--temporary-byte-ceiling",
                "2000",
                "--reserve-bytes",
                "3000",
                "--reviewer-pseudonym",
                "reviewer-A",
                "--review-record",
                "local-review-1",
                "--review-expires-at",
                "2030-01-02T00:00:00Z",
                "--compensating-control",
                "encrypted host",
                "--deletion-plan",
                "operator verifies cleanup",
                "--wall-timeout-seconds",
                "12",
                "--cpu-time-seconds",
                "11",
                "--address-space-bytes",
                str(1024**3),
                "--output-file-size-bytes",
                str(1024**2),
                "--open-files",
                "32",
                "--process-count",
                "128",
                "--capture-bytes",
                str(512 * 1024),
                "--cleanup-timeout-seconds",
                "2",
            ]
        )
        == 0
    )
    assert captured["max_source_bytes"] == 1000
    assert captured["max_temporary_bytes"] == 2000
    assert captured["reserve_bytes"] == 3000
    assert captured["reviewer_pseudonym"] == "reviewer-A"
    assert captured["compensating_controls"] == ("encrypted host",)
    assert captured["resource_limits"] == {
        "wall_timeout_seconds": 12,
        "cpu_time_seconds": 11,
        "address_space_bytes": 1024**3,
        "output_file_size_bytes": 1024**2,
        "open_files": 32,
        "process_count": 128,
        "core_dump_bytes": 0,
        "capture_bytes": 512 * 1024,
        "cleanup_timeout_seconds": 2,
    }


def test_policy_create_rejects_private_root_before_bubblewrap_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inspections = 0

    def inspect(**_kwargs: object) -> dict[str, Any]:
        nonlocal inspections
        inspections += 1
        raise AssertionError("invalid root must stop before Bubblewrap inventory")

    monkeypatch.setattr(cli, "inspect_bubblewrap", inspect)
    monkeypatch.setattr(
        cli,
        "preflight_pilot_security_root",
        lambda *_: (_ for _ in ()).throw(AtlasError("synthetic unsafe root")),
    )
    result = cli.main(
        [
            "pilot-security-create",
            "--root",
            str(tmp_path / "unsafe"),
            "--pilot-id",
            "PILOT_SYNTHETIC",
            "--pilot-spec",
            str(tmp_path / "spec.json"),
            "--output",
            str(tmp_path / "test.pilot-security-policy.local.json"),
            "--expires-at",
            "2099-01-01T00:00:00Z",
            "--storage-decision",
            "verified-tmpfs",
        ]
    )
    assert result == 2
    assert inspections == 0
    assert "synthetic unsafe root" in capsys.readouterr().err


def test_synthetic_check_and_pilot_commands_forward_security_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        cli,
        "run_synthetic_pilot_security_check",
        lambda *args: calls.append(args) or {"state": "passed"},
    )
    monkeypatch.setattr(
        cli,
        "prepare_pilot",
        lambda *args: calls.append(args) or {"state": "prepared"},
    )
    monkeypatch.setattr(
        cli,
        "run_pilot_ocr",
        lambda *args: calls.append(args) or {"state": "succeeded"},
    )
    media = tmp_path / "fixture.mkv"
    rights = tmp_path / "fixture.rights.json"
    spec = tmp_path / "pilot-spec.json"
    policy = tmp_path / "pilot-policy.json"
    output = tmp_path / "output"
    assert (
        cli.main(
            [
                "pilot-security-synthetic-check",
                str(media),
                str(rights),
                str(spec),
                str(policy),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert (
        cli.main(
            [
                "pilot-prepare",
                str(spec),
                "--output",
                str(output),
                "--security-policy",
                str(policy),
            ]
        )
        == 0
    )
    frozen = tmp_path / "frozen.json"
    assert (
        cli.main(
            [
                "pilot-run-ocr",
                str(tmp_path / "pilot"),
                str(frozen),
                "--output",
                str(output),
                "--security-policy",
                str(policy),
            ]
        )
        == 0
    )
    assert calls == [
        (media, rights, spec, policy, output),
        (spec, output, policy),
        (tmp_path / "pilot", frozen, output, policy),
    ]


@pytest.mark.parametrize(
    ("arguments", "forbidden_name"),
    [
        (["pilot-prepare", "spec.json", "--output", "out"], "prepare_pilot"),
        (
            ["pilot-run-ocr", "pilot", "frozen.json", "--output", "out"],
            "run_pilot_ocr",
        ),
    ],
)
def test_pilot_execution_commands_require_security_policy_during_parsing(
    arguments: list[str],
    forbidden_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        forbidden_name,
        lambda *_, **__: pytest.fail("pilot execution started without a security policy"),
    )
    with pytest.raises(SystemExit) as exc:
        cli.main(arguments)
    assert exc.value.code == 2


def test_doctor_reports_missing_optional_bubblewrap_without_private_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "inspect_bubblewrap", lambda **_: _unavailable_bubblewrap())
    monkeypatch.setattr(cli, "inspect_ocr", lambda: {"state": "available"})
    monkeypatch.setattr(cli, "tool_version", lambda _: "test-version")
    assert cli.main(["doctor"]) == 0
    captured = capsys.readouterr()
    assert BUBBLEWRAP_INSTALL_COMMAND in captured.err
    assert "/home/" not in captured.out + captured.err
