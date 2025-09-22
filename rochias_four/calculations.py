"""Core calculation helpers for the oven timelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .calibration import (
    K1_DIST,
    K2_DIST,
    K3_DIST,
    compute_times,
)


@dataclass(frozen=True)
class StagePlan:
    """Computed data for a single conveyor belt."""

    frequency_hz: float
    duration_min: float
    distance_target: float


@dataclass(frozen=True)
class CalculationResult:
    """Complete snapshot for a set of belt frequencies."""

    stages: Tuple[StagePlan, StagePlan, StagePlan]
    total_minutes: float
    ls_durations: Tuple[float, float, float]
    total_model_minutes: float
    model_params: Tuple[float, float, float, float]
    anchor_durations: Tuple[float, float, float]
    alpha_anchor: float
    beta_ls: float


def compute_simulation_plan(f1: float, f2: float, f3: float) -> CalculationResult:
    """Return the time allocation for the three conveyors.

    The plan is entirely based on the ancrage distances so that each belt only
    depends on its own frequency.  The regression model is still computed and
    exposed for diagnostics/analytics.
    """

    t1_ls, t2_ls, t3_ls, total_ls, params = compute_times(f1, f2, f3)
    anchor_durations = (
        K1_DIST / f1,
        K2_DIST / f2,
        K3_DIST / f3,
    )
    total_anchor = sum(anchor_durations)
    alpha = total_ls / total_anchor if total_anchor > 0 else float("nan")
    sum_ls = t1_ls + t2_ls + t3_ls
    beta = total_ls / sum_ls if sum_ls > 0 else float("nan")

    stages = tuple(
        StagePlan(freq, duration, distance)
        for freq, duration, distance in zip(
            (f1, f2, f3),
            anchor_durations,
            (K1_DIST, K2_DIST, K3_DIST),
        )
    )

    return CalculationResult(
        stages=stages,
        total_minutes=total_anchor,
        ls_durations=(t1_ls, t2_ls, t3_ls),
        total_model_minutes=total_ls,
        model_params=params,
        anchor_durations=anchor_durations,
        alpha_anchor=alpha,
        beta_ls=beta,
    )


def thickness_and_accum(f1: float, f2: float, f3: float, h0_cm: float) -> Dict[str, float]:
    """Return thickness variations between conveyors."""

    u1, u2, u3 = (f1 / K1_DIST), (f2 / K2_DIST), (f3 / K3_DIST)

    h1 = h0_cm
    h2 = h0_cm * (u1 / u2) if u2 > 0 else float("inf")
    h3 = h0_cm * (u1 / u3) if u3 > 0 else float("inf")

    A12 = (u1 / u2) - 1.0
    A23 = (u2 / u3) - 1.0

    return {
        "h1_cm": h1,
        "h2_cm": h2,
        "h3_cm": h3,
        "A12_x": A12 + 1.0,
        "A23_x": A23 + 1.0,
        "A12_pct": A12 * 100.0,
        "A23_pct": A23 * 100.0,
    }


__all__ = [
    "CalculationResult",
    "StagePlan",
    "compute_simulation_plan",
    "thickness_and_accum",
]

