"""Calibration utilities for the Rochias four model."""

from __future__ import annotations

from typing import Iterable, Sequence, Tuple

try:
    import numpy as np
except Exception as exc:  # pragma: no cover - fatal at import time
    raise SystemExit("Installe numpy : pip install numpy\n" + str(exc)) from exc


def hm(hours: float, minutes: float) -> float:
    return 60 * hours + minutes


EXPS: Sequence[Tuple[int, int, int, float]] = [
    (4000, 5000, 9000, hm(2, 36)),
    (4000, 5000, 8000, hm(3, 11)),
    (2500, 3500, 8500, hm(3, 26)),
    (8500, 4500, 4565, hm(4, 30)),
    (9000, 9000, 9000, hm(0, 57)),
    (9000, 9000, 5000, hm(3, 18)),
    (5000, 9000, 9000, hm(1, 39)),
    (9000, 5000, 9000, hm(1, 43)),
    (5951, 4567, 8777, hm(2, 28)),
    (5000, 2000, 3500, hm(6, 13)),
    (4000, 5000, 9000, hm(2, 36)),
    (4400, 5700, 9250, hm(2, 24)),
]


def _X_row(T1: float, T2: float, T3: float) -> Sequence[float]:
    return [1.0, 100.0 / T1, 100.0 / T2, 100.0 / T3]


def calibrate_regression(exps: Iterable[Sequence[float]] = EXPS):
    """Least-squares regression across the 12 experiments."""
    X = np.array([_X_row(*e[:3]) for e in exps], float)
    y = np.array([e[3] for e in exps], float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    d, K1, K2, K3 = beta.tolist()

    yhat = X @ beta
    resid = y - yhat
    mae = float(np.mean(np.abs(resid)))
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return (d, K1, K2, K3), {"MAE": mae, "RMSE": rmse, "R2": r2}


def _phi_features(f1: float, f2: float, f3: float) -> np.ndarray:
    inv1, inv2, inv3 = 1.0 / f1, 1.0 / f2, 1.0 / f3
    return np.array(
        [
            1.0,
            inv1,
            inv2,
            inv3,
            inv1 ** 2,
            inv2 ** 2,
            inv3 ** 2,
            inv1 * inv2,
            inv1 * inv3,
            inv2 * inv3,
            inv1 ** 3,
            inv3 ** 3,
        ],
        float,
    )


def calibrate_interp12(exps: Iterable[Sequence[float]] = EXPS):
    """Exact interpolation of the 12 experiments."""
    X = np.array([_phi_features(e[0] / 100.0, e[1] / 100.0, e[2] / 100.0) for e in exps], float)
    y = np.array([e[3] for e in exps], float)
    theta, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ theta
    resid = y - yhat
    mae = float(np.mean(np.abs(resid)))
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    max_abs = float(np.max(np.abs(resid)))
    return theta, {"MAE": mae, "RMSE": rmse, "MAXABS": max_abs}


def predict_T_interp12(f1: float, f2: float, f3: float, theta: np.ndarray) -> float:
    return float(_phi_features(f1, f2, f3) @ theta)


def calibrate_anchor_from_ABCD(exps: Iterable[Sequence[float]], ref_ihm: float = 9000):
    ref_hz = ref_ihm / 100.0
    T_ref = next(
        T for T1, T2, T3, T in exps if T1 == ref_ihm and T2 == ref_ihm and T3 == ref_ihm
    )

    def K_for_index(idx: int) -> float:
        for T1, T2, T3, T in exps:
            arr = [T1, T2, T3]
            if sum(1 for value in arr if value == ref_ihm) == 2 and arr[idx] != ref_ihm:
                f_var = arr[idx] / 100.0
                delta = (1.0 / f_var) - (1.0 / ref_hz)
                if abs(delta) <= 1e-12:
                    raise RuntimeError(f"Delta nul pour l'index {idx}")
                return (T - T_ref) / delta
        raise RuntimeError(f"Essai d'ancrage manquant pour l'index {idx}")

    K1 = K_for_index(0)
    K2 = K_for_index(1)
    K3 = K_for_index(2)
    d = T_ref - (K1 + K2 + K3) / ref_hz
    return K1, K2, K3, d


PARAMS_REG, METRICS_REG = calibrate_regression(EXPS)
D_R, K1_R, K2_R, K3_R = PARAMS_REG

K1_DIST, K2_DIST, K3_DIST, D_ANCH = calibrate_anchor_from_ABCD(EXPS)

THETA12, METRICS_EXACT = calibrate_interp12(EXPS)


def compute_times(f1: float, f2: float, f3: float):
    d, K1, K2, K3 = D_R, K1_R, K2_R, K3_R
    t1, t2, t3 = K1 / f1, K2 / f2, K3 / f3
    total_ls = d + t1 + t2 + t3
    return t1, t2, t3, total_ls, (d, K1, K2, K3)


__all__ = [
    "EXPS",
    "METRICS_EXACT",
    "METRICS_REG",
    "PARAMS_REG",
    "THETA12",
    "compute_times",
    "hm",
    "predict_T_interp12",
    "calibrate_regression",
    "calibrate_interp12",
    "calibrate_anchor_from_ABCD",
    "K1_DIST",
    "K2_DIST",
    "K3_DIST",
    "D_ANCH",
    "D_R",
    "K1_R",
    "K2_R",
    "K3_R",
]
