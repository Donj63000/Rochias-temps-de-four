# rochias_four/graphs.py
from __future__ import annotations

import math
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from .calibration import K1_DIST, K2_DIST, K3_DIST, THETA12, compute_times, predict_T_interp12
from .utils import parse_hz, fmt_hms
from .config import TICK_SECONDS


@dataclass
class GraphInputs:
    f1: float
    f2: float
    f3: float
    h0_cm: float
    t1s_min: float
    t2s_min: float
    t3s_min: float
    T_exact_min: float


def _compute_last_or_recalc(app) -> GraphInputs:
    """
    Récupère les données du dernier calcul (si dispo) sinon recalcule depuis les entrées.
    Retourne fréquences, h0, durées par tapis (t*_i) et T_exact.
    """
    # 1) lire f1,f2,f3 depuis last_calc si possible, sinon depuis les champs UI
    if getattr(app, "last_calc", None):
        f1 = float(app.last_calc["f1"]); f2 = float(app.last_calc["f2"]); f3 = float(app.last_calc["f3"])
        T_exact = float(app.last_calc["T_exp"])
        t1s = float(app.last_calc["t1_star"]); t2s = float(app.last_calc["t2_star"]); t3s = float(app.last_calc["t3_star"])
    else:
        f1 = parse_hz(app.e1.get()); f2 = parse_hz(app.e2.get()); f3 = parse_hz(app.e3.get())
        # Recalcul minimal (même logique que app.on_calculer)
        t1, t2, t3, _T_ls, (_d, _K1, _K2, _K3) = compute_times(f1, f2, f3)
        T_exact = predict_T_interp12(f1, f2, f3, THETA12)
        # Décomposition via alpha (comme dans app.py)
        t1_base, t2_base, t3_base = K1_DIST / f1, K2_DIST / f2, K3_DIST / f3
        sum_base = t1_base + t2_base + t3_base
        if sum_base <= 1e-12:
            raise ValueError("Somme des temps d'ancrage nulle.")
        alpha = T_exact / sum_base
        t1s, t2s, t3s = alpha * t1_base, alpha * t2_base, alpha * t3_base

    # 2) lire h0 si l'appli a un champ self.h0 ; sinon défaut 2.00 cm
    h0_cm = 2.0
    h_widget = getattr(app, "h0", None)
    if h_widget is not None:
        try:
            h0_cm = float(h_widget.get().replace(",", "."))
            if not (h0_cm > 0): h0_cm = 2.0
        except Exception:
            h0_cm = 2.0

    return GraphInputs(
        f1=f1, f2=f2, f3=f3, h0_cm=h0_cm,
        t1s_min=t1s, t2s_min=t2s, t3s_min=t3s,
        T_exact_min=(t1s + t2s + t3s) if math.isfinite(t1s+t2s+t3s) else T_exact
    )


def _heights_cm(f1: float, f2: float, f3: float, h0_cm: float):
    """
    Épaisseurs par tapis à partir des capacités u_i = f_i / K'_i (mêmes K' que l'app).
    """
    u1, u2, u3 = (f1 / K1_DIST), (f2 / K2_DIST), (f3 / K3_DIST)
    h1 = h0_cm
    h2 = h0_cm * (u1 / u2) if u2 > 0 else float("inf")
    h3 = h0_cm * (u1 / u3) if u3 > 0 else float("inf")
    return h1, h2, h3


