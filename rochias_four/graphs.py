from __future__ import annotations

import math
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

# Répartition du delta d'épaisseur par cellules (somme = 1.0)
CELL_PROFILE_2 = (0.10, 0.35, 0.55)   # rampe h1→h2 sur Tapis 2
CELL_PROFILE_3 = (0.20, 0.40, 0.40)   # rampe h2→h3 sur Tapis 3

CURVE_MODE = "ramps"  # "ramps" recommandé ; "steps" = ancienne courbe en paliers


def _piecewise_by_cells(t0: float, L: float, h_in: float, h_out: float, profile):
    if L <= 0.0 or not math.isfinite(L):
        return [t0, t0, t0, t0], [h_in, h_in, h_in, h_in]
    p = [float(pi) for pi in profile]
    s = sum(p) if sum(p) > 0 else 1.0
    p = [pi / s for pi in p]
    x0, x1, x2, x3 = t0, t0 + L/3.0, t0 + 2.0*L/3.0, t0 + L
    acc = 0.0
    y0 = h_in
    acc += p[0]; y1 = h_in + (h_out - h_in) * acc
    acc += p[1]; y2 = h_in + (h_out - h_in) * acc
    acc += p[2]; y3 = h_in + (h_out - h_in) * acc
    return [x0, x1, x2, x3], [y0, y1, y2, y3]


from .maintenance_ref import compute_times_maintenance
from .calibration_overrides import get_current_anchor
from .config import TICK_SECONDS
from .utils import fmt_hms


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
    calc = getattr(app, "last_calc", None)
    if calc:
        f1 = float(calc["f1"])
        f2 = float(calc["f2"])
        f3 = float(calc["f3"])
        T_total = float(calc.get("T_total_min", 0.0))
        t1s = float(calc.get("parts_reparties", (0.0, 0.0, 0.0))[0])
        t2s = float(calc.get("parts_reparties", (0.0, 0.0, 0.0))[1])
        t3s = float(calc.get("parts_reparties", (0.0, 0.0, 0.0))[2])
    else:
        # Fallback cohérent L/v : on recalcule avec compute_times_maintenance(units="auto")
        try:
            v1 = float((app.e1.get() or "0").replace(",", "."))
            v2 = float((app.e2.get() or "0").replace(",", "."))
            v3 = float((app.e3.get() or "0").replace(",", "."))
        except Exception:
            v1 = v2 = v3 = 0.0
        res = compute_times_maintenance(v1, v2, v3, units="auto")
        f1, f2, f3 = float(res.f1_hz), float(res.f2_hz), float(res.f3_hz)
        t1s, t2s, t3s = float(res.t1_min), float(res.t2_min), float(res.t3_min)
        T_total = float(res.total_min)

    h0_cm = 2.0
    h_widget = getattr(app, "h0", None)
    if h_widget is not None:
        try:
            h0_cm = float((h_widget.get() or "2").replace(",", "."))
            if not (h0_cm > 0):
                h0_cm = 2.0
        except Exception:
            h0_cm = 2.0

    return GraphInputs(
        f1=f1, f2=f2, f3=f3, h0_cm=h0_cm,
        t1s_min=t1s, t2s_min=t2s, t3s_min=t3s,
        T_total_min=T_total
    )


def _heights_cm(f1: float, f2: float, f3: float, h0_cm: float):
    anch = get_current_anchor()
    u1, u2, u3 = (f1 / anch.K1), (f2 / anch.K2), (f3 / anch.K3)
    h1 = h0_cm
    h2 = h0_cm * (u1 / u2) if u2 > 0 else float("inf")
    h3 = h0_cm * (u1 / u3) if u3 > 0 else float("inf")
    return h1, h2, h3


class GraphWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Graphiques — Épaisseur vs Temps (h(t))")
        self.geometry("980x560")
        try:
            bg_color = app.theme.colors.get("bg", "#ffffff")
        except Exception:
            bg_color = "#ffffff"
        self.configure(bg=bg_color)
        self._after = None

        top = ttk.Frame(self); top.pack(fill="x", padx=10, pady=6)
        ttk.Label(top, text="Épaisseur de couche (cm) vs Temps (min) — partitionné par tapis").pack(side="left")
        self.info = ttk.Label(top, text="")
        self.info.pack(side="right")

        fig = Figure(figsize=(8.8, 4.8), dpi=100)
        self.fig = fig
        self.ax = fig.add_subplot(111)
        try:
            app.theme.apply_matplotlib(fig)
        except Exception:
            pass
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 4))
        NavigationToolbar2Tk(self.canvas, self).update()

        self.cursor_line = None
        self._plot_static()
        self._start_cursor_loop()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _plot_static(self):
        data = _compute_last_or_recalc(self.app)
        h1, h2, h3 = _heights_cm(data.f1, data.f2, data.f3, data.h0_cm)
        t1, t2, t3 = data.t1s_min, data.t2s_min, data.t3s_min
        T = data.T_total_min

        self.ax.clear()
        try:
            self.app.theme.apply_matplotlib(self.ax)
        except Exception:
            pass

        starts = [0.0, t1, t1 + t2]
        lengths = [t1, t2, t3]
        labels = ["Tapis 1", "Tapis 2", "Tapis 3"]
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

        if CURVE_MODE == "steps":
            xs = [0.0, t1, t1 + t2, T]
            ys = [h1, h2, h3, h3]
            self.ax.step(xs, ys, where="post", linewidth=2.0, label="h(t) calculée")
        else:
            xs, ys = [0.0], [h1]
            xs += [t1/3.0, 2.0*t1/3.0, t1]
            ys += [h1, h1, h1]
            x2, y2 = _piecewise_by_cells(t1, t2, h1, h2, CELL_PROFILE_2)
            xs += x2[1:]; ys += y2[1:]
            x3, y3 = _piecewise_by_cells(t1 + t2, t3, h2, h3, CELL_PROFILE_3)
            xs += x3[1:]; ys += y3[1:]
            self.ax.plot(xs, ys, linewidth=2.0, label="h(t) calculée")

        self.ax.set_xlim(0.0, max(1e-6, T))
        ymax = max(h1, h2, h3) * 1.15 if math.isfinite(max(h1, h2, h3)) else 1.0
        self.ax.set_ylim(0.0, ymax)
        self.ax.grid(True, which="both", linestyle=":", linewidth=0.8, alpha=0.6)
        self.ax.set_xlabel("Temps (min)")
        self.ax.set_ylabel("Épaisseur h (cm)")
        self.ax.legend(loc="upper right")

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

    def redraw_with_mode(self, mode: str):
        self._plot_static()
        self.canvas.draw_idle()

    def _now_sim_minutes(self) -> float:
        app = self.app
        if not getattr(app, "animating", False) or getattr(app, "paused", False):
            return 0.0
        i = int(getattr(app, "seg_idx", 0))
        elapsed = max(0.0, time.perf_counter() - getattr(app, "seg_start", time.perf_counter()))
        past = sum(float(s) for s in app.seg_durations[:i]) / 60.0
        return past + elapsed / 60.0

    def _start_cursor_loop(self):
        def _tick():
            try:
                T = float(self.app.total_duration) / 60.0 if self.app.total_duration else None
                if not T or T <= 0:
                    return
                x = self._now_sim_minutes()
                if x < 0 or x > T:
                    x = max(0.0, min(T, x))
                if self.cursor_line:
                    try:
                        self.cursor_line.remove()
                    except Exception:
                        pass
                    self.cursor_line = None
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
