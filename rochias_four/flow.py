# rochias_four/flow.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GapEvent:
    start_min: float
    end_min: Optional[float] = None


def _normalize(events: List[GapEvent], now_min: float) -> list[tuple[float, float]]:
    norm: list[tuple[float, float]] = []
    for ev in events:
        s = float(ev.start_min)
        e = float(now_min if ev.end_min is None else ev.end_min)
        if e > s:
            norm.append((s, e))
    return norm


def _project_to_belt(
    intervals: list[tuple[float, float]],
    now_min: float,
    offset_min: float,
    belt_len_sec: float,
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for s, e in intervals:
        a = (now_min - (e + offset_min)) * 60.0
        b = (now_min - (s + offset_min)) * 60.0
        lo = max(0.0, min(belt_len_sec, a))
        hi = max(0.0, min(belt_len_sec, b))
        if hi - lo > 1e-6:
            out.append((lo, hi))
    return out


def holes_for_all_belts(
    events: List[GapEvent],
    now_min: float,
    t1_min: float,
    t2_min: float,
    t3_min: float,
) -> list[list[tuple[float, float]]]:
    intervals = _normalize(events, now_min)
    lens = [t1_min * 60.0, t2_min * 60.0, t3_min * 60.0]
    offsets = [0.0, t1_min, t1_min + t2_min]
    return [
        _project_to_belt(intervals, now_min, offsets[i], lens[i])
        for i in (0, 1, 2)
    ]
