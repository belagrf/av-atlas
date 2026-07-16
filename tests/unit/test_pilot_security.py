from __future__ import annotations

import json
import os
import stat
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from av_atlas.errors import AtlasError, ResourceLimitError
from av_atlas.pilot_security import (
    create_pilot_security_policy,
    load_pilot_security_policy,
    make_security_receipt,
    open_retained_output_directory,
    open_verified_pilot_root,
    open_verified_retained_root,
    private_pilot_workspace,
    recover_stale_pilot_workspaces,
    retained_output_directory,
    validate_private_policy_output_path,
    validate_security_receipt,
    verify_sandbox_policy,
)


def _limits() -> dict[str, int]:
    return {
        "wall_timeout_seconds": 30,
        "cpu_time_seconds": 20,
        "address_space_bytes": 1_073_741_824,
        "output_file_size_bytes": 16_777_216,
        "open_files": 64,
        "process_count": 512,
        "core_dump_bytes": 0,
        "capture_bytes": 1_048_576,
        "cleanup_timeout_seconds": 5,
    }


def _inventory() -> dict[str, Any]:
    return {
        "state": "available",
        "profile_version": "av-atlas-bubblewrap-pilot/1.1.0",
        "profile_sha256": "1" * 64,
        "capability_smoke": {"passed": True},
        "executable": {
            "basename": "bwrap",
            "path_class": "system",
            "sha256": "2" * 64,
            "size_bytes": 72_160,
        },
        "version": "bubblewrap 0.9.0",
        "package": {
            "package": "bubblewrap",
            "version": "0.9.0-1ubuntu0.1",
            "architecture": "amd64",
            "source_package": "bubblewrap",
            "source_version": "0.9.0-1ubuntu0.1",
            "license_id": "LGPL-2.0-or-later",
            "license_verification": "read installed package copyright metadata",
        },
        "dependency_identity_sha256": "3" * 64,
        "exposed_host_subtrees": [
            "/usr/bin",
            "/usr/lib",
            "/usr/lib64",
            "/usr/share/tesseract-ocr",
            "/etc/alternatives",
        ],
        "masked_host_subtrees": [
            "/usr/local",
            "/usr/src",
            "/usr/include",
            "/usr/share/doc",
            "/usr/share/man",
        ],
    }


