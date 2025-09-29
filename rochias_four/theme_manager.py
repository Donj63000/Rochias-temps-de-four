# -*- coding: utf-8 -*-
"""Manage ttk and matplotlib themes with persistence and cycling helpers."""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import ttk
from typing import Sequence

from .ui.theming import apply_theme as apply_plot_theme, theme as current_plot_theme

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".rochias_four")
CONFIG_PATH = os.path.join(CONFIG_DIR, "theme.json")

DEFAULT_THEME = "blanc"
THEME_SEQUENCE: tuple[str, ...] = ("blanc", "vert", "sombre", "orange", "rouge")

THEME_PRESETS: dict[str, dict[str, object]] = {
    "blanc": {
        "bg": "#fdfdfd",
        "surface": "#ffffff",
        "panel": "#f4f4f5",
        "fg": "#1f2933",
        "fg_muted": "#6b7280",
        "accent": "#2563eb",
        "accent_fg": "#ffffff",
        "border": "#e5e7eb",
        "grid": "#d1d5db",
        "success": "#15803d",
        "warn": "#b91c1c",
        "is_dark": False,
    },
    "vert": {
        "bg": "#f6fbf7",
        "surface": "#ffffff",
        "panel": "#e7f6ed",
        "fg": "#065f46",
        "fg_muted": "#1b8f5a",
        "accent": "#16a34a",
        "accent_fg": "#ffffff",
        "border": "#cde8d9",
        "grid": "#d1eddb",
        "success": "#15803d",
        "warn": "#dc2626",
        "is_dark": False,
    },
    "sombre": {
        "bg": "#111827",
        "surface": "#1f2937",
        "panel": "#27303f",
        "fg": "#e5e7eb",
        "fg_muted": "#9ca3af",
        "accent": "#f97316",
        "accent_fg": "#111827",
        "border": "#374151",
        "grid": "#2f3a4b",
        "success": "#4ade80",
        "warn": "#f87171",
        "is_dark": True,
    },
    "rouge": {
        "bg": "#fef2f2",
        "surface": "#ffffff",
        "panel": "#fee2e2",
        "fg": "#7f1d1d",
        "fg_muted": "#b91c1c",
        "accent": "#dc2626",
        "accent_fg": "#ffffff",
        "border": "#fecaca",
        "grid": "#fca5a5",
        "success": "#15803d",
        "warn": "#991b1b",
        "is_dark": False,
    },
    "orange": {
        "bg": "#2A1E17",
        "surface": "#3A2820",
        "panel": "#241A14",
        "fg": "#FDEAD7",
        "fg_muted": "#F3C8A6",
        "accent": "#FF8C00",
        "accent_fg": "#2A1E17",
        "border": "#5C4033",
        "grid": "#6B4D3B",
        "success": "#27AE60",
        "warn": "#E74C3C",
        "is_dark": True,
    },
}

THEME_ALIASES = {
    "light": "blanc",
    "clair": "blanc",
    "white": "blanc",
    "green": "vert",
    "dark": "sombre",
    "noir": "sombre",
    "gris": "sombre",
    "dark_rouge": "sombre",
    "red": "rouge",
    "orange": "orange",
}

PLOT_THEME_MAP = {
    "blanc": "light",
    "vert": "light",
    "sombre": "dark",
    "rouge": "orange",
    "orange": "orange",
}

STYLE_NAMES = {
    "Frame": "R.Frame",
    "Label": "R.Label",
    "Button": "R.TButton",
    "Entry": "R.TEntry",
    "Notebook": "R.TNotebook",
    "NotebookTab": "R.TNotebook.Tab",
    "Progressbar": "R.Horizontal.TProgressbar",
    "Treeview": "R.Treeview",
}


def _canonical(name: str) -> str:
    key = str(name or "").strip().lower()
    if key in THEME_PRESETS:
        return key
    alias = THEME_ALIASES.get(key)
    if alias in THEME_PRESETS:
        return alias
    return DEFAULT_THEME


def _order_tuple(names: Sequence[str] | None) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    if names:
        for name in names:
            canonical = _canonical(name)
            if canonical not in seen:
                seen.add(canonical)
                ordered.append(canonical)
    if not ordered:
        ordered.append(DEFAULT_THEME)
    return tuple(ordered)


