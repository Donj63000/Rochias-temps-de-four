# -*- coding: utf-8 -*-
"""
Module de calculs pour "Four 3 Tapis" (Rochias)
================================================

Ce module implémente trois modèles physiques pour prédire le temps total (minutes)
et ventiler les temps par tapis, à partir des fréquences variateurs f1,f2,f3 :

  (A) Modèle d'ANCRAGE :                T = B_A + K1_A/f1 + K2_A/f2 + K3_A/f3
  (B) Modèle 1/f (OLS) :                T = B   + K1/f1   + K2/f2   + K3/f3
  (C) Modèle 1/f + SYNERGIE (OLS) :     T = B   + K1/f1   + K2/f2   + K3/f3 + S/(f1*f2*f3)

Répartition affichée (par défaut) : "ANCRAGE" — on ventile le total
proportionnellement à (K_Ai/f_i). Ce choix reflète bien la réalité terrain :
T2 > T1 à Hz comparables, et reste stable même si on change le modèle de TOTAL.

Les paramètres par défaut sont **recalibrés automatiquement** à l'import à partir
des 12 expériences intégrées ci-dessous (valeurs en centi-Hz et temps en minutes).

Auteur : Val & co.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple, Dict, Literal, Optional
import math

try:
    import numpy as np
except Exception as e:  # pragma: no cover
    raise RuntimeError("Numpy est requis pour ce module. Installe : pip install numpy") from e


# ---------------------------------------------------------------------------
# 1) Données d'expériences (12 essais historiques)
#    - T1,T2,T3 en centi-Hz (ex. 9000 ≙ 90.00 Hz)
#    - t_total en minutes
# ---------------------------------------------------------------------------

DEFAULT_EXPERIMENTS_CENTI_HZ: List[Tuple[int, int, int, float]] = [
    (4000, 5000, 9000, 2 * 60 + 36),   # 156
    (4000, 5000, 8000, 3 * 60 + 11),   # 191
    (2500, 3500, 8500, 3 * 60 + 26),   # 206
    (8500, 4500, 4565, 4 * 60 + 30),   # 270
    (9000, 9000, 9000, 0 * 60 + 57),   # 57  (run très rapide)
    (9000, 9000, 5000, 3 * 60 + 18),   # 198
    (5000, 9000, 9000, 1 * 60 + 39),   # 99
    (9000, 5000, 9000, 1 * 60 + 43),   # 103
    (5951, 4567, 8777, 2 * 60 + 28),   # 148
    (5000, 2000, 3500, 6 * 60 + 13),   # 373
    (4000, 5000, 9000, 2 * 60 + 36),   # 156 (doublon exp.1)
    (4400, 5700, 9250, 2 * 60 + 24),   # 144
]


# ---------------------------------------------------------------------------
# 2) Structures de paramètres
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnchorParams:
    """Paramètres du modèle d'ancrage (min, min·Hz)."""
    K1: float
    K2: float
    K3: float
    B: float


@dataclass(frozen=True)
class OLSParams:
    """Paramètres du modèle 1/f (min, min·Hz)."""
    K1: float
    K2: float
    K3: float
    B: float


@dataclass(frozen=True)
class SynergyParams:
    """Paramètres du modèle 1/f + synergie (min, min·Hz, min·Hz^3)."""
    K1: float
    K2: float
    K3: float
    S: float
    B: float


# ---------------------------------------------------------------------------
# 3) Utilitaires d’unités et formatage
# ---------------------------------------------------------------------------

def to_hz(x: float, clamp: bool = True) -> float:
    """
    Convertit une entrée utilisateur en Hz 'affichés' (5..99).
    - Si x > 200 → suppose 'IHM' en centi-Hz et divise par 100.
    - Sinon, x est déjà en Hz.
    - clamp=True : tronque à [5,99] au lieu de lever une erreur.

    >>> to_hz(4000)   # IHM
    40.0
    >>> to_hz(40.0)
    40.0
    """
    if x is None:
        raise ValueError("Fréquence manquante.")
    f = float(x)
    f = f / 100.0 if f > 200.0 else f
    if clamp:
        return max(5.0, min(99.0, f))
    if not (5.0 <= f <= 99.0):
        raise ValueError(f"Fréquence {f} Hz hors plage [5..99].")
    return f