def _create(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "pilot-private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    retained_root = tmp_path / "pilot-retained"
    retained_root.mkdir(mode=0o700)
    retained_root.chmod(0o700)
    spec = tmp_path / "pilot-spec.json"
    spec.write_text('{"pilot_id":"PILOT_SECURITY_TEST"}\n', encoding="utf-8")
    output = tmp_path / "test.pilot-security-policy.local.json"
    value = create_pilot_security_policy(
        root=root,
        retained_root=retained_root,
        pilot_id="PILOT_SECURITY_TEST",
        pilot_spec=spec,
        output=output,
        expires_at="2099-01-01T00:00:00+00:00",
        storage_decision="reviewed-remanence-acceptance",
        retained_storage_decision="reviewed-remanence-acceptance",
        bubblewrap_inventory=_inventory(),
        resource_limits=_limits(),
        reviewer_pseudonym="REVIEWER_SECURITY",
        review_record="local private root reviewed for the synthetic pilot",
        review_expires_at="2099-01-01T00:00:00+00:00",
        compensating_controls=("local synthetic-only execution",),
        deletion_plan="logical unlink, fsync, and marker-aware recovery",
        max_source_bytes=1_000_000,
        max_temporary_bytes=2_000_000,
        max_retained_bytes=2_000_000,
        reserve_bytes=1_000_000,
        retained_reserve_bytes=1_000_000,
    )
    return root, spec, value


def _capability() -> dict[str, bool]:
    return {
        "namespace_smoke_test_passed": True,
        "network_denied": True,
        "external_sentinel_denied": True,
        "outside_write_denied": True,
        "mutable_runtime_subtree_denied": True,
    }


def test_private_policy_binds_spec_root_and_sanitized_receipt(tmp_path: Path) -> None:
    root, spec, created = _create(tmp_path)
    policy_path = tmp_path / "test.pilot-security-policy.local.json"
    assert oct(policy_path.stat().st_mode & 0o777) == "0o600"
    policy = load_pilot_security_policy(
        policy_path,
        pilot_id="PILOT_SECURITY_TEST",
        pilot_spec=spec,
    )
    assert policy == created
    with (
        open_verified_pilot_root(policy) as verified,
        open_verified_retained_root(policy) as retained,
    ):
        receipt = make_security_receipt(
            policy=policy,
            root=verified,
            retained_root=retained,
            stage="policy-validated",
            source_rights_aggregate_sha256="4" * 64,
            sandbox_inventory=_inventory(),
            capability=_capability(),
            cleanup_succeeded=True,
        )
    validate_security_receipt(
        receipt,
        policy_hash=policy["policy_hash"],
        pilot_spec_sha256=policy["pilot_spec_sha256"],
    )
    tampered = deepcopy(receipt)
    tampered["storage"]["available_bytes"] += 1
    with pytest.raises(AtlasError, match="checksum"):
        validate_security_receipt(tampered)
    relinked = deepcopy(receipt)
    relinked["policy_sha256"] = "f" * 64
    from av_atlas import pilot_security

    relinked["receipt_hash"] = pilot_security._digest(relinked, "receipt_hash")
    with pytest.raises(AtlasError, match="another policy"):
        validate_security_receipt(relinked, policy_hash=policy["policy_hash"])
    exported = json.dumps(receipt, sort_keys=True)
    assert receipt["retained_storage"]["private_path_exported"] is False
    assert receipt["output_binding_sha256"] is None
    assert "reviewer_pseudonym" not in exported
    assert str(root) not in exported
    assert str(Path.home()) not in exported
    if user := os.environ.get("USER"):
        assert user not in exported


def test_ocr_completion_receipt_requires_exact_output_binding(tmp_path: Path) -> None:
    _, _, policy = _create(tmp_path)
    with (
        open_verified_pilot_root(policy) as root,
        open_verified_retained_root(policy) as retained,
    ):
        with pytest.raises(AtlasError, match="requires its exact output binding"):
            make_security_receipt(
                policy=policy,
                root=root,
                retained_root=retained,
                stage="ocr-complete",
                source_rights_aggregate_sha256="4" * 64,
                sandbox_inventory=_inventory(),
                capability=_capability(),
                cleanup_succeeded=True,
            )
        receipt = make_security_receipt(
            policy=policy,
            root=root,
            retained_root=retained,
            stage="ocr-complete",
            source_rights_aggregate_sha256="4" * 64,
            sandbox_inventory=_inventory(),
            capability=_capability(),
            cleanup_succeeded=True,
            output_binding_sha256="5" * 64,
        )
    validate_security_receipt(receipt)
    assert receipt["output_binding_sha256"] == "5" * 64


def test_reviewer_pseudonym_is_private_required_and_checksum_bound(tmp_path: Path) -> None:
    from av_atlas import pilot_security

    _, _, policy = _create(tmp_path)
    policy_path = tmp_path / "test.pilot-security-policy.local.json"
    assert policy["storage"]["reviewer_pseudonym"] == "REVIEWER_SECURITY"
    assert policy["retained_storage"]["reviewer_pseudonym"] == "REVIEWER_SECURITY"

    tampered = json.loads(policy_path.read_text(encoding="utf-8"))
    tampered["retained_storage"]["reviewer_pseudonym"] = "REVIEWER_CHANGED"
    policy_path.write_text(json.dumps(tampered), encoding="utf-8")
    policy_path.chmod(0o600)
    with pytest.raises(AtlasError, match="checksum mismatch"):
        load_pilot_security_policy(policy_path)

    tampered["retained_storage"].pop("reviewer_pseudonym")
    tampered["policy_hash"] = pilot_security._digest(tampered, "policy_hash")
    policy_path.write_text(json.dumps(tampered), encoding="utf-8")
    policy_path.chmod(0o600)
    with pytest.raises(AtlasError, match="reviewer_pseudonym"):
        load_pilot_security_policy(policy_path)


def test_retained_output_is_descriptor_created_private_bounded_and_persistent(
    tmp_path: Path,
) -> None:
    _, _, policy = _create(tmp_path)
    retained_path = Path(policy["retained_root"]["path"])
    output = retained_path / "pilot-package"
    with open_verified_retained_root(policy) as root:
        with retained_output_directory(policy, root, output) as lease:
            descriptor = os.open(
                "artifact.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=lease.descriptor,
            )
            try:
                os.write(descriptor, b"{}\n")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            assert lease.descriptor_path.is_dir()
        assert root.measure_aggregate_bytes() == 3
    assert output.is_dir()
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "artifact.json").stat().st_mode) == 0o600
    with (
        open_verified_retained_root(policy) as root,
        open_retained_output_directory(policy, root, output) as reopened,
    ):
        assert (reopened.descriptor_path / "artifact.json").read_bytes() == b"{}\n"


