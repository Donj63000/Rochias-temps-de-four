# rochias_four/flow.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


@dataclass
class GapEvent:
    """Evénement d'arrêt/reprise alimentation, temps en minutes de simulation."""

    start_min: float
    end_min: Optional[float] = None  # None = encore à l'arrêt


def thickness_and_accum(f1: float, f2: float, f3: float, h0_cm: float) -> Dict[str, float]:
    """Épaisseurs absolues (cm) sur chaque tapis et cumulations locales en %."""

    h1 = h0_cm
    h2 = h0_cm * (f1 / f2)
    h3 = h0_cm * (f1 / f3)
    A12 = f1 / f2  # facteur h2/h1
    A23 = f2 / f3  # facteur h3/h2
    return {
        "h1_cm": h1,
        "h2_cm": h2,
        "h3_cm": h3,
        "A12_x": A12,
        "A23_x": A23,
        "A12_pct": (A12 - 1.0) * 100.0,
        "A23_pct": (A23 - 1.0) * 100.0,
    }


def _hole_on_belt(
    ev: GapEvent,
    t_now_min: float,
    belt_idx: int,
    t1_min: float,
    t2_min: float,
    t3_min: float,
    f1: float,
    f2: float,
    f3: float,
    D1: float,
    D2: float,
    D3: float,
) -> Optional[Tuple[float, float]]:
    """Retourne l'intervalle [x0,x1] occupé par le trou sur le tapis demandé."""

    tjs = [t1_min, t2_min, t3_min]  # minutes
    fs = [f1, f2, f3]  # Hz
    Ds = [D1, D2, D3]  # « min·Hz »
    cum_prev = sum(tjs[:belt_idx])  # décalage temporel amont (min)
    tj = tjs[belt_idx]
    fj = fs[belt_idx]
    Dj = Ds[belt_idx]

    s = ev.start_min
    e = ev.end_min if ev.end_min is not None else t_now_min  # encore à l'arrêt → on prend « maintenant »

    t_in_front = s + cum_prev
    t_in_back = e + cum_prev
    t_out_front = t_in_front + tj
    t_out_back = t_in_back + tj

    if t_now_min < t_in_front or t_now_min > t_out_back:
        return None  # pas encore arrivé / déjà reparti

    def _clip(value: float, lo: float = 0.0, hi: float = Dj) -> float:
        return max(lo, min(hi, value))

    x_front = _clip(fj * (t_now_min - t_in_front))
    x_back = _clip(fj * (t_now_min - t_in_back))

    if t_now_min < t_in_back:  # phase de croissance du trou
        x0, x1 = 0.0, x_front
    elif t_now_min <= t_out_front:  # deux bords présents (longueur constante = fj * (e - s))
        x0, x1 = x_back, x_front
    else:  # la tête est sortie, la queue reste
        x0, x1 = x_back, Dj

    if x1 - x0 <= 1e-6:
        return None
    return (x0, x1)


def holes_for_all_belts(
    events: List[GapEvent],
    t_now_min: float,
    t1_min: float,
    t2_min: float,
    t3_min: float,
    f1: float,
    f2: float,
    f3: float,
    D1: float,
    D2: float,
    D3: float,
) -> List[List[Tuple[float, float]]]:
    """Calcule les intervalles de trous pour chaque tapis à l'instant donné."""

    holes: List[List[Tuple[float, float]]] = [[], [], []]
    for ev in events:
        for belt in range(3):
            seg = _hole_on_belt(ev, t_now_min, belt, t1_min, t2_min, t3_min, f1, f2, f3, D1, D2, D3)
            if seg:
                holes[belt].append(seg)
    return holes

