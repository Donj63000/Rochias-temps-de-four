# -*- coding: utf-8 -*-
"""
ThemeManager — gestion des thèmes ttk (clair / dark_rouge) + matplotlib.
- Application atomique et réversible (aucune casse du code existant),
- Persistance dans ~/.rochias_four/theme.json,
- API: tm.apply('light'|'dark_rouge'), tm.toggle(), tm.load_saved_or('light'),
       tm.style (ttk.Style), tm.colors (dict), tm.apply_matplotlib(fig|axes).
"""

from __future__ import annotations
import os, json, platform
import tkinter as tk
from tkinter import ttk

# ---------- Persistance ----------
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".rochias_four")
CONFIG_PATH = os.path.join(CONFIG_DIR, "theme.json")

# ---------- Palettes ----------
THEMES = {
    "light": {
        "bg":        "#F7F7F7",
        "surface":   "#FFFFFF",
        "panel":     "#F3F3F3",
        "fg":        "#1A1A1A",
        "fg_muted":  "#606060",
        "accent":    "#C62828",  # rouge profond cohérent
        "accent_fg": "#FFFFFF",
        "border":    "#DADADA",
        "grid":      "#E2E2E2",
        "success":   "#2E7D32",
        "warn":      "#EF6C00",
    },
    "dark_rouge": {
        "bg":        "#111213",
        "surface":   "#171819",
        "panel":     "#1E1F21",
        "fg":        "#EAEAEA",
        "fg_muted":  "#A0A0A0",
        "accent":    "#D32F2F",
        "accent_fg": "#FFFFFF",
        "border":    "#2A2B2D",
        "grid":      "#2C2D2F",
        "success":   "#66BB6A",
        "warn":      "#FFA726",
    },
}

# Quelques styles nommés (pour éviter les conflits)
STYLE_NAMES = {
    "Frame":        "R.Frame",
    "Label":        "R.Label",
    "Button":       "R.TButton",
    "Entry":        "R.TEntry",
    "Notebook":     "R.TNotebook",
    "NotebookTab":  "R.TNotebook.Tab",
    "Progressbar":  "R.Horizontal.TProgressbar",
    "Treeview":     "R.Treeview",
}


class ThemeManager:
    def __init__(self, root: tk.Misc):
        self.root = root
        self.style = ttk.Style(root)
        # Pour personnaliser, on part d'un thème ttk modifiable
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.current = "light"
        self.colors = THEMES["light"]

    # ---------- Persistence ----------
    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"theme": self.current}, f, indent=2, ensure_ascii=False)

    def load_saved_or(self, fallback: str = "light"):
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    d = json.load(f)
                name = d.get("theme", fallback)
            else:
                name = fallback
        except Exception:
            name = fallback
        self.apply(name)

    # ---------- Public API ----------
    def toggle(self, order=("light", "dark_rouge")) -> str:
        next_name = order[1] if self.current == order[0] else order[0]
        self.apply(next_name)
        return self.current

    def apply(self, name: str):
        if name not in THEMES:
            name = "light"
        self.current = name
        self.colors = THEMES[name]
        c = self.colors

        # Fond racine + toplevels
        try:
            self.root.configure(bg=c["bg"])
        except tk.TclError:
            pass

        # Bases
        self.style.configure(STYLE_NAMES["Frame"],
                             background=c["bg"], borderwidth=0)
        self.style.configure(STYLE_NAMES["Label"],
                             background=c["bg"], foreground=c["fg"])
        # Boutons
        self.style.configure(STYLE_NAMES["Button"],
                             background=c["surface"],
                             foreground=c["fg"],
                             bordercolor=c["border"],
                             focusthickness=1,
                             focustcolor=c["accent"])
        self.style.map(STYLE_NAMES["Button"],
                       background=[("active", c["panel"])],
                       foreground=[("disabled", c["fg_muted"])],
                       relief=[("pressed", "sunken"), ("!pressed", "raised")])

        # Entrées
        self.style.configure(STYLE_NAMES["Entry"],
                             fieldbackground=c["surface"],
                             background=c["surface"],
                             foreground=c["fg"],
                             bordercolor=c["border"])
        self.style.map(STYLE_NAMES["Entry"],
                       fieldbackground=[("focus", c["surface"])],
                       bordercolor=[("focus", c["accent"])])

        # Notebook / Tabs
        self.style.configure(STYLE_NAMES["Notebook"],
                             background=c["bg"], bordercolor=c["border"])
        self.style.configure(STYLE_NAMES["NotebookTab"],
                             background=c["panel"], foreground=c["fg"],
                             lightcolor=c["panel"], darkcolor=c["panel"],
                             bordercolor=c["border"])
        self.style.map(STYLE_NAMES["NotebookTab"],
                       background=[("selected", c["surface"]), ("active", c["panel"])],
                       foreground=[("disabled", c["fg_muted"]), ("selected", c["fg"])])

        # Progressbar
        self.style.configure(STYLE_NAMES["Progressbar"],
                             background=c["accent"], troughcolor=c["panel"],
                             lightcolor=c["accent"], darkcolor=c["accent"],
                             bordercolor=c["panel"])
        # Treeview
        self.style.configure(STYLE_NAMES["Treeview"],
                             background=c["surface"],
                             fieldbackground=c["surface"],
                             foreground=c["fg"],
                             bordercolor=c["border"])
        self.style.map(STYLE_NAMES["Treeview"],
                       background=[("selected", c["accent"])],
                       foreground=[("selected", c["accent_fg"])])

        # Styles génériques (TFrame/TLabel/etc) pour widgets qui ne sont pas stylés explicitement
        self.style.configure("TFrame", background=c["bg"])
        self.style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        self.style.configure("TButton", foreground=c["fg"])
        self.style.configure("TEntry", fieldbackground=c["surface"], foreground=c["fg"])
        self.style.configure("TNotebook", background=c["bg"])
        self.style.configure("TNotebook.Tab", background=c["panel"], foreground=c["fg"])

        # Sauvegarde
        self.save()

    # ---------- Matplotlib ----------
    def apply_matplotlib(self, fig_or_axes):
        """Applique le thème aux figures/axes matplotlib (fond, ticks, grille, titres)."""
        c = self.colors
        try:
            import matplotlib
            import matplotlib.pyplot as plt  # noqa
        except Exception:
            return  # matplotlib pas dispo → ignorer

        def _style_axes(ax):
            ax.set_facecolor(c["surface"])
            # ticks & labels
            ax.tick_params(colors=c["fg_muted"])
            if ax.title:
                ax.title.set_color(c["fg"])
            if ax.xaxis.label:
                ax.xaxis.label.set_color(c["fg"])
            if ax.yaxis.label:
                ax.yaxis.label.set_color(c["fg"])
            # spines
            for spine in ax.spines.values():
                spine.set_color(c["border"])
            # grid
            ax.grid(True, color=c["grid"], linestyle=":", linewidth=0.8, alpha=0.7)

        if hasattr(fig_or_axes, "axes"):  # Figure
            fig = fig_or_axes
            fig.patch.set_facecolor(c["bg"])
            for ax in fig.axes:
                _style_axes(ax)
        else:  # Axes
            ax = fig_or_axes
            if ax.figure:
                ax.figure.patch.set_facecolor(c["bg"])
            _style_axes(ax)