@pytest.mark.parametrize("failure", [AtlasError("synthetic failure"), KeyboardInterrupt()])
def test_retained_output_cleans_after_failure_and_interruption(
    tmp_path: Path, failure: BaseException
) -> None:
    _, _, policy = _create(tmp_path)
    output = Path(policy["retained_root"]["path"]) / "incomplete-package"
    with (
        open_verified_retained_root(policy) as root,
        pytest.raises(type(failure)),
        retained_output_directory(policy, root, output) as lease,
    ):
        descriptor = os.open(
            "private.bin",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=lease.descriptor,
        )
        os.close(descriptor)
        raise failure
    assert not output.exists()


def test_retained_output_replacement_is_rejected_without_deleting_replacement(
    tmp_path: Path,
) -> None:
    _, _, policy = _create(tmp_path)
    retained_path = Path(policy["retained_root"]["path"])
    output = retained_path / "replace-me"
    moved = retained_path / "moved-original"
    with (
        open_verified_retained_root(policy) as root,
        pytest.raises(AtlasError, match="identity"),
        retained_output_directory(policy, root, output),
    ):
        output.rename(moved)
        output.mkdir(mode=0o700)
        sentinel = output / "operator-sentinel"
        sentinel.write_bytes(b"do not remove")
        sentinel.chmod(0o600)
    assert not moved.exists()
    assert (output / "operator-sentinel").read_bytes() == b"do not remove"


def test_retained_output_parent_replacement_is_rejected_and_incomplete_data_removed(
    tmp_path: Path,
) -> None:
    _, _, policy = _create(tmp_path)
    retained_path = Path(policy["retained_root"]["path"])
    displaced = retained_path.with_name("displaced-retained-root")
    output = retained_path / "parent-replacement"
    with (
        pytest.raises(AtlasError, match="retained root"),
        open_verified_retained_root(policy) as root,
        retained_output_directory(policy, root, output),
    ):
        retained_path.rename(displaced)
        retained_path.mkdir(mode=0o700)
    assert retained_path.is_dir()
    assert displaced.is_dir()
    assert list(displaced.iterdir()) == []


def test_retained_output_mode_and_aggregate_capacity_drift_fail_closed(
    tmp_path: Path,
) -> None:
    _, _, policy = _create(tmp_path)
    retained_path = Path(policy["retained_root"]["path"])
    with open_verified_retained_root(policy) as root:
        mode_output = retained_path / "mode-drift"
        with (
            pytest.raises(AtlasError, match="mode 0700|permissions changed"),
            retained_output_directory(policy, root, mode_output),
        ):
            mode_output.chmod(0o755)
        assert not mode_output.exists()

        capacity_output = retained_path / "capacity-drift"
        with (
            pytest.raises(ResourceLimitError, match="aggregate byte ceiling"),
            retained_output_directory(policy, root, capacity_output) as lease,
        ):
            root.byte_ceiling = 1
            descriptor = os.open(
                "too-large.bin",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=lease.descriptor,
            )
            try:
                os.write(descriptor, b"xx")
            finally:
                os.close(descriptor)
        assert not capacity_output.exists()


def test_retained_bounded_write_rejects_before_creating_over_limit_payload(
    tmp_path: Path,
) -> None:
    _, _, policy = _create(tmp_path)
    retained_path = Path(policy["retained_root"]["path"])
    output = retained_path / "bounded-write"
    with (
        open_verified_retained_root(policy) as root,
        retained_output_directory(policy, root, output) as lease,
    ):
        root.byte_ceiling = 1
        with pytest.raises(ResourceLimitError, match="would exceed"):
            lease.write_bounded_bytes("too-large.bin", b"xx")
        assert list(output.iterdir()) == []
        lease.write_bounded_bytes("within-limit.bin", b"x")
        assert (output / "within-limit.bin").read_bytes() == b"x"