class ThemeManager:
    def __init__(self, root: tk.Misc):
        self.root = root
        self.style = ttk.Style(root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.current = DEFAULT_THEME
        self.colors = dict(THEME_PRESETS[DEFAULT_THEME])
        self._plot_theme_name = None
        self._matplotlib_axes: set = set()
        apply_plot_theme(PLOT_THEME_MAP.get(self.current, "dark"))

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"theme": self.current}, f, indent=2, ensure_ascii=False)

    def load_saved_or(self, fallback: str = DEFAULT_THEME):
        name = fallback
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                name = data.get("theme", fallback)
        except Exception:
            name = fallback
        self.apply(name)

    def toggle(self, order: Sequence[str] = THEME_SEQUENCE) -> str:
        canonical_order = _order_tuple(order)
        if self.current not in canonical_order:
            next_name = canonical_order[0]
        else:
            idx = canonical_order.index(self.current)
            next_name = canonical_order[(idx + 1) % len(canonical_order)]
        self.apply(next_name)
        return self.current

    def apply(self, name: str):
        canonical = _canonical(name)
        self.current = canonical
        self.colors = dict(THEME_PRESETS[canonical])
        c = self.colors
        plot_name = PLOT_THEME_MAP.get(canonical, canonical)
        if plot_name != self._plot_theme_name:
            apply_plot_theme(plot_name)
            self._plot_theme_name = plot_name

        try:
            self.root.configure(bg=c["bg"])
        except tk.TclError:
            pass

        self.style.configure(STYLE_NAMES["Frame"], background=c["bg"], borderwidth=0)
        self.style.configure(STYLE_NAMES["Label"], background=c["bg"], foreground=c["fg"])

        self.style.configure(
            STYLE_NAMES["Button"],
            background=c["surface"],
            foreground=c["fg"],
            bordercolor=c["border"],
            focusthickness=1,
            focuscolor=c["accent"],
        )
        self.style.map(
            STYLE_NAMES["Button"],
            background=[("active", c["panel"])],
            foreground=[("disabled", c["fg_muted"])],
            relief=[("pressed", "sunken"), ("!pressed", "raised")],
        )

        self.style.configure(
            STYLE_NAMES["Entry"],
            fieldbackground=c["surface"],
            background=c["surface"],
            foreground=c["fg"],
            bordercolor=c["border"],
        )
        self.style.map(
            STYLE_NAMES["Entry"],
            fieldbackground=[("focus", c["surface"])],
            bordercolor=[("focus", c["accent"])],
        )

        self.style.configure(
            STYLE_NAMES["Notebook"], background=c["bg"], bordercolor=c["border"]
        )
        self.style.configure(
            STYLE_NAMES["NotebookTab"],
            background=c["panel"],
            foreground=c["fg"],
            lightcolor=c["panel"],
            darkcolor=c["panel"],
            bordercolor=c["border"],
        )
        self.style.map(
            STYLE_NAMES["NotebookTab"],
            background=[("selected", c["surface"]), ("active", c["panel"])],
            foreground=[("disabled", c["fg_muted"]), ("selected", c["fg"])],
        )

        self.style.configure(
            STYLE_NAMES["Progressbar"],
            background=c["accent"],
            troughcolor=c["panel"],
            lightcolor=c["accent"],
            darkcolor=c["accent"],
            bordercolor=c["panel"],
        )
        self.style.configure(
            STYLE_NAMES["Treeview"],
            background=c["surface"],
            fieldbackground=c["surface"],
            foreground=c["fg"],
            bordercolor=c["border"],
        )
        self.style.map(
            STYLE_NAMES["Treeview"],
            background=[("selected", c["accent"])],
            foreground=[("selected", c["accent_fg"])],
        )

        self.style.configure("TFrame", background=c["bg"])
        self.style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        self.style.configure("TButton", foreground=c["fg"])
        self.style.map(
            "TButton",
            background=[("active", c["panel"]), ("disabled", c["surface"])],
            foreground=[("disabled", c["fg_muted"])],
        )
        self.style.configure("TEntry", fieldbackground=c["surface"], foreground=c["fg"])
        self.style.configure("TNotebook", background=c["bg"])
        self.style.configure("TNotebook.Tab", background=c["panel"], foreground=c["fg"])

        self.save()
        self.refresh_registered_axes()

    def apply_matplotlib(self, fig_or_axes):
        """Apply the current theme to matplotlib figures or axes."""
        try:
            import matplotlib  # noqa: F401
            import matplotlib.pyplot as plt  # noqa: F401
        except Exception:
            return
        if hasattr(fig_or_axes, "axes"):
            fig = fig_or_axes
            for ax in fig.axes:
                self.register_axes(ax)
        else:
            self.register_axes(fig_or_axes)

    def register_axes(self, ax):
        if ax is None:
            return
        self._matplotlib_axes.add(ax)
        self._apply_axes_theme(ax)

    def refresh_registered_axes(self):
        for ax in list(self._matplotlib_axes):
            if ax is None:
                self._matplotlib_axes.discard(ax)
                continue
            self._apply_axes_theme(ax)

    def _apply_axes_theme(self, ax):
        try:
            t = current_plot_theme()
        except Exception:
            return
        if getattr(ax, "figure", None):
            try:
                ax.figure.set_facecolor(t.surface)
                ax.figure.patch.set_facecolor(t.surface)
            except Exception:
                pass
        try:
            ax.set_facecolor(t.surface)
        except Exception:
            pass
        try:
            for spine in ax.spines.values():
                spine.set_color(t.stroke)
        except Exception:
            pass
        try:
            ax.tick_params(colors=t.text_muted)
        except Exception:
            pass
        try:
            ax.grid(True, color=t.grid, alpha=0.35)
        except Exception:
            pass
        try:
            ax.set_xlabel(ax.get_xlabel(), color=t.text)
            ax.set_ylabel(ax.get_ylabel(), color=t.text)
        except Exception:
            pass
        try:
            if ax.title:
                ax.title.set_color(t.text)
        except Exception:
            pass
        line = getattr(ax, "_product_line", None)
        if line is not None:
            try:
                line.set_color(t.curve)
            except Exception:
                pass
        fill = getattr(ax, "_product_fill", None)
        if fill is not None:
            try:
                fill.set_color(t.curve_fill)
                fill.set_alpha(t.curve_fill_alpha)
            except Exception:
                pass
        try:
            ax.figure.canvas.draw_idle()
        except Exception:
            pass