class GraphWindow(tk.Toplevel):
    """
    Fenêtre modale contenant le graphique h(t) partitionné par tapis.
    Fidèle aux barres : partitions = t*_i, courbe = épaisseur calibrée.
    """

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Graphiques — Épaisseur vs Temps (h(t))")
        self.geometry("980x560")
        self.configure(bg=getattr(app, "BG", "#ffffff"))  # tolérant si thème non exporté
        self._after = None

        # -- panneau haut (infos)
        top = ttk.Frame(self); top.pack(fill="x", padx=10, pady=6)
        ttk.Label(top, text="Épaisseur de couche (cm) vs Temps (min) — partitionné par tapis").pack(side="left")
        self.info = ttk.Label(top, text="")
        self.info.pack(side="right")

        # -- figure matplotlib
        fig = Figure(figsize=(8.8, 4.8), dpi=100)
        self.ax = fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 4))
        NavigationToolbar2Tk(self.canvas, self).update()

        # tracer initial
        self._plot_static()

        # (option) curseur temps réel si la simulation tourne
        self.cursor_line = None
        self._start_cursor_loop()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _plot_static(self):
        data = _compute_last_or_recalc(self.app)
        h1, h2, h3 = _heights_cm(data.f1, data.f2, data.f3, data.h0_cm)

        # Abscisses des frontières (minutes)
        t1 = data.t1s_min
        t2 = data.t2s_min
        t3 = data.t3s_min
        T = data.T_exact_min

        # Courbe à paliers (steps-post)
        xs = [0.0, t1, t1 + t2, T]
        ys = [h1,  h2,  h3,     h3]
        self.ax.clear()
        self.ax.step(xs, ys, where="post", linewidth=2.0, label="h(t) calculée")

        # Fond partitionné T1/T2/T3 + traits 1/3–2/3 par tapis (comme les « cellules »)
        starts = [0.0, t1, t1 + t2]
        lengths = [t1, t2, t3]
        labels = ["Tapis 1", "Tapis 2", "Tapis 3"]
        for i, (t0, L, lab) in enumerate(zip(starts, lengths, labels)):
            if L <= 0: continue
            # bande de fond légère
            self.ax.axvspan(t0, t0 + L, alpha=0.10)
            # marques 1/3 et 2/3 (cellules)
            self.ax.axvline(t0 + L / 3, linestyle="--", linewidth=1.0, alpha=0.35)
            self.ax.axvline(t0 + 2 * L / 3, linestyle="--", linewidth=1.0, alpha=0.35)
            # légende de segment
            self.ax.text(t0 + 0.01 * L, max(ys) * 1.02, lab, fontsize=9, va="bottom")

        # Axes, grille, légende
        self.ax.set_xlim(0, max(1e-6, T))
        ymax = max(h1, h2, h3) * 1.15 if math.isfinite(max(h1, h2, h3)) else 1.0
        self.ax.set_ylim(0, ymax)
        self.ax.grid(True, which="both", linestyle=":", linewidth=0.8, alpha=0.6)
        self.ax.set_xlabel("Temps (min)")
        self.ax.set_ylabel("Épaisseur h (cm)")
        self.ax.legend(loc="upper right")

        # Infos en haut
        self.info.config(text=f"f1={data.f1:.2f} Hz, f2={data.f2:.2f} Hz, f3={data.f3:.2f} Hz | "
                              f"h₁={h1:.2f} cm, h₂={h2:.2f} cm, h₃={h3:.2f} cm | "
                              f"T={T:.2f} min ({fmt_hms(T*60)})")

        self.canvas.draw()

    def _now_sim_minutes(self) -> float:
        """
        Temps global de la simulation (min), fidèle à l’app : somme des durées déjà passées
        + temps courant sur le segment actif. Lit seg_idx, seg_durations, seg_start.
        """
        app = self.app
        if not getattr(app, "animating", False) or getattr(app, "paused", False):
            # si non animée, on place le curseur au début (0)
            return 0.0
        i = int(getattr(app, "seg_idx", 0))
        elapsed = max(0.0, time.perf_counter() - getattr(app, "seg_start", time.perf_counter()))
        past = sum(float(s) for s in app.seg_durations[:i]) / 60.0
        return past + elapsed / 60.0

    def _start_cursor_loop(self):
        """Dessine/actualise une ligne verticale à la position temps réel."""
        def _tick():
            try:
                T = float(self.app.total_duration) / 60.0 if self.app.total_duration else None
                if not T or T <= 0:
                    # rien à faire si pas encore de calcul
                    return
                x = self._now_sim_minutes()
                if x < 0 or x > T:
                    x = max(0.0, min(T, x))
                # supprimer l'ancienne ligne
                if self.cursor_line:
                    try:
                        self.cursor_line.remove()
                    except Exception:
                        pass
                    self.cursor_line = None
                # dessiner la ligne
                self.cursor_line = self.ax.axvline(x, color="red", linestyle="-", linewidth=1.2, alpha=0.75)
                self.canvas.draw_idle()
            finally:
                self._after = self.after(int(TICK_SECONDS * 1000), _tick)

        _tick()

    def _on_close(self):
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        self.destroy()
