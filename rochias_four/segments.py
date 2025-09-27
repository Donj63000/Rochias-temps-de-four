from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BeltGeom:
    pre_cm: float
    cells_cm: tuple[float, ...]
    transfer_cm: float
    convoy_cm: float
    chauffe_cm: float  # somme des cellules (pour contrôle)


GEOM: dict[int, BeltGeom] = {
    1: BeltGeom(
        pre_cm=115.0,
        cells_cm=(240.0, 240.0, 244.0),
        transfer_cm=310.0,
        convoy_cm=1148.5,
        chauffe_cm=723.5,
    ),
    2: BeltGeom(
        pre_cm=100.0,
        cells_cm=(240.0, 240.0, 244.0),
        transfer_cm=345.0,
        convoy_cm=1168.5,
        chauffe_cm=723.5,
    ),
    3: BeltGeom(
        pre_cm=80.0,
        cells_cm=(240.0, 240.0),
        transfer_cm=138.0,
        convoy_cm=698.0,
        chauffe_cm=480.0,
    ),
}


def sec_per_meter_from_conv(belt_index: int, conv_time_sec: float) -> float:
    """Temps pour 1 m (s/m) = t_conv / (L_convoy en m)."""
    g = GEOM[belt_index]
    return float(conv_time_sec) / (g.convoy_cm / 100.0)


def breakdown_for_belt(belt_index: int, conv_time_sec: float) -> dict:
    """Décomposition fine du tapis : temps par segment, totaux, contrôles."""
    g = GEOM[belt_index]
    s_per_m = sec_per_meter_from_conv(belt_index, conv_time_sec)

    def seg_time(cm: float) -> float:
        return s_per_m * (cm / 100.0)

    pre = seg_time(g.pre_cm)
    cells = [seg_time(c) for c in g.cells_cm]
    transfer = seg_time(g.transfer_cm)
    chauffe = sum(cells)
    convoy = pre + chauffe + transfer

    return {
        "s_per_m": s_per_m,
        "pre_sec": pre,
        "cell_secs": cells,
        "transfer_sec": transfer,
        "chauffe_sec": chauffe,
        "convoy_sec": conv_time_sec,
        "convoy_rebuilt_sec": convoy,
        "geom": g,
    }


@dataclass(frozen=True)
class SegmentWeights:
    k1: dict[str, float]
    k2: dict[str, float]
    k3: dict[str, float]


_DEFAULT = SegmentWeights(
    k1={"entry1": 0.0, "c1": 1 / 3, "c2": 1 / 3, "c3": 1 / 3},
    k2={"transfer1": 0.0, "c4": 1 / 3, "c5": 1 / 3, "c6": 1 / 3},
    k3={"transfer2": 0.0, "c7": 1 / 3, "c8": 1 / 3, "c9": 1 / 3},
)


def _norm_block(values: dict[str, float]) -> dict[str, float]:
    total = sum(float(v) for v in values.values()) or 1.0
    return {key: float(val) / total for key, val in values.items()}


def load_segment_weights() -> SegmentWeights:
    path = Path(__file__).with_name("segments_weights.json")
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            k1 = _norm_block(raw.get("k1", _DEFAULT.k1))
            k2 = _norm_block(raw.get("k2", _DEFAULT.k2))
            k3 = _norm_block(raw.get("k3", _DEFAULT.k3))
            return SegmentWeights(k1=k1, k2=k2, k3=k3)
        except Exception:
            pass
    return _DEFAULT


def compute_segment_times_minutes(
    t1_min: float,
    t2_min: float,
    t3_min: float,
    weights: SegmentWeights,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, fraction in weights.k1.items():
        out[key] = float(fraction) * float(t1_min)
    for key, fraction in weights.k2.items():
        out[key] = float(fraction) * float(t2_min)
    for key, fraction in weights.k3.items():
        out[key] = float(fraction) * float(t3_min)
    return out


def cumulative_markers_for_bar(
    block: list[tuple[str, float]],
    total_min: float,
) -> list[float]:
    markers: list[float] = []
    acc = 0.0
    span = float(total_min) or 1e-6
    for idx, (_, duration) in enumerate(block):
        acc += float(duration)
        if idx < len(block) - 1:
            markers.append(max(0.0, min(1.0, acc / span)))
    return markers


__all__ = [
    "BeltGeom",
    "GEOM",
    "sec_per_meter_from_conv",
    "breakdown_for_belt",
    "SegmentWeights",
    "load_segment_weights",
    "compute_segment_times_minutes",
    "cumulative_markers_for_bar",
]
