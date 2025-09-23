# -*- coding: utf-8 -*-
# Calculs cohérents pour Four 3 tapis (total + parts)

from typing import Tuple

from .calibration_overrides import get_current_anchor

# === 1) Constantes ===
# Ancrage (parts "indépendantes" et poids de répartition)
K1_ANCH, K2_ANCH, K3_ANCH = 4725.0, 5175.0, 15862.5  # min·Hz
B_ANCH = -229.25                                     # min

# Modèle "1/f + synergie" (temps total robuste)
K1_SYN, K2_SYN, K3_SYN = 5572.48229, 6972.24662, 16679.5377    # min·Hz
S_SYN, B_SYN = -11202288.2, -246.382563                        # min·Hz^3, min

# Utilitaire
def _clamp_hz(f: float) -> float:
    f = float(f)
    # Autoriser saisie IHM (centi-Hz) : si >200 on divise par 100
    if f > 200.0:
        f /= 100.0
    return max(5.0, min(99.0, f))

# === 2) Total (minutes) ===
def total_minutes_synergy(f1, f2, f3) -> float:
    f1, f2, f3 = _clamp_hz(f1), _clamp_hz(f2), _clamp_hz(f3)
    return (B_SYN
            + K1_SYN/f1 + K2_SYN/f2 + K3_SYN/f3
            + S_SYN/(f1*f2*f3))

def total_minutes_anchor(f1, f2, f3) -> float:
    f1, f2, f3 = _clamp_hz(f1), _clamp_hz(f2), _clamp_hz(f3)
    anch = get_current_anchor()
    return anch.B + anch.K1 / f1 + anch.K2 / f2 + anch.K3 / f3

# === 3) Parts ===
def parts_independantes(f1, f2, f3) -> Tuple[float, float, float]:
    """Contributions indépendantes (ancrage) : Ki/f_i, NE SOMMENT PAS AU TOTAL."""
    f1, f2, f3 = _clamp_hz(f1), _clamp_hz(f2), _clamp_hz(f3)
    anch = get_current_anchor()
    return (anch.K1 / f1, anch.K2 / f2, anch.K3 / f3)

def parts_reparties(total_min: float, f1, f2, f3) -> Tuple[float, float, float]:
    """
    Répartition du total par poids "ancrage" : w_i ∝ Ki/f_i.
    Garantit t1+t2+t3 = total et t_i <= total.
    """
    f1, f2, f3 = _clamp_hz(f1), _clamp_hz(f2), _clamp_hz(f3)
    anch = get_current_anchor()
    w1, w2, w3 = anch.K1 / f1, anch.K2 / f2, anch.K3 / f3
    s = w1 + w2 + w3
    if s <= 0:
        return (total_min/3.0, total_min/3.0, total_min/3.0)
    return (total_min*(w1/s), total_min*(w2/s), total_min*(w3/s))

def correction_recouvrement(total_min: float, f1, f2, f3) -> float:
    """Écart entre total affiché et somme des contributions indépendantes."""
    c1, c2, c3 = parts_independantes(f1, f2, f3)
    return total_min - (c1 + c2 + c3)
