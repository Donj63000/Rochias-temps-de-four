from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

# --- Constantes maintenance (référence tableur L/v) ---
# NB : ces valeurs proviennent de la calibration maintenance ; on ne les modifie pas ici.
# Elles servent UNIQUEMENT au calcul du temps de CONVOYAGE par tapis.  (t_i = K_i / f_i)
C1 = 1330585.39
C2 = 916784.29
C3 = 6911721.07

# Longueurs de convoyage utilisées par la maintenance (référence)
Lconv1 = 11.485
Lconv2 = 11.685
Lconv3 = 6.980

# --------------------------------------------------------------------------------------
# Aide : conversion saisie opérateur -> "UI" (IHM×100) -> Hz ; bornes de sécurité
def _to_ui(value: float, units: Literal["auto", "hz", "ui"] = "auto") -> float:
    v = float(value)
    if units == "ui":
        ui = v
    elif units == "hz":
        ui = v * 100.0
    else:
        ui = v if v > 200.0 else v * 100.0
    # bornes IHM réalistes (évite divisions extrêmes)
    if ui < 500.0:
        ui = 500.0
    if ui > 9999.0:
        ui = 9999.0
    return ui


def _fmt_hms_from_seconds(sec: float) -> str:
    s = math.floor(sec + 1e-12)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}min {s:02d}s"


# --------------------------------------------------------------------------------------
# Résultats "maintenance" = CONVOYAGE (on ne manipule PAS un temps de chauffe ici)
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
    # formats H:M:S
    t1_hms: str
    t2_hms: str
    t3_hms: str
    total_hms: str
    # fréquences de calcul (cohérence UI/Hz)
    f1_hz: float
    f2_hz: float
    f3_hz: float
    ui1: float
    ui2: float
    ui3: float


def compute_times_maintenance(
    f1_in: float, f2_in: float, f3_in: float, units: Literal["auto", "hz", "ui"] = "auto"
) -> MaintTimes:
    """
    Calcule les TEMPS DE CONVOYAGE par tapis (référence maintenance tableur L/v).
    Rappel explicite : le 'temps de chauffe' est un sous-ensemble de ce temps et
    NE DOIT PAS être additionné au total.
    """
    ui1 = _to_ui(f1_in, units)
    ui2 = _to_ui(f2_in, units)
    ui3 = _to_ui(f3_in, units)

    # Formule validée maintenance (équivalente t_i = K_i / f_i ; K_i = Lconv_i * C_i en s·Hz)
    t1_s = Lconv1 * C1 / ui1
    t2_s = Lconv2 * C2 / ui2
    t3_s = Lconv3 * C3 / ui3
    T_s = t1_s + t2_s + t3_s

    return MaintTimes(
        t1_s=t1_s,
        t2_s=t2_s,
        t3_s=t3_s,
        total_s=T_s,
        t1_min=t1_s / 60.0,
        t2_min=t2_s / 60.0,
        t3_min=t3_s / 60.0,
        total_min=T_s / 60.0,
        t1_hms=_fmt_hms_from_seconds(t1_s),
        t2_hms=_fmt_hms_from_seconds(t2_s),
        t3_hms=_fmt_hms_from_seconds(t3_s),
        total_hms=_fmt_hms_from_seconds(T_s),
        f1_hz=ui1 / 100.0,
        f2_hz=ui2 / 100.0,
        f3_hz=ui3 / 100.0,
        ui1=ui1,
        ui2=ui2,
        ui3=ui3,
    )


# --------------------------------------------------------------------------------------
# OUTIL D’APPOINT (pour l’UI) : déduire la CHAUFFE à partir du convoyage
# On utilise la géométrie physique (longueurs) des tapis : 'chauffe_cm' / 'convoy_cm'.
# => la chauffe est de toute façon incluse dans le convoyage ; cette API sert uniquement
#    à AFFICHER un rappel clair à l’opérateur.
try:
    from .segments import GEOM  # GEOM[i].convoy_cm et GEOM[i].chauffe_cm
except Exception:
    GEOM = {1: None, 2: None, 3: None}


@dataclass(frozen=True)
class ChauffeTimes:
    c1_s: float
    c2_s: float
    c3_s: float
    c1_hms: str
    c2_hms: str
    c3_hms: str


def compute_chauffe_seconds_from_maintenance(
    f1_in: float, f2_in: float, f3_in: float, units: Literal["auto", "hz", "ui"] = "auto"
) -> ChauffeTimes:
    """
    Retourne les temps de CHAUFFE (en s + H:M:S) pour chaque tapis,
    déduits des temps de CONVOYAGE via le ratio géométrique (∑ cellules / longueur convoyage).

    ⚠️ Information process UNIQUEMENT — ne s’additionne pas au total.
    """
    maint = compute_times_maintenance(f1_in, f2_in, f3_in, units=units)

    def r(i: int) -> float:
        g = GEOM[i]
        return float(g.chauffe_cm) / float(g.convoy_cm) if g is not None else float("nan")

    c1 = maint.t1_s * r(1)
    c2 = maint.t2_s * r(2)
    c3 = maint.t3_s * r(3)
    return ChauffeTimes(
        c1_s=c1,
        c2_s=c2,
        c3_s=c3,
        c1_hms=_fmt_hms_from_seconds(c1),
        c2_hms=_fmt_hms_from_seconds(c2),
        c3_hms=_fmt_hms_from_seconds(c3),
    )
