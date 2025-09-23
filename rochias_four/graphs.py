# rochias_four/graphs.py
from __future__ import annotations

import math
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

# -------- Profils de rampe par cellules (somme = 1.0) --------
CELL_PROFILE_2 = (0.10, 0.35, 0.55)   # répartition du delta (h2-h1) sur les 3 cellules du Tapis 2
CELL_PROFILE_3 = (0.20, 0.40, 0.40)   # répartition du delta (h3-h2) sur les 3 cellules du Tapis 3

# Mode d'affichage de la courbe: "ramps" (nouveau, recommandé) ou "steps" (ancien)
CURVE_MODE = "ramps"

def _piecewise_by_cells(t0: float, L: float, h_in: float, h_out: float, profile):
    """
    Construit les 4 points (x,y) aux frontières des 3 cellules d'un tapis:
      x = [t0, t0+L/3, t0+2L/3, t0+L]
      y = progression cumulée de h_in -> h_out selon 'profile' (normalisé).
    Si L <= 0 ou non-fini: plateau sur h_in.
    """
    if L <= 0.0 or not math.isfinite(L):
        return [t0, t0, t0, t0], [h_in, h_in, h_in, h_in]

    # normalisation du profil
    p = [float(pi) for pi in profile]
    s = sum(p) if sum(p) > 0 else 1.0
    p = [pi / s for pi in p]

    # abscisses aux frontières de cellules
    x0, x1, x2, x3 = t0, t0 + L/3.0, t0 + 2.0*L/3.0, t0 + L

    # ordonnées (cumul du delta)
    acc = 0.0
    y0 = h_in
    acc += p[0]; y1 = h_in + (h_out - h_in) * acc
    acc += p[1]; y2 = h_in + (h_out - h_in) * acc
    acc += p[2]; y3 = h_in + (h_out - h_in) * acc  # ≈ h_out

    return [x0, x1, x2, x3], [y0, y1, y2, y3]

from .calc_models import parts_reparties, total_minutes_synergy
from .calibration_overrides import get_current_anchor
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
    T_total_min: float


def _compute_last_or_recalc(app) -> GraphInputs:
    """
    Récupère les données du dernier calcul (si dispo) sinon recalcule depuis les entrées.
    Retourne fréquences, h0, durées par tapis (t*_i) et T_modèle.
    """
    # 1) lire f1,f2,f3 depuis last_calc si possible, sinon depuis les champs UI
    calc = getattr(app, "last_calc", None)
    if calc:
        f1 = float(calc["f1"]); f2 = float(calc["f2"]); f3 = float(calc["f3"])
        T_total = float(calc.get("T_total_min", calc.get("T_exp", 0.0)))
        t1s = float(calc.get("t1s_min", calc.get("t1_star", 0.0)))
        t2s = float(calc.get("t2s_min", calc.get("t2_star", 0.0)))
        t3s = float(calc.get("t3s_min", calc.get("t3_star", 0.0)))
    else:
        f1 = parse_hz(app.e1.get()); f2 = parse_hz(app.e2.get()); f3 = parse_hz(app.e3.get())
        T_total = total_minutes_synergy(f1, f2, f3)
        t1s, t2s, t3s = parts_reparties(T_total, f1, f2, f3)

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
        T_total_min=T_total
    )


