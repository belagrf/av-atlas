from __future__ import annotations

import json
from pathlib import Path

import pytest

from av_atlas.fixture import make_m2b_fixture
from av_atlas.io import sha256_file, source_id_from_sha256
from av_atlas.native_process import NativeResourceLimits, inspect_bubblewrap
from av_atlas.ocr import inspect_ocr
from av_atlas.ocr_pilot import run_synthetic_pilot_security_check
from av_atlas.pilot_security import create_pilot_security_policy, policy_resource_limits
from av_atlas.rights import create_rights_manifest
from av_atlas.schemas import validate_instance


@pytest.mark.bubblewrap
@pytest.mark.tesseract
def test_actual_m2b3_synthetic_pilot_runs_all_native_tools_in_sandbox(
    tmp_path: Path,
) -> None:
    bubblewrap = inspect_bubblewrap()
    if bubblewrap["state"] != "available":
        pytest.skip(
            "approved Bubblewrap capability unavailable; operator command: "
            "sudo apt-get install bubblewrap"
        )
    if inspect_ocr()["state"] != "available":
        pytest.skip(
            "approved Tesseract English dependency unavailable; operator command: "
            "sudo apt-get install tesseract-ocr tesseract-ocr-eng"
        )

    media = make_m2b_fixture(tmp_path / "controlled-fixture")
    media_hash = sha256_file(media)
    source_id = source_id_from_sha256(media_hash)
    rights = tmp_path / "synthetic.rights.json"
    create_rights_manifest(
        media,
        rights,
        "m2b3-synthetic-test",
        "synthetic-controlled",
        {"analysis", "evaluation", "derivative_artifact_retention"},
    )
    spec = tmp_path / "synthetic-pilot-spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "pilot_id": "PILOT_M2B3_SYNTHETIC_TEST",
                "source_sha256": media_hash,
                "source_id": source_id,
                "timestamp_ms": 1000,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    private_root = tmp_path / "pilot-private"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)
    policy_path = tmp_path / "pilot-security-policy.local.json"
    create_pilot_security_policy(
        root=private_root.resolve(),
        pilot_id="PILOT_M2B3_SYNTHETIC_TEST",
        pilot_spec=spec,
        output=policy_path,
        expires_at="2099-01-01T00:00:00+00:00",
        storage_decision="reviewed-remanence-acceptance",
        bubblewrap_inventory=bubblewrap,
        resource_limits=policy_resource_limits(NativeResourceLimits()),
        reviewer_pseudonym="SYNTHETIC_TEST_REVIEWER",
        review_record="project-authored synthetic integration test root",
        review_expires_at="2099-01-01T00:00:00+00:00",
        compensating_controls=("project-authored synthetic data only",),
        deletion_plan="logical unlink and bounded marker-aware recovery",
        max_source_bytes=64 * 1024 * 1024,
        max_temporary_bytes=256 * 1024 * 1024,
        reserve_bytes=16 * 1024 * 1024,
    )
    outside = tmp_path / "outside-sentinel"
    outside.write_text("must remain outside the sandbox", encoding="utf-8")
    output = tmp_path / "m2b3-output"
    report = run_synthetic_pilot_security_check(media, rights, spec, policy_path, output)

    validate_instance(
        "pilot_security_synthetic_report",
        report,
        "actual M2B.3 synthetic security report",
    )
    assert report["state"] == "succeeded"
    assert report["tools"] == {
        "ffprobe_sandboxed": True,
        "ffmpeg_sandboxed": True,
        "tesseract_sandboxed": True,
    }
    assert all(report["capability"].values())
    assert report["measurements"]["ocr_frames_processed"] == 1
    assert report["measurements"]["ocr_observation_count"] > 0
    assert outside.read_text(encoding="utf-8") == "must remain outside the sandbox"
    assert not list(private_root.iterdir())
    exported = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(output.iterdir()) if path.is_file()
    )
    assert str(tmp_path) not in exported
    assert str(Path.home()) not in exported
    assert not any(path.suffix in {".mkv", ".png", ".traineddata"} for path in output.iterdir())
