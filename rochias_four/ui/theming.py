from __future__ import annotations

from matplotlib import rcParams

from .theme import THEMES, Theme

_current_theme: Theme = THEMES["dark"]


def apply_theme(name: str) -> Theme:
    global _current_theme
    _current_theme = THEMES.get(name, _current_theme)
    t = _current_theme

    rcParams.update({
        "figure.facecolor": t.surface,
        "savefig.facecolor": t.surface,
        "axes.facecolor": t.surface,
        "axes.edgecolor": t.stroke,
        "axes.labelcolor": t.text,
        "xtick.color": t.text_muted,
        "ytick.color": t.text_muted,
        "grid.color": t.grid,
        "text.color": t.text,
    })
    return t


def theme() -> Theme:
    return _current_theme
