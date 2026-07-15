from av_atlas.contracts import Observation
from av_atlas.pipeline import _records
from av_atlas.timeline import chunks


def _chunk_values(duration: int, size: int, overlap: int) -> list[dict[str, int]]:
    return [item.__dict__ for item in chunks(duration, size, overlap)]


def _chunk_ids(start: int, end: int, values: list[dict[str, int]]) -> list[str]:
    observation = Observation("OBS", "visual", start, end, "visible", "data", 1.0, "VID")
    records, _ = _records([observation], "SRC_000000000000", 10000, "final", "run", values)
    return records[0]["provenance"]["chunk_ids"]


def test_provenance_uses_actual_2000_and_3000_ms_chunks() -> None:
    assert _chunk_ids(2200, 2300, _chunk_values(6001, 2000, 0)) == ["CHK_0002"]
    assert _chunk_ids(2200, 2300, _chunk_values(6001, 3000, 0)) == ["CHK_0001"]


def test_non_round_duration_overlap_boundary_and_spanning_event() -> None:
    values = _chunk_values(6501, 3000, 500)
    assert values[-1]["end_ms"] == 6501
    assert _chunk_ids(2500, 2501, values) == ["CHK_0001", "CHK_0002"]
    assert _chunk_ids(3000, 3001, values) == ["CHK_0002"]
    assert _chunk_ids(2400, 5600, values) == ["CHK_0001", "CHK_0002", "CHK_0003"]