def fmt_hms(minutes: float) -> str:
    """Retourne 'H:MM:SS' à partir de minutes (peut être non entier)."""
    total_sec = int(round(minutes * 60))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h}h {m:02d}min {s:02d}s"


# ---------------------------------------------------------------------------
# 4) Calibration à partir des expériences (régression moindres carrés)
# ---------------------------------------------------------------------------

def _build_design_matrix_ols(exps: Iterable[Tuple[int, int, int, float]]) -> Tuple[np.ndarray, np.ndarray]:
    # Caractéristiques pour le modèle 1/f : [1/f1, 1/f2, 1/f3, 1]
    X, y = [], []
    for t1, t2, t3, tmin in exps:
        f1, f2, f3 = t1 / 100.0, t2 / 100.0, t3 / 100.0
        X.append([1.0 / f1, 1.0 / f2, 1.0 / f3, 1.0])
        y.append(tmin)
    return np.array(X, float), np.array(y, float)


def _build_design_matrix_synergy(exps: Iterable[Tuple[int, int, int, float]]) -> Tuple[np.ndarray, np.ndarray]:
    # Caractéristiques pour 1/f + synergie : [1/f1, 1/f2, 1/f3, 1/(f1 f2 f3), 1]
    X, y = [], []
    for t1, t2, t3, tmin in exps:
        f1, f2, f3 = t1 / 100.0, t2 / 100.0, t3 / 100.0
        X.append([1.0 / f1, 1.0 / f2, 1.0 / f3, 1.0 / (f1 * f2 * f3), 1.0])
        y.append(tmin)
    return np.array(X, float), np.array(y, float)


def fit_ols_params(exps: Iterable[Tuple[int, int, int, float]]) -> Tuple[OLSParams, Dict[str, float]]:
    """
    Ajuste B, K1, K2, K3 pour le modèle 1/f.
    Retourne les paramètres et des métriques (RMSE, R2 approx).
    """
    X, y = _build_design_matrix_ols(exps)
    beta, residuals, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    K1, K2, K3, B = beta  # en min·Hz et min
    yhat = X @ beta
    rss = float(np.sum((y - yhat) ** 2))
    rmse = math.sqrt(rss / len(y))
    tss = float(np.sum((y - float(np.mean(y))) ** 2))
    r2 = 1.0 - (rss / tss) if tss > 0 else float("nan")
    return OLSParams(K1, K2, K3, B), {"RMSE": rmse, "R2": r2}


def fit_synergy_params(exps: Iterable[Tuple[int, int, int, float]]) -> Tuple[SynergyParams, Dict[str, float]]:
    """
    Ajuste B, K1, K2, K3 et S pour le modèle 1/f + synergie.
    """
    X, y = _build_design_matrix_synergy(exps)
    beta, residuals, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    K1, K2, K3, S, B = beta
    yhat = X @ beta
    rss = float(np.sum((y - yhat) ** 2))
    rmse = math.sqrt(rss / len(y))
    tss = float(np.sum((y - float(np.mean(y))) ** 2))
    r2 = 1.0 - (rss / tss) if tss > 0 else float("nan")
    return SynergyParams(K1, K2, K3, S, B), {"RMSE": rmse, "R2": r2}


# ---------------------------------------------------------------------------
# 5) Paramètres par défaut (calculés depuis les 12 essais intégrés)
#     - ANCRAGE (choisi pour passer par 90/90/90 = 57 min)
#     - OLS (1/f)
#     - SYNERGY (1/f + 1/(f1 f2 f3))
# ---------------------------------------------------------------------------

