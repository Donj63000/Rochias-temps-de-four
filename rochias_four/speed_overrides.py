# -*- coding: utf-8 -*-
"""
Calibration des vitesses m/s en fonction des Hz (par tapis).
- Permet d'ajouter des points (Hz, t_1m en s) ou (Hz, m/s),
- Fait un fit linéaire v = a·f (+ b optionnel) pour T1, T2, T3,
- Persiste dans ~/.rochias_four/speed_params.json,
- N'affecte PAS les calculs de temps (total/répartition) tant qu'on ne les branche pas.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Tuple, Dict
import os, json
import numpy as np

# ---------- Dataclasses ----------
@dataclass(frozen=True)
class SpeedParams:
    a: float  # pente m/s par Hz
    b: float  # offset m/s à 0 Hz

@dataclass(frozen=True)
class SpeedSet:
    t1: SpeedParams
    t2: SpeedParams
    t3: SpeedParams

# ---------- Persistance ----------
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".rochias_four")
CONFIG_PATH = os.path.join(CONFIG_DIR, "speed_params.json")

# état courant en mémoire (None = pas calibré)
_CURRENT: SpeedSet | None = None

def _default_speedset() -> SpeedSet:
    # Valeurs neutres (n'interviennent pas dans tes calculs tant que non utilisées)
    return SpeedSet(
        t1=SpeedParams(a=0.0, b=0.0),
        t2=SpeedParams(a=0.0, b=0.0),
        t3=SpeedParams(a=0.0, b=0.0),
    )

def get_current_speedset() -> SpeedSet | None:
    """Retourne les vitesses courantes (None s'il n'y a pas d'override)."""
    return _CURRENT

def set_current_speedset(s: SpeedSet | None) -> None:
    global _CURRENT
    _CURRENT = s

def reset_speed_to_default() -> None:
    set_current_speedset(None)
    if os.path.exists(CONFIG_PATH):
        try:
            os.remove(CONFIG_PATH)
        except OSError:
            pass

def load_speed_from_disk() -> bool:
    """Charge depuis ~, retourne True si succès, False sinon."""
    try:
        if not os.path.exists(CONFIG_PATH):
            set_current_speedset(None)
            return False
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        s = SpeedSet(
            t1=SpeedParams(**d["t1"]),
            t2=SpeedParams(**d["t2"]),
            t3=SpeedParams(**d["t3"]),
        )
        set_current_speedset(s)
        return True
    except Exception:
        set_current_speedset(None)
        return False

def save_speed_to_disk() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    s = get_current_speedset() or _default_speedset()
    d = {
        "t1": asdict(s.t1),
        "t2": asdict(s.t2),
        "t3": asdict(s.t3),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

# ---------- Utilitaires ----------
def _to_hz(x: float) -> float:
    """Accepte Hz affichés (5..99) ou centi-Hz (>200)."""
    f = float(x)
    if f > 200.0:
        f /= 100.0
    return max(5.0, min(99.0, f))

def _to_mps_from_pair(freq_hz: float, t1m_s: float | None, v_mps: float | None) -> tuple[float, float]:
    f = _to_hz(freq_hz)
    if (t1m_s is None) and (v_mps is None):
        raise ValueError("Il faut fournir t_1m (s) ou v (m/s).")
    if v_mps is None:
        if t1m_s <= 0:
            raise ValueError("t_1m doit être > 0 s.")
        v = 1.0 / float(t1m_s)
    else:
        v = float(v_mps)
        if v <= 0:
            raise ValueError("La vitesse m/s doit être > 0.")
    return f, v

# ---------- Fits ----------
def fit_line_through_origin(points: List[tuple[float, float]]) -> SpeedParams:
    """
    Fit v = a·f (b=0) sur des points (f, v).
    a = (Σ f·v) / (Σ f²)
    """
    if len(points) == 0:
        raise ValueError("Pas de point pour le fit.")
    F = np.array([p[0] for p in points], float)
    V = np.array([p[1] for p in points], float)
    a = float(np.dot(F, V) / np.dot(F, F))
    return SpeedParams(a=a, b=0.0)

def fit_line_with_intercept(points: List[tuple[float, float]]) -> SpeedParams:
    """
    Fit v = a·f + b sur des points (f, v) avec moindres carrés.
    """
    if len(points) < 2:
        raise ValueError("Au moins 2 points pour estimer (a,b).")
    F = np.array([p[0] for p in points], float)
    V = np.array([p[1] for p in points], float)
    X = np.column_stack([F, np.ones_like(F)])
    beta, *_ = np.linalg.lstsq(X, V, rcond=None)
    a, b = float(beta[0]), float(beta[1])
    return SpeedParams(a=a, b=b)

def estimate_speed_mps(params: SpeedParams, freq_hz: float) -> float:
    """Renvoie v(f) en m/s pour une fréquence (Hz ou centi-Hz)."""
    f = _to_hz(freq_hz)
    v = params.a * f + params.b
    return max(0.0, v)
