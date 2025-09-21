"""Reusable Tkinter widgets tailored for the application."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from .theme import ACCENT, BG, BORDER, CARD, FILL, GLOW, RED, SUBTEXT, TRACK


class VScrollFrame(ttk.Frame):
    """Scroll-aware frame to stack cards vertically without clipping."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=BG, bd=0)
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
            bg=CARD,
            highlightthickness=0,
            bd=0,
            height=height,
            **kwargs,
        )
        self.height = height
        self.total = 0.0
        self.elapsed = 0.0
        self.show_ticks = True
        self._markers = [(1 / 3, "1/3"), (2 / 3, "2/3")]
        self._cell_labels = []
        self.bind("<Configure>", lambda _event: self.redraw())

    def set_total_distance(self, distance: float):
        self.total = max(0.0, float(distance))
        self.elapsed = 0.0
        self.redraw()

    set_total = set_total_distance

    def set_progress(self, seconds_elapsed: float):
        self.elapsed = max(0.0, float(seconds_elapsed))
        self.redraw()

    def reset(self):
        self.total = 0.0
        self.elapsed = 0.0
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
            markers.append((pct_float, text))
        self._markers = markers
        self.redraw()

    def set_cell_labels(self, labels):
        cells = []
        for entry in labels:
            try:
                pct, text = entry
                pct_float = float(pct)
            except (TypeError, ValueError):
                continue
            cells.append((pct_float, str(text)))
        self._cell_labels = cells
        self.redraw()

    def redraw(self):
        width = self.winfo_width() or 120
        height = self.winfo_height() or self.height
        self.delete("all")

        radius = height // 2
        outer_top = max(0, radius - 14)
        outer_bot = min(height, radius + 14)
        self.create_rectangle(0, outer_top, width, outer_bot, fill=BORDER, outline=BORDER)

        track_left = 4
        track_right = max(track_left, width - 4)
        track_top = max(outer_top + 2, radius - 10)
        track_bot = min(outer_bot - 2, radius + 10)
        self.create_rectangle(track_left, track_top, track_right, track_bot, fill=TRACK, outline=ACCENT, width=1)

        pct = 0.0 if self.total <= 1e-9 else min(1.0, self.elapsed / self.total)
        inner_width = max(0, track_right - track_left)
        fill_width = 0
        if pct > 0.0 and inner_width > 0:
            fill_width = max(1, min(inner_width, math.ceil(pct * inner_width)))

        if fill_width > 0:
            fill_right = min(track_right, track_left + fill_width)
            self.create_rectangle(
                track_left,
                track_top,
                fill_right,
                track_bot,
                fill=FILL,
                outline=FILL,
            )
            self.create_line(track_left, track_top, fill_right, track_top, fill=GLOW, width=2)

        if inner_width > 0 and self.show_ticks:
            for pct_value, text in self._markers:
                x_pos = track_left + max(0.0, min(1.0, pct_value)) * inner_width
                self.create_line(int(x_pos), track_top, int(x_pos), track_bot, fill=RED, width=2)
                if text:
                    self.create_text(
                        int(x_pos) + 2,
                        track_top - 6,
                        text=text,
                        anchor="w",
                        fill=SUBTEXT,
                        font=("Consolas", 9),
                    )

        if inner_width > 0 and self._cell_labels:
            label_y = max(0, track_top - 6)
            for pct_value, text in self._cell_labels:
                x_pos = track_left + max(0.0, min(1.0, pct_value)) * inner_width
                self.create_text(
                    int(x_pos),
                    label_y,
                    text=text,
                    anchor="s",
                    fill=SUBTEXT,
                    font=("Segoe UI Semibold", 9),
                )


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
        tk.Label(tip, text=self.text, bg="#111111", fg="#ffffff", font=("Segoe UI", 9), padx=8, pady=4).pack()
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
