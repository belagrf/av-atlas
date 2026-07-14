import pytest

from av_atlas.errors import AtlasError
from av_atlas.timeline import Interval, chunks, uniform_samples


def test_chunking_has_deterministic_overlap_and_bounded_end() -> None:
    assert chunks(6000, 2000, 250) == [
        Interval(0, 2000),
        Interval(1750, 3750),
        Interval(3500, 5500),
        Interval(5250, 6000),
    ]


@pytest.mark.parametrize(
    ("duration", "size", "overlap"), [(0, 2, 0), (2, 0, 0), (2, 2, -1), (2, 2, 2)]
)
def test_chunking_rejects_zero_length_and_invalid_overlap(
    duration: int, size: int, overlap: int
) -> None:
    with pytest.raises(AtlasError):
        chunks(duration, size, overlap)


def test_uniform_sampling_excludes_out_of_range_endpoint() -> None:
    assert uniform_samples(6000, 1000) == [0, 1000, 2000, 3000, 4000, 5000]