def test_retained_root_and_output_must_remain_outside_repository_and_policy_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import pilot_security

    checkout = tmp_path / "checkout"
    module_path = checkout / "src/av_atlas/pilot_security.py"
    module_path.parent.mkdir(parents=True)
    repository_local = checkout / "private-retained"
    repository_local.mkdir(mode=0o700)
    monkeypatch.setattr(pilot_security, "__file__", str(module_path))
    with pytest.raises(AtlasError, match="outside the tracked repository"):
        pilot_security._root_measurement(repository_local, label="pilot retained root")

    _, _, policy = _create(tmp_path / "policy")
    retained_path = Path(policy["retained_root"]["path"])
    outside = retained_path.parent / "unbound-output"
    with (
        open_verified_retained_root(policy) as root,
        pytest.raises(AtlasError, match="direct child"),
        retained_output_directory(policy, root, outside),
    ):
        pytest.fail("an output outside the policy-bound retained root must not be yielded")
    assert not outside.exists()


def test_success_receipt_rechecks_policy_review_and_root_identity(tmp_path: Path) -> None:
    root_path, _, policy = _create(tmp_path)
    with (
        open_verified_pilot_root(policy) as root,
        open_verified_retained_root(policy) as retained,
    ):
        expired_policy = deepcopy(policy)
        expired_policy["expires_at"] = "2000-01-01T00:00:00+00:00"
        with pytest.raises(AtlasError, match="policy has expired"):
            make_security_receipt(
                policy=expired_policy,
                root=root,
                retained_root=retained,
                stage="synthetic-smoke-complete",
                source_rights_aggregate_sha256="4" * 64,
                sandbox_inventory=_inventory(),
                capability=_capability(),
                cleanup_succeeded=True,
            )

        expired_review = deepcopy(policy)
        expired_review["storage"]["review_expires_at"] = "2000-01-01T00:00:00+00:00"
        with pytest.raises(AtlasError, match="storage review has expired"):
            make_security_receipt(
                policy=expired_review,
                root=root,
                retained_root=retained,
                stage="synthetic-smoke-complete",
                source_rights_aggregate_sha256="4" * 64,
                sandbox_inventory=_inventory(),
                capability=_capability(),
                cleanup_succeeded=True,
            )

        root_path.chmod(0o755)
        try:
            with pytest.raises(AtlasError, match="identity, owner, or permissions"):
                make_security_receipt(
                    policy=policy,
                    root=root,
                    retained_root=retained,
                    stage="synthetic-smoke-complete",
                    source_rights_aggregate_sha256="4" * 64,
                    sandbox_inventory=_inventory(),
                    capability=_capability(),
                    cleanup_succeeded=True,
                )
        finally:
            root_path.chmod(0o700)


def test_policy_checksum_spec_expiry_and_private_mode_fail_closed(tmp_path: Path) -> None:
    _, spec, _ = _create(tmp_path)
    policy_path = tmp_path / "test.pilot-security-policy.local.json"
    value = json.loads(policy_path.read_text())

    value["capacity"]["reserve_bytes"] += 1
    policy_path.write_text(json.dumps(value), encoding="utf-8")
    policy_path.chmod(0o600)
    with pytest.raises(AtlasError, match="checksum"):
        load_pilot_security_policy(policy_path)

    _, spec, _ = _create(tmp_path / "second")
    policy_path = tmp_path / "second/test.pilot-security-policy.local.json"
    spec.write_text("changed", encoding="utf-8")
    with pytest.raises(AtlasError, match="pilot specification"):
        load_pilot_security_policy(policy_path, pilot_spec=spec)

    policy_path.chmod(0o644)
    with pytest.raises(AtlasError, match="mode 0600"):
        load_pilot_security_policy(policy_path)

    with pytest.raises(AtlasError, match="ignored.*suffix"):
        validate_private_policy_output_path(tmp_path / "trackable-policy.json")


