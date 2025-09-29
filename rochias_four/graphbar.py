"""Matplotlib-based belt graph displaying layer thickness over time."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .config import DISPLAY_Y_MAX_CM
from .geometry import TapisGeometry
from .timeline import FeedTimeline


@dataclass
class _Style:
    line_color: str
    face_color: str
    grid_color: str
    text_color: str
    fill_color: str
    fill_alpha: float


class GraphBar:
    """Embeds a Matplotlib figure that renders h(x, t) for a belt."""

    def __init__(
        self,
        master,
        *,
        y_max: float = DISPLAY_Y_MAX_CM,
        height_px: int = 110,
        line_color: str = "#15803d",
        face_color: str = "#ffffff",
        grid_color: str = "#d4d4d8",
        text_color: str = "#52525b",
        fill_color: str | None = None,
        fill_alpha: float = 0.25,
    ) -> None:
        fill = fill_color if fill_color is not None else line_color
        self._style = _Style(line_color, face_color, grid_color, text_color, fill, float(fill_alpha))
        self._y_max = float(y_max)
        figsize = (6.4, max(1.0, height_px / 96.0))
        self.figure = Figure(figsize=figsize, dpi=96)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=master)
        self.widget = self.canvas.get_tk_widget()
        self._geometry: Optional[TapisGeometry] = None
        self._offset_min: float = 0.0
        self._last_y: List[float] = []
        self._ticks = []
        self._fill = None
        self._setup_axes(self._y_max)

    def _setup_axes(self, y_max: float) -> None:
        self.ax.clear()
        self.ax.set_xlim(0.0, 1.0)
        self.ax.set_ylim(0.0, float(y_max))
        self.ax.set_facecolor(self._style.face_color)
        for spine in self.ax.spines.values():
            spine.set_visible(False)
        self.ax.grid(True, which="major", axis="y", color=self._style.grid_color, alpha=0.4, linewidth=0.8)
        self.ax.set_xticks([])
        self.ax.set_yticks([0, float(y_max) / 2.0, float(y_max)])
        self.ax.tick_params(axis="y", colors=self._style.text_color, labelsize=8)
        self.ax.margins(x=0.0, y=0.05)
        for line in self._ticks:
            line.remove()
        self._ticks.clear()
        x_values = self._geometry.samples_x if self._geometry else []
        if not self._last_y:
            self._last_y = [0.0 for _ in x_values]
        self._line, = self.ax.plot(
            x_values,
            self._last_y,
            linewidth=2.0,
            color=self._style.line_color,
            solid_joinstyle="round",
            zorder=3,
        )
        if self._fill is not None:
            try:
                self._fill.remove()
            except Exception:
                pass
        self._fill = None
        if x_values:
            self._fill = self.ax.fill_between(
                x_values,
                self._last_y,
                0.0,
                color=self._style.fill_color,
                alpha=self._style.fill_alpha,
                zorder=2,
            )
        self.ax._product_line = self._line
        self.ax._product_fill = self._fill
        if self._geometry is not None:
            for pos in self._geometry.ticks_x:
                tick = self.ax.axvline(pos, color=self._style.grid_color, linewidth=1.0, alpha=0.4)
                self._ticks.append(tick)
        self.canvas.draw_idle()

    def pack(self, **kwargs):  # pragma: no cover - thin wrapper for Tk geometry
        self.widget.pack(**kwargs)

    def grid(self, **kwargs):  # pragma: no cover
        self.widget.grid(**kwargs)

    def place(self, **kwargs):  # pragma: no cover
        self.widget.place(**kwargs)

    def set_geometry(self, geometry: Optional[TapisGeometry], offset_min: float) -> None:
        self._geometry = geometry
        self._offset_min = float(offset_min)
        if geometry is None:
            self._last_y = []
            self._setup_axes(self._y_max)
            return
        self._last_y = [0.0 for _ in geometry.samples_x]
        self._setup_axes(self._y_max)

    def clear(self) -> None:
        self.set_geometry(None, 0.0)

    def update(self, t_now_min: float, timeline: FeedTimeline) -> None:
        geometry = self._geometry
        if geometry is None:
            return
        alphas = [timeline.alpha_at(t_now_min - (self._offset_min + tau)) for tau in geometry.tau_min]
        self._last_y = [max(0.0, min(self._y_max, alpha * target)) for alpha, target in zip(alphas, geometry.h_target_cm)]
        self._line.set_data(geometry.samples_x, self._last_y)
        if self._fill is not None:
            try:
                self._fill.remove()
            except Exception:
                pass
        if geometry.samples_x:
            self._fill = self.ax.fill_between(
                geometry.samples_x,
                self._last_y,
                0.0,
                color=self._style.fill_color,
                alpha=self._style.fill_alpha,
                zorder=2,
            )
        else:
            self._fill = None
        self.ax._product_fill = self._fill
        self.canvas.draw_idle()

    def apply_theme(
        self,
        line_color: str,
        face_color: str,
        grid_color: str,
        text_color: str,
        fill_color: str,
        fill_alpha: float,
        y_max: float,
    ) -> None:
        self._style = _Style(line_color, face_color, grid_color, text_color, fill_color, float(fill_alpha))
        self._y_max = float(y_max)
        self._setup_axes(self._y_max)


__all__ = ["GraphBar"]