def _heights_cm(f1: float, f2: float, f3: float, h0_cm: float):
    """
    Épaisseurs par tapis à partir des capacités u_i = f_i / K'_i (mêmes K' que l'app).
    """
    anch = get_current_anchor()
    u1, u2, u3 = (f1 / anch.K1), (f2 / anch.K2), (f3 / anch.K3)
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
        bg_color = getattr(app.theme, "colors", {}).get("bg", getattr(app, "BG", "#ffffff"))
        self.configure(bg=bg_color)
        self._after = None

        # -- panneau haut (infos)
        top = ttk.Frame(self); top.pack(fill="x", padx=10, pady=6)
        ttk.Label(top, text="Épaisseur de couche (cm) vs Temps (min) — partitionné par tapis").pack(side="left")
        self.info = ttk.Label(top, text="")
        self.info.pack(side="right")

        # -- figure matplotlib
        fig = Figure(figsize=(8.8, 4.8), dpi=100)
        self.fig = fig
        self.ax = fig.add_subplot(111)
        if hasattr(self.app, "theme"):
            try:
                self.app.theme.apply_matplotlib(fig)
            except Exception:
                pass
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
        # Récupère les données calculées (on ne touche à aucun calcul existant)
        data = _compute_last_or_recalc(self.app)
        h1, h2, h3 = _heights_cm(data.f1, data.f2, data.f3, data.h0_cm)

        # Durées par tapis (minutes) + total
        t1 = data.t1s_min
        t2 = data.t2s_min
        t3 = data.t3s_min
        T  = data.T_total_min

        self.ax.clear()
        if hasattr(self.app, "theme"):
            try:
                self.app.theme.apply_matplotlib(self.ax)
            except Exception:
                pass

        # --- Fond : zones par tapis + traits 1/3 et 2/3 (repères de cellules) ---
        starts = [0.0, t1, t1 + t2]
        lengths = [t1, t2, t3]
        labels  = ["Tapis 1", "Tapis 2", "Tapis 3"]
        ymax_rough = max(h1, h2, h3)
        for t0, L, lab in zip(starts, lengths, labels):
            if L <= 0:
                continue
            self.ax.axvspan(t0, t0 + L, alpha=0.10)
            self.ax.axvline(t0 + L/3.0, linestyle="--", linewidth=1.0, alpha=0.35)
            self.ax.axvline(t0 + 2.0*L/3.0, linestyle="--", linewidth=1.0, alpha=0.35)
            self.ax.text(t0 + 0.01*max(L, 1e-6),
                         ymax_rough * 1.02 if math.isfinite(ymax_rough) else 1.0,
                         lab, fontsize=9, va="bottom")

        # --- Courbe h(t) ---
        if CURVE_MODE == "steps":
            # Ancien rendu : paliers instantanés aux changements de tapis
            xs = [0.0, t1, t1 + t2, T]
            ys = [h1,  h2,  h3,     h3]
            self.ax.step(xs, ys, where="post", linewidth=2.0, label="h(t) calculée")
        else:
            # Nouveau rendu : rampes par cellules (aucun changement des valeurs calculées)
            xs, ys = [0.0], [h1]

            # Tapis 1 : plateau (on laisse constant à h1 sur T1)
            xs += [t1/3.0, 2.0*t1/3.0, t1]
            ys += [h1,     h1,         h1]

            # Tapis 2 : rampe h1 -> h2, distribuée sur les 3 cellules
            x2, y2 = _piecewise_by_cells(t1, t2, h1, h2, CELL_PROFILE_2)
            xs += x2[1:]  # évite le doublon au point t1
            ys += y2[1:]

            # Tapis 3 : rampe h2 -> h3, distribuée sur les 3 cellules
            x3, y3 = _piecewise_by_cells(t1 + t2, t3, h2, h3, CELL_PROFILE_3)
            xs += x3[1:]
            ys += y3[1:]

            self.ax.plot(xs, ys, linewidth=2.0, label="h(t) calculée")

        # --- Axes, grille, légendes ---
        self.ax.set_xlim(0.0, max(1e-6, T))
        ymax = max(h1, h2, h3) * 1.15 if math.isfinite(max(h1, h2, h3)) else 1.0
        self.ax.set_ylim(0.0, ymax)
        self.ax.grid(True, which="both", linestyle=":", linewidth=0.8, alpha=0.6)
        self.ax.set_xlabel("Temps (min)")
        self.ax.set_ylabel("Épaisseur h (cm)")
        self.ax.legend(loc="upper right")

        # Bandeau d'info (inchangé)
        self.info.config(text=(
            f"f1={data.f1:.2f} Hz, f2={data.f2:.2f} Hz, f3={data.f3:.2f} Hz | "
            f"h₁={h1:.2f} cm, h₂={h2:.2f} cm, h₃={h3:.2f} cm | "
            f"T={T:.2f} min ({fmt_hms(T*60)})"
        ))
        self.canvas.draw()

    def redraw_with_theme(self, theme):
        try:
            self.configure(bg=theme.colors.get("bg", "#111111"))
        except Exception:
            pass
        try:
            theme.apply_matplotlib(self.fig)
        except Exception:
            pass
        self._plot_static()
        self.canvas.draw_idle()

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
        try:
            if hasattr(self.app, "graph_window") and self.app.graph_window is self:
                self.app.graph_window = None
        except Exception:
            pass
        self.destroy()
