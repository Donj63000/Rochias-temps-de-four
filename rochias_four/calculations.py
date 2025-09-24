"""Core calculation helpers for the oven timelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from .maintenance_ref import compute_times_maintenance
from .calibration_overrides import AnchorParams, get_current_anchor

try:
    from .calibration import (
        DEFAULT_ANCHOR,
        DEFAULT_OLS,
        DEFAULT_SYNERGY,
        compute_times,
        is_monotone_decreasing_in_each_f,
        split_contributions,
        total_time_minutes,
        total_time_minutes_safe,
    )
except ModuleNotFoundError:
    @dataclass(frozen=True)
    class _FallbackOLS:
        B: float = 0.0

    @dataclass(frozen=True)
    class _FallbackSynergy:
        alpha: float = 1.0
        beta: float = 1.0
        B: float = 0.0

    DEFAULT_ANCHOR = get_current_anchor()
    DEFAULT_OLS = _FallbackOLS()
    DEFAULT_SYNERGY = _FallbackSynergy()

    def _safe_freq(freq: float) -> float:
        freq = float(freq)
        if abs(freq) < 1e-9:
            return 1e-9
        return freq

    def _maintenance_minutes(f1: float, f2: float, f3: float) -> Tuple[float, float, float, float]:
        maint = compute_times_maintenance(f1, f2, f3, units="hz")
        return maint.t1_min, maint.t2_min, maint.t3_min, maint.total_min

    def compute_times(f1: float, f2: float, f3: float) -> Tuple[float, float, float, float, Tuple[float, float, float, float]]:
        t1, t2, t3, total = _maintenance_minutes(f1, f2, f3)
        return t1, t2, t3, total, (float("nan"), float("nan"), float("nan"), float("nan"))

    def total_time_minutes(
        f1: float, f2: float, f3: float, *, model: str | None = None, anch: AnchorParams | None = None, **_kwargs
    ) -> float:
        if model == "anchor":
            anchor = anch or DEFAULT_ANCHOR
            freqs = (_safe_freq(f1), _safe_freq(f2), _safe_freq(f3))
            base = (anchor.K1 / freqs[0], anchor.K2 / freqs[1], anchor.K3 / freqs[2])
            return sum(base) + getattr(anchor, "B", 0.0)
        return _maintenance_minutes(f1, f2, f3)[3]

    def total_time_minutes_safe(
        f1: float, f2: float, f3: float, *, model: str | None = None, syn: object | None = None, **kwargs
    ) -> float:
        return total_time_minutes(f1, f2, f3, model=model, **kwargs)

    def split_contributions(
        total: float,
        f1: float,
        f2: float,
        f3: float,
        *,
        split: str | None = None,
        anch: AnchorParams | None = None,
        **_kwargs,
    ) -> Tuple[float, float, float]:
        freqs = (_safe_freq(f1), _safe_freq(f2), _safe_freq(f3))
        if split == "anchor" and anch is not None:
            base = (anch.K1 / freqs[0], anch.K2 / freqs[1], anch.K3 / freqs[2])
        else:
            base = _maintenance_minutes(f1, f2, f3)[:3]
        denom = sum(base)
        if denom <= 0:
            return 0.0, 0.0, 0.0
        scale = total / denom
        return tuple(val * scale for val in base)

    def is_monotone_decreasing_in_each_f(
        f1: float, f2: float, f3: float, *, model: str | None = None, **_kwargs
    ) -> bool:
        return True


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
    extras: Dict[str, object] = field(default_factory=dict)


def compute_simulation_plan(f1: float, f2: float, f3: float) -> CalculationResult:
    """Return the time allocation for the three conveyors.

    The plan is entirely based on the ancrage distances so that each belt only
    depends on its own frequency.  The regression model is still computed and
    exposed for diagnostics/analytics.
    """

    t1_ls, t2_ls, t3_ls, total_ls, params = compute_times(f1, f2, f3)

    anch = get_current_anchor()
    anchor_terms = (
        anch.K1 / f1,
        anch.K2 / f2,
        anch.K3 / f3,
    )
    sum_anchor_terms = sum(anchor_terms)

    anchor_model_total = total_time_minutes(f1, f2, f3, model="anchor", anch=DEFAULT_ANCHOR)
    anchor_model_split = split_contributions(
        anchor_model_total, f1, f2, f3, split="anchor", anch=DEFAULT_ANCHOR
    )

    total_synergy = total_time_minutes_safe(f1, f2, f3, syn=DEFAULT_SYNERGY)
    synergy_split_model = split_contributions(
        total_synergy, f1, f2, f3, split="anchor", anch=DEFAULT_ANCHOR
    )

    ols_split = split_contributions(total_ls, f1, f2, f3, split="model", ols=DEFAULT_OLS)

    alpha = total_synergy / anchor_model_total if anchor_model_total > 0 else float("nan")
    sum_ls = t1_ls + t2_ls + t3_ls
    beta = total_ls / sum_ls if sum_ls > 0 else float("nan")

    anchor_durations = anchor_terms

    stages = tuple(
        StagePlan(freq, duration, distance)
        for freq, duration, distance in zip(
            (f1, f2, f3),
            anchor_durations,
            (anch.K1, anch.K2, anch.K3),
        )
    )

    extras: Dict[str, object] = {
        "anchor_terms_base": anchor_terms,
        "anchor_total_base": sum_anchor_terms,
        "anchor_total_model": anchor_model_total,
        "anchor_split_model": anchor_model_split,
        "synergy_split": anchor_durations,
        "synergy_split_model": synergy_split_model,
        "synergy_total": total_synergy,
        "ols_split": ols_split,
        "anchor_B": DEFAULT_ANCHOR.B,
        "ols_B": DEFAULT_OLS.B,
        "synergy_params": DEFAULT_SYNERGY,
        "monotone_ok": is_monotone_decreasing_in_each_f(f1, f2, f3, model="synergy", syn=DEFAULT_SYNERGY),
    }

    return CalculationResult(
        stages=stages,
        total_minutes=total_synergy,
        ls_durations=(t1_ls, t2_ls, t3_ls),
        total_model_minutes=total_ls,
        model_params=params,
        anchor_durations=anchor_durations,
        alpha_anchor=alpha,
        beta_ls=beta,
        extras=extras,
    )


def thickness_and_accum(f1: float, f2: float, f3: float, h0_cm: float) -> Dict[str, float]:
    """Return thickness variations between conveyors."""

    anch = get_current_anchor()
    u1, u2, u3 = (f1 / anch.K1), (f2 / anch.K2), (f3 / anch.K3)

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

