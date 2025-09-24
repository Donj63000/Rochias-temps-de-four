# rochias_four/graphs.py
from __future__ import annotations

import math
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from .maintenance_ref import compute_times_maintenance
from .calibration_overrides import get_current_anchor
from .utils import fmt_hms
from .config import TICK_SECONDS

CELL_PROFILE_2 = (0.10, 0.35, 0.55)
CELL_PROFILE_3 = (0.20, 0.40, 0.40)
CURVE_MODE = "ramps"


def _piecewise_by_cells(t0: float, L: float, y_in: float, y_out: float, profile: tuple[float, float, float]):
    if not (L > 0) or not math.isfinite(L):
        return [t0, t0, t0, t0], [y_in, y_in, y_in, y_in]
    p = [float(pi) for pi in profile]
    s = sum(p) if sum(p) > 0 else 1.0
    p = [pi / s for pi in p]
    x0, x1, x2, x3 = t0, t0 + L / 3.0, t0 + 2.0 * L / 3.0, t0 + L
    acc = 0.0
    y0 = y_in
    acc += p[0]; y1 = y_in + (y_out - y_in) * acc
    acc += p[1]; y2 = y_in + (y_out - y_in) * acc
    acc += p[2]; y3 = y_in + (y_out - y_in) * acc
    return [x0, x1, x2, x3], [y0, y1, y2, y3]


@dataclass
class GraphInputs:
    f1_hz: float
    f2_hz: float
    f3_hz: float
    h0_cm: float
    t1_min: float
    t2_min: float
    t3_min: float
    total_min: float


def _compute_inputs(app) -> GraphInputs:
    calc = getattr(app, "last_calc", None)
    if calc and str(calc.get("calc_mode", "")) == "maintenance":
        f1 = float(calc.get("f1", 0.0))
        f2 = float(calc.get("f2", 0.0))
        f3 = float(calc.get("f3", 0.0))
        t1 = float(calc.get("t1s_min", calc.get("t1_star", 0.0)))
        t2 = float(calc.get("t2s_min", calc.get("t2_star", 0.0)))
        t3 = float(calc.get("t3s_min", calc.get("t3_star", 0.0)))
        T = float(calc.get("T_total_min", calc.get("T_exp", 0.0)))
    else:
        try:
            raw1 = getattr(app, "e1").get()
            raw2 = getattr(app, "e2").get()
            raw3 = getattr(app, "e3").get()
            f1_in = float((raw1 or "").replace(",", "."))
            f2_in = float((raw2 or "").replace(",", "."))
            f3_in = float((raw3 or "").replace(",", "."))
        except Exception:
            f1_in = f2_in = f3_in = 0.0
        res = compute_times_maintenance(f1_in, f2_in, f3_in, units="auto")
        f1, f2, f3 = res.f1_hz, res.f2_hz, res.f3_hz
        t1, t2, t3 = res.t1_min, res.t2_min, res.t3_min
        T = res.total_min
    h0 = 2.0
    h_widget = getattr(app, "h0", None)
    if h_widget is not None:
        try:
            h0 = float(h_widget.get().replace(",", "."))
            if not (h0 > 0):
                h0 = 2.0
        except Exception:
            h0 = 2.0
    return GraphInputs(f1_hz=f1, f2_hz=f2, f3_hz=f3, h0_cm=h0, t1_min=t1, t2_min=t2, t3_min=t3, total_min=T)


def _heights_cm(f1: float, f2: float, f3: float, h0_cm: float):
    anch = get_current_anchor()
    u1 = f1 / anch.K1 if anch.K1 else float("inf")
    u2 = f2 / anch.K2 if anch.K2 else float("inf")
    u3 = f3 / anch.K3 if anch.K3 else float("inf")
    h1 = h0_cm
    h2 = h0_cm * (u1 / u2) if u2 > 0 else float("inf")
    h3 = h0_cm * (u1 / u3) if u3 > 0 else float("inf")
    return h1, h2, h3


class GraphWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Graphiques — Méthode tableur (L/v)")
        self.geometry("980x560")
        bg = getattr(getattr(app, "theme", None), "colors", {}).get("bg", getattr(app, "BG", "#ffffff"))
        self.configure(bg=bg)
        self._after = None
        self.mode = "maintenance"

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=6)
        ttk.Label(top, text="Épaisseur de couche (cm) vs Temps (min) — méthode tableur (L/v)").pack(side="left")
        self.info = ttk.Label(top, text="")
        self.info.pack(side="right")

        self.fig = Figure(figsize=(8.8, 4.8), dpi=100)
        self.ax = self.fig.add_subplot(111)
        if hasattr(self.app, "theme"):
            try:
                self.app.theme.apply_matplotlib(self.fig)
            except Exception:
                pass
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 4))
        NavigationToolbar2Tk(self.canvas, self).update()

        self.cursor_line = None
        self._plot_static()
        self._start_cursor_loop()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _plot_static(self):
        data = _compute_inputs(self.app)
        h1, h2, h3 = _heights_cm(data.f1_hz, data.f2_hz, data.f3_hz, data.h0_cm)
        t1, t2, t3 = max(0.0, data.t1_min), max(0.0, data.t2_min), max(0.0, data.t3_min)
        T = max(0.0, data.total_min) or (t1 + t2 + t3)
        self.ax.clear()
        if hasattr(self.app, "theme"):
            try:
                self.app.theme.apply_matplotlib(self.ax)
            except Exception:
                pass

        starts = [0.0, t1, t1 + t2]
        lengths = [t1, t2, t3]
        labels = ["Tapis 1", "Tapis 2", "Tapis 3"]
        y_max_ref = max(v for v in (h1, h2, h3) if math.isfinite(v)) if any(math.isfinite(v) for v in (h1, h2, h3)) else 1.0
        for t0, L, lab in zip(starts, lengths, labels):
            if L <= 0:
                continue
            self.ax.axvspan(t0, t0 + L, alpha=0.10)
            self.ax.axvline(t0 + L / 3.0, linestyle="--", linewidth=1.0, alpha=0.35)
            self.ax.axvline(t0 + 2.0 * L / 3.0, linestyle="--", linewidth=1.0, alpha=0.35)
            self.ax.text(t0 + 0.01 * max(L, 1e-6), y_max_ref * 1.02, lab, fontsize=9, va="bottom")

        if CURVE_MODE == "steps":
            xs = [0.0, t1, t1 + t2, T]
            ys = [h1, h2, h3, h3]
            self.ax.step(xs, ys, where="post", linewidth=2.0, label="h(t)")
        else:
            xs, ys = [0.0], [h1]
            xs += [t1 / 3.0, 2.0 * t1 / 3.0, t1]; ys += [h1, h1, h1]
            x2, y2 = _piecewise_by_cells(t1, t2, h1, h2, CELL_PROFILE_2)
            xs += x2[1:]; ys += y2[1:]
            x3, y3 = _piecewise_by_cells(t1 + t2, t3, h2, h3, CELL_PROFILE_3)
            xs += x3[1:]; ys += y3[1:]
            self.ax.plot(xs, ys, linewidth=2.0, label="h(t)")

        self.ax.set_xlim(0.0, max(T, 1e-6))
        y_max = max(v for v in (h1, h2, h3) if math.isfinite(v)) if any(math.isfinite(v) for v in (h1, h2, h3)) else 1.0
        self.ax.set_ylim(0.0, y_max * 1.15)
        self.ax.grid(True, which="both", linestyle=":", linewidth=0.8, alpha=0.6)
        self.ax.set_xlabel("Temps (min)")
        self.ax.set_ylabel("Épaisseur h (cm)")
        self.ax.legend(loc="upper right")

        self.info.config(text=(
            f"f1={data.f1_hz:.2f} Hz, f2={data.f2_hz:.2f} Hz, f3={data.f3_hz:.2f} Hz | "
            f"h₁={h1:.2f} cm, h₂={h2:.2f} cm, h₃={h3:.2f} cm | "
            f"T={T:.2f} min ({fmt_hms(T * 60)})"
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
        self.mode = "maintenance"
        self._plot_static()
        self.canvas.draw_idle()

    def _now_sim_minutes(self) -> float:
        app = self.app
        if not getattr(app, "animating", False) or getattr(app, "paused", False):
            return 0.0
        i = int(getattr(app, "seg_idx", 0))
        elapsed = max(0.0, time.perf_counter() - getattr(app, "seg_start", time.perf_counter()))
        past = sum(float(s) for s in getattr(app, "seg_durations", [])[:i]) / 60.0
        return past + elapsed / 60.0

    def _start_cursor_loop(self):
        def _tick():
            try:
                T = float(getattr(self.app, "total_duration", 0.0)) / 60.0 if getattr(self.app, "total_duration", 0.0) else None
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