# ANCRAGE : constants issues de ton réglage de référence
DEFAULT_ANCHOR = AnchorParams(
    K1=4725.0,
    K2=5175.0,
    K3=15862.5,
    B=-229.25,
)

# 1/f simple (moindres carrés)
DEFAULT_OLS, METRICS_OLS = fit_ols_params(DEFAULT_EXPERIMENTS_CENTI_HZ)
# Exemple (attendus) :
#   DEFAULT_OLS ≈ OLSParams(K1=3313.92056, K2=1355.28020, K3=12357.78520, B=-97.37548)
#   METRICS_OLS ≈ {'RMSE': 18.33, 'R2': 0.948}

# 1/f + synergie (moindres carrés)
DEFAULT_SYNERGY, METRICS_SYN = fit_synergy_params(DEFAULT_EXPERIMENTS_CENTI_HZ)
# Exemple (attendus) :
#   Synergy ≈ K1=5572.48229, K2=6972.24662, K3=16679.5377, S=-1.12022882e7, B=-246.382563
#   RMSE ≈ 8.77, R2 ≈ 0.988


# ---------------------------------------------------------------------------
# 6) Modèles : totaux et répartitions
# ---------------------------------------------------------------------------

ModelName = Literal["anchor", "ols", "synergy"]
SplitName = Literal["anchor", "model"]


def total_time_minutes(
    f1_hz: float, f2_hz: float, f3_hz: float,
    model: ModelName = "synergy",
    ols: OLSParams = DEFAULT_OLS,
    anch: AnchorParams = DEFAULT_ANCHOR,
    syn: SynergyParams = DEFAULT_SYNERGY,
) -> float:
    """Calcule le temps total (minutes) pour le modèle demandé."""
    f1, f2, f3 = float(f1_hz), float(f2_hz), float(f3_hz)
    if model == "anchor":
        return anch.B + anch.K1 / f1 + anch.K2 / f2 + anch.K3 / f3
    elif model == "ols":
        return ols.B + ols.K1 / f1 + ols.K2 / f2 + ols.K3 / f3
    elif model == "synergy":
        return syn.B + syn.K1 / f1 + syn.K2 / f2 + syn.K3 / f3 + syn.S / (f1 * f2 * f3)
    else:
        raise ValueError(f"Modèle inconnu: {model}")


def split_contributions(
    total_minutes: float,
    f1_hz: float, f2_hz: float, f3_hz: float,
    split: SplitName = "anchor",
    ols: OLSParams = DEFAULT_OLS,
    anch: AnchorParams = DEFAULT_ANCHOR,
    syn: SynergyParams = DEFAULT_SYNERGY,
) -> Tuple[float, float, float]:
    """
    Ventile le temps total sur T1,T2,T3.
    - split="anchor" : proportionnel à (K_Ai / f_i) → recommandé (T2 > T1 à Hz similaires).
    - split="model"  : proportionnel aux termes 1/f_i du modèle choisi (puis rescaling pour sommer à total).
    """
    f1, f2, f3 = float(f1_hz), float(f2_hz), float(f3_hz)

    if split == "anchor":
        w1, w2, w3 = anch.K1 / f1, anch.K2 / f2, anch.K3 / f3
    elif split == "model":
        # Par défaut : on utilise le modèle OLS simple pour les poids (stables).
        w1, w2, w3 = ols.K1 / f1, ols.K2 / f2, ols.K3 / f3
    else:
        raise ValueError(f"split inconnu: {split}")

    S = w1 + w2 + w3
    if S <= 0:
        # impossible physiquement ; fallback équitable
        return total_minutes / 3.0, total_minutes / 3.0, total_minutes / 3.0

    return total_minutes * (w1 / S), total_minutes * (w2 / S), total_minutes * (w3 / S)


