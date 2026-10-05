"""Evenly spaced sampling shared by every consumer of video frames."""
from typing import List


def sample_indices(total: int, wanted: int) -> List[int]:
    """Indices of `wanted` evenly spaced items out of `total`; all of them when `total <= wanted`."""
    if total <= wanted:
        return list(range(total))
    step = total / wanted
    return [int(i * step) for i in range(wanted)]
