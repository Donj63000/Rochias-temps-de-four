# -*- coding: utf-8 -*-
"""Manage ttk and matplotlib themes with persistence and cycling helpers."""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import ttk
from typing import Sequence

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".rochias_four")
CONFIG_PATH = os.path.join(CONFIG_DIR, "theme.json")

DEFAULT_THEME = "blanc"
THEME_SEQUENCE: tuple[str, ...] = ("blanc", "vert", "sombre", "rouge")

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

    def apply_matplotlib(self, fig_or_axes):
        """Apply the current theme to matplotlib figures or axes."""
        c = self.colors
        try:
            import matplotlib  # noqa: F401
            import matplotlib.pyplot as plt  # noqa: F401
        except Exception:
            return

        def _style_axes(ax):
            ax.set_facecolor(c["surface"])
            ax.tick_params(colors=c["fg_muted"])
            if ax.title:
                ax.title.set_color(c["fg"])
            if ax.xaxis.label:
                ax.xaxis.label.set_color(c["fg"])
            if ax.yaxis.label:
                ax.yaxis.label.set_color(c["fg"])
            for spine in ax.spines.values():
                spine.set_color(c["border"])
            ax.grid(True, color=c["grid"], linestyle=":", linewidth=0.8, alpha=0.7)

        if hasattr(fig_or_axes, "axes"):
            fig = fig_or_axes
            fig.patch.set_facecolor(c["bg"])
            for ax in fig.axes:
                _style_axes(ax)
        else:
            ax = fig_or_axes
            if ax.figure:
                ax.figure.patch.set_facecolor(c["bg"])
            _style_axes(ax)
