from __future__ import annotations

import ctypes
import csv
import json
import math
import os
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, scrolledtext, ttk

from .config import DEFAULT_INPUTS, PREFS_PATH, TICK_SECONDS, DISPLAY_Y_MAX_CM
from .cells import is_cell_visible, visible_cells_for_tapis
from .calculations import thickness_and_accum
from .curves import piecewise_curve_normalized
from .maintenance_ref import compute_times_maintenance
from .calibration_overrides import load_anchor_from_disk
from .flow import GapEvent, holes_for_all_belts
from .segments import (
    load_segment_weights,
    compute_segment_times_minutes,
    cumulative_markers_for_bar,
)
from .theme import (
    ACCENT,
    ACCENT_DISABLED,
    ACCENT_HOVER,
    ACCENT_SOFT_BG,
    ACCENT_SOFT_BG_HOVER,
    ACCENT_SOFT_FG,
    BADGE_NEUTRAL_BG,
    BADGE_READY_BG,
    BADGE_READY_FG,
    BADGE_IDLE_FG,
    BG,
    BORDER,
    CARD,
    DISABLED_BG,
    DISABLED_FG,
    FIELD,
    FIELD_FOCUS,
    GLOW,
    HERO_BG,
    HERO_DETAIL_FG,
    MONO_FG,
    SECONDARY,
    SECONDARY_HOVER,
    SUBTEXT,
    TEXT,
)
from .theme_manager import ThemeManager, STYLE_NAMES, THEME_SEQUENCE
from .utils import fmt_hms, fmt_minutes
from .widgets import Collapsible, SegmentedBar, Tooltip, VScrollFrame
from .graphs import CELL_PROFILE_2, CELL_PROFILE_3, GraphWindow
from .timeline import FeedTimeline
from .geometry import build_line_geometry
from .graphbar import GraphBar
from .details_window import DetailsWindow


