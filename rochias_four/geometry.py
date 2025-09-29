"""Utilities to derive belt geometry for the live thickness graphs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple
import bisect
import math


@dataclass
class TapisGeometry:
    samples_x: List[float]
    tau_min: List[float]
    h_target_cm: List[float]
    ticks_x: List[float]


def _normalized_profile(profile: Sequence[float], n_cells: int) -> List[float]:
    if n_cells <= 0:
        return []
    if not profile or len(profile) < n_cells:
        weights = [1.0] * n_cells
    else:
        weights = [float(profile[i]) for i in range(n_cells)]
    total = sum(weights) or 1.0
    return [w / total for w in weights]


def build_tapis_geometry(
    durations_min: Sequence[float],
    h_in_cm: float,
    h_out_cm: float,
    profile: Sequence[float],
    samples: int = 200,
) -> TapisGeometry:
    n_cells = len(durations_min)
    if n_cells == 0 or samples <= 1:
        xs = [0.0, 1.0]
        tau = [0.0, 0.0]
        h_val = float(h_in_cm) if math.isfinite(h_in_cm) else 0.0
        return TapisGeometry(xs, tau, [h_val, h_val], [])
    durations = [max(0.0, float(val)) for val in durations_min]
    total = sum(durations)
    if total <= 0.0:
        xs = [0.0, 1.0]
        tau = [0.0, 0.0]
        h_val = float(h_in_cm) if math.isfinite(h_in_cm) else 0.0
        return TapisGeometry(xs, tau, [h_val, h_val], [])
    cumulative = [0.0]
    acc = 0.0
    for value in durations:
        acc += value
        cumulative.append(acc)
    xs: List[float] = []
    tau: List[float] = []
    tau_local: List[float] = []
    for idx in range(samples):
        frac = idx / (samples - 1)
        local_tau = frac * total
        tau_local.append(local_tau)
        tau.append(local_tau)
        xs.append(local_tau / total if total else 0.0)
    ticks = [val / total for val in cumulative[1:-1]]
    weights = _normalized_profile(profile, n_cells)
    prefix = [0.0]
    acc_weight = 0.0
    for w in weights:
        acc_weight += w
        prefix.append(acc_weight)
    heights: List[float] = []
    delta_h = float(h_out_cm) - float(h_in_cm)
    for local_tau in tau_local:
        cell_idx = max(0, min(n_cells - 1, bisect.bisect_right(cumulative, local_tau) - 1))
        cell_start = cumulative[cell_idx]
        cell_end = cumulative[cell_idx + 1]
        span = cell_end - cell_start
        if span <= 0:
            rel = 0.0
        else:
            rel = (local_tau - cell_start) / span
        ratio_start = prefix[cell_idx]
        ratio_end = prefix[cell_idx + 1]
        interp_ratio = ratio_start + (ratio_end - ratio_start) * rel
        height = float(h_in_cm) + delta_h * interp_ratio
        if not math.isfinite(height):
            height = 0.0
        heights.append(height)
    return TapisGeometry(xs, tau, heights, ticks)


def build_line_geometry(
    seg_times: Dict[str, float],
    h1_cm: float,
    h2_cm: float,
    h3_cm: float,
) -> Dict[str, Tuple[TapisGeometry, float]]:
    seg = {key: float(value) for key, value in (seg_times or {}).items()}
    cells_1 = [seg.get("c1", 0.0), seg.get("c2", 0.0), seg.get("c3", 0.0)]
    cells_2 = [seg.get("c4", 0.0), seg.get("c5", 0.0), seg.get("c6", 0.0)]
    cells_3 = [seg.get("c7", 0.0), seg.get("c8", 0.0)]
    geo1 = build_tapis_geometry(cells_1, h1_cm, h1_cm, [1.0, 0.0, 0.0])
    geo2 = build_tapis_geometry(cells_2, h1_cm, h2_cm, [0.10, 0.35, 0.55])
    geo3 = build_tapis_geometry(cells_3, h2_cm, h3_cm, [0.55, 0.45])
    entry = seg.get("entry1", 0.0)
    offset1 = entry
    offset2 = offset1 + sum(cells_1) + seg.get("transfer1", 0.0)
    offset3 = offset2 + sum(cells_2) + seg.get("transfer2", 0.0)
    return {
        "t1": (geo1, offset1),
        "t2": (geo2, offset2),
        "t3": (geo3, offset3),
    }


__all__ = ["TapisGeometry", "build_tapis_geometry", "build_line_geometry"]