def is_monotone_decreasing_in_each_f(
    f1_hz: float, f2_hz: float, f3_hz: float,
    model: ModelName = "synergy",
    eps: float = 1.0,
    ols: OLSParams = DEFAULT_OLS,
    anch: AnchorParams = DEFAULT_ANCHOR,
    syn: SynergyParams = DEFAULT_SYNERGY,
) -> bool:
    """Vérifie que T(f) > T(f+eps) pour chaque axe (sanity check)."""
    T = total_time_minutes(f1_hz, f2_hz, f3_hz, model, ols, anch, syn)
    return (
        T > total_time_minutes(f1_hz + eps, f2_hz, f3_hz, model, ols, anch, syn) and
        T > total_time_minutes(f1_hz, f2_hz + eps, f3_hz, model, ols, anch, syn) and
        T > total_time_minutes(f1_hz, f2_hz, f3_hz + eps, model, ols, anch, syn)
    )


# ---------------------------------------------------------------------------
# 7) API principale pour ton application / HMI
# ---------------------------------------------------------------------------

def predict(
    f1_in: float, f2_in: float, f3_in: float,
    *,
    units: Literal["auto", "hz", "ihm"] = "auto",
    model: ModelName = "synergy",
    split: SplitName = "anchor",
    clamp: bool = True,
) -> Dict[str, float]:
    """
    Calcule un scénario complet.

    Paramètres
    ----------
    f1_in, f2_in, f3_in : fréquence saisie (Hz affichés ou IHM)
        - units="auto" : si valeur > 200 on considère IHM (centi-Hz).
        - units="hz"   : déjà en Hz affichés (5..99).
        - units="ihm"  : en centi-Hz (ex. 4000 = 40.00 Hz).
    model : "synergy" | "ols" | "anchor"
        Modèle utilisé pour le **temps total**.
    split : "anchor" | "model"
        Méthode de **répartition** sur T1/T2/T3 (par défaut : "anchor").

    Retour
    ------
    dict avec :
        f1,f2,f3 (Hz),
        total_min, t1_min, t2_min, t3_min,
        total_hms, t1_hms, t2_hms, t3_hms
    """
    # 1) Conversion unités
    if units == "auto":
        f1 = to_hz(f1_in, clamp=clamp)
        f2 = to_hz(f2_in, clamp=clamp)
        f3 = to_hz(f3_in, clamp=clamp)
    elif units == "hz":
        f1, f2, f3 = (to_hz(f1_in, clamp=clamp), to_hz(f2_in, clamp=clamp), to_hz(f3_in, clamp=clamp))
    elif units == "ihm":
        f1, f2, f3 = (to_hz(f1_in / 100.0, clamp=clamp), to_hz(f2_in / 100.0, clamp=clamp), to_hz(f3_in / 100.0, clamp=clamp))
    else:
        raise ValueError("units doit être 'auto', 'hz' ou 'ihm'.")

    # 2) Calcul du total
    total_min = total_time_minutes(f1, f2, f3, model=model)

    # 3) Répartition
    t1_min, t2_min, t3_min = split_contributions(total_min, f1, f2, f3, split=split)

    # 4) Sanity monotone (optionnel : ici juste informatif)
    _monotone_ok = is_monotone_decreasing_in_each_f(f1, f2, f3, model=model)

    return {
        "f1": f1, "f2": f2, "f3": f3,
        "total_min": total_min,
        "t1_min": t1_min, "t2_min": t2_min, "t3_min": t3_min,
        "total_hms": fmt_hms(total_min),
        "t1_hms": fmt_hms(t1_min), "t2_hms": fmt_hms(t2_min), "t3_hms": fmt_hms(t3_min),
        "monotone_ok": float(_monotone_ok),
    }