def test_review_scope_must_match_policy_pilot(tmp_path: Path) -> None:
    from av_atlas import pilot_security

    _create(tmp_path)
    policy_path = tmp_path / "test.pilot-security-policy.local.json"
    value = json.loads(policy_path.read_text(encoding="utf-8"))
    value["storage"]["review_scope"] = "PILOT_ANOTHER_SCOPE"
    value["policy_hash"] = pilot_security._digest(value, "policy_hash")
    policy_path.write_text(json.dumps(value), encoding="utf-8")
    policy_path.chmod(0o600)
    with pytest.raises(AtlasError, match="review scope"):
        load_pilot_security_policy(policy_path)

    _, _, _ = _create(tmp_path / "expired-review")
    expired_path = tmp_path / "expired-review/test.pilot-security-policy.local.json"
    expired = json.loads(expired_path.read_text(encoding="utf-8"))
    expired["storage"]["review_expires_at"] = "2000-01-01T00:00:00+00:00"
    expired["policy_hash"] = pilot_security._digest(expired, "policy_hash")
    expired_path.write_text(json.dumps(expired), encoding="utf-8")
    expired_path.chmod(0o600)
    with pytest.raises(AtlasError, match="storage review has expired"):
        load_pilot_security_policy(expired_path)

    _create(tmp_path / "expired-retained-review")
    retained_expired_path = (
        tmp_path / "expired-retained-review/test.pilot-security-policy.local.json"
    )
    retained_expired = json.loads(retained_expired_path.read_text(encoding="utf-8"))
    retained_expired["retained_storage"]["review_expires_at"] = "2000-01-01T00:00:00+00:00"
    retained_expired["policy_hash"] = pilot_security._digest(retained_expired, "policy_hash")
    retained_expired_path.write_text(json.dumps(retained_expired), encoding="utf-8")
    retained_expired_path.chmod(0o600)
    with pytest.raises(AtlasError, match="retained storage review has expired"):
        load_pilot_security_policy(retained_expired_path)


def test_private_root_replacement_permission_and_capacity_drift_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import pilot_security

    root, _, policy = _create(tmp_path)
    root.chmod(0o755)
    with (
        pytest.raises(AtlasError, match="mode 0700"),
        open_verified_pilot_root(policy),
    ):
        pytest.fail("unsafe root must not be yielded")
    root.chmod(0o700)

    wrong_device = deepcopy(policy)
    wrong_device["private_root"]["expected_device"] += 1
    with (
        pytest.raises(AtlasError, match="identity"),
        open_verified_pilot_root(wrong_device),
    ):
        pytest.fail("unexpected root device must not be accepted")

    moved = tmp_path / "moved"
    root.rename(moved)
    root.mkdir(mode=0o700)
    with (
        pytest.raises(AtlasError, match="identity"),
        open_verified_pilot_root(policy),
    ):
        pytest.fail("replacement root must not be yielded")
    root.rmdir()
    moved.rename(root)

    original = pilot_security._root_measurement

    def insufficient(path: Path) -> dict[str, Any]:
        measured = deepcopy(original(path))
        measured["available_bytes"] = 1
        return measured

    monkeypatch.setattr(pilot_security, "_root_measurement", insufficient)
    with (
        pytest.raises(ResourceLimitError, match="free capacity"),
        open_verified_pilot_root(policy),
    ):
        pytest.fail("capacity-deficient root must not be yielded")


def test_private_root_owner_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import pilot_security

    _, _, policy = _create(tmp_path)
    current_uid = os.geteuid()
    monkeypatch.setattr(pilot_security.os, "geteuid", lambda: current_uid + 1)
    with (
        pytest.raises(AtlasError, match="owned by the current"),
        open_verified_pilot_root(policy),
    ):
        pytest.fail("owner drift must not yield the private root")


def test_changed_sandbox_identity_profile_and_capability_fail_closed(tmp_path: Path) -> None:
    _, _, policy = _create(tmp_path)
    inventory = _inventory()
    inventory["capability_smoke"] = {"passed": True}
    inventory["profile_version"] = "av-atlas-bubblewrap-pilot/1.1.0"
    verify_sandbox_policy(policy, inventory)

    for field, value in (
        ("profile_sha256", "9" * 64),
        ("dependency_identity_sha256", "8" * 64),
    ):
        changed = deepcopy(inventory)
        changed[field] = value
        with pytest.raises(AtlasError, match="identity or capability"):
            verify_sandbox_policy(policy, changed)
    failed_smoke = deepcopy(inventory)
    failed_smoke["capability_smoke"] = {"passed": False}
    with pytest.raises(AtlasError, match="identity or capability"):
        verify_sandbox_policy(policy, failed_smoke)