class FourApp(tk.Tk):
    def __init__(self):
        if sys.platform == "win32":
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
        super().__init__()
        self.theme = ThemeManager(self)
        self.theme.load_saved_or(THEME_SEQUENCE[0])
        self._update_theme_palette()
        self._sync_theme_attributes()
        self.title("Four • 3 Tapis — Référence maintenance (L/v)")
        self.configure(bg=BG)
        self.minsize(1100, 700)
        self._toasts = []
        self._cards = []
        self._responsive_labels = []
        self.compact_mode = False
        self.feed_events: list[GapEvent] = []
        self.feed_on = True
        self.feed_timeline = FeedTimeline()
        self.fill_alpha = 0.0
        self.accum_badges: list[ttk.Label | None] = []
        self.bars_heading_label: ttk.Label | None = None
        self._init_styles()
        self._apply_option_defaults()
        self.animating = False
        self.paused = False
        self.seg_idx = 0
        self.seg_start = 0.0
        self.seg_durations = [0.0, 0.0, 0.0]
        self.seg_distances = [0.0, 0.0, 0.0]
        self.seg_speeds = [0.0, 0.0, 0.0]
        self._after_id = None
        self.last_calc: dict | None = None
        self.total_duration = 0.0
        self.notified_stage1 = False
        self.notified_stage2 = False
        self.notified_exit = False
        self.stage_status = []
        self.kpi_labels = {}
        self.stage_rows = []
        self.graph_window = None
        self.operator_mode = True
        self.logo_img = None
        self._error_after = None
        self.graph_bars: list[GraphBar] = []
        self._load_logo()
        self._build_ui()
        load_anchor_from_disk()
        self.set_density(True)
        self._set_default_inputs()
        self.set_operator_mode(True)
        self.bind_all("<Return>", lambda e: self.on_calculer())
        self.bind_all("<F5>", lambda e: self.on_start())
        self.bind_all("<space>", lambda e: self.on_pause() if self.animating else None)
        self.bind_all("<Control-r>", lambda e: self.on_reset())
        self.bind_all("<F1>", lambda e: self.on_explanations())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(0, self._auto_scaling)
        self.after(0, self._load_prefs)
        self.after(0, self._fit_to_screen)

    @staticmethod
    def _blend_colors(color_a: str, color_b: str, ratio: float) -> str:
        ratio = max(0.0, min(1.0, float(ratio)))
        def _to_rgb(value: str) -> tuple[int, int, int]:
            value = value.strip().lstrip("#")
            if len(value) != 6:
                value = value[:6].ljust(6, "0")
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        r1, g1, b1 = _to_rgb(color_a)
        r2, g2, b2 = _to_rgb(color_b)
        r = round(r1 + (r2 - r1) * ratio)
        g = round(g1 + (g2 - g1) * ratio)
        b = round(b1 + (b2 - b1) * ratio)
        return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"

    def _graph_palette(self) -> tuple[str, str, str, str]:
        colors = getattr(self.theme, "colors", {})
        line = colors.get("success", BADGE_READY_FG)
        face = colors.get("surface", CARD)
        grid = colors.get("border", BORDER)
        text = colors.get("fg_muted", SUBTEXT)
        return line, face, grid, text

    def _update_theme_palette(self):
        from . import theme as theme_constants
        colors = self.theme.colors
        blend = self._blend_colors
        tint = lambda base, color, ratio: blend(base, color, ratio)
        lighten = lambda c, amount: blend(c, "#FFFFFF", amount)
        darken = lambda c, amount: blend(c, "#000000", amount)
        secondary = blend(colors["panel"], colors["surface"], 0.5)
        track = blend(colors["panel"], colors["bg"], 0.5)
        is_dark = bool(colors.get("is_dark", False))
        accent_hover = lighten(colors["accent"], 0.2) if is_dark else darken(colors["accent"], 0.2)
        secondary_hover_target = colors["surface"] if is_dark else colors["bg"]

        if is_dark:
            accent_soft = tint(colors["surface"], colors["accent"], 0.18)
            accent_soft_hover = tint(colors["surface"], colors["accent"], 0.28)
            warn_soft = tint(colors["surface"], colors["warn"], 0.24)
            warn_soft_hover = tint(colors["surface"], colors["warn"], 0.34)
            success_soft = tint(colors["surface"], colors["success"], 0.26)
            success_soft_hover = tint(colors["surface"], colors["success"], 0.36)
            neutral_soft = tint(colors["surface"], secondary, 0.4)
            disabled_bg = tint(colors["surface"], colors["bg"], 0.55)
            disabled_fg = tint(colors["fg_muted"], colors["bg"], 0.45)
            hero_bg = tint(colors["surface"], colors["accent"], 0.16)
            hero_detail_fg = tint(colors["fg_muted"], hero_bg, 0.35)
            tooltip_bg = tint(colors["surface"], colors["fg"], 0.6)
            tooltip_fg = colors["fg"]
            accent_soft_fg = colors["accent"]
            badge_ready_fg = colors["success"]
            badge_idle_fg = colors["fg"]
        else:
            accent_soft = tint(colors["bg"], colors["accent"], 0.14)
            accent_soft_hover = tint(colors["bg"], colors["accent"], 0.24)
            warn_soft = tint(colors["bg"], colors["warn"], 0.22)
            warn_soft_hover = tint(colors["bg"], colors["warn"], 0.32)
            success_soft = tint(colors["bg"], colors["success"], 0.26)
            success_soft_hover = tint(colors["bg"], colors["success"], 0.36)
            neutral_soft = tint(colors["bg"], secondary, 0.38)
            disabled_bg = tint(colors["bg"], colors["panel"], 0.35)
            disabled_fg = tint(colors["fg_muted"], colors["bg"], 0.65)
            hero_bg = tint(colors["bg"], colors["accent"], 0.18)
            hero_detail_fg = tint(colors["fg_muted"], hero_bg, 0.4)
            tooltip_bg = tint(colors["bg"], colors["accent"], 0.32)
            tooltip_fg = "#ffffff"
            accent_soft_fg = colors["accent"]
            badge_ready_fg = colors["success"]
            badge_idle_fg = colors["fg_muted"]

        palette = {
            "BG": colors["bg"],
            "CARD": colors["surface"],
            "BORDER": colors["border"],
            "ACCENT": colors["accent"],
            "ACCENT_HOVER": accent_hover,
            "ACCENT_DISABLED": blend(colors["accent"], colors["panel"], 0.7),
            "SECONDARY": secondary,
            "SECONDARY_HOVER": blend(secondary, secondary_hover_target, 0.4),
            "FIELD": colors["surface"],
            "FIELD_FOCUS": blend(colors["surface"], colors["accent"], 0.18),
            "TEXT": colors["fg"],
            "SUBTEXT": colors["fg_muted"],
            "RED": colors["warn"],
            "FILL": colors["accent"],
            "TRACK": track,
            "GLOW": lighten(colors["accent"], 0.45),
            "ACCENT_SOFT_BG": accent_soft,
            "ACCENT_SOFT_BG_HOVER": accent_soft_hover,
            "ACCENT_SOFT_FG": accent_soft_fg,
            "WARN_SOFT_BG": warn_soft,
            "WARN_SOFT_BG_HOVER": warn_soft_hover,
            "SUCCESS_SOFT_BG": success_soft,
            "SUCCESS_SOFT_BG_HOVER": success_soft_hover,
            "NEUTRAL_SOFT_BG": neutral_soft,
            "DISABLED_BG": disabled_bg,
            "DISABLED_FG": disabled_fg,
            "MONO_FG": blend(colors["fg"], colors["accent"], 0.35),
            "HERO_BG": hero_bg,
            "HERO_DETAIL_FG": hero_detail_fg,
            "TOOLTIP_BG": tooltip_bg,
            "TOOLTIP_FG": tooltip_fg,
            "BADGE_READY_BG": success_soft,
            "BADGE_READY_FG": badge_ready_fg,
            "BADGE_NEUTRAL_BG": neutral_soft,
            "BADGE_IDLE_FG": badge_idle_fg,

            # <<< ICI : jauni les "trous"
            "HOLE": "#FACC15",         # jaune (500) -- rempli sur la partie pass?e
            "HOLE_BORDER": "#A16207",  # jaune fonc? -- liser? sur la partie future
        }
        self._palette = palette
        module_globals = globals()
        for key, value in palette.items():
            setattr(theme_constants, key, value)
            if key in module_globals:
                module_globals[key] = value

    def _refresh_graphbars_theme(self):
        if not getattr(self, "graph_bars", None):
            return
        line, face, grid, text = self._graph_palette()
        for graph in self.graph_bars:
            try:
                graph.apply_theme(line, face, grid, text, DISPLAY_Y_MAX_CM)
            except Exception:
                pass

    def _update_graphs(self, t_now_min: float) -> None:
        alpha = self.feed_timeline.alpha_at(t_now_min)
        self.fill_alpha = alpha
        for bar in getattr(self, "bars", []):
            try:
                bar.set_curve_alpha(alpha)
            except Exception:
                pass
        for graph in getattr(self, "graph_bars", []):
            try:
                graph.update(t_now_min, self.feed_timeline)
            except Exception:
                pass
    def _sync_theme_attributes(self):
        palette = getattr(self, "_palette", {})
        for key, value in palette.items():
            setattr(self, key, value)

    def _apply_option_defaults(self):
        self.option_add("*TButton.Cursor", "hand2")
        self.option_add("*TRadiobutton.Cursor", "hand2")
        self.option_add("*Entry.insertBackground", TEXT)
        self.option_add("*Entry.selectBackground", ACCENT)
        self.option_add("*Entry.selectForeground", "#ffffff")

    def on_toggle_theme(self):
        self.theme.toggle(THEME_SEQUENCE)
        try:
            self.refresh_after_theme_change()
        except Exception:
            pass

    def refresh_after_theme_change(self):
        self._update_theme_palette()
        self._sync_theme_attributes()
        self.configure(bg=BG)
        self._init_styles()
        self._apply_option_defaults()
        for wrapper, _inner in self._cards:
            try:
                wrapper.configure(bg=BORDER, highlightbackground=BORDER, highlightcolor=BORDER)
            except Exception:
                pass
        body = getattr(self, "body_frame", None)
        if body is not None:
            try:
                body.refresh_theme()
            except Exception:
                pass
        for bar in getattr(self, "bars", []):
            try:
                if hasattr(bar, "refresh_theme"):
                    bar.refresh_theme()
                else:
                    bar.configure(bg=CARD)
                    bar.redraw()
            except Exception:
                pass
        self._refresh_graphbars_theme()
        for window in self.winfo_children():
            if isinstance(window, tk.Toplevel):
                try:
                    window.configure(bg=BG)
                except Exception:
                    pass
                for child in window.winfo_children():
                    if isinstance(child, scrolledtext.ScrolledText):
                        try:
                            child.configure(bg=CARD, fg=TEXT, insertbackground=TEXT)
                        except Exception:
                            pass
        if hasattr(self, "details") and isinstance(self.details, Collapsible):
            try:
                self.details.configure(style="CardInner.TFrame")
            except Exception:
                pass
        if self.graph_window and self.graph_window.winfo_exists():
            try:
                self.graph_window.redraw_with_theme(self.theme)
            except Exception:
                pass

    def _fit_to_screen(self, margin=60):
        self.update_idletasks()
        req_w, req_h = self.winfo_reqwidth(), self.winfo_reqheight()
        scr_w, scr_h = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(max(req_w, 1100), scr_w - 2 * margin)
        h = min(max(req_h, 700), scr_h - 2 * margin)
        self.geometry(f"{int(w)}x{int(h)}")

    def _auto_scaling(self):
        try:
            dpi = self.winfo_fpixels("1i")
        except Exception:
            return
        if dpi <= 0:
            return
        scale = dpi / 72.0
        try:
            self.call("tk", "scaling", scale)
        except Exception:
            pass

    def _clear_toasts(self):
        for tip in list(self._toasts):
            try:
                tip.destroy()
            except Exception:
                pass
        self._toasts.clear()

    def toast(self, message: str, ms=2000):
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)
        tip.configure(bg="#000000")
        try:
            tip.attributes("-alpha", 0.9)
        except Exception:
            pass
        lbl = tk.Label(tip, text=message, bg="#000000", fg="#ffffff", font=("Segoe UI", 10), padx=12, pady=6)
        lbl.pack()
        tip.update_idletasks()
        x = self.winfo_rootx() + 40
        y = self.winfo_rooty() + 20
        tip.geometry(f"+{x}+{y}")
        tip.after(ms, tip.destroy)
        def _cleanup(_=None):
            if tip in self._toasts:
                self._toasts.remove(tip)
        tip.bind("<Destroy>", _cleanup)
        self._toasts.append(tip)

    def _clear_error(self):
        if self._error_after is not None:
            try:
                self.after_cancel(self._error_after)
            except Exception:
                pass
            self._error_after = None
        if hasattr(self, "err_box"):
            self.err_box.config(text="")

    def _show_error(self, msg):
        if not hasattr(self, "err_box"):
            return
        self._clear_error()
        self.err_box.config(text=f"⚠ {msg}")
        self._error_after = self.after(4000, self._clear_error)
        try:
            self.bell()
        except Exception:
            pass

    def _validate_num(self, s: str) -> bool:
        if s in ("", "."):
            return True
        try:
            float(s.replace(",", "."))
            return True
        except ValueError:
            try:
                self.bell()
            except Exception:
                pass
            return False

    def _set_default_inputs(self):
        for widget, value in zip((self.e1, self.e2, self.e3), DEFAULT_INPUTS):
            widget.delete(0, tk.END)
            widget.insert(0, value)

    def _save_prefs(self):
        data = dict(
            geom=self.winfo_geometry(),
            f1=self.e1.get(),
            f2=self.e2.get(),
            f3=self.e3.get(),
            compact=self.compact_mode,
        )
        try:
            PREFS_PATH.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def _load_prefs(self):
        if not PREFS_PATH.exists():
            return
        try:
            data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        self.e1.delete(0, tk.END)
        self.e1.insert(0, data.get("f1", DEFAULT_INPUTS[0]))
        self.e2.delete(0, tk.END)
        self.e2.insert(0, data.get("f2", DEFAULT_INPUTS[1]))
        self.e3.delete(0, tk.END)
        self.e3.insert(0, data.get("f3", DEFAULT_INPUTS[2]))
        if data.get("compact"):
            self.set_density(True)
        geom = data.get("geom")
        if geom:
            self.geometry(geom)

    def _on_close(self):
        self._save_prefs()
        self._clear_toasts()
        self.destroy()

    def set_density(self, compact: bool):
        compact = bool(compact)
        self.compact_mode = compact
        pad = (12, 8) if compact else (20, 16)
        hero_value_size = 20 if compact else 22
        card_heading_size = 13 if compact else 14
        self.style.configure("CardHeading.TLabel", font=("Segoe UI Semibold", card_heading_size))
        self.style.configure("HeroStatValue.TLabel", font=("Segoe UI", hero_value_size, "bold"))
        self.style.configure("HeroStatLabel.TLabel", font=("Segoe UI Semibold", 9 if compact else 10))
        for wrapper, inner in self._cards:
            try:
                inner.configure(padding=pad)
            except Exception:
                pass
        if hasattr(self, "density_button"):
            self.density_button.config(text="Mode confortable" if compact else "Mode compact")

    def _cancel_after(self):
        if getattr(self, "_after_id", None):
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _schedule_tick(self):
        self._cancel_after()
        self._after_id = self.after(int(TICK_SECONDS * 1000), self._tick)

    def _init_styles(self):
        style = self.theme.style
        base_font = ("Segoe UI", 11)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("CardInner.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=TEXT, font=base_font)
        style.configure("Card.TLabel", background=CARD, foreground=TEXT, font=base_font)
        style.configure("Title.TLabel", background=CARD, foreground=ACCENT, font=("Segoe UI Semibold", 17))
        style.configure("HeroTitle.TLabel", background=CARD, foreground=ACCENT, font=("Segoe UI Semibold", 18))
        style.configure("HeroSub.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI", 11))
        style.configure("CardHeading.TLabel", background=CARD, foreground=ACCENT, font=("Segoe UI Semibold", 14))
        style.configure("Subtle.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI", 10))
        style.configure("Hint.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI", 10, "italic"))
        style.configure("TableHead.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI Semibold", 11))
        style.configure("Big.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI", 20, "bold"))
        style.configure("Result.TLabel", background=CARD, foreground=ACCENT, font=("Segoe UI", 22, "bold"))
        style.configure("Mono.TLabel", background=CARD, foreground=MONO_FG, font=("Consolas", 11))
        style.configure("Status.TLabel", background=CARD, foreground=SUBTEXT, font=("Consolas", 11))
        style.configure("Footer.TLabel", background=BG, foreground=SUBTEXT, font=("Segoe UI", 10))
        style.configure("Dark.TSeparator", background=BORDER)
        style.configure("TSeparator", background=BORDER)
        style.configure("StatCard.TFrame", background=SECONDARY, relief="flat")
        style.configure("StatTitle.TLabel", background=SECONDARY, foreground=SUBTEXT, font=("Segoe UI Semibold", 10))
        style.configure("StatValue.TLabel", background=SECONDARY, foreground=TEXT, font=("Segoe UI", 18, "bold"))
        style.configure("StatDetail.TLabel", background=SECONDARY, foreground=SUBTEXT, font=("Consolas", 11))
        style.configure("ParamName.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI Semibold", 10))
        style.configure("ParamValue.TLabel", background=CARD, foreground=TEXT, font=("Consolas", 11))
        style.configure("HeroStat.TFrame", background=HERO_BG, relief="flat")
        style.configure("HeroStatValue.TLabel", background=HERO_BG, foreground=ACCENT, font=("Segoe UI", 22, "bold"))
        style.configure("HeroStatLabel.TLabel", background=HERO_BG, foreground=SUBTEXT, font=("Segoe UI Semibold", 10))
        style.configure("HeroStatDetail.TLabel", background=HERO_BG, foreground=HERO_DETAIL_FG, font=("Segoe UI", 10))
        style.configure("Logo.TLabel", background=CARD)
        style.configure("StageRow.TFrame", background=CARD)
        style.configure("StageTitle.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 12))
        style.configure("StageFreq.TLabel", background=CARD, foreground=SUBTEXT, font=("Consolas", 11))
        style.configure("StageTime.TLabel", background=CARD, foreground=ACCENT, font=("Segoe UI Semibold", 18))
        style.configure("StageTimeDetail.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI", 10))
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#ffffff",
            padding=10,
            borderwidth=0,
            focusthickness=0,
            relief="flat",
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_HOVER), ("disabled", ACCENT_DISABLED)],
            foreground=[("disabled", DISABLED_FG)],
        )
        style.configure(
            "Ghost.TButton",
            background=SECONDARY,
            foreground=TEXT,
            padding=10,
            borderwidth=0,
            focusthickness=0,
            relief="flat",
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", SECONDARY_HOVER), ("disabled", DISABLED_BG)],
            foreground=[("disabled", DISABLED_FG)],
        )
        style.configure(
            "Chip.TButton",
            background=ACCENT_SOFT_BG,
            foreground=ACCENT_SOFT_FG,
            padding=(12, 6),
            borderwidth=0,
            focusthickness=0,
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Chip.TButton",
            background=[("active", ACCENT_SOFT_BG_HOVER), ("disabled", DISABLED_BG)],
            foreground=[("disabled", DISABLED_FG)],
        )
        style.configure(
            "Dark.TEntry",
            fieldbackground=FIELD,
            background=FIELD,
            foreground=TEXT,
            bordercolor=BORDER,
            insertcolor=TEXT,
        )
        style.map(
            "Dark.TEntry",
            fieldbackground=[("focus", FIELD_FOCUS)],
            bordercolor=[("focus", ACCENT)],
            foreground=[("disabled", SUBTEXT)],
        )
        style.configure(
            "Dark.TSpinbox",
            fieldbackground=FIELD,
            background=FIELD,
            foreground=TEXT,
            arrowsize=12,
            bordercolor=BORDER,
            insertcolor=TEXT,
        )
        style.map(
            "Dark.TSpinbox",
            fieldbackground=[("focus", FIELD_FOCUS)],
            bordercolor=[("focus", ACCENT)],
            foreground=[("disabled", SUBTEXT)],
        )
        style.configure(
            "Accent.TRadiobutton",
            background=CARD,
            foreground=TEXT,
            indicatorcolor=BORDER,
            focuscolor=ACCENT,
            padding=4,
            font=base_font,
        )
        style.map(
            "Accent.TRadiobutton",
            indicatorcolor=[("selected", ACCENT), ("!selected", BORDER)],
            foreground=[("disabled", DISABLED_FG)],
        )
        badge_font = ("Segoe UI Semibold", 10)
        style.configure("BadgeIdle.TLabel", background=SECONDARY, foreground=BADGE_IDLE_FG, font=badge_font, padding=(10, 2))
        style.configure("BadgeReady.TLabel", background=BADGE_READY_BG, foreground=BADGE_READY_FG, font=badge_font, padding=(10, 2))
        style.configure("BadgeActive.TLabel", background=ACCENT, foreground="#ffffff", font=badge_font, padding=(10, 2))
        style.configure("BadgeDone.TLabel", background=ACCENT_HOVER, foreground="#ffffff", font=badge_font, padding=(10, 2))
        style.configure("BadgePause.TLabel", background=ACCENT_DISABLED, foreground=TEXT, font=badge_font, padding=(10, 2))
        style.configure("BadgeNeutral.TLabel", background=BADGE_NEUTRAL_BG, foreground=TEXT, font=badge_font, padding=(10, 2))
        self.style = style

    def _load_logo(self):
        path = Path(__file__).with_name("rochias.png")
        if not path.exists():
            return
        try:
            img = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return
        max_height = 72
        max_width = 260
        height = img.height()
        width = img.width()
        if height > max_height:
            factor = max(1, int(math.ceil(height / max_height)))
            img = img.subsample(factor, factor)
            height = img.height()
            width = img.width()
        if width > max_width:
            factor = max(1, int(math.ceil(width / max_width)))
            img = img.subsample(factor, factor)
        self.logo_img = img

    def _card(self, parent, *, padding=(20, 16), **pack_kwargs):
        wrapper = tk.Frame(parent, bg=BORDER, highlightbackground=BORDER, highlightcolor=BORDER, highlightthickness=1, bd=0)
        inner = ttk.Frame(wrapper, style="Card.TFrame", padding=padding)
        inner.pack(fill="both", expand=True)
        wrapper.pack(**pack_kwargs)
        self._cards.append((wrapper, inner))
        return inner

    def _create_stat_card(self, parent, column, title, *, frame_style="StatCard.TFrame", title_style="StatTitle.TLabel", value_style="StatValue.TLabel", detail_style="StatDetail.TLabel"):
        frame = ttk.Frame(parent, style=frame_style, padding=(16, 12))
        frame.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 12, 0))
        ttk.Label(frame, text=title, style=title_style).pack(anchor="w")
        value = ttk.Label(frame, text="--", style=value_style)
        value.pack(anchor="w", pady=(4, 2))
        detail = ttk.Label(frame, text="--", style=detail_style)
        detail.pack(anchor="w")
        parent.columnconfigure(column, weight=1, uniform="stat")
        return value, detail

    def _update_kpi(self, key, main_text, detail_text="--"):
        labels = self.kpi_labels.get(key)
        if not labels:
            return
        value_lbl, detail_lbl = labels
        value_lbl.config(text=main_text)
        detail_lbl.config(text=detail_text)

    def _build_ui(self):
        header = self._card(self, fill="x", padx=18, pady=(16, 8), padding=(28, 22))
        header.columnconfigure(0, weight=1)
        accent = tk.Frame(header, background=ACCENT, height=4)
        accent.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_rowconfigure(0, weight=0)
        header.grid_rowconfigure(1, weight=1)
        hero = ttk.Frame(header, style="Card.TFrame")
        hero.grid(row=1, column=0, sticky="ew")
        hero.columnconfigure(0, weight=0)
        hero.columnconfigure(1, weight=1)
        hero.columnconfigure(2, weight=0)
        hero.grid_rowconfigure(3, weight=1)
        if self.logo_img is not None:
            ttk.Label(hero, image=self.logo_img, style="Logo.TLabel").grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 20))
        title = ttk.Label(hero, text="Simulation four 3 tapis — Référence maintenance (L/v)", style="HeroTitle.TLabel")
        title.grid(row=0, column=1, sticky="w")
        badge_box = ttk.Frame(hero, style="CardInner.TFrame")
        badge_box.grid(row=0, column=2, sticky="e", padx=(12, 0))
        ttk.Label(badge_box, text="Méthode tableur (L/v)", style="BadgeReady.TLabel").pack(side="left")
        self.density_button = ttk.Button(badge_box, text="Mode compact", style="Chip.TButton", command=lambda: self.set_density(not self.compact_mode))
        self.density_button.pack(side="left", padx=(8, 0))
        hero_stats = ttk.Frame(hero, style="CardInner.TFrame")
        hero_stats.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        hero_stats.columnconfigure((0, 1, 2, 3), weight=1, uniform="hero")
        kpi_defs = [("total", "Temps total"), ("t1", "Tapis 1"), ("t2", "Tapis 2"), ("t3", "Tapis 3")]
        for idx, (key, label) in enumerate(kpi_defs):
            pill = ttk.Frame(hero_stats, style="HeroStat.TFrame", padding=(16, 12))
            pill.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 12, 0))
            ttk.Label(pill, text=label, style="HeroStatLabel.TLabel").pack(anchor="w")
            value = ttk.Label(pill, text="--", style="HeroStatValue.TLabel")
            value.pack(anchor="w", pady=(4, 0))
            detail = ttk.Label(pill, text="--", style="HeroStatDetail.TLabel")
            detail.pack(anchor="w", pady=(2, 0))
            self.kpi_labels[key] = (value, detail)
        Tooltip(self.kpi_labels["total"][0], "Temps total par la référence maintenance (L/v).")
        body = VScrollFrame(self)
        body.pack(fill="both", expand=True)
        self.body_frame = body
        pcard = self._card(body.inner, fill="x", expand=False, padx=18, pady=8, padding=(24, 20))
        self.bars_heading_label = ttk.Label(pcard, text="Barres de chargement — Référence maintenance (L/v)", style="CardHeading.TLabel")
        self.bars_heading_label.pack(anchor="w", pady=(0, 12))
        self.bars = []
        self.graph_bars = []
        self.bar_texts = []
        self.bar_duration_labels = []
        self.stage_status = []
        self.accum_badges = []
        for i in range(3):
            holder = ttk.Frame(pcard, style="CardInner.TFrame")
            holder.pack(fill="x", pady=10)
            setattr(holder, "DISPLAY_Y_MAX_CM", DISPLAY_Y_MAX_CM)
            setattr(holder, "CURVE_COLOR", BADGE_READY_FG)
            title_row = ttk.Frame(holder, style="CardInner.TFrame")
            title_row.pack(fill="x")
            ttk.Label(title_row, text=f"Tapis {i + 1}", style="Card.TLabel").pack(side="left")
            status_lbl = ttk.Label(title_row, text="⏳ En attente", style="BadgeIdle.TLabel")
            status_lbl.pack(side="left", padx=(12, 0))
            accum_lbl = ttk.Label(title_row, text="", style="BadgeNeutral.TLabel")
            if i > 0:
                accum_lbl.pack(side="left", padx=(8, 0))
            self.accum_badges.append(accum_lbl if i > 0 else None)
            g_line, g_face, g_grid, g_text = self._graph_palette()
            graph = GraphBar(
                holder,
                y_max=DISPLAY_Y_MAX_CM,
                height_px=120,
                line_color=g_line,
                face_color=g_face,
                grid_color=g_grid,
                text_color=g_text,
            )
            graph.pack(fill="x", expand=True, pady=(8, 6))
            self.graph_bars.append(graph)
            bar = SegmentedBar(holder, height=30)
            bar.pack(fill="x", expand=True, pady=(8, 4))
            bar.set_markers([1 / 3, 2 / 3], ["", ""])
            visible_cells = visible_cells_for_tapis(i + 1)
            count_visible = len(visible_cells)
            if count_visible:
                positions = [((2 * idx + 1) / (2 * count_visible), f"Cellule {cell_id}")
                             for idx, cell_id in enumerate(visible_cells)]
                bar.set_cell_labels(positions)
            else:
                bar.set_cell_labels([])
            txt = ttk.Label(holder, text="En attente", style="Status.TLabel", anchor="w", wraplength=860)
            txt.pack(anchor="w")
            detail_lbl = ttk.Label(holder, text="", style="Mono.TLabel", anchor="w", wraplength=860)
            detail_lbl.pack(anchor="w", pady=(2, 0))
            self.stage_status.append(status_lbl)
            self.bars.append(bar)
            self.bar_texts.append(txt)
            self.bar_duration_labels.append(detail_lbl)
        top = ttk.Frame(body.inner, style="TFrame")
        top.pack(fill="x", expand=False, padx=18, pady=6)
        card_in = self._card(top, side="left", fill="both", expand=True, padx=(0, 0))
        card_in.columnconfigure(0, weight=1)
        ttk.Label(card_in, text="Entrées (fréquences variateur)", style="CardHeading.TLabel").pack(anchor="w", pady=(0, 12))
        g = ttk.Frame(card_in, style="CardInner.TFrame")
        g.pack(fill="x", pady=(12, 6))
        g.columnconfigure(1, weight=1)
        ttk.Label(g, text="Tapis 1 : Hz =", style="Card.TLabel").grid(row=0, column=0, sticky="e", padx=(0, 12), pady=6)
        vcmd = (self.register(self._validate_num), "%P")
        self.e1 = ttk.Spinbox(g, from_=1, to=120, increment=0.01, format="%.2f", width=10, style="Dark.TSpinbox", validate="key", validatecommand=vcmd)
        self.e1.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(g, text="Tapis 2 : Hz =", style="Card.TLabel").grid(row=1, column=0, sticky="e", padx=(0, 12), pady=6)
        self.e2 = ttk.Spinbox(g, from_=1, to=120, increment=0.01, format="%.2f", width=10, style="Dark.TSpinbox", validate="key", validatecommand=vcmd)
        self.e2.grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(g, text="Tapis 3 : Hz =", style="Card.TLabel").grid(row=2, column=0, sticky="e", padx=(0, 12), pady=6)
        self.e3 = ttk.Spinbox(g, from_=1, to=120, increment=0.01, format="%.2f", width=10, style="Dark.TSpinbox", validate="key", validatecommand=vcmd)
        self.e3.grid(row=2, column=1, sticky="w", pady=6)
        ttk.Label(g, text="Épaisseur entrée h0 (cm) =", style="Card.TLabel").grid(row=3, column=0, sticky="e", padx=(0, 12), pady=6)
        self.h0 = ttk.Spinbox(g, from_=0.10, to=20.0, increment=0.10, format="%.2f", width=10, style="Dark.TSpinbox", validate="key", validatecommand=vcmd)
        self.h0.grid(row=3, column=1, sticky="w", pady=6)
        self.h0.delete(0, tk.END)
        self.h0.insert(0, "2.00")
        ttk.Label(card_in, text="Astuce : 40.00 ou 4000 (IHM). >200 = IHM/100.", style="Hint.TLabel").pack(anchor="w", pady=(4, 12))
        self.err_box = ttk.Label(card_in, text="", style="Hint.TLabel")
        self.err_box.pack(anchor="w", pady=(0, 0))
        btns = ttk.Frame(card_in, style="CardInner.TFrame")
        btns.pack(fill="x", pady=(4, 8))
        btns.columnconfigure(8, weight=1)
        self.btn_calculer = ttk.Button(btns, text="Calculer", command=self.on_calculer, style="Accent.TButton")
        self.btn_calculer.grid(row=0, column=0, padx=(0, 12), pady=2, sticky="w")
        self.btn_start = ttk.Button(btns, text="▶ Démarrer (temps réel)", command=self.on_start, state="disabled", style="Accent.TButton")
        self.btn_start.grid(row=0, column=1, padx=(0, 12), pady=2, sticky="w")
        self.btn_pause = ttk.Button(btns, text="⏸ Pause", command=self.on_pause, state="disabled", style="Ghost.TButton")
        self.btn_pause.grid(row=0, column=2, padx=(0, 12), pady=2, sticky="w")
        ttk.Button(btns, text="↺ Réinitialiser", command=self.on_reset, style="Ghost.TButton").grid(row=0, column=3, pady=2, sticky="w")
        ttk.Button(btns, text="ℹ Explications", command=self.on_explanations, style="Ghost.TButton").grid(row=0, column=4, pady=2, sticky="e")
        ttk.Button(btns, text="🧭 Détails", command=self.on_details, style="Ghost.TButton").grid(row=0, column=5, pady=2, sticky="e")
        ttk.Button(btns, text="📈 Graphiques", command=self.on_graphs, style="Ghost.TButton").grid(row=0, column=6, pady=2, sticky="e")
        ttk.Button(
            btns,
            text="🔎 Détails cellules/transferts",
            command=self.on_details_segments,
            style="Ghost.TButton"
        ).grid(row=0, column=7, padx=(8, 0), pady=2, sticky="e")
        ttk.Button(btns, text="Thème", style=STYLE_NAMES["Button"], command=self.on_toggle_theme).grid(row=0, column=8, padx=(12, 0), pady=2, sticky="e")
        self.btn_feed_stop = ttk.Button(btns, text="⛔ Arrêt alimentation", command=self.on_feed_stop, state="disabled", style="Ghost.TButton")
        self.btn_feed_stop.grid(row=1, column=0, padx=(0, 12), pady=(8, 2), sticky="w")
        self.btn_feed_resume = ttk.Button(btns, text="✅ Reprise alimentation", command=self.on_feed_resume, state="disabled", style="Ghost.TButton")
        self.btn_feed_resume.grid(row=1, column=1, padx=(0, 12), pady=(8, 2), sticky="w")
        self.details = Collapsible(body.inner, title="Détails résultats (référence maintenance L/v)", open=False)
        self.details.pack(fill="x", padx=18, pady=(8, 0))
        card_out = self._card(self.details.body, fill="both", expand=True)
        card_out.bind("<Configure>", lambda e: self.lbl_analysis_info.configure(wraplength=max(200, int(e.width * 0.85))))
        card_out.columnconfigure(0, weight=1)
        ttk.Label(card_out, text="Résultats", style="CardHeading.TLabel").pack(anchor="w", pady=(0, 12))
        self.lbl_total_big = ttk.Label(card_out, text="Référence maintenance (L/v) : --", style="Result.TLabel")
        self.lbl_total_big.pack(anchor="w", pady=(0, 10))
        ttk.Label(card_out, text="Formule : tᵢ = Lconvᵢ · Cᵢ / UIᵢ  — UI en IHM (x100), conversion automatique IHM↔Hz.", style="HeroSub.TLabel", wraplength=820, justify="left").pack(anchor="w", pady=(4, 2))
        self.lbl_analysis_info = ttk.Label(card_out, text="", style="Hint.TLabel", wraplength=820, justify="left")
        self.lbl_analysis_info.pack(anchor="w", pady=(0, 12))
        self.parts_section_label = ttk.Label(card_out, text="Référence maintenance (L/v)", style="CardHeading.TLabel")
        self.parts_section_label.pack(anchor="w", pady=(8, 0))
        stage_list = ttk.Frame(card_out, style="CardInner.TFrame")
        stage_list.pack(fill="x", pady=(0, 12))
        self.stage_rows = []
        for i in range(3):
            row = ttk.Frame(stage_list, style="StageRow.TFrame")
            row.pack(fill="x", pady=6)
            row.columnconfigure(2, weight=1)
            ttk.Label(row, text=f"Tapis {i + 1}", style="StageTitle.TLabel").grid(row=0, column=0, rowspan=2, sticky="w")
            freq_lbl = ttk.Label(row, text="-- Hz", style="StageFreq.TLabel")
            freq_lbl.grid(row=0, column=1, sticky="w", padx=(12, 0))
            time_lbl = ttk.Label(row, text="--", style="StageTime.TLabel")
            time_lbl.grid(row=0, column=2, sticky="e")
            detail_lbl = ttk.Label(row, text="--", style="StageTimeDetail.TLabel")
            detail_lbl.grid(row=1, column=2, sticky="e")
            self.stage_rows.append({"freq": freq_lbl, "time": time_lbl, "detail": detail_lbl})
        ttk.Separator(card_out, style="Dark.TSeparator").pack(fill="x", pady=8)
        footer = ttk.Frame(body.inner, style="TFrame")
        footer.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Label(footer, text="Astuce : lance un calcul pour activer la simulation en temps réel.", style="Footer.TLabel").pack(anchor="w")
        for key in ("total", "t1", "t2", "t3"):
            self._update_kpi(key, "--", "--")
        for i in range(len(self.stage_status)):
            self._set_stage_status(i, "idle")

    def set_operator_mode(self, on: bool):
        self.operator_mode = bool(on)
        if hasattr(self, "details"):
            try:
                self.details.set_open(not self.operator_mode)
            except Exception:
                pass

    def _update_bar_targets(self):
        if not self.last_calc:
            return
        if hasattr(self, "bars_heading_label"):
            self.bars_heading_label.config(text="Barres de chargement — Référence maintenance (L/v)")
        targets = self.last_calc.get("parts_reparties")
        if not targets:
            return
        seconds = [max(0.0, float(value) * 60.0) for value in targets]
        if self.animating:
            return
        self.seg_durations = seconds
        self.total_duration = sum(seconds)
        if not self.bars:
            return
        for idx in range(min(len(self.bars), len(seconds))):
            bar = self.bars[idx]
            txt = self.bar_texts[idx]
            try:
                freq = float(self.seg_speeds[idx])
            except Exception:
                freq = 0.0
            target_sec = seconds[idx]
            bar.set_total_distance(target_sec)
            bar.set_progress(0.0)
            txt.config(text=f"0.0% | vitesse {freq:.2f} Hz | 00:00:00 / {fmt_hms(target_sec)} | en attente")

    def _apply_parts(self):
        data = self.last_calc
        if not data:
            return
        parts = tuple(data.get("parts_reparties") or (0.0, 0.0, 0.0))
        f_values = (data.get("f1"), data.get("f2"), data.get("f3"))
        if hasattr(self, "parts_section_label"):
            self.parts_section_label.config(text="Référence maintenance (L/v)")
        for row, part, freq in zip(self.stage_rows, parts, f_values):
            row["time"].config(text=fmt_minutes(part))
            row["detail"].config(text=f"{part:.2f} min | {fmt_hms(part * 60)}")
            if freq is not None:
                row["freq"].config(text=f"{float(freq):.2f} Hz")
        self._update_kpi("t1", fmt_minutes(parts[0]), f"{parts[0]:.2f} min | {fmt_hms(parts[0] * 60)}")
        self._update_kpi("t2", fmt_minutes(parts[1]), f"{parts[1]:.2f} min | {fmt_hms(parts[1] * 60)}")
        self._update_kpi("t3", fmt_minutes(parts[2]), f"{parts[2]:.2f} min | {fmt_hms(parts[2] * 60)}")
        self._update_bar_targets()

    def _apply_graph_geometry(self, seg_times: dict[str, float], h1: float, h2: float, h3: float) -> None:
        if not getattr(self, "graph_bars", None):
            return
        geometry_map = build_line_geometry(seg_times or {}, h1, h2, h3)
        for idx, key in enumerate(("t1", "t2", "t3")):
            graph = self.graph_bars[idx] if idx < len(self.graph_bars) else None
            if graph is None:
                continue
            geo = geometry_map.get(key)
            if geo is None:
                graph.clear()
            else:
                geom, offset = geo
                graph.set_geometry(geom, offset)
        self._update_graphs(0.0)

    def on_reset(self):
        self._cancel_after()
        self.animating = False
        self.paused = False
        self.seg_idx = 0
        self.seg_start = 0.0
        self._clear_error()
        self._clear_toasts()
        for b, t in zip(self.bars, self.bar_texts):
            b.reset()
            t.config(text="En attente")
            try:
                b.set_holes([])
                b.set_curve_alpha(0.0)
            except Exception:
                pass
        for row in self.stage_rows:
            row["freq"].config(text="-- Hz")
            row["time"].config(text="--")
            row["detail"].config(text="--")
        for lbl in getattr(self, "bar_duration_labels", []):
            try:
                lbl.config(text="")
            except Exception:
                pass
        self.feed_events.clear()
        self.feed_on = True
        self.feed_timeline.reset(0.0, 0.0, 0)
        self.fill_alpha = 0.0
        if hasattr(self, "btn_feed_stop"):
            self.btn_feed_stop.config(state="disabled")
        if hasattr(self, "btn_feed_resume"):
            self.btn_feed_resume.config(state="disabled")
        self.lbl_total_big.config(text="Référence maintenance (L/v) : --")
        self.lbl_analysis_info.config(text="")
        if self.bars_heading_label is not None:
            self.bars_heading_label.config(text="Barres de chargement — Référence maintenance (L/v)")
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="disabled", text="⏸ Pause")
        self.btn_calculer.config(state="normal")
        self._update_graphs(0.0)
        self.seg_durations = [0.0, 0.0, 0.0]
        self.seg_distances = [0.0, 0.0, 0.0]
        self.seg_speeds = [0.0, 0.0, 0.0]
        self.total_duration = 0.0
        self.notified_stage1 = False
        self.notified_stage2 = False
        self.notified_exit = False
        self.last_calc = None
        for key in ("total", "t1", "t2", "t3"):
            self._update_kpi(key, "--", "--")
        for i in range(len(self.stage_status)):
            self._set_stage_status(i, "idle")

    def on_graphs(self):
        if not self.last_calc:
            try:
                self.on_calculer()
            except Exception:
                pass
        try:
            if self.graph_window and self.graph_window.winfo_exists():
                self.graph_window.lift()
                self.graph_window.redraw_with_theme(self.theme)
                self.graph_window.redraw_with_mode("maintenance")
            else:
                self.graph_window = GraphWindow(self)
                self.graph_window.redraw_with_mode("maintenance")
        except Exception as e:
            self._show_error(f"Impossible d'ouvrir le graphique : {e}")

    def on_details(self):
        if not self.last_calc:
            try:
                self.on_calculer()
            except Exception:
                return
        try:
            if getattr(self, "details_window", None) and self.details_window.winfo_exists():
                self.details_window.lift()
                self.details_window.refresh_from_app()
            else:
                self.details_window = DetailsWindow(self)
        except Exception as e:
            self._show_error(f"Impossible d'ouvrir les détails : {e}")

    def on_details_segments(self):
        calc = self.last_calc or {}
        seg = calc.get("segments") or {}
        times = seg.get("times_min") or {}
        if not times:
            self._show_error("Aucun détail segment. Lance d’abord un calcul.")
            return

        t1, t2, t3 = calc.get("parts_reparties", (0.0, 0.0, 0.0))

        def line(label, minutes):
            return f"{label:<18}  {fmt_minutes(minutes):>8}  ({minutes:6.2f} min | {fmt_hms(minutes * 60)})"

        lines: list[str] = []
        lines.append("TAPIS 1")
        lines.append(line("Entrée (avant C1)", times.get("entry1", 0.0)))
        lines.append(line("Cellule 1",          times.get("c1", 0.0)))
        lines.append(line("Cellule 2",          times.get("c2", 0.0)))
        lines.append(line("Cellule 3",          times.get("c3", 0.0)))
        lines.append(line("Somme T1",           t1))
        lines.append("")

        lines.append("TRANSFERT 1 (T1→T2)")
        lines.append(line("Transfer 1",         times.get("transfer1", 0.0)))
        lines.append("")

        lines.append("TAPIS 2")
        lines.append(line("Cellule 4",          times.get("c4", 0.0)))
        lines.append(line("Cellule 5",          times.get("c5", 0.0)))
        lines.append(line("Cellule 6",          times.get("c6", 0.0)))
        lines.append(line("Somme T2",           t2))
        lines.append("")

        lines.append("TRANSFERT 2 (T2→T3)")
        lines.append(line("Transfer 2",         times.get("transfer2", 0.0)))
        lines.append("")

        lines.append("TAPIS 3")
        for cell_id in visible_cells_for_tapis(3):
            lines.append(line(f"Cellule {cell_id}",          times.get(f"c{cell_id}", 0.0)))
        lines.append(line("Somme T3",           t3))
        lines.append("")
        total = (t1 or 0.0) + (t2 or 0.0) + (t3 or 0.0)
        lines.append(line("TOTAL",              total))

        win = tk.Toplevel(self)
        win.title("Détails — Cellules, transferts, entrée")
        bg = getattr(self, "BG", BG)
        card = getattr(self, "CARD", CARD)
        text_color = getattr(self, "TEXT", TEXT)
        win.configure(bg=bg)
        win.geometry("760x640")

        box = scrolledtext.ScrolledText(
            win,
            wrap="word",
            font=("Consolas", 11),
            bg=card,
            fg=text_color,
            insertbackground=text_color,
        )
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.insert("1.0", "\n".join(lines))
        box.configure(state="disabled")


    def on_calculer(self):
        if self.animating or self.paused:
            self.on_reset()
        else:
            self._cancel_after()
        self._clear_error()
        self.feed_timeline.reset(0.0, 0.0, 0)
        try:
            raw1 = (self.e1.get() or "").strip()
            raw2 = (self.e2.get() or "").strip()
            raw3 = (self.e3.get() or "").strip()
            f1_in = float(raw1.replace(",", "."))
            f2_in = float(raw2.replace(",", "."))
            f3_in = float(raw3.replace(",", "."))
        except Exception as e:
            self._show_error(f"Saisie invalide : {e}")
            return
        try:
            result = compute_times_maintenance(f1_in, f2_in, f3_in, units="auto")
        except Exception as exc:
            self._show_error(f"Calcul maintenance indisponible : {exc}")
            return
        parts_minutes = (result.t1_min, result.t2_min, result.t3_min)
        freq_display = (float(result.f1_hz), float(result.f2_hz), float(result.f3_hz))
        self.seg_distances = [0.0, 0.0, 0.0]
        self.seg_speeds = [float(val) for val in freq_display]
        self.seg_durations = [value * 60.0 for value in parts_minutes]
        self.total_duration = float(result.total_s)
        self.notified_stage1 = False
        self.notified_stage2 = False
        self.notified_exit = False
        self.last_calc = dict(
            f1=freq_display[0],
            f2=freq_display[1],
            f3=freq_display[2],
            parts_reparties=parts_minutes,
            T_total_min=float(result.total_min),
            total_s=float(result.total_s),
            t1_hms=result.t1_hms,
            t2_hms=result.t2_hms,
            t3_hms=result.t3_hms,
            total_hms=result.total_hms,
            t1s_min=float(parts_minutes[0]),
            t2s_min=float(parts_minutes[1]),
            t3s_min=float(parts_minutes[2]),
        )
        # ---- Détails segments: entrée / cellules / transferts ----
        for lbl in getattr(self, "bar_duration_labels", []):
            try:
                lbl.config(text="")
            except Exception:
                pass
        seg_times: dict[str, float] = {}
        try:
            weights = load_segment_weights()
            t1, t2, t3 = self.last_calc["parts_reparties"]  # minutes par tapis (t1_min, t2_min, t3_min)
            seg_times = compute_segment_times_minutes(t1, t2, t3, weights)
            self.last_calc["segments"] = {"weights": weights, "times_min": seg_times}

            def _fmt_min(val: float) -> str:
                return f"{val:.2f} min"
            try:
                if self.bar_duration_labels:
                    parts = [f"Entrée : {_fmt_min(seg_times.get('entry1', 0.0))}"]
                    for cell_id in cells_belt1:
                        parts.append(f"Cellule {cell_id} : {_fmt_min(seg_times.get(f'c{cell_id}', 0.0))}")
                    self.bar_duration_labels[0].config(text="  |  ".join(parts))
                if len(self.bar_duration_labels) > 1:
                    parts = [f"Transfert 1 : {_fmt_min(seg_times.get('transfer1', 0.0))}"]
                    for cell_id in cells_belt2:
                        parts.append(f"Cellule {cell_id} : {_fmt_min(seg_times.get(f'c{cell_id}', 0.0))}")
                    self.bar_duration_labels[1].config(text="  |  ".join(parts))
                if len(self.bar_duration_labels) > 2:
                    parts = [f"Transfert 2 : {_fmt_min(seg_times.get('transfer2', 0.0))}"]
                    for cell_id in cells_belt3:
                        parts.append(f"Cellule {cell_id} : {_fmt_min(seg_times.get(f'c{cell_id}', 0.0))}")
                    self.bar_duration_labels[2].config(text="  |  ".join(parts))
            except Exception:
                pass

            # Marqueurs réalistes sur les barres (fin de chaque sous-segment sauf le dernier)
            blk1 = [("entry1", seg_times.get("entry1", 0.0)),
                    ("c1", seg_times.get("c1", 0.0)),
                    ("c2", seg_times.get("c2", 0.0)),
                    ("c3", seg_times.get("c3", 0.0))]
            m1 = cumulative_markers_for_bar(blk1, t1)

            blk2 = []
            for cell_id in visible_cells_for_tapis(2):
                blk2.append((f"c{cell_id}", seg_times.get(f"c{cell_id}", 0.0)))
            m2 = cumulative_markers_for_bar(blk2, t2)

            blk3 = []
            for cell_id in visible_cells_for_tapis(3):
                blk3.append((f"c{cell_id}", seg_times.get(f"c{cell_id}", 0.0)))
            m3 = cumulative_markers_for_bar(blk3, t3)

            try:
                self.bars[0].set_markers(m1, [""] * len(m1))
                self.bars[1].set_markers(m2, [""] * len(m2))
                self.bars[2].set_markers(m3, [""] * len(m3))
            except Exception:
                # Si SegmentedBar n’accepte que 2 marqueurs, les 1/3-2/3 initiaux resteront en place.
                pass
        except Exception:
            # En cas de souci de chargement JSON etc., on ne casse pas le calcul principal
            pass
        for row, minutes, freq, hms in zip(self.stage_rows, parts_minutes, freq_display, (result.t1_hms, result.t2_hms, result.t3_hms)):
            row["time"].config(text=fmt_minutes(minutes))
            row["detail"].config(text=f"{minutes:.2f} min | {hms}")
            row["freq"].config(text=f"{freq:.2f} Hz")
        self._update_kpi("t1", fmt_minutes(parts_minutes[0]), f"{parts_minutes[0]:.2f} min | {result.t1_hms}")
        self._update_kpi("t2", fmt_minutes(parts_minutes[1]), f"{parts_minutes[1]:.2f} min | {result.t2_hms}")
        self._update_kpi("t3", fmt_minutes(parts_minutes[2]), f"{parts_minutes[2]:.2f} min | {result.t3_hms}")
        self._update_kpi("total", fmt_minutes(result.total_min), f"{float(result.total_min):.2f} min | {result.total_hms}")
        self.lbl_total_big.config(text=f"Référence maintenance (L/v) : {fmt_minutes(result.total_min)} | {result.total_hms}")
        try:
            h0_cm = float(self.h0.get().replace(",", "."))
            if not (h0_cm > 0):
                raise ValueError
        except Exception:
            h0_cm = 2.0
        th = thickness_and_accum(self.seg_speeds[0], self.seg_speeds[1], self.seg_speeds[2], h0_cm)
        cells_belt1 = visible_cells_for_tapis(1)
        cells_belt2 = visible_cells_for_tapis(2)
        cells_belt3 = visible_cells_for_tapis(3)
        n1 = max(1, len(cells_belt1))
        n2 = max(1, len(cells_belt2))
        n3 = max(1, len(cells_belt3))
        profile1 = [1.0] * n1
        profile2 = list(CELL_PROFILE_2) if len(CELL_PROFILE_2) == n2 else [1.0] * n2
        profile3 = [0.55, 0.45] if n3 == 2 else (list(CELL_PROFILE_3) if len(CELL_PROFILE_3) == n3 else [1.0] * n3)
        curve1 = piecewise_curve_normalized(th["h1_cm"], th["h1_cm"], n1, profile1)
        curve2 = piecewise_curve_normalized(th["h1_cm"], th["h2_cm"], n2, profile2)
        curve3 = piecewise_curve_normalized(th["h2_cm"], th["h3_cm"], n3, profile3)
        self.fill_alpha = 0.0
        for bar, curve in zip(self.bars, (curve1, curve2, curve3)):
            try:
                bar.set_curve(curve, y_max_cm=DISPLAY_Y_MAX_CM)
                bar.set_curve_alpha(self.fill_alpha)
            except Exception:
                pass
        self._apply_graph_geometry(seg_times, th["h1_cm"], th["h2_cm"], th["h3_cm"])
        def _badge_style(pct: float) -> str:
            if pct > 0.5:
                return "BadgeActive.TLabel"
            if pct < -0.5:
                return "BadgeReady.TLabel"
            return "BadgeNeutral.TLabel"
        if len(self.accum_badges) > 1 and self.accum_badges[1] is not None:
            txt12 = f"Variation épaisseur 1→2 : {th['A12_pct']:+.0f}% | h₂≈{th['h2_cm']:.2f} cm"
            self.accum_badges[1].config(text=txt12, style=_badge_style(th["A12_pct"]))
        if len(self.accum_badges) > 2 and self.accum_badges[2] is not None:
            txt23 = f"Variation épaisseur 2→3 : {th['A23_pct']:+.0f}% | h₃≈{th['h3_cm']:.2f} cm"
            self.accum_badges[2].config(text=txt23, style=_badge_style(th["A23_pct"]))
        self.feed_events.clear()
        self.feed_on = True
        if hasattr(self, "btn_feed_stop"):
            self.btn_feed_stop.config(state="disabled")
        if hasattr(self, "btn_feed_resume"):
            self.btn_feed_resume.config(state="disabled")
        for bar in self.bars:
            try:
                bar.set_holes([])
            except Exception:
                pass
        for txt in self.bar_texts:
            txt.config(text="En attente")
        info = (
            "Mode maintenance L/v : tᵢ = Lconvᵢ · Cᵢ / UIᵢ (référence tableur). "
            f"UI saisis = {f1_in:.2f} / {f2_in:.2f} / {f3_in:.2f} → Hz = {freq_display[0]:.2f} / {freq_display[1]:.2f} / {freq_display[2]:.2f}. "
            f"t₁={result.t1_hms}, t₂={result.t2_hms}, t₃={result.t3_hms} | Total={result.total_hms}"
        )
        self.lbl_analysis_info.config(text=info)
        self._apply_parts()
        try:
            if hasattr(self, "graph_window") and self.graph_window and self.graph_window.winfo_exists():
                self.graph_window.redraw_with_mode("maintenance")
        except Exception:
            pass
        self.total_duration = sum(self.seg_durations)
        self.notified_stage1 = False
        self.notified_stage2 = False
        self.notified_exit = False
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸ Pause")
        self.btn_calculer.config(state="normal")
        try:
            if getattr(self, "details_window", None) and self.details_window.winfo_exists():
                self.details_window.refresh_from_app()
        except Exception:
            pass

    def on_start(self):
        if self.animating:
            return
        if sum(self.seg_durations) <= 0:
            self.on_calculer()
            if sum(self.seg_durations) <= 0:
                return
        self.animating = True
        self.paused = False
        self.seg_idx = 0
        self.seg_start = time.perf_counter()
        self.total_duration = sum(self.seg_durations)
        self.notified_stage1 = False
        self.notified_stage2 = False
        self.notified_exit = False
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸ Pause")
        self.btn_calculer.config(state="disabled")
        self.feed_events.clear()
        self.feed_on = True
        self.feed_timeline.reset(0.0, 0.0, 1)
        self.fill_alpha = 0.0
        self.btn_feed_stop.config(state="normal")
        self.btn_feed_resume.config(state="disabled")
        for bar in self.bars:
            try:
                bar.set_holes([])
                bar.set_curve_alpha(self.fill_alpha)
            except Exception:
                pass
        self._update_graphs(0.0)
        self._set_stage_status(0, "active")
        self._set_stage_status(1, "ready")
        self._set_stage_status(2, "idle")
        self._cancel_after()
        self._tick()

    def _set_stage_status(self, index, status):
        if not (0 <= index < len(self.stage_status)):
            return
        label = self.stage_status[index]
        mapping = {
            "idle": ("⏳ En attente", "BadgeIdle.TLabel"),
            "ready": ("▶ Prêt", "BadgeReady.TLabel"),
            "active": ("⏵ En cours", "BadgeActive.TLabel"),
            "done": ("✓ Terminé", "BadgeDone.TLabel"),
            "pause": ("⏸ En pause", "BadgePause.TLabel"),
        }
        text_value, style_name = mapping.get(status, ("⏳ En attente", "BadgeIdle.TLabel"))
        label.config(text=text_value, style=style_name)

    def on_pause(self):
        if not self.animating:
            return
        if not self.paused:
            self.paused = True
            self.pause_t0 = time.perf_counter()
            self._cancel_after()
            self.btn_pause.config(text="▶ Reprendre")
            self._set_stage_status(self.seg_idx, "pause")
        else:
            delta = time.perf_counter() - self.pause_t0
            self.seg_start += delta
            self.paused = False
            self.btn_pause.config(text="⏸ Pause")
            self._set_stage_status(self.seg_idx, "active")
            self._tick()

    def _sim_minutes(self) -> float:
        base_min = sum(self.seg_durations[: self.seg_idx]) / 60.0
        if not self.animating:
            return base_min
        if self.paused:
            return base_min + max(0.0, self.pause_t0 - self.seg_start) / 60.0
        return base_min + (time.perf_counter() - self.seg_start) / 60.0

    def on_feed_stop(self):
        if not self.animating:
            self._show_error("Lance la simulation avant d'arrêter l'alimentation.")
            return
        if not self.feed_on:
            return
        tnow = self._sim_minutes()
        self.feed_events.append(GapEvent(start_min=tnow))
        self.feed_on = False
        self.feed_timeline.set_target(0, tnow)
        self.btn_feed_stop.config(state="disabled")
        self.btn_feed_resume.config(state="normal")
        self.toast("Arrêt alimentation enregistré")
        self._update_graphs(tnow)

    def on_feed_resume(self):
        if not self.animating:
            return
        if self.feed_on:
            return
        tnow = self._sim_minutes()
        for ev in reversed(self.feed_events):
            if ev.end_min is None:
                ev.end_min = tnow
                break
        self.feed_on = True
        self.feed_timeline.set_target(1, tnow)
        self.btn_feed_stop.config(state="normal")
        self.btn_feed_resume.config(state="disabled")
        self.toast("Reprise alimentation enregistrée")
        self._update_graphs(tnow)

    def _tick(self):
        if not self.animating or self.paused:
            return
        i = self.seg_idx
        dur = max(1e-6, self.seg_durations[i])
        vitesse = self.seg_speeds[i]
        now = time.perf_counter()
        elapsed_raw = now - self.seg_start
        elapsed = max(0.0, elapsed_raw)
        clamped_elapsed = min(elapsed, dur)
        t_now_min = (sum(self.seg_durations[: self.seg_idx]) + clamped_elapsed) / 60.0
        self._update_graphs(t_now_min)
        remaining_current = max(0.0, dur - elapsed)
        remaining_future = sum(self.seg_durations[j] for j in range(i + 1, 3))
        total_remaining = max(0.0, remaining_current + remaining_future)
        if not self.notified_exit and self.total_duration > 5 * 60 and total_remaining <= 5 * 60:
            self.notified_exit = True
            self.toast("Le produit va sortir du four (≤ 5 min)")
        if elapsed >= dur:
            clamped_elapsed = dur
            self.bars[i].set_progress(dur)
            self.bar_texts[i].config(text=f"100% | vitesse {vitesse:.2f} Hz | {fmt_hms(dur)} / {fmt_hms(dur)} | terminé")
            if i == 0 and not self.notified_stage1:
                self.toast("Passage → Tapis 2")
                self.notified_stage1 = True
            elif i == 1 and not self.notified_stage2:
                self.toast("Passage → Tapis 3")
                self.notified_stage2 = True
            self._set_stage_status(i, "done")
            self.seg_idx += 1
            if self.seg_idx >= 3:
                self.animating = False
                self.btn_pause.config(state="disabled", text="⏸ Pause")
                self.btn_start.config(state="normal")
                self.btn_calculer.config(state="normal")
                self.feed_on = True
                self.btn_feed_stop.config(state="disabled")
                self.btn_feed_resume.config(state="disabled")
                return
            self.seg_start = now
            j = self.seg_idx
            vitesse_j = self.seg_speeds[j]
            duree_j = self.seg_durations[j]
            self.bars[j].set_total_distance(duree_j)
            self.bar_texts[j].config(text=f"0.0% | vitesse {vitesse_j:.2f} Hz | 00:00:00 / {fmt_hms(duree_j)} | en cours")
            self._set_stage_status(j, "active")
            if j + 1 < 3:
                self._set_stage_status(j + 1, "ready")
            self._schedule_tick()
            return
        pct = max(0.0, min(1.0, clamped_elapsed / dur)) * 100.0
        self.bars[i].set_progress(clamped_elapsed)
        self.bar_texts[i].config(text=f"{pct:5.1f}% | vitesse {vitesse:.2f} Hz | {fmt_hms(clamped_elapsed)} / {fmt_hms(dur)} | en cours")
        try:
            t1m = self.seg_durations[0] / 60.0
            t2m = self.seg_durations[1] / 60.0
            t3m = self.seg_durations[2] / 60.0
            D1, D2, D3 = self.seg_distances
            f1, f2, f3 = self.seg_speeds
            holes = holes_for_all_belts(self.feed_events, t_now_min, t1m, t2m, t3m, f1, f2, f3, D1, D2, D3)
            for belt_idx, intervals in enumerate(holes):
                try:
                    freq = self.seg_speeds[belt_idx] if belt_idx < len(self.seg_speeds) else 0.0
                    if freq and math.isfinite(freq):
                        converted = [(start / freq * 60.0, end / freq * 60.0) for start, end in intervals]
                    else:
                        converted = []
                    self.bars[belt_idx].set_holes(converted)
                except Exception:
                    pass
        except Exception:
            pass

        self._schedule_tick()

    def export_csv(self):
        calc = self.last_calc
        if not calc:
            self._show_error('Aucun calcul à exporter. Lance d\'abord "Calculer".')
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv"), ("Tous fichiers", "*.*")], title="Exporter résultats")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=";")
                for key, value in calc.items():
                    writer.writerow([key, value])
            self.toast(f"Export CSV : {path}")
        except Exception as e:
            self._show_error(f"Export CSV impossible : {e}")

    def export_bars_ps(self):
        if not self.bars:
            self._show_error("Aucune barre à exporter.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".ps", filetypes=[("PostScript", "*.ps"), ("Tous fichiers", "*.*")], title="Exporter barres")
        if not path:
            return
        base, ext = os.path.splitext(path)
        saved = []
        try:
            for idx, canvas in enumerate(self.bars, 1):
                target = path if len(self.bars) == 1 else f"{base}_{idx}{ext}"
                canvas.postscript(file=target, colormode="color")
                saved.append(target)
        except Exception as e:
            self._show_error(f"Export PS impossible : {e}")
            return
        self.toast("Export PS : " + "; ".join(saved))

    def on_explanations(self):
        calc = self.last_calc or {}
        try:
            f1 = float(calc.get("f1", 0.0))
            f2 = float(calc.get("f2", 0.0))
            f3 = float(calc.get("f3", 0.0))
            t1 = float(calc.get("t1s_min", 0.0))
            t2 = float(calc.get("t2s_min", 0.0))
            t3 = float(calc.get("t3s_min", 0.0))
            T = float(calc.get("T_total_min", 0.0))
        except Exception:
            f1 = f2 = f3 = t1 = t2 = t3 = T = 0.0
        text = (
            "RÉFÉRENCE MAINTENANCE (L/v)\n\n"
            "Principe : pour chaque tapis i, le temps est tᵢ = Lconvᵢ · Cᵢ / UIᵢ.\n"
            "L’application convertit automatiquement les valeurs UI (IHM x100) en Hz, "
            "et affiche t₁, t₂, t₃ ainsi que le total.\n\n"
            f"Dernier calcul : f = {f1:.2f}/{f2:.2f}/{f3:.2f} Hz • t = {t1:.2f}/{t2:.2f}/{t3:.2f} min • Total = {T:.2f} min."
        )
        win = tk.Toplevel(self)
        win.title("Explications — Référence maintenance (L/v)")
        win.configure(bg=BG)
        win.geometry("900x640")
        txt = scrolledtext.ScrolledText(win, wrap="word", font=("Consolas", 11), bg=CARD, fg=TEXT, insertbackground=TEXT)
        txt.pack(fill="both", expand=True, padx=12, pady=12)
        txt.insert("1.0", text)
        txt.configure(state="disabled")
        bar = ttk.Frame(win, style="TFrame")
        bar.pack(fill="x", padx=12, pady=(0, 12))
        def _copy():
            self.clipboard_clear()
            self.clipboard_append(text)
            self.toast("Explications copiées")
        def _export():
            path = filedialog.asksaveasfilename(title="Exporter les explications", defaultextension=".txt", filetypes=[("Fichier texte", "*.txt"), ("Tous fichiers", "*.*")])
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                except Exception as e:
                    self._show_error(f"Export TXT impossible : {e}")
                else:
                    self.toast(f"Export TXT : {path}")
        ttk.Button(bar, text="Copier dans le presse-papiers", command=_copy, style="Ghost.TButton").pack(side="left")
        ttk.Button(bar, text="Exporter en .txt", command=_export, style="Ghost.TButton").pack(side="left", padx=(8, 0))


def main() -> None:
    app = FourApp()
    app.mainloop()


__all__ = ["FourApp", "main"]

