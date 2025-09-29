from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .theming import theme


class ProductCurveWidget:
    """
    Affiche la 'couche produit' (épaisseur [cm] en fonction de la longueur du four [m]).
    - Courbe en escaliers (épaisseur pièce par cellule).
    - Remplissage sous la courbe.
    - Actualisation fluide via .update(head_x, thickness_by_cell).
    """

    def __init__(self, parent, total_length_m: float, y_max_cm: float = 10.0):
        self.total_length_m = float(total_length_m)
        self.y_max_cm = float(y_max_cm)

        self.fig = Figure(figsize=(7.5, 1.6), dpi=100)
        self.ax = self.fig.add_subplot(111)

        t = theme()
        self.ax.set_facecolor(t.surface)
        for s in self.ax.spines.values():
            s.set_color(t.stroke)
        self.ax.grid(True, color=t.grid, alpha=0.35)
        self.ax.set_xlim(0.0, self.total_length_m)
        self.ax.set_ylim(0.0, self.y_max_cm)
        self.ax.set_xlabel("")
        self.ax.set_ylabel("")
        self.ax.tick_params(axis="x", labelsize=8)
        self.ax.tick_params(axis="y", labelsize=8)

        (self._line,) = self.ax.plot([], [], lw=2, color=t.curve, drawstyle="steps-post", zorder=3)
        self._fill = None

        self.ax._product_line = self._line
        self.ax._product_fill = None

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.widget = self.canvas.get_tk_widget()

    def pack(self, **kwargs):  # pragma: no cover - wrapper Tk
        self.widget.pack(**kwargs)

    def grid(self, **grid_kw):  # pragma: no cover
        self.widget.grid(**grid_kw)

    def place(self, **kwargs):  # pragma: no cover
        self.widget.place(**kwargs)

    def set_total_length(self, total_length_m: float):
        self.total_length_m = max(0.0, float(total_length_m))
        upper = self.total_length_m if self.total_length_m > 0 else 1.0
        self.ax.set_xlim(0.0, upper)
        self.canvas.draw_idle()

    def _build_profile(self, head_x: float, cell_lengths_m, thickness_cm):
        head_x = float(max(0.0, min(head_x, self.total_length_m)))
        x, y = [0.0], [0.0]
        pos = 0.0

        for L, h in zip(cell_lengths_m, thickness_cm):
            L = float(L)
            h = float(h)
            start, end = pos, pos + L
            if head_x <= start:
                break
            seg_end = min(head_x, end)
            x.extend([start, seg_end])
            y.extend([h, h])
            pos = end
            if head_x <= seg_end:
                break

        x.append(x[-1])
        y.append(0.0)

        return np.array(x), np.array(y)

    def update(self, head_x: float, cell_lengths_m, thickness_cm, y_max_cm: float | None = None):
        if y_max_cm is not None and y_max_cm > 0:
            self.y_max_cm = y_max_cm
            self.ax.set_ylim(0.0, self.y_max_cm)

        x, y = self._build_profile(head_x, cell_lengths_m, thickness_cm)

        self._line.set_data(x, y)

        if self._fill is not None:
            try:
                self._fill.remove()
            except Exception:
                pass
        t = theme()
        self._fill = self.ax.fill_between(
            x,
            y,
            0.0,
            step="post",
            color=t.curve_fill,
            alpha=t.curve_fill_alpha,
            zorder=2,
        )
        self.ax._product_fill = self._fill

        self.canvas.draw_idle()
