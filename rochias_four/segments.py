from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class BeltGeom:
    pre_cm: float
    cells_cm: tuple[float, ...]
    transfer_cm: float
    convoy_cm: float
    chauffe_cm: float  # somme des cellules (pour contrôle)

GEOM: dict[int, BeltGeom] = {
    # Tapis 1
    1: BeltGeom(
        pre_cm=115.0,
        cells_cm=(240.0, 240.0, 244.0),
        transfer_cm=310.0,
        convoy_cm=1148.5,
        chauffe_cm=723.5,
    ),
    # Tapis 2
    2: BeltGeom(
        pre_cm=100.0,
        cells_cm=(240.0, 240.0, 244.0),
        transfer_cm=345.0,
        convoy_cm=1168.5,
        chauffe_cm=723.5,
    ),
    # Tapis 3
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
        "convoy_sec": conv_time_sec,   # temps officiel (référence app/tableur)
        "convoy_rebuilt_sec": convoy,  # somme des segments (contrôle)
        "geom": g,
    }
