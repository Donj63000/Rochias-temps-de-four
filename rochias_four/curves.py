"""Helpers to generate piecewise curves for the UI overlays."""

from __future__ import annotations

from typing import List, Sequence, Tuple


def piecewise_curve_normalized(
    h_in: float,
    h_out: float,
    n_cells: int,
    profile: Sequence[float] | None = None,
) -> List[Tuple[float, float]]:
    """Return (x, y_cm) points distributed over *n_cells*.

    The x coordinates span 0..1 inclusively. Y values remain in centimetres.
    The optional *profile* scales the interpolation weight of each cell.
    """

    n = max(1, int(n_cells))
    if not profile or len(profile) != n:
        profile = [1.0] * n
    weights = [float(val) for val in profile]
    total = sum(weights) or 1.0
    norm = [w / total for w in weights]

    xs = [i / n for i in range(0, n + 1)]
    ys = [float(h_in)]
    acc = 0.0
    for idx in range(n):
        acc += norm[idx]
        ys.append(float(h_in) + (float(h_out) - float(h_in)) * acc)
    # Align sizes (n+1 points)
    if len(ys) < len(xs):
        ys.append(float(h_out))
    elif len(ys) > len(xs):
        ys = ys[: len(xs)]
    return list(zip(xs, ys))

__all__ = ["piecewise_curve_normalized"]