def test_symlink_and_remote_filesystem_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import pilot_security

    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    retained = tmp_path / "retained"
    retained.mkdir(mode=0o700)
    spec = tmp_path / "spec.json"
    spec.write_text("{}", encoding="utf-8")
    with pytest.raises(AtlasError, match="non-symlink"):
        create_pilot_security_policy(
            root=linked,
            retained_root=retained,
            pilot_id="PILOT_SECURITY_TEST",
            pilot_spec=spec,
            output=tmp_path / "test.pilot-security-policy.local.json",
            expires_at="2099-01-01T00:00:00+00:00",
            storage_decision="reviewed-encrypted-volume",
            retained_storage_decision="reviewed-encrypted-volume",
            bubblewrap_inventory=_inventory(),
            resource_limits=_limits(),
            reviewer_pseudonym="REVIEWER",
            review_record="review",
            review_expires_at="2099-01-01T00:00:00+00:00",
            deletion_plan="logical deletion",
            max_source_bytes=1,
            max_temporary_bytes=1,
            max_retained_bytes=1,
            reserve_bytes=0,
            retained_reserve_bytes=0,
        )

    monkeypatch.setattr(
        pilot_security,
        "_filesystem_record",
        lambda _path, _device, **_kwargs: (_ for _ in ()).throw(
            AtlasError("pilot private root must not use a network or remote filesystem")
        ),
    )
    with pytest.raises(AtlasError, match="network or remote"):
        pilot_security._root_measurement(real)


def test_private_workspace_cleans_success_failure_and_interruption(tmp_path: Path) -> None:
    _, _, policy = _create(tmp_path)
    paths: list[Path] = []
    with open_verified_pilot_root(policy) as root:
        with private_pilot_workspace(policy, root) as work:
            paths.append(work.path)
            (work.path / "nested").mkdir()
            (work.path / "nested/data.bin").write_bytes(b"private synthetic derivative")
        assert not paths[-1].exists()

        with (
            pytest.raises(AtlasError, match="synthetic failure"),
            private_pilot_workspace(policy, root) as work,
        ):
            paths.append(work.path)
            (work.path / "failure.bin").write_bytes(b"private")
            raise AtlasError("synthetic failure")
        assert not paths[-1].exists()

        with (
            pytest.raises(KeyboardInterrupt),
            private_pilot_workspace(policy, root) as work,
        ):
            paths.append(work.path)
            (work.path / "interrupt.bin").write_bytes(b"private")
            raise KeyboardInterrupt
        assert not paths[-1].exists()


def test_low_space_does_not_block_private_workspace_cleanup(tmp_path: Path) -> None:
    _, _, policy = _create(tmp_path)
    with open_verified_pilot_root(policy) as root:
        original_required = root.required_free_bytes
        with private_pilot_workspace(policy, root) as work:
            private_path = work.path
            (private_path / "reclaim-me.bin").write_bytes(b"synthetic private bytes")
            root.required_free_bytes = root.available_bytes + 1
        assert not private_path.exists()
        root.required_free_bytes = original_required


def test_private_workspace_stale_recovery_is_marker_bound_and_does_not_follow_symlink(
    tmp_path: Path,
) -> None:
    from av_atlas import pilot_security

    _, _, policy = _create(tmp_path)
    outside = tmp_path / "outside-sentinel"
    outside.write_text("do not delete", encoding="utf-8")
    with open_verified_pilot_root(policy) as root:
        name = "pilot-work-" + "a" * 32
        directory = root.path / name
        directory.mkdir(mode=0o700)
        marker = directory / pilot_security.WORK_MARKER_NAME
        marker.write_text(
            json.dumps(pilot_security._work_marker(policy, name, root)) + "\n",
            encoding="utf-8",
        )
        marker.chmod(0o600)
        (directory / "outside-link").symlink_to(outside)
        (directory / "private.bin").write_bytes(b"stale synthetic bytes")
        assert recover_stale_pilot_workspaces(policy, root) == 1
        assert not directory.exists()
        assert outside.read_text(encoding="utf-8") == "do not delete"

        unknown = root.path / ("pilot-work-" + "b" * 32)
        unknown.mkdir(mode=0o700)
        unknown_marker = unknown / pilot_security.WORK_MARKER_NAME
        unknown_marker.write_text("{}\n", encoding="utf-8")
        unknown_marker.chmod(0o600)
        assert recover_stale_pilot_workspaces(policy, root) == 0
        assert unknown.exists()
        unknown_marker.unlink()
        unknown.rmdir()


def test_private_workspace_cleanup_enumeration_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from av_atlas import pilot_security

    directory = tmp_path / "bounded"
    directory.mkdir(mode=0o700)
    for index in range(3):
        (directory / f"entry-{index}").write_bytes(b"x")
    descriptor = os.open(
        directory,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    monkeypatch.setattr(pilot_security, "MAX_WORK_ENTRIES", 2)
    try:
        with pytest.raises(ResourceLimitError, match="entry bound"):
            pilot_security._remove_private_tree(
                descriptor,
                pilot_security._RemovalBudget(0, 0, 1024),
            )
    finally:
        os.close(descriptor)
