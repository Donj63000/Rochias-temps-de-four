# -*- coding: utf-8 -*-
"""
Référence maintenance (L/v) — reproduction exacte du tableur.
Formule par tapis i : t_i (s) = Lconv_i (m) * C_i / UI_i
- UI_i : fréquence IHM en centi-Hz (9999 -> 99.99 Hz)
- Lconv_i : longueur de convoyage du tapis i (m)
- C_i : coefficient du tapis i lu dans l'en-tête "T(1m) = C/UI" du tableur

Cette implémentation évite les erreurs d'arrondi (pas de passage par v=a*f).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Dict

# --- Constantes (tableur) ---
C1 = 1330585.39
C2 = 916784.29
C3 = 6911721.07

Lconv1 = 11.485
Lconv2 = 11.685
Lconv3 = 6.980

# (Optionnel) longueurs de chauffe si un jour tu veux les afficher
Lheat1 = 7.235
Lheat2 = 7.235
Lheat3 = 4.800

def _to_ui(value: float, units: Literal["auto","hz","ui"]="auto") -> float:
    """
    Convertit une saisie en UI (centi-Hz) :
      - units="ui"   : value est déjà UI (ex. 4000..9999)
      - units="hz"   : value est en Hz  (5..99) -> UI = Hz*100
      - units="auto" : si value>200 => UI, sinon => Hz*100
    Clamp à [500..9999].
    """
    v = float(value)
    if units == "ui":
        ui = v
    elif units == "hz":
        ui = v * 100.0
    else:
        ui = v if v > 200.0 else v * 100.0
    # bornes IHM
    if ui < 500.0:   ui = 500.0
    if ui > 9999.0:  ui = 9999.0
    return ui

def _fmt_hms_from_seconds(sec: float) -> str:
    s = int(round(sec))
    h = s // 3600
    m = (s % 3600) // 60
    ss = s % 60
    return f"{h}h {m:02d}min {ss:02d}s"

@dataclass(frozen=True)
class MaintTimes:
    # secondes
    t1_s: float
    t2_s: float
    t3_s: float
    total_s: float
    # minutes
    t1_min: float
    t2_min: float
    t3_min: float
    total_min: float
    # hms
    t1_hms: str
    t2_hms: str
    t3_hms: str
    total_hms: str
    # fréquences affichées
    f1_hz: float
    f2_hz: float
    f3_hz: float
    ui1: float
    ui2: float
    ui3: float

def compute_times_maintenance(
    f1_in: float, f2_in: float, f3_in: float,
    units: Literal["auto","hz","ui"] = "auto",
) -> MaintTimes:
    """
    Calcul "Référence maintenance" exactement comme le tableur:
        t1 = Lconv1 * C1 / UI1   (secondes), etc.
    """
    ui1 = _to_ui(f1_in, units)
    ui2 = _to_ui(f2_in, units)
    ui3 = _to_ui(f3_in, units)

    t1_s = Lconv1 * C1 / ui1
    t2_s = Lconv2 * C2 / ui2
    t3_s = Lconv3 * C3 / ui3
    T_s  = t1_s + t2_s + t3_s

    return MaintTimes(
        t1_s=t1_s, t2_s=t2_s, t3_s=t3_s, total_s=T_s,
        t1_min=t1_s/60.0, t2_min=t2_s/60.0, t3_min=t3_s/60.0, total_min=T_s/60.0,
        t1_hms=_fmt_hms_from_seconds(t1_s),
        t2_hms=_fmt_hms_from_seconds(t2_s),
        t3_hms=_fmt_hms_from_seconds(t3_s),
        total_hms=_fmt_hms_from_seconds(T_s),
        f1_hz=ui1/100.0, f2_hz=ui2/100.0, f3_hz=ui3/100.0,
        ui1=ui1, ui2=ui2, ui3=ui3
    )

# --- Auto-tests (deve) : commente si tu veux ---
if __name__ == "__main__":
    # Cas 1 : 99.99 / 99.99 / 99.99  (UI=9999)
    r = compute_times_maintenance(9999, 9999, 9999, units="ui")
    print("[9999/9999/9999] T1=", r.t1_s, "T2=", r.t2_s, "T3=", r.t3_s, "Total=", r.total_s, r.total_hms)
    # attendu (tableur) ~ 1528.330 s ; 1071.370 s ; 4824.864 s ; Total 7424.564 s = 2h 03min 44.6s

    # Cas 2 : 4000 / 5000 / 9000 (UI)
    r = compute_times_maintenance(4000, 5000, 9000, units="ui")
    print("[4000/5000/9000] T1=", r.t1_s, "T2=", r.t2_s, "T3=", r.t3_s, "Total=", r.total_s, r.total_hms)
    # attendu (tableur) ~ 3820.443 s ; 2142.525 s ; 5360.424 s ; Total 11323.392 s = 3h 08min 43.4s
