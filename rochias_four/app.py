"""Main Tkinter application for the Rochias four dashboard."""

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

from .calibration import (
    D_R,
    K1_R,
    K2_R,
    K3_R,
    METRICS_EXACT,
    METRICS_REG,
)
from .config import DEFAULT_INPUTS, PREFS_PATH, TICK_SECONDS
from .calc_models import (
    correction_recouvrement,
    parts_independantes,
    parts_reparties,
    total_minutes_anchor,
    total_minutes_synergy,
)
from .calibration_overrides import load_anchor_from_disk, get_current_anchor
from .calculations import compute_simulation_plan, thickness_and_accum
from .flow import GapEvent, holes_for_all_belts
from .theme import (
    ACCENT,
    ACCENT_DISABLED,
    ACCENT_HOVER,
    BG,
    BORDER,
    CARD,
    FIELD,
    FIELD_FOCUS,
    GLOW,
    SECONDARY,
    SECONDARY_HOVER,
    SUBTEXT,
    TEXT,
)
from .theme_manager import ThemeManager, STYLE_NAMES
from .utils import fmt_hms, fmt_minutes, parse_hz
from .widgets import Collapsible, SegmentedBar, Tooltip, VScrollFrame
from .graphs import GraphWindow
from .calibration_window import CalibrationWindow
from .speed_overrides import load_speed_from_disk


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
        self.theme.load_saved_or("light")
        self._update_theme_palette()
        self._sync_theme_attributes()

        self.title("Four • 3 Tapis — Calcul & Barres (Temps réel)")
        self.configure(bg=BG)
        # Tu peux garder la géométrie initiale si tu veux
        # self.geometry("1180x760")
        self.minsize(1100, 700)

        self._toasts = []
        self._cards = []
        self._responsive_labels = []
        self.compact_mode = False
        self.feed_events: list[GapEvent] = []
        self.feed_on = True
        self.accum_badges: list[ttk.Label | None] = []
        self.bars_heading_label: ttk.Label | None = None

        self._init_styles()
        self._apply_option_defaults()

        # États animation
        self.animating = False
        self.paused = False
        self.seg_idx = 0
        self.seg_start = 0.0
        self.seg_durations = [0.0, 0.0, 0.0]   # secondes réelles (t1,t2,t3)
        self.seg_distances = [0.0, 0.0, 0.0]   # longueurs équivalentes (K1,K2,K3)
        self.seg_speeds = [0.0, 0.0, 0.0]      # vitesses (Hz) des 3 tapis
        self._after_id = None       # gestion propre du timer Tk
        self.alpha = 1.0            # facteur d’échelle diag (Σ ancrage → T_modèle)
        self.last_calc = None       # stockage du dernier calcul pour Explications
        self.total_duration = 0.0
        self.notified_stage1 = False
        self.notified_stage2 = False
        self.notified_exit = False

        self.stat_cards = {}
        self.stage_status = []
        self.kpi_labels = {}
        self.stage_rows = []
        self.graph_window = None
        self.operator_mode = True
        self.parts_mode = tk.StringVar(value="repartition")

        self.logo_img = None
        self._error_after = None

        self._load_logo()

        # UI
        self._build_ui()
        load_speed_from_disk()
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
        # Ajuste la taille à ce que l'écran peut afficher, sans couper
        self.after(0, self._fit_to_screen)

        self.parts_mode.trace_add("write", self._on_parts_mode_changed)

    @staticmethod
    def _blend_colors(color_a: str, color_b: str, ratio: float) -> str:
        ratio = max(0.0, min(1.0, float(ratio)))
        def _to_rgb(value: str) -> tuple[int, int, int]:
            value = value.strip().lstrip("#")
            if len(value) != 6:
                value = value[:6].ljust(6, "0")
            return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))

        r1, g1, b1 = _to_rgb(color_a)
        r2, g2, b2 = _to_rgb(color_b)
        r = round(r1 + (r2 - r1) * ratio)
        g = round(g1 + (g2 - g1) * ratio)
        b = round(b1 + (b2 - b1) * ratio)
        return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"

    def _update_theme_palette(self):
        from . import theme as theme_constants

        colors = self.theme.colors
        blend = self._blend_colors
        lighten = lambda c, amount: blend(c, "#FFFFFF", amount)
        darken = lambda c, amount: blend(c, "#000000", amount)

        secondary = blend(colors["panel"], colors["surface"], 0.5)
        track = blend(colors["panel"], colors["bg"], 0.5)
        accent_hover = darken(colors["accent"], 0.2) if self.theme.current == "light" else lighten(colors["accent"], 0.2)
        secondary_hover_target = colors["surface"] if self.theme.current == "dark_rouge" else colors["bg"]

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
            "HOLE": blend(colors["warn"], colors["panel"], 0.6),
            "HOLE_BORDER": colors["warn"],
        }

        self._palette = palette
        for key, value in palette.items():
            setattr(theme_constants, key, value)

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
        self.theme.toggle(("light", "dark_rouge"))
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

    def refresh_after_calibration(self):
        # Recalcule le scénario courant avec les overrides qui viennent d'être appliqués
        # (tes calculs de temps ne changent pas ; si tu affiches des vitesses dans l'UI/graph,
        # tu peux relire get_current_speedset() ici).
        self.on_calculer()

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
        self.e1.delete(0, tk.END); self.e1.insert(0, data.get("f1", DEFAULT_INPUTS[0]))
        self.e2.delete(0, tk.END); self.e2.insert(0, data.get("f2", DEFAULT_INPUTS[1]))
        self.e3.delete(0, tk.END); self.e3.insert(0, data.get("f3", DEFAULT_INPUTS[2]))
        if data.get("compact"):
            self.set_density(True)
        geom = data.get("geom")
        if geom:
            self.geometry(geom)

    def _on_close(self):
        self._save_prefs()
        self._clear_toasts()
        self.destroy()

    def _on_resize_wrapping(self, event):
        width = max(0, event.width)
        for label, ratio in self._responsive_labels:
            try:
                label.configure(wraplength=int(width * ratio))
            except Exception:
                pass

    def set_density(self, compact: bool):
        compact = bool(compact)
        self.compact_mode = compact
        pad = (12, 8) if compact else (20, 16)
        hero_value_size = 20 if compact else 22
        card_heading_size = 13 if compact else 14
        self.style.configure("CardHeading.TLabel", font=("Segoe UI Semibold", card_heading_size))
        self.style.configure(
            "HeroStatValue.TLabel",
            font=("Segoe UI", hero_value_size, "bold"),
        )
        self.style.configure(
            "HeroStatLabel.TLabel",
            font=("Segoe UI Semibold", 9 if compact else 10),
        )
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
        style.configure("Mono.TLabel", background=CARD, foreground="#3b7e63", font=("Consolas", 11))
        style.configure("Status.TLabel", background=CARD, foreground=SUBTEXT, font=("Consolas", 11))
        style.configure("Footer.TLabel", background=BG, foreground=SUBTEXT, font=("Segoe UI", 10))

        style.configure("Dark.TSeparator", background=BORDER)
        style.configure("TSeparator", background=BORDER)

        style.configure("StatCard.TFrame", background=SECONDARY, relief="flat")
        style.configure("StatCardAccent.TFrame", background="#bbf7d0", relief="flat")
        style.configure("StatTitle.TLabel", background=SECONDARY, foreground=SUBTEXT, font=("Segoe UI Semibold", 10))
        style.configure("StatTitleAccent.TLabel", background="#bbf7d0", foreground="#065f46", font=("Segoe UI Semibold", 10))
        style.configure("StatValue.TLabel", background=SECONDARY, foreground=TEXT, font=("Segoe UI", 18, "bold"))
        style.configure("StatValueAccent.TLabel", background="#bbf7d0", foreground="#064e3b", font=("Segoe UI", 20, "bold"))
        style.configure("StatDetail.TLabel", background=SECONDARY, foreground=SUBTEXT, font=("Consolas", 11))
        style.configure("StatDetailAccent.TLabel", background="#bbf7d0", foreground="#065f46", font=("Consolas", 11))

        style.configure("ParamName.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI Semibold", 10))
        style.configure("ParamValue.TLabel", background=CARD, foreground=TEXT, font=("Consolas", 11))

        style.configure("HeroStat.TFrame", background="#ecfdf5", relief="flat")
        style.configure("HeroStatValue.TLabel", background="#ecfdf5", foreground=ACCENT, font=("Segoe UI", 22, "bold"))
        style.configure("HeroStatLabel.TLabel", background="#ecfdf5", foreground=SUBTEXT, font=("Segoe UI Semibold", 10))
        style.configure("HeroStatDetail.TLabel", background="#ecfdf5", foreground=SUBTEXT, font=("Segoe UI", 10))

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
            foreground=[("disabled", "#0f5132")],
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
            background=[("active", SECONDARY_HOVER), ("disabled", "#edf6f0")],
            foreground=[("disabled", "#7c8f82")],
        )

        style.configure(
            "Chip.TButton",
            background="#f0fdf4",
            foreground=ACCENT,
            padding=(12, 6),
            borderwidth=0,
            focusthickness=0,
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Chip.TButton",
            background=[("active", "#dcfce7"), ("disabled", "#f0f1ef")],
            foreground=[("disabled", "#7c8f82")],
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
            foreground=[("disabled", "#7c8f82")],
        )

        badge_font = ("Segoe UI Semibold", 10)
        style.configure("BadgeIdle.TLabel", background=SECONDARY, foreground=SUBTEXT, font=badge_font, padding=(10, 2))
        style.configure("BadgeReady.TLabel", background="#bbf7d0", foreground=ACCENT, font=badge_font, padding=(10, 2))
        style.configure("BadgeActive.TLabel", background=ACCENT, foreground="#ffffff", font=badge_font, padding=(10, 2))
        style.configure("BadgeDone.TLabel", background=ACCENT_HOVER, foreground="#ffffff", font=badge_font, padding=(10, 2))
        style.configure("BadgePause.TLabel", background=ACCENT_DISABLED, foreground=TEXT, font=badge_font, padding=(10, 2))
        style.configure("BadgeNeutral.TLabel", background="#d1eddb", foreground=TEXT, font=badge_font, padding=(10, 2))

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
        wrapper = tk.Frame(
            parent,
            bg=BORDER,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1,
            bd=0,
        )
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

    def _update_stat_card(self, key, main_text, detail_text="--"):
        labels = self.stat_cards.get(key)
        if not labels:
            return
        value_lbl, detail_lbl = labels
        value_lbl.config(text=main_text)
        detail_lbl.config(text=detail_text)

    def _reset_stat_cards(self):
        for value_lbl, detail_lbl in self.stat_cards.values():
            value_lbl.config(text="--")
            detail_lbl.config(text="--")

    def _reset_stage_statuses(self):
        for idx in range(len(self.stage_status)):
            self._set_stage_status(idx, "idle")

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

    def _update_kpi(self, key, main_text, detail_text="--"):
        labels = self.kpi_labels.get(key)
        if not labels:
            return
        value_lbl, detail_lbl = labels
        value_lbl.config(text=main_text)
        detail_lbl.config(text=detail_text)

    def _reset_kpis(self):
        for value_lbl, detail_lbl in self.kpi_labels.values():
            value_lbl.config(text="--")
            detail_lbl.config(text="--")

    def _hide_correction_row(self):
        if hasattr(self, "correction_row") and self.correction_row.winfo_manager():
            try:
                self.correction_row.pack_forget()
            except Exception:
                pass
        if hasattr(self, "correction_value"):
            self.correction_value.config(text="--")
        if hasattr(self, "correction_detail"):
            self.correction_detail.config(text="--")

    def _show_correction_row(self, corr: float, sum_indep: float):
        if not hasattr(self, "correction_row"):
            return
        if not self.correction_row.winfo_manager():
            try:
                self.correction_row.pack(fill="x", pady=6)
            except Exception:
                pass
        self.correction_value.config(text=f"{corr:+.2f} min")
        self.correction_detail.config(
            text=f"Σ indépendantes = {sum_indep:.2f} min | {fmt_hms(sum_indep * 60)}"
        )

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
            ttk.Label(hero, image=self.logo_img, style="Logo.TLabel").grid(
                row=0, column=0, rowspan=2, sticky="nw", padx=(0, 20)
            )

        title = ttk.Label(hero, text="Simulation four 3 tapis (temps réel)", style="HeroTitle.TLabel")
        title.grid(row=0, column=1, sticky="w")

        badge_box = ttk.Frame(hero, style="CardInner.TFrame")
        badge_box.grid(row=0, column=2, sticky="e", padx=(12, 0))
        ttk.Label(badge_box, text="Mode temps réel", style="BadgeReady.TLabel").pack(side="left", padx=(0, 8))
        ttk.Label(badge_box, text="Modèle synergie (calibré)", style="BadgeNeutral.TLabel").pack(side="left")
        self.density_button = ttk.Button(
            badge_box,
            text="Mode compact",
            style="Chip.TButton",
            command=lambda: self.set_density(not self.compact_mode),
        )
        self.density_button.pack(side="left", padx=(8, 0))
        self.mode_button = ttk.Button(
            badge_box,
            text="Mode opérateur",
            style="Chip.TButton",
            command=lambda: self.set_operator_mode(not self.operator_mode),
        )
        self.mode_button.pack(side="left", padx=(8, 0))

        hero_stats = ttk.Frame(hero, style="CardInner.TFrame")
        hero_stats.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        hero_stats.columnconfigure((0, 1, 2, 3), weight=1, uniform="hero")

        kpi_defs = [
            ("total", "Temps total"),
            ("t1", "Tapis 1"),
            ("t2", "Tapis 2"),
            ("t3", "Tapis 3"),
        ]
        for idx, (key, label) in enumerate(kpi_defs):
            pill = ttk.Frame(hero_stats, style="HeroStat.TFrame", padding=(16, 12))
            pill.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 12, 0))
            ttk.Label(pill, text=label, style="HeroStatLabel.TLabel").pack(anchor="w")
            value = ttk.Label(pill, text="--", style="HeroStatValue.TLabel")
            value.pack(anchor="w", pady=(4, 0))
            detail = ttk.Label(pill, text="--", style="HeroStatDetail.TLabel")
            detail.pack(anchor="w", pady=(2, 0))
            self.kpi_labels[key] = (value, detail)
        Tooltip(self.kpi_labels["total"][0], "Temps total modèle 1/f + synergie.")
        Tooltip(self.kpi_labels["t1"][0], "Durée affichée selon le mode de parts sélectionné.")
        Tooltip(self.kpi_labels["t2"][0], "Durée affichée selon le mode de parts sélectionné.")
        Tooltip(self.kpi_labels["t3"][0], "Durée affichée selon le mode de parts sélectionné.")

        body = VScrollFrame(self)
        body.pack(fill="both", expand=True)
        self.body_frame = body

        pcard = self._card(body.inner, fill="x", expand=False, padx=18, pady=8, padding=(24, 20))
        self.bars_heading_label = ttk.Label(
            pcard,
            text="Barres de chargement — Durée tapis (répartition)",
            style="CardHeading.TLabel",
        )
        self.bars_heading_label.pack(anchor="w", pady=(0, 12))

        self.bars = []
        self.bar_texts = []
        self.stage_status = []
        self.accum_badges = []

        for i in range(3):
            holder = ttk.Frame(pcard, style="CardInner.TFrame")
            holder.pack(fill="x", pady=10)
            title_row = ttk.Frame(holder, style="CardInner.TFrame")
            title_row.pack(fill="x")
            ttk.Label(title_row, text=f"Tapis {i+1}", style="Card.TLabel").pack(side="left")
            status_lbl = ttk.Label(title_row, text="⏳ En attente", style="BadgeIdle.TLabel")
            status_lbl.pack(side="left", padx=(12, 0))
            accum_lbl = ttk.Label(title_row, text="", style="BadgeNeutral.TLabel")
            if i > 0:
                accum_lbl.pack(side="left", padx=(8, 0))
            self.accum_badges.append(accum_lbl if i > 0 else None)
            bar = SegmentedBar(holder, height=30)
            bar.pack(fill="x", expand=True, pady=(8, 4))
            bar.set_markers([1 / 3, 2 / 3], ["", ""])
            first_cell = (i * 3) + 1
            cell_labels = [((2 * j + 1) / 6, f"Cellule {first_cell + j}") for j in range(3)]
            bar.set_cell_labels(cell_labels)
            txt = ttk.Label(holder, text="En attente", style="Status.TLabel", anchor="w", wraplength=860)
            txt.pack(anchor="w")
            self.stage_status.append(status_lbl)
            self.bars.append(bar)
            self.bar_texts.append(txt)

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
        self.e1 = ttk.Spinbox(
            g,
            from_=1,
            to=120,
            increment=0.01,
            format="%.2f",
            width=10,
            style="Dark.TSpinbox",
            validate="key",
            validatecommand=vcmd,
        )
        self.e1.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(g, text="Tapis 2 : Hz =", style="Card.TLabel").grid(row=1, column=0, sticky="e", padx=(0, 12), pady=6)
        self.e2 = ttk.Spinbox(
            g,
            from_=1,
            to=120,
            increment=0.01,
            format="%.2f",
            width=10,
            style="Dark.TSpinbox",
            validate="key",
            validatecommand=vcmd,
        )
        self.e2.grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(g, text="Tapis 3 : Hz =", style="Card.TLabel").grid(row=2, column=0, sticky="e", padx=(0, 12), pady=6)
        self.e3 = ttk.Spinbox(
            g,
            from_=1,
            to=120,
            increment=0.01,
            format="%.2f",
            width=10,
            style="Dark.TSpinbox",
            validate="key",
            validatecommand=vcmd,
        )
        self.e3.grid(row=2, column=1, sticky="w", pady=6)

        ttk.Label(
            g,
            text="Épaisseur entrée h0 (cm) =",
            style="Card.TLabel",
        ).grid(row=3, column=0, sticky="e", padx=(0, 12), pady=6)
        self.h0 = ttk.Spinbox(
            g,
            from_=0.10,
            to=20.0,
            increment=0.10,
            format="%.2f",
            width=10,
            style="Dark.TSpinbox",
            validate="key",
            validatecommand=vcmd,
        )
        self.h0.grid(row=3, column=1, sticky="w", pady=6)
        self.h0.delete(0, tk.END)
        self.h0.insert(0, "2.00")

        ttk.Label(
            card_in,
            text="Astuce : 40.00 ou 4000 (IHM). >200 = IHM/100.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 12))

        self.err_box = ttk.Label(card_in, text="", style="Hint.TLabel")
        self.err_box.pack(anchor="w", pady=(0, 0))

        btns = ttk.Frame(card_in, style="CardInner.TFrame")
        btns.pack(fill="x", pady=(4, 8))
        btns.columnconfigure(7, weight=1)
        self.btn_calculer = ttk.Button(btns, text="Calculer", command=self.on_calculer, style="Accent.TButton")
        self.btn_calculer.grid(row=0, column=0, padx=(0, 12), pady=2, sticky="w")
        self.btn_start = ttk.Button(
            btns,
            text="▶ Démarrer (temps réel)",
            command=self.on_start,
            state="disabled",
            style="Accent.TButton",
        )
        self.btn_start.grid(row=0, column=1, padx=(0, 12), pady=2, sticky="w")
        self.btn_pause = ttk.Button(
            btns,
            text="⏸ Pause",
            command=self.on_pause,
            state="disabled",
            style="Ghost.TButton",
        )
        self.btn_pause.grid(row=0, column=2, padx=(0, 12), pady=2, sticky="w")
        ttk.Button(btns, text="↺ Réinitialiser", command=self.on_reset, style="Ghost.TButton").grid(row=0, column=3, pady=2, sticky="w")
        ttk.Button(btns, text="ℹ Explications", command=self.on_explanations, style="Ghost.TButton").grid(row=0, column=4, pady=2, sticky="e")
        ttk.Button(btns, text="Calibrer…", command=lambda: CalibrationWindow(self), style="Ghost.TButton").grid(row=0, column=5, padx=(12, 0), pady=2, sticky="e")
        ttk.Button(btns, text="📈 Graphiques", command=self.on_graphs, style="Ghost.TButton").grid(row=0, column=6, pady=2, sticky="e")
        ttk.Button(btns, text="Thème", style=STYLE_NAMES["Button"], command=self.on_toggle_theme).grid(row=0, column=7, padx=(12, 0), pady=2, sticky="e")

        self.btn_feed_stop = ttk.Button(
            btns,
            text="⛔ Arrêt alimentation",
            command=self.on_feed_stop,
            state="disabled",
            style="Ghost.TButton",
        )
        self.btn_feed_stop.grid(row=1, column=0, padx=(0, 12), pady=(8, 2), sticky="w")

        self.btn_feed_resume = ttk.Button(
            btns,
            text="✅ Reprise alimentation",
            command=self.on_feed_resume,
            state="disabled",
            style="Ghost.TButton",
        )
        self.btn_feed_resume.grid(row=1, column=1, padx=(0, 12), pady=(8, 2), sticky="w")

        self.details = Collapsible(body.inner, title="Détails résultats & analyse", open=False)
        self.details.pack(fill="x", padx=18, pady=(8, 0))

        card_out = self._card(self.details.body, fill="both", expand=True)
        card_out.bind("<Configure>", self._on_resize_wrapping)
        card_out.columnconfigure(0, weight=1)
        ttk.Label(card_out, text="Résultats", style="CardHeading.TLabel").pack(anchor="w", pady=(0, 12))
        self.lbl_total_big = ttk.Label(card_out, text="Temps total (modèle synergie) : --", style="Result.TLabel")
        self.lbl_total_big.pack(anchor="w", pady=(0, 10))
        ttk.Label(
            card_out,
            text="Modèle : T = B + K1/f1 + K2/f2 + K3/f3 + S/(f1·f2·f3). Régression 1/f + synergie pour le total ; répartition pondérée par ancrage.",
            style="HeroSub.TLabel",
            wraplength=820,
            justify="left",
        ).pack(anchor="w", pady=(4, 2))
        ttk.Label(
            card_out,
            text="Tableau de bord visuel pour suivre la cuisson et les tapis en parallèle.",
            style="Subtle.TLabel",
            wraplength=820,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))
        self.lbl_analysis_info = ttk.Label(
            card_out,
            text="",
            style="Hint.TLabel",
            wraplength=820,
            justify="left",
        )
        self.lbl_analysis_info.pack(anchor="w", pady=(0, 12))
        self._responsive_labels.append((self.lbl_analysis_info, 0.85))

        parts_selector = ttk.Frame(card_out, style="CardInner.TFrame")
        parts_selector.pack(fill="x", pady=(0, 12))
        ttk.Label(parts_selector, text="Parts :", style="HeroSub.TLabel").pack(side="left")
        ttk.Radiobutton(
            parts_selector,
            text="Répartition du total",
            value="repartition",
            variable=self.parts_mode,
            command=self._on_parts_mode_changed,
        ).pack(side="left", padx=(12, 0))
        ttk.Radiobutton(
            parts_selector,
            text="Indépendant (diag)",
            value="independant",
            variable=self.parts_mode,
            command=self._on_parts_mode_changed,
        ).pack(side="left", padx=(12, 0))

        export_row = ttk.Frame(card_out, style="CardInner.TFrame")
        export_row.pack(fill="x", pady=(0, 10))
        ttk.Button(export_row, text="⬇ Export CSV", command=self.export_csv, style="Ghost.TButton").pack(side="left")
        ttk.Button(export_row, text="🖨 Export PS", command=self.export_bars_ps, style="Ghost.TButton").pack(side="left", padx=(8, 0))

        self.parts_section_label = ttk.Label(
            card_out,
            text="Répartition du total (somme = T)",
            style="CardHeading.TLabel",
        )
        self.parts_section_label.pack(anchor="w", pady=(8, 0))

        stage_list = ttk.Frame(card_out, style="CardInner.TFrame")
        stage_list.pack(fill="x", pady=(0, 12))
        self.stage_rows = []
        for i in range(3):
            row = ttk.Frame(stage_list, style="StageRow.TFrame")
            row.pack(fill="x", pady=6)
            row.columnconfigure(2, weight=1)
            ttk.Label(row, text=f"Tapis {i+1}", style="StageTitle.TLabel").grid(row=0, column=0, rowspan=2, sticky="w")
            freq_lbl = ttk.Label(row, text="-- Hz", style="StageFreq.TLabel")
            freq_lbl.grid(row=0, column=1, sticky="w", padx=(12, 0))
            time_lbl = ttk.Label(row, text="--", style="StageTime.TLabel")
            time_lbl.grid(row=0, column=2, sticky="e")
            detail_lbl = ttk.Label(row, text="--", style="StageTimeDetail.TLabel")
            detail_lbl.grid(row=1, column=2, sticky="e")
            self.stage_rows.append({"freq": freq_lbl, "time": time_lbl, "detail": detail_lbl})

        self.correction_row = ttk.Frame(stage_list, style="StageRow.TFrame")
        self.correction_row.columnconfigure(2, weight=1)
        self.correction_title = ttk.Label(
            self.correction_row,
            text="Correction de recouvrement",
            style="StageTitle.TLabel",
        )
        self.correction_title.grid(row=0, column=0, rowspan=2, sticky="w")
        self.correction_value = ttk.Label(self.correction_row, text="--", style="StageTime.TLabel")
        self.correction_value.grid(row=0, column=2, sticky="e")
        self.correction_detail = ttk.Label(
            self.correction_row,
            text="--",
            style="StageTimeDetail.TLabel",
        )
        self.correction_detail.grid(row=1, column=2, sticky="e")

        ttk.Separator(card_out, style="Dark.TSeparator").pack(fill="x", pady=8)
        ttk.Label(card_out, text="Analyse modèle", style="Subtle.TLabel").pack(anchor="w")
        stats = ttk.Frame(card_out, style="CardInner.TFrame")
        stats.pack(fill="x", pady=(4, 16))
        stat_defs = [
            ("ls", "Total LS (4 paramètres)", "StatCard.TFrame", "StatTitle.TLabel", "StatValue.TLabel", "StatDetail.TLabel"),
            ("sum", "Somme t_i (LS)", "StatCard.TFrame", "StatTitle.TLabel", "StatValue.TLabel", "StatDetail.TLabel"),
            ("alpha", "Facteurs α / β", "StatCard.TFrame", "StatTitle.TLabel", "StatValue.TLabel", "StatDetail.TLabel"),
            ("delta", "Delta total - LS", "StatCardAccent.TFrame", "StatTitleAccent.TLabel", "StatValueAccent.TLabel", "StatDetailAccent.TLabel"),
        ]
        for col, (key, title, frame_style, title_style, value_style, detail_style) in enumerate(stat_defs):
            self.stat_cards[key] = self._create_stat_card(
                stats,
                col,
                title,
                frame_style=frame_style,
                title_style=title_style,
                value_style=value_style,
                detail_style=detail_style,
            )

        params = ttk.Frame(card_out, style="CardInner.TFrame")
        params.pack(fill="x", pady=(8, 0))
        ttk.Label(params, text="Paramètres de calibrage", style="Subtle.TLabel").pack(anchor="w")
        params_grid = ttk.Frame(params, style="CardInner.TFrame")
        params_grid.pack(anchor="w", pady=(4, 0))
        param_values = [
            ("d (offset)", f"{D_R:+.3f} min"),
            ("K1 (tapis 1)", f"{K1_R:.3f}"),
            ("K2 (tapis 2)", f"{K2_R:.3f}"),
            ("K3 (tapis 3)", f"{K3_R:.3f}"),
            ("MAE (LS)", f"{METRICS_REG['MAE']:.2f} min"),
            ("RMSE (LS)", f"{METRICS_REG['RMSE']:.2f} min"),
            ("R2 (LS)", f"{METRICS_REG['R2']:.3f}"),
            ("MAE (interp. exacte)", f"{METRICS_EXACT['MAE']:.2e} min"),
            ("RMSE (interp. exacte)", f"{METRICS_EXACT['RMSE']:.2e} min"),
            ("MAX abs (interp. exacte)", f"{METRICS_EXACT['MAXABS']:.2e} min"),
        ]
        for name, value in param_values:
            row = ttk.Frame(params_grid, style="CardInner.TFrame")
            row.pack(anchor="w", pady=2)
            ttk.Label(row, text=name, style="ParamName.TLabel").pack(side="left")
            ttk.Label(row, text=value, style="ParamValue.TLabel").pack(side="left", padx=(12, 0))

        footer = ttk.Frame(body.inner, style="TFrame")
        footer.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Label(
            footer,
            text="Astuce : lance un calcul pour activer la simulation en temps réel.",
            style="Footer.TLabel",
        ).pack(anchor="w")

        self._reset_kpis()
        self._reset_stat_cards()
        self._reset_stage_statuses()

    def set_operator_mode(self, on: bool):
        self.operator_mode = bool(on)
        if hasattr(self, "details"):
            try:
                self.details.set_open(not self.operator_mode)
            except Exception:
                pass
        if hasattr(self, "mode_button"):
            if self.operator_mode:
                self.mode_button.config(text="Mode ingénieur")
            else:
                self.mode_button.config(text="Mode opérateur")

    def _on_parts_mode_changed(self, *_):
        mode = self.parts_mode.get()
        if mode not in {"repartition", "independant"}:
            self.parts_mode.set("repartition")
            mode = "repartition"
        if not self.last_calc:
            if hasattr(self, "parts_section_label"):
                if mode == "independant":
                    self.parts_section_label.config(
                        text="Contribution équivalente (diagnostic) (ne somme pas au total)"
                    )
                    self._hide_correction_row()
                else:
                    self.parts_section_label.config(text="Répartition du total (somme = T)")
                    self._hide_correction_row()
            return
        self._apply_parts_mode()

    def _update_bar_targets(self, mode: str | None = None):
        if not self.last_calc:
            return
        if mode is None:
            mode = self.parts_mode.get()
        legend = "répartition" if mode != "independant" else "indépendant"
        if hasattr(self, "bars_heading_label"):
            self.bars_heading_label.config(
                text=f"Barres de chargement — Durée tapis ({legend})"
            )
        targets = None
        if mode == "independant":
            targets = self.last_calc.get("parts_indep")
        else:
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
            freq_raw = self.seg_speeds[idx] if idx < len(self.seg_speeds) else 0.0
            try:
                freq = float(freq_raw)
            except (TypeError, ValueError):
                freq = 0.0
            target_sec = seconds[idx]
            bar.set_total_distance(target_sec)
            bar.set_progress(0.0)
            txt.config(
                text=(
                    f"0.0% | vitesse {freq:.2f} Hz | 00:00:00 / {fmt_hms(target_sec)} | en attente"
                )
            )

    def _apply_parts_mode(self):
        data = self.last_calc
        if not data:
            return
        mode = self.parts_mode.get()
        total = data.get("T_total", 0.0)
        f_values = (data.get("f1"), data.get("f2"), data.get("f3"))
        if mode == "independant":
            parts = data.get("parts_indep")
            heading = "Contribution équivalente (diagnostic) (ne somme pas au total)"
            corr = data.get("correction")
            sum_indep = data.get("sum_indep")
            if parts is None:
                parts = parts_independantes(*f_values)
            if corr is None:
                corr = correction_recouvrement(total, *f_values)
            if sum_indep is None and parts is not None:
                sum_indep = sum(parts)
            if sum_indep is None:
                sum_indep = 0.0
            self._show_correction_row(corr or 0.0, sum_indep)
        else:
            parts = data.get("parts_reparties")
            heading = "Répartition du total (somme = T)"
            if parts is None:
                parts = parts_reparties(total, *f_values)
            self._hide_correction_row()
        if parts is None:
            return
        parts = tuple(parts)
        if hasattr(self, "parts_section_label"):
            self.parts_section_label.config(text=heading)
        for row, part, freq in zip(self.stage_rows, parts, f_values):
            row["time"].config(text=fmt_minutes(part))
            row["detail"].config(text=f"{part:.2f} min | {fmt_hms(part * 60)}")
            if freq is not None:
                row["freq"].config(text=f"{freq:.2f} Hz")
        self._update_kpi(
            "t1",
            fmt_minutes(parts[0]),
            f"{parts[0]:.2f} min | {fmt_hms(parts[0] * 60)}",
        )
        self._update_kpi(
            "t2",
            fmt_minutes(parts[1]),
            f"{parts[1]:.2f} min | {fmt_hms(parts[1] * 60)}",
        )
        self._update_kpi(
            "t3",
            fmt_minutes(parts[2]),
            f"{parts[2]:.2f} min | {fmt_hms(parts[2] * 60)}",
        )
        data["parts_mode"] = mode
        self._update_bar_targets(mode)

    # ---------- Actions ----------
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
            except Exception:
                pass
        for row in self.stage_rows:
            row["freq"].config(text="-- Hz")
            row["time"].config(text="--")
            row["detail"].config(text="--")
        self.feed_events.clear()
        self.feed_on = True
        if hasattr(self, "btn_feed_stop"):
            self.btn_feed_stop.config(state="disabled")
        if hasattr(self, "btn_feed_resume"):
            self.btn_feed_resume.config(state="disabled")
        for badge in self.accum_badges:
            if badge is not None:
                badge.config(text="", style="BadgeNeutral.TLabel")
        self.lbl_total_big.config(text="Temps total (modèle synergie) : --")
        if hasattr(self, "parts_section_label"):
            self.parts_section_label.config(text="Répartition du total (somme = T)")
        self._hide_correction_row()
        self.lbl_analysis_info.config(text="")
        if self.bars_heading_label is not None:
            self.bars_heading_label.config(text="Barres de chargement — Durée tapis (répartition)")
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="disabled", text="⏸ Pause")
        self.btn_calculer.config(state="normal")
        self.seg_durations = [0.0, 0.0, 0.0]
        self.seg_distances = [0.0, 0.0, 0.0]
        self.seg_speeds = [0.0, 0.0, 0.0]
        self.total_duration = 0.0
        self.notified_stage1 = False
        self.notified_stage2 = False
        self.notified_exit = False
        self.last_calc = None
        self._reset_kpis()
        self._reset_stat_cards()
        self._reset_stage_statuses()

    def on_graphs(self):
        # Sécurise : force un calcul rapide si rien n'est prêt
        if not self.last_calc:
            try:
                self.on_calculer()
            except Exception:
                pass
        try:
            if self.graph_window and self.graph_window.winfo_exists():
                self.graph_window.lift()
                self.graph_window.redraw_with_theme(self.theme)
            else:
                self.graph_window = GraphWindow(self)
        except Exception as e:
            self._show_error(f"Impossible d'ouvrir le graphique : {e}")

    def refresh_after_calibration(self):
        """Recalcule immédiatement en relisant les ancrages courants."""
        try:
            self.on_calculer()
        except Exception:
            pass

    def on_calculer(self):
        if self.animating or self.paused:
            self.on_reset()
        else:
            self._cancel_after()
        self._clear_error()
        try:
            f1 = parse_hz(self.e1.get()); f2 = parse_hz(self.e2.get()); f3 = parse_hz(self.e3.get())
            if f1 <= 0 or f2 <= 0 or f3 <= 0:
                raise ValueError("Les fréquences doivent être > 0.")
        except Exception as e:
            self._show_error(f"Saisie invalide : {e}")
            return

        calc = compute_simulation_plan(f1, f2, f3)
        extras = getattr(calc, "extras", {})
        t1_ls, t2_ls, t3_ls = calc.ls_durations
        T_LS = calc.total_model_minutes
        d, K1, K2, K3 = calc.model_params
        T_model_calc = calc.total_minutes
        T_total = total_minutes_synergy(f1, f2, f3)
        T_exp = T_total
        anchor_terms = tuple(parts_independantes(f1, f2, f3))
        t1_indep, t2_indep, t3_indep = anchor_terms
        anchor_model_total = extras.get("anchor_total_model", float("nan"))
        if not math.isfinite(anchor_model_total):
            anchor_model_total = total_minutes_anchor(f1, f2, f3)
        anchor_model_split = extras.get("anchor_split_model", calc.anchor_durations)
        ols_split = extras.get("ols_split", None)

        if T_total <= 0:
            self._show_error("Temps calculé ≤ 0 : vérifie les entrées et le calibrage.")
            return

        anch = get_current_anchor()
        parts_split = tuple(parts_reparties(T_total, f1, f2, f3))
        t1_rep, t2_rep, t3_rep = parts_split
        correction = correction_recouvrement(T_total, f1, f2, f3)
        sum_base = sum(anchor_terms)
        sum_ls = t1_ls + t2_ls + t3_ls
        alpha_ratio = calc.alpha_anchor
        scale_ls = calc.beta_ls

        self.seg_distances = [stage.distance_target for stage in calc.stages]
        self.seg_speeds = [stage.frequency_hz for stage in calc.stages]
        self.seg_durations = [value * 60.0 for value in parts_split]

        for row, freq in zip(self.stage_rows, (f1, f2, f3)):
            row["freq"].config(text=f"{freq:.2f} Hz")

        self.lbl_total_big.config(
            text=f"Temps total (modèle synergie) : {fmt_minutes(T_total)} | {fmt_hms(T_total * 60)}"
        )

        self.alpha = 1.0

        try:
            h0_cm = float(self.h0.get().replace(",", "."))
            if not (h0_cm > 0):
                raise ValueError
        except Exception:
            h0_cm = 2.0
        th = thickness_and_accum(self.seg_speeds[0], self.seg_speeds[1], self.seg_speeds[2], h0_cm)

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

        delta_total = T_total - T_LS
        delta_parts = T_total - sum_base
        anchor_total_txt = (
            f"{fmt_hms(anchor_model_total * 60)} ({anchor_model_total:.2f} min)"
            if math.isfinite(anchor_model_total)
            else "n/a"
        )
        info = (
            "→ Barres = distances ancrage K'_i (constantes) parcourues à la vitesse f_i.\n"
            f"Total (synergie) : {fmt_hms(T_total * 60)} ({T_total:.2f} min)\n"
            f"Total (ancrage) : {anchor_total_txt} | B_A = {extras.get('anchor_B', float('nan')):+.3f} min\n"
            f"Total modèle 1/f : {fmt_hms(T_LS * 60)} ({T_LS:.2f} min) | d = {d:+.3f} min | β (LS→total) = {scale_ls:.3f}\n"
            f"Σ ancrage brut : {fmt_hms(sum_base * 60)} ({sum_base:.2f} min) | α (synergie/ancrage) = {alpha_ratio:.3f}\n"
            f"Δ total − Σ ancrage : {delta_parts:+.2f} min\n"
            f"K1'={anch.K1:.1f}  K2'={anch.K2:.1f}  K3'={anch.K3:.1f}"
        )
        self.lbl_analysis_info.config(text=info)

        self._update_kpi("total", fmt_minutes(T_total), f"{T_total:.2f} min | {fmt_hms(T_total * 60)}")

        self._update_stat_card("ls", f"{T_LS:.2f} min", fmt_hms(T_LS * 60))
        sum_ls = t1_ls + t2_ls + t3_ls
        self._update_stat_card("sum", f"{sum_ls:.2f} min", fmt_hms(sum_ls * 60))
        alpha_val = f"{alpha_ratio:.3f}" if math.isfinite(alpha_ratio) else "n/a"
        beta_val = f"{scale_ls:.3f}" if math.isfinite(scale_ls) else "n/a"
        self._update_stat_card(
            "alpha",
            f"α={alpha_val} | β={beta_val}",
            f"Σbase {sum_base:.2f} | ΔΣ={delta_parts:+.2f} | ΣLS {sum_ls:.2f}",
        )
        self._update_stat_card("delta", f"{delta_total:+.2f} min", fmt_hms(abs(delta_total) * 60))

        self._set_stage_status(0, "ready")
        self._set_stage_status(1, "idle")
        self._set_stage_status(2, "idle")

        self.last_calc = dict(
            f1=f1, f2=f2, f3=f3,
            d=d, K1=K1, K2=K2, K3=K3,
            t1=t1_ls, t2=t2_ls, t3=t3_ls,
            t1_base=t1_indep, t2_base=t2_indep, t3_base=t3_indep,
            t1_star=t1_indep, t2_star=t2_indep, t3_star=t3_indep,
            T_LS=T_LS, T_exp=T_total, T_total=T_total, T_model_calc=T_model_calc,
            T_total_min=T_total,
            t1s_min=t1_rep, t2s_min=t2_rep, t3s_min=t3_rep,
            alpha=alpha_ratio, beta=scale_ls,
            sum_t=t1_ls + t2_ls + t3_ls, sum_base=sum_base, delta=delta_total,
            delta_parts=delta_parts,
            K1_dist=anch.K1, K2_dist=anch.K2, K3_dist=anch.K3,
            anchor_model_total=anchor_model_total,
            anchor_model_split=anchor_model_split,
            ols_split=ols_split,
            parts_reparties=parts_split,
            parts_indep=anchor_terms,
            correction=correction,
            sum_indep=sum_base,
        )

        self._apply_parts_mode()

        self.total_duration = sum(self.seg_durations)
        self.notified_stage1 = False
        self.notified_stage2 = False
        self.notified_exit = False

        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸ Pause")
        self.btn_calculer.config(state="normal")

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
        self.btn_feed_stop.config(state="normal")
        self.btn_feed_resume.config(state="disabled")
        for bar in self.bars:
            try:
                bar.set_holes([])
            except Exception:
                pass
        self._set_stage_status(0, "active")
        self._set_stage_status(1, "ready")
        self._set_stage_status(2, "idle")
        self._cancel_after()
        self._tick()

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
        self.btn_feed_stop.config(state="disabled")
        self.btn_feed_resume.config(state="normal")
        self.toast("Arrêt alimentation enregistré")

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
        self.btn_feed_stop.config(state="normal")
        self.btn_feed_resume.config(state="disabled")
        self.toast("Reprise alimentation enregistrée")

    def _tick(self):
        if not self.animating or self.paused:
            return

        i = self.seg_idx
        dur = max(1e-6, self.seg_durations[i])
        vitesse = self.seg_speeds[i]
        now = time.perf_counter()
        elapsed = now - self.seg_start
        remaining_current = max(0.0, dur - elapsed)
        remaining_future = sum(self.seg_durations[j] for j in range(i + 1, 3))
        total_remaining = max(0.0, remaining_current + remaining_future)
        if (not self.notified_exit and self.total_duration > 5 * 60 and total_remaining <= 5 * 60):
            self.notified_exit = True
            self.toast("Le produit va sortir du four (≤ 5 min)")
        if elapsed >= dur:
            elapsed = dur
            self.bars[i].set_progress(dur)
            self.bar_texts[i].config(
                text=f"100% | vitesse {vitesse:.2f} Hz | {fmt_hms(dur)} / {fmt_hms(dur)} | terminé"
            )
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
            self.bar_texts[j].config(
                text=f"0.0% | vitesse {vitesse_j:.2f} Hz | 00:00:00 / {fmt_hms(duree_j)} | en cours"
            )
            self._set_stage_status(j, "active")
            if j + 1 < 3:
                self._set_stage_status(j + 1, "ready")
            self._schedule_tick()
            return

        pct = max(0.0, min(1.0, elapsed / dur)) * 100.0
        self.bars[i].set_progress(elapsed)
        self.bar_texts[i].config(
            text=f"{pct:5.1f}% | vitesse {vitesse:.2f} Hz | {fmt_hms(elapsed)} / {fmt_hms(dur)} | en cours"
        )

        try:
            t_now_min = (sum(self.seg_durations[: self.seg_idx]) + max(0.0, elapsed)) / 60.0
            t1m = self.seg_durations[0] / 60.0
            t2m = self.seg_durations[1] / 60.0
            t3m = self.seg_durations[2] / 60.0
            D1, D2, D3 = self.seg_distances
            f1, f2, f3 = self.seg_speeds
            holes = holes_for_all_belts(
                self.feed_events,
                t_now_min,
                t1m,
                t2m,
                t3m,
                f1,
                f2,
                f3,
                D1,
                D2,
                D3,
            )
            for belt_idx, intervals in enumerate(holes):
                try:
                    freq = self.seg_speeds[belt_idx] if belt_idx < len(self.seg_speeds) else 0.0
                    if freq and math.isfinite(freq):
                        converted = [
                            (start / freq * 60.0, end / freq * 60.0)
                            for start, end in intervals
                        ]
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
            self._show_error("Aucun calcul à exporter. Lance d'abord \"Calculer\".")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Tous fichiers", "*.*")],
            title="Exporter résultats",
        )
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
        path = filedialog.asksaveasfilename(
            defaultextension=".ps",
            filetypes=[("PostScript", "*.ps"), ("Tous fichiers", "*.*")],
            title="Exporter barres",
        )
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
        # Récupérer les dernières valeurs ; sinon tenter un calcul rapide
        calc = self.last_calc
        try:
            if calc is None:
                f1 = parse_hz(self.e1.get()); f2 = parse_hz(self.e2.get()); f3 = parse_hz(self.e3.get())
                plan = compute_simulation_plan(f1, f2, f3)
                extras = getattr(plan, "extras", {})
                t1, t2, t3 = plan.ls_durations
                T_LS = plan.total_model_minutes
                T_exp = plan.total_minutes
                d, K1, K2, K3 = plan.model_params
                anch = get_current_anchor()
                anchor_terms = (
                    anch.K1 / f1,
                    anch.K2 / f2,
                    anch.K3 / f3,
                )
                t1_indep, t2_indep, t3_indep = anchor_terms
                sum_base = sum(anchor_terms)
                alpha = plan.alpha_anchor
                sum_ls = t1 + t2 + t3
                beta = plan.beta_ls
                parts_split = parts_reparties(T_exp, f1, f2, f3)
                t1_rep, t2_rep, t3_rep = parts_split
                calc = dict(
                    f1=f1, f2=f2, f3=f3,
                    d=d, K1=K1, K2=K2, K3=K3,
                    t1=t1, t2=t2, t3=t3,
                    t1_base=t1_indep, t2_base=t2_indep, t3_base=t3_indep,
                    t1_star=t1_indep, t2_star=t2_indep, t3_star=t3_indep,
                    T_LS=T_LS, T_exp=T_exp, T_total_min=T_exp, alpha=alpha, beta=beta,
                    sum_t=t1 + t2 + t3,
                    sum_base=sum_base,
                    delta=T_exp - T_LS,
                    delta_parts=T_exp - sum_base,
                    K1_dist=anch.K1, K2_dist=anch.K2, K3_dist=anch.K3,
                    anchor_model_total=extras.get("anchor_total_model"),
                    anchor_model_split=extras.get("anchor_split_model"),
                    ols_split=extras.get("ols_split"),
                    parts_reparties=parts_split,
                    parts_indep=anchor_terms,
                    t1s_min=t1_rep, t2s_min=t2_rep, t3s_min=t3_rep,
                )
        except Exception:
            pass

        # Construire le texte d'explication
        def _as_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return float("nan")

        def _fmt_val(value, unit=" min"):
            return f"{value:.2f}{unit}" if math.isfinite(value) else "n/a"

        if calc:
            f1 = _as_float(calc.get("f1"))
            f2 = _as_float(calc.get("f2"))
            f3 = _as_float(calc.get("f3"))
            T_LS = _as_float(calc.get("T_LS"))
            T_exp = _as_float(calc.get("T_exp"))
            alpha = _as_float(calc.get("alpha"))
            beta = _as_float(calc.get("beta"))
            t1_base = _as_float(calc.get("t1_base"))
            t2_base = _as_float(calc.get("t2_base"))
            t3_base = _as_float(calc.get("t3_base"))
            t1s = _as_float(calc.get("t1_star"))
            t2s = _as_float(calc.get("t2_star"))
            t3s = _as_float(calc.get("t3_star"))
            sum_base = _as_float(calc.get("sum_base"))
            delta_total = _as_float(calc.get("delta"))
            if not math.isfinite(delta_total) and math.isfinite(T_exp) and math.isfinite(T_LS):
                delta_total = T_exp - T_LS
            alpha_values = [t1s, t2s, t3s]
            sum_alpha = sum(alpha_values) if all(math.isfinite(v) for v in alpha_values) else float("nan")
        else:
            f1 = f2 = f3 = float("nan")
            T_LS = T_exp = alpha = beta = sum_base = delta_total = float("nan")
            t1_base = t2_base = t3_base = float("nan")
            t1s = t2s = t3s = float("nan")
            sum_alpha = float("nan")

        text = """GUIDE DÉTAILLÉ — MODÈLE « Four 3 tapis »
0) Notations & unités (glossaire rapide)

𝑓₁, 𝑓₂, 𝑓₃ : fréquences variateur des tapis 1–2–3 en Hz (ou en IHM /100 côté saisie). L’appli accepte 40.00 (Hz) ou 4000 (IHM) ;
 toute valeur >200 est automatiquement divisée par 100.  utils

𝐾₁′, 𝐾₂′, 𝐾₃′ : distances d’ancrage (min·Hz) issues des essais A/B/C/D ; elles servent d’indicateurs pour les rapports d’épaisseur.
 (Dans le code : get_current_anchor().K1, .K2, .K3).  calibration_overrides

𝑑, 𝐾₁, 𝐾₂, 𝐾₃ : paramètres du modèle 1/f (régression LS) donnant le temps total :
𝑇ₘₒd = 𝑑 + 𝐾₁/𝑓₁ + 𝐾₂/𝑓₂ + 𝐾₃/𝑓₃.  calibration

β (LS→total) = 𝑇ₘₒd⁄(𝐾₁/𝑓₁ + 𝐾₂/𝑓₂ + 𝐾₃/𝑓₃).  app

𝛼 (ABCD→modèle) = 𝑇ₘₒd⁄(𝐾₁′/𝑓₁ + 𝐾₂′/𝑓₂ + 𝐾₃′/𝑓₃).  app

𝑡ᵢ (ancrage) = 𝐾ᵢ′/𝑓ᵢ : durées affichées par tapis, indépendantes des autres fréquences.  app

𝑡ᵢ,ᴸˢ = 𝐾ᵢ/𝑓ᵢ (min) : durées issues du modèle LS (utilisées pour le diagnostic).  calibration

𝐷ᵢ = 𝐾ᵢ′ (min·Hz) : distances cibles fixes pour les barres de progression.  widgets

𝑢ᵢ = 𝑓ᵢ/𝐾ᵢ′ : capacités relatives pour l’épaisseur (ℎ₁ = ℎ₀, ℎ₂ = ℎ₀·𝑢₁/𝑢₂, ℎ₃ = ℎ₀·𝑢₁/𝑢₃).  calibration/app


8) « Recette de calcul » (prête à coder / relire dans ton code)

Lire les entrées 𝑓ᵢ via parse_hz :
f1 = parse_hz(e1.get()); f2 = parse_hz(e2.get()); f3 = parse_hz(e3.get()).  utils

Temps total :
t1_ls, t2_ls, t3_ls, T_mod, (d, K1, K2, K3) = compute_times(f1, f2, f3).  calibration

Répartition :
anch = get_current_anchor();
t1 = anch.K1 / f1; t2 = anch.K2 / f2; t3 = anch.K3 / f3 (durées affichées) ;
D1 = anch.K1, etc. (cibles fixes des barres).  app

Diagnostics ancrage :
sum_base = anch.K1/f1 + anch.K2/f2 + anch.K3/f3 ;
alpha_diag = T_mod / sum_base (utilisé uniquement dans l’encart explicatif).  app

Épaisseur (si ℎ₀ fourni) :
u1 = f1/anch.K1; u2 = f2/anch.K2; u3 = f3/anch.K3;
h1 = h0; h2 = h0*(u1/u2); h3 = h0*(u1/u3) ;
Δ12% = ((f1*anch.K2)/(f2*anch.K1) - 1)*100 ;
Δ23% = ((f2*anch.K3)/(f3*anch.K2) - 1)*100.  app


9) Ce qu’il faut retenir

Les barres visualisent un parcours 𝐷ᵢ = β·𝐾ᵢ à la vitesse 𝑓ᵢ.

Les barres visualisent un parcours fixe 𝐷ᵢ = 𝐾ᵢ′ à la vitesse 𝑓ᵢ.

Les durées par tapis sont 𝑡ᵢ = 𝐾ᵢ′/𝑓ᵢ et leur somme redonne le total ancrage.

L’épaisseur dépend des capacités 𝑢ᵢ = 𝑓ᵢ/𝐾ᵢ′ (monotone en 𝑓ᵢ).

Les ancrages ABCD servent encore de repère mais ne conditionnent plus la somme totale.


Références de code (où tout se trouve)

Entrées package / exécution : __init__.py, __main__.py, Main.py.  __init__

Application & UI (barres, KPI, calculs, β, _tick) : app.py.  app

Calibration & modèles (LS, ancrages) : calibration.py.  calibration

Config (tick, valeurs par défaut) : config.py.  config

Thème/couleurs : theme.py.  theme

Helpers (parse des Hz/IHM, formats) : utils.py.  utils

Widgets (dont SegmentedBar) : widgets.py.  widgets

Annexe — Exemple chiffré complet (cas de la capture 49.99/99/99)

Entrées : 𝑓₁ = 49.99, 𝑓₂ = 99, 𝑓₃ = 99 Hz ;

  Durées LS brutes : 𝐾₁/𝑓₁ = 66.29 min, 𝐾₂/𝑓₂ = 13.69 min, 𝐾₃/𝑓₃ = 124.83 min → Σ = 204.81 min.

  Temps modèle : 𝑇ₘₒd = 107.43 min ⇒ β = 0.525.

  Durées affichées (ancrage) : 𝑡₁ = 94.52 min, 𝑡₂ = 52.27 min, 𝑡₃ = 160.23 min (Σ = 307.02 min).

  Distances barres : 𝐷₁ = 4 725.00, 𝐷₂ = 5 175.00, 𝐷₃ = 15 862.50 (min·Hz).

Épaisseurs (ℎ₀ = 2.00 cm) : 𝑢₁ = 0.01058, 𝑢₂ = 0.01913, 𝑢₃ = 0.00624 → ℎ₂ ≈ 1.11 cm (−44.7 % vs T1), ℎ₃ ≈ 3.39 cm (+206.5 % vs T2).
"""

        # Fenêtre modale
        win = tk.Toplevel(self)
        win.title("Explications détaillées")
        win.configure(bg=BG)
        win.geometry("900x640")

        # Zone scrollable en lecture seule
        txt = scrolledtext.ScrolledText(win, wrap="word", font=("Consolas", 11), bg=CARD, fg=TEXT, insertbackground=TEXT)
        txt.pack(fill="both", expand=True, padx=12, pady=12)
        txt.insert("1.0", text)
        txt.configure(state="disabled")

        # Boutons copier / exporter
        bar = ttk.Frame(win, style="TFrame"); bar.pack(fill="x", padx=12, pady=(0,12))
        def _copy():
            self.clipboard_clear(); self.clipboard_append(text)
            self.toast("Explications copiées")
        def _export():
            path = filedialog.asksaveasfilename(
                title="Exporter les explications",
                defaultextension=".txt",
                filetypes=[("Fichier texte", "*.txt"), ("Tous fichiers", "*.*")]
            )
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                except Exception as e:
                    self._show_error(f"Export TXT impossible : {e}")
                else:
                    self.toast(f"Export TXT : {path}")
        ttk.Button(bar, text="Copier dans le presse-papiers", command=_copy, style="Ghost.TButton").pack(side="left")
        ttk.Button(bar, text="Exporter en .txt", command=_export, style="Ghost.TButton").pack(side="left", padx=(8,0))


def main() -> None:
    app = FourApp()
    app.mainloop()


__all__ = ["FourApp", "main"]