# ---------------------------------------------------------------------------
# 8) Exemple d'utilisation (exécuté seulement en script direct)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Démo rapide : 99/99/99 (Hz affichés)
    for mode in ("anchor", "ols", "synergy"):
        res = predict(99, 99, 99, units="hz", model=mode, split="anchor")
        print(f"[{mode}] total={res['total_hms']} | T1={res['t1_hms']} T2={res['t2_hms']} T3={res['t3_hms']}")
    # Démo IHM : 9900/9900/8000 (centi-Hz)
    res = predict(9900, 9900, 8000, units="ihm", model="synergy", split="anchor")
    print(f"[ihm→synergy] {res}")


# ---------------------------------------------------------------------------
# 9) Compatibilité API historique
# ---------------------------------------------------------------------------

K1_DIST = DEFAULT_ANCHOR.K1
K2_DIST = DEFAULT_ANCHOR.K2
K3_DIST = DEFAULT_ANCHOR.K3

D_ANCH = DEFAULT_ANCHOR.B
D_R = DEFAULT_OLS.B
K1_R = DEFAULT_OLS.K1
K2_R = DEFAULT_OLS.K2
K3_R = DEFAULT_OLS.K3


def compute_times(f1: float, f2: float, f3: float) -> Tuple[float, float, float, float, Tuple[float, float, float, float]]:
    """Retourne les contributions 1/f du modèle OLS et son total."""

    t1 = K1_R / f1
    t2 = K2_R / f2
    t3 = K3_R / f3
    total_ls = total_time_minutes(f1, f2, f3, model="ols", ols=DEFAULT_OLS)
    return t1, t2, t3, total_ls, (D_R, K1_R, K2_R, K3_R)


def _errors_for_model(model: ModelName) -> Tuple[np.ndarray, np.ndarray]:
    residuals = []
    observations = []
    for t1, t2, t3, minutes in DEFAULT_EXPERIMENTS_CENTI_HZ:
        f1, f2, f3 = t1 / 100.0, t2 / 100.0, t3 / 100.0
        pred = total_time_minutes(f1, f2, f3, model=model)
        residuals.append(pred - minutes)
        observations.append(minutes)
    return np.array(residuals, float), np.array(observations, float)


def _metrics_from_errors(residuals: np.ndarray, observations: np.ndarray) -> Tuple[float, float, float, float]:
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    max_abs = float(np.max(np.abs(residuals)))
    tss = float(np.sum((observations - np.mean(observations)) ** 2))
    rss = float(np.sum(residuals ** 2))
    r2 = 1.0 - rss / tss if tss > 0 else float("nan")
    return mae, rmse, max_abs, r2


_res_ols, _obs = _errors_for_model("ols")
_mae_ols, _rmse_ols, _maxabs_ols, _r2_ols = _metrics_from_errors(_res_ols, _obs)
METRICS_REG = {"MAE": _mae_ols, "RMSE": _rmse_ols, "R2": _r2_ols}

_res_syn, _obs_syn = _errors_for_model("synergy")
_mae_syn, _rmse_syn, _maxabs_syn, _r2_syn = _metrics_from_errors(_res_syn, _obs_syn)
METRICS_EXACT = {"MAE": _mae_syn, "RMSE": _rmse_syn, "MAXABS": _maxabs_syn, "R2": _r2_syn}


__all__ = [
    "AnchorParams",
    "DEFAULT_ANCHOR",
    "DEFAULT_EXPERIMENTS_CENTI_HZ",
    "DEFAULT_OLS",
    "DEFAULT_SYNERGY",
    "K1_DIST",
    "K1_R",
    "K2_DIST",
    "K2_R",
    "K3_DIST",
    "K3_R",
    "METRICS_EXACT",
    "METRICS_OLS",
    "METRICS_REG",
    "METRICS_SYN",
    "ModelName",
    "OLSParams",
    "SplitName",
    "SynergyParams",
    "compute_times",
    "fit_ols_params",
    "fit_synergy_params",
    "fmt_hms",
    "is_monotone_decreasing_in_each_f",
    "predict",
    "split_contributions",
    "to_hz",
    "total_time_minutes",
]

