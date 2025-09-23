# -*- coding: utf-8 -*-
"""
Overrides d'ancrage utilisateur (sans casser les calculs existants).
- Chargement / sauvegarde JSON des paramètres d'ancrage (K1,K2,K3,B)
- Calcul (fit) à partir de points d'ancrage simples ou de mesures complètes
- Accès uniforme aux ancrages "courants" (user override sinon défaut)
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional
import os, json, math

import numpy as np

# --- Importe tes paramètres par défaut depuis calibration.py ---
try:
    from .calibration import AnchorParams as _AnchorParamsDefault
    from .calibration import DEFAULT_ANCHOR as _DEFAULT_ANCHOR
except Exception:
    # Fallback minimal si noms différents
    @dataclass(frozen=True)
    class _AnchorParamsDefault:  # type: ignore
        K1: float
        K2: float
        K3: float
        B: float
    _DEFAULT_ANCHOR = _AnchorParamsDefault(4725.0, 5175.0, 15862.5, -229.25)  # min·Hz, min

@dataclass(frozen=True)
class AnchorParams:
    K1: float
    K2: float
    K3: float
    B: float

# --- Fichier de config (persistance) ---
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".rochias_four")
CONFIG_PATH = os.path.join(CONFIG_DIR, "anchor_params.json")

# --- Etat courant (en mémoire) ---
_CURRENT: AnchorParams = AnchorParams(_DEFAULT_ANCHOR.K1, _DEFAULT_ANCHOR.K2,
                                      _DEFAULT_ANCHOR.K3, _DEFAULT_ANCHOR.B)

def get_current_anchor() -> AnchorParams:
    """Retourne les ancrages courants (user override s’il existe, sinon défaut)."""
    return _CURRENT

def set_current_anchor(params: AnchorParams) -> None:
    global _CURRENT
    _CURRENT = params

def reset_anchor_to_default() -> None:
    set_current_anchor(AnchorParams(_DEFAULT_ANCHOR.K1, _DEFAULT_ANCHOR.K2,
                                    _DEFAULT_ANCHOR.K3, _DEFAULT_ANCHOR.B))

def load_anchor_from_disk() -> bool:
    """Charge les ancrages depuis le disque. Retourne True si OK."""
    try:
        if not os.path.exists(CONFIG_PATH):
            reset_anchor_to_default()
            return False
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        set_current_anchor(AnchorParams(**d))
        return True
    except Exception:
        reset_anchor_to_default()
        return False

def save_anchor_to_disk() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(asdict(_CURRENT), f, indent=2, ensure_ascii=False)

# ---------- Utilitaires de conversion ----------
def _to_hz(x: float) -> float:
    """Accepte Hz ou centi-Hz (>200). Tronque à [5..99]."""
    f = float(x)
    if f > 200.0:  # IHM centi-Hz
        f = f / 100.0
    return max(5.0, min(99.0, f))

# ---------- Fits d'ancrage ----------
def fit_anchor_from_direct(
    f1_ref: float, f2_ref: float, f3_ref: float,
    t1_ref_min: float, t2_ref_min: float, t3_ref_min: float,
    T_total_ref_min: float
) -> AnchorParams:
    """
    Ancrage "simple" : on saisit des couples (fi_ref, ti_ref) et un T_total pour ce triplet.
    On pose K1=t1* f1, K2=t2* f2, K3=t3* f3 ; puis B = T - sum(Ki/fi).
    """
    f1, f2, f3 = _to_hz(f1_ref), _to_hz(f2_ref), _to_hz(f3_ref)
    K1 = t1_ref_min * f1
    K2 = t2_ref_min * f2
    K3 = t3_ref_min * f3
    B  = T_total_ref_min - (K1/f1 + K2/f2 + K3/f3)
    return AnchorParams(K1=K1, K2=K2, K3=K3, B=B)

def fit_anchor_from_points(points: List[Tuple[float, float, float, float]]) -> AnchorParams:
    """
    Fit moindres carrés sur n>=4 points (f1,f2,f3 en Hz ou centi-Hz, T en minutes):
        T ≈ B + K1/f1 + K2/f2 + K3/f3
    """
    X, y = [], []
    for f1, f2, f3, T in points:
        f1, f2, f3 = _to_hz(f1), _to_hz(f2), _to_hz(f3)
        X.append([1.0/f1, 1.0/f2, 1.0/f3, 1.0])
        y.append(float(T))
    X = np.array(X, float)
    y = np.array(y, float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    K1, K2, K3, B = beta
    return AnchorParams(K1=float(K1), K2=float(K2), K3=float(K3), B=float(B))
