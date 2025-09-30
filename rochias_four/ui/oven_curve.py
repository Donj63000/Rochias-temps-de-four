from __future__ import annotations

import bisect
from typing import Iterable, List, Sequence

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .theming import theme


class OvenCurveWidget:
    """Widget matplotlib affichant la courbe d'occupation du four.

    La géométrie (longueur/épaisseur par cellule) est fournie via :meth:`set_geometry`.
    La courbe garde en mémoire des segments occupés (liste d'intervalles [x₀, x₁]) et
    applique des mises à jour incrémentales sur chaque tick : translation suivant les
    vitesses réelles, ajout d'un tronçon d'entrée lorsque l'alimentation est active,
    suppression automatique des morceaux sortis du four et fusion des segments contigus.
    """

    def __init__(self, parent, y_max_cm: float = 10.0):
        self.y_max_cm = float(y_max_cm)
        self.total_length = 0.0
        self.sections: List[dict] = []
        self._cell_starts: List[float] = []
        self._cell_ends: List[float] = []
        self._cell_thickness: List[float] = []
        self._cell_belts: List[int] = []
        self.segments: List[dict] = []
        self.belt_speeds: dict[int, float] = {}
        self.feeding = False
        self._epsilon = 1e-6

        self.fig = Figure(figsize=(7.5, 1.6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self._configure_axes()

        t = theme()
        (self._line,) = self.ax.plot([], [], lw=2, color=t.curve, drawstyle="steps-post", zorder=3)
        self._fills: List = []
        self.ax._product_line = self._line
        self.ax._product_fill = None

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.widget = self.canvas.get_tk_widget()

        self.set_geometry([])
        self.reset_segments(draw=False)

    # Tk proxy helpers -------------------------------------------------
    def pack(self, **kwargs):  # pragma: no cover - Tk binding
        self.widget.pack(**kwargs)

    def grid(self, **grid_kw):  # pragma: no cover
        self.widget.grid(**grid_kw)

    def place(self, **kwargs):  # pragma: no cover
        self.widget.place(**kwargs)

    # Configuration ----------------------------------------------------
    def _configure_axes(self) -> None:
        t = theme()
        self.ax.set_facecolor(t.surface)
        for spine in self.ax.spines.values():
            spine.set_color(t.stroke)
        self.ax.grid(True, color=t.grid, alpha=0.35)
        self.ax.set_xlim(0.0, 1.0)
        self.ax.set_ylim(0.0, self.y_max_cm)
        self.ax.set_xlabel("")
        self.ax.set_ylabel("")
        self.ax.tick_params(axis="x", labelsize=8)
        self.ax.tick_params(axis="y", labelsize=8)

    def set_y_max(self, y_max_cm: float) -> None:
        if y_max_cm and y_max_cm > 0:
            self.y_max_cm = float(y_max_cm)
            self.ax.set_ylim(0.0, self.y_max_cm)
            self.canvas.draw_idle()

    def set_geometry(self, sections: Sequence[dict] | None) -> None:
        self.sections = []
        self._cell_starts = []
        self._cell_ends = []
        self._cell_thickness = []
        self._cell_belts = []
        self.total_length = 0.0
        if sections:
            pos = 0.0
            for raw in sections:
                try:
                    length = max(0.0, float(raw.get("length", 0.0)))
                    thickness = float(raw.get("thickness", 0.0))
                    belt = int(raw.get("belt_index", 0))
                except Exception:
                    continue
                if length <= 0.0:
                    continue
                start = pos
                end = pos + length
                self.sections.append({
                    "start": start,
                    "end": end,
                    "thickness": thickness,
                    "belt": belt,
                })
                self._cell_starts.append(start)
                self._cell_ends.append(end)
                self._cell_thickness.append(thickness)
                self._cell_belts.append(belt)
                pos = end
            self.total_length = pos
        upper = self.total_length if self.total_length > 0 else 1.0
        self.ax.set_xlim(0.0, upper)
        self.reset_segments(draw=False)
        self._redraw()

    def set_speeds(self, speeds_mps: Sequence[float]) -> None:
        self.belt_speeds = {idx: max(0.0, float(val)) for idx, val in enumerate(speeds_mps or [])}

    def set_feeding(self, feeding: bool) -> None:
        self.feeding = bool(feeding)

    def reset_segments(self, *, draw: bool = True) -> None:
        self.segments = []
        if draw:
            self._redraw()

    # Simulation -------------------------------------------------------
    def tick(self, delta_seconds: float) -> None:
        if not self.sections or self.total_length <= 0.0:
            return
        dt = float(delta_seconds)
        if dt <= 0.0:
            return
        moved: List[dict] = []
        for seg in self.segments:
            start = seg["start"]
            end = seg["end"]
            start_speed = self._speed_at(start)
            end_speed = self._speed_at(end)
            new_start = start + start_speed * dt
            new_end = end + end_speed * dt
            if new_end <= 0.0 or new_start >= self.total_length:
                continue
            moved.append({
                "start": max(0.0, new_start),
                "end": min(self.total_length, new_end),
            })
        if self.feeding:
            entry_speed = self._speed_at(0.0)
            if entry_speed > 0.0:
                delta = entry_speed * dt
                if delta > 0.0:
                    moved.append({"start": 0.0, "end": min(self.total_length, delta)})
        self.segments = self._normalize_segments(moved)
        self._redraw()

    # Helpers ----------------------------------------------------------
    def _speed_at(self, position: float) -> float:
        if not self.sections:
            return 0.0
        if position <= 0.0:
            idx = 0
        elif position >= self.total_length:
            idx = len(self.sections) - 1
        else:
            idx = bisect.bisect_right(self._cell_starts, position) - 1
            if idx < 0:
                idx = 0
        belt = self._cell_belts[idx] if 0 <= idx < len(self._cell_belts) else 0
        return float(self.belt_speeds.get(belt, 0.0))

    def _normalize_segments(self, segments: Iterable[dict]) -> List[dict]:
        tol = self._epsilon
        cleaned: List[dict] = []
        for seg in segments:
            try:
                start = float(seg["start"])
                end = float(seg["end"])
            except Exception:
                continue
            start = max(0.0, min(start, self.total_length))
            end = max(0.0, min(end, self.total_length))
            if end - start <= tol:
                continue
            cleaned.append({"start": start, "end": end})
        if not cleaned:
            return []
        cleaned.sort(key=lambda item: item["start"])
        merged: List[dict] = []
        for seg in cleaned:
            if not merged:
                merged.append(seg)
                continue
            last = merged[-1]
            if seg["start"] <= last["end"] + tol:
                last["end"] = max(last["end"], seg["end"])
            else:
                merged.append(seg)
        normalized: List[dict] = []
        for seg in merged:
            start = seg["start"]
            end = seg["end"]
            idx = self._cell_index(start)
            while start < end - tol and idx < len(self.sections):
                cell = self.sections[idx]
                cell_end = cell["end"]
                part_end = min(end, cell_end)
                normalized.append({
                    "start": start,
                    "end": part_end,
                    "cell": idx,
                })
                start = part_end
                if start >= end - tol:
                    break
                idx += 1
        if not normalized:
            return []
        normalized.sort(key=lambda item: (item["cell"], item["start"]))
        final: List[dict] = []
        for seg in normalized:
            if not final:
                final.append(seg)
                continue
            last = final[-1]
            if seg["cell"] == last["cell"] and seg["start"] <= last["end"] + tol:
                last["end"] = max(last["end"], seg["end"])
            else:
                final.append(seg)
        final.sort(key=lambda item: item["start"])
        return final

    def _cell_index(self, position: float) -> int:
        if not self.sections:
            return 0
        if position <= 0.0:
            return 0
        if position >= self.total_length:
            return len(self.sections) - 1
        idx = bisect.bisect_right(self._cell_starts, position) - 1
        if idx < 0:
            return 0
        return min(idx, len(self.sections) - 1)

    def _segment_step(self, segment: dict) -> tuple[list[float], list[float]]:
        tol = self._epsilon
        start = segment["start"]
        end = segment["end"]
        idx = segment.get("cell", self._cell_index(start))
        x: List[float] = [start]
        y: List[float] = [0.0]
        current = start
        while current < end - tol and idx < len(self.sections):
            cell = self.sections[idx]
            cell_end = min(end, cell["end"])
            height = float(cell["thickness"])
            x.extend([current, cell_end])
            y.extend([height, height])
            current = cell_end
            if current >= end - tol:
                break
            idx += 1
        x.append(end)
        y.append(0.0)
        return x, y

    def _build_plot_arrays(self) -> tuple[list[float], list[float]]:
        if not self.segments:
            return [0.0, 0.0], [0.0, 0.0]
        xs: List[float] = []
        ys: List[float] = []
        tol = self._epsilon
        for seg in self.segments:
            seg_x, seg_y = self._segment_step(seg)
            if not seg_x:
                continue
            if xs and abs(seg_x[0] - xs[-1]) <= tol and abs(ys[-1]) <= tol:
                seg_x = seg_x[1:]
                seg_y = seg_y[1:]
            xs.extend(seg_x)
            ys.extend(seg_y)
        if not xs:
            return [0.0, 0.0], [0.0, 0.0]
        return xs, ys

    def _clear_fills(self) -> None:
        for artist in getattr(self, "_fills", []):
            try:
                artist.remove()
            except Exception:
                pass
        self._fills = []

    def _redraw(self) -> None:
        xs, ys = self._build_plot_arrays()
        self._line.set_data(xs, ys)
        self._clear_fills()
        t = theme()
        fills: List = []
        for seg in self.segments:
            seg_x, seg_y = self._segment_step(seg)
            if len(seg_x) < 2:
                continue
            fill = self.ax.fill_between(
                seg_x,
                seg_y,
                0.0,
                step="post",
                color=t.curve_fill,
                alpha=t.curve_fill_alpha,
                zorder=2,
            )
            fills.append(fill)
        self._fills = fills
        self.ax._product_fill = fills[-1] if fills else None
        self.canvas.draw_idle()


__all__ = ["OvenCurveWidget"]
