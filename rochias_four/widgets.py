"""Reusable Tkinter widgets tailored for the application."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme


class VScrollFrame(ttk.Frame):
    """Scroll-aware frame to stack cards vertically without clipping."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        bg = getattr(master, "BG", theme.BG)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=bg, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = ttk.Frame(self.canvas, style="TFrame")
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-4>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-5>", self._on_mousewheel, add="+")

    def refresh_theme(self):
        self.canvas.configure(bg=getattr(self.master, "BG", theme.BG))
        try:
            self.inner.configure(style="TFrame")
        except Exception:
            pass

    def _on_frame_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._inner_id, width=event.width)

    def _on_mousewheel(self, event):
        if getattr(event, "delta", 0) > 0 or getattr(event, "num", None) == 4:
            self.canvas.yview_scroll(-1, "units")
        elif getattr(event, "delta", 0) < 0 or getattr(event, "num", None) == 5:
            self.canvas.yview_scroll(+1, "units")


class SegmentedBar(tk.Canvas):
    """Visual bar composed of segments with optional tick markers."""

    def __init__(self, master, height=22, **kwargs):
        super().__init__(
            master,
            bg=getattr(master, "CARD", theme.CARD),
            highlightthickness=0,
            bd=0,
            height=height,
            **kwargs,
        )
        self.height = height
        self.total_distance = 0.0
        self.progress = 0.0
        self.show_ticks = True
        self._markers = [(1 / 3, "1/3"), (2 / 3, "2/3")]
        self._cell_labels: list[tuple[float, str]] = []
        self.holes: list[tuple[float, float]] = []
        self.pad = 4
        self._track = getattr(master, "TRACK", theme.TRACK)
        self._border = getattr(master, "BORDER", theme.BORDER)
        self._fill = getattr(master, "FILL", theme.FILL)
        self._hole_future = getattr(master, "HOLE", theme.HOLE)
        self._hole_past = getattr(master, "HOLE_BORDER", theme.HOLE_BORDER)
        self._glow = getattr(master, "GLOW", theme.GLOW)
        self._red = getattr(master, "RED", theme.RED)
        self._subtext = getattr(master, "SUBTEXT", theme.SUBTEXT)
        self.bind("<Configure>", lambda _event: self.redraw())

    def set_total_distance(self, distance: float):
        self.total_distance = max(0.0, float(distance))
        self.progress = 0.0
        self.redraw()

    set_total = set_total_distance

    def set_progress(self, seconds_elapsed: float):
        value = max(0.0, float(seconds_elapsed))
        if self.total_distance > 0.0:
            value = min(value, self.total_distance)
        self.progress = value
        self.redraw()

    def reset(self):
        self.total_distance = 0.0
        self.progress = 0.0
        self.holes = []
        self.redraw()

    def set_markers(self, percentages, labels=None):
        markers = []
        if labels is None:
            labels = ["" for _ in percentages]
        for pct, text in zip(percentages, labels):
            try:
                pct_float = float(pct)
            except (TypeError, ValueError):
                continue
            markers.append((pct_float, str(text)))
        self._markers = markers
        self.redraw()

    def set_cell_labels(self, labels):
        cells: list[tuple[float, str]] = []
        for entry in labels:
            try:
                pct, text = entry
                pct_float = float(pct)
            except (TypeError, ValueError):
                continue
            cells.append((pct_float, str(text)))
        self._cell_labels = cells
        self.redraw()

    def set_holes(self, intervals):
        limit = max(0.0, float(self.total_distance))
        if not intervals or limit <= 0.0:
            self.holes = []
            self.redraw()
            return
        clamped: list[tuple[float, float]] = []
        for entry in intervals:
            try:
                a, b = entry
                a = float(a)
                b = float(b)
            except Exception:
                continue
            lo = max(0.0, min(limit, a))
            hi = max(0.0, min(limit, b))
            if hi - lo > 1e-6:
                clamped.append((lo, hi))
        self.holes = sorted(clamped, key=lambda item: (item[0], item[1]))
        self.redraw()

    def redraw(self):
        width = self.winfo_width() or 120
        height = self.winfo_height() or self.height
        self.delete("all")

        label_space = 18 if self._cell_labels else 0
        base_height = max(4, height - label_space)
        radius = base_height // 2
        outer_top = max(0, radius - 14)
        outer_bot = min(base_height, radius + 14)
        offset = label_space

        self.create_rectangle(
            0,
            outer_top + offset,
            width,
            outer_bot + offset,
            fill=self._border,
            outline=self._border,
        )

        track_left = 4
        track_right = max(track_left, width - 4)
        track_top = max(outer_top + 2, radius - 10) + offset
        track_bot = min(outer_bot - 2, radius + 10) + offset
        self.create_rectangle(
            track_left,
            track_top,
            track_right,
            track_bot,
            fill=self._track,
            outline=self._border,
            width=1,
        )

        inner_width = max(0.0, track_right - track_left)
        total = max(0.0, float(self.total_distance))
        scale = inner_width / max(1e-6, total) if inner_width > 0 and total > 0.0 else 0.0
        progress_sec = max(0.0, min(self.progress, total))
        prog_x = track_left
        if scale > 0.0:
            prog_x = track_left + progress_sec * scale
            prog_x = max(track_left, min(track_right, prog_x))

        if scale > 0.0:
            for a, b in self.holes:
                xa = track_left + a * scale
                xb = track_left + b * scale
                if xb <= prog_x:
                    continue
                x_left = max(prog_x, xa)
                if xb - x_left > 0.5:
                    self.create_rectangle(x_left, track_top, xb, track_bot, fill=self._hole_future, outline="")

        if prog_x - track_left > 0.5:
            self.create_rectangle(track_left, track_top, prog_x, track_bot, fill=self._fill, outline="")
            self.create_line(track_left, track_top, prog_x, track_top, fill=self._glow, width=2)

        if scale > 0.0:
            for a, b in self.holes:
                xa = track_left + a * scale
                xb = track_left + b * scale
                if xa >= prog_x:
                    continue
                x_right = min(prog_x, xb)
                if x_right - xa > 0.5:
                    self.create_rectangle(xa, track_top, x_right, track_bot, fill=self._hole_past, outline="")

        if inner_width > 0 and self.show_ticks:
            for pct_value, text in self._markers:
                x_pos = track_left + max(0.0, min(1.0, pct_value)) * inner_width
                self.create_line(int(x_pos), track_top, int(x_pos), track_bot, fill=self._red, width=2)
                if text:
                    self.create_text(
                        int(x_pos) + 2,
                        track_top - 6,
                        text=text,
                        anchor="w",
                        fill=self._subtext,
                        font=("Consolas", 9),
                    )

        if inner_width > 0 and self._cell_labels:
            label_y = max(4, label_space - 4)
            for pct_value, text in self._cell_labels:
                x_pos = track_left + max(0.0, min(1.0, pct_value)) * inner_width
                self.create_text(
                    int(x_pos),
                    label_y,
                    text=text,
                    anchor="s",
                    fill=self._subtext,
                    font=("Segoe UI Semibold", 9),
                )

    def refresh_theme(self):
        self.configure(bg=getattr(self.master, "CARD", theme.CARD))
        self._track = getattr(self.master, "TRACK", theme.TRACK)
        self._border = getattr(self.master, "BORDER", theme.BORDER)
        self._fill = getattr(self.master, "FILL", theme.FILL)
        self._hole_future = getattr(self.master, "HOLE", theme.HOLE)
        self._hole_past = getattr(self.master, "HOLE_BORDER", theme.HOLE_BORDER)
        self._glow = getattr(self.master, "GLOW", theme.GLOW)
        self._red = getattr(self.master, "RED", theme.RED)
        self._subtext = getattr(self.master, "SUBTEXT", theme.SUBTEXT)
        self.redraw()

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event=None):
        if self.tip is not None:
            return
        tip = tk.Toplevel(self.widget)
        tip.overrideredirect(True)
        try:
            tip.attributes("-alpha", 0.95)
        except Exception:
            pass
        bg = getattr(self.widget, "TOOLTIP_BG", getattr(self.widget.master, "TOOLTIP_BG", theme.TOOLTIP_BG))
        fg = getattr(self.widget, "TOOLTIP_FG", getattr(self.widget.master, "TOOLTIP_FG", theme.TOOLTIP_FG))
        tip.configure(bg=bg)
        tk.Label(tip, text=self.text, bg=bg, fg=fg, font=("Segoe UI", 9), padx=8, pady=4).pack()
        tip.update_idletasks()
        x_pos = self.widget.winfo_rootx() + 12
        y_pos = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip.geometry(f"+{x_pos}+{y_pos}")
        self.tip = tip

    def hide(self, _event=None):
        if self.tip is None:
            return
        try:
            self.tip.destroy()
        except Exception:
            pass
        self.tip = None


class Collapsible(ttk.Frame):
    """Disclosure widget offering a collapsible body."""

    def __init__(self, master, title="Détails", open=False):
        super().__init__(master, style="CardInner.TFrame")
        self._open = bool(open)
        self._title = title
        header = ttk.Frame(self, style="CardInner.TFrame")
        header.pack(fill="x")
        self._btn = ttk.Button(
            header,
            text=self._label_text(),
            style="Ghost.TButton",
            command=self.toggle,
            padding=(8, 4),
        )
        self._btn.pack(side="left")
        self.body = ttk.Frame(self, style="CardInner.TFrame")
        if self._open:
            self.body.pack(fill="both", expand=True, pady=(6, 0))

    def _label_text(self):
        return ("[-] " if self._open else "[+] ") + self._title

    def toggle(self):
        self._open = not self._open
        self._btn.config(text=self._label_text())
        if self._open:
            self.body.pack(fill="both", expand=True, pady=(6, 0))
        else:
            self.body.forget()

    def set_open(self, open_: bool):
        if bool(open_) != self._open:
            self.toggle()


__all__ = [
    "Collapsible",
    "SegmentedBar",
    "Tooltip",
    "VScrollFrame",
]
