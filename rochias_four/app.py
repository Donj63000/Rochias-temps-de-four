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
    K1_DIST,
    K1_R,
    K2_DIST,
    K2_R,
    K3_DIST,
    K3_R,
    METRICS_EXACT,
    METRICS_REG,
    THETA12,
    compute_times,
    predict_T_interp12,
)
from .config import DEFAULT_INPUTS, PREFS_PATH, TICK_SECONDS
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
from .utils import fmt_hms, fmt_minutes, parse_hz
from .widgets import Collapsible, SegmentedBar, Tooltip, VScrollFrame


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
        self.title("Four • 3 Tapis — Calcul & Barres (Temps réel)")
        self.configure(bg=BG)
        # Tu peux garder la géométrie initiale si tu veux
        # self.geometry("1180x760")
        self.minsize(1100, 700)

        self._toasts = []
        self._cards = []
        self._responsive_labels = []
        self.compact_mode = False

        self._init_styles()
        self.option_add("*TButton.Cursor", "hand2")
        self.option_add("*TRadiobutton.Cursor", "hand2")
        self.option_add("*Entry.insertBackground", TEXT)
        self.option_add("*Entry.selectBackground", ACCENT)
        self.option_add("*Entry.selectForeground", "#ffffff")

        # États animation
        self.animating = False
        self.paused = False
        self.seg_idx = 0
        self.seg_start = 0.0
        self.seg_durations = [0.0, 0.0, 0.0]   # secondes réelles (t1,t2,t3)
        self.seg_distances = [0.0, 0.0, 0.0]   # longueurs équivalentes (K1,K2,K3)
        self.seg_speeds = [0.0, 0.0, 0.0]      # vitesses (Hz) des 3 tapis
        self._after_id = None       # gestion propre du timer Tk
        self.alpha = 1.0            # facteur d’échelle des barres : T / (t1+t2+t3)
        self.last_calc = None       # stockage du dernier calcul pour Explications
        self.total_duration = 0.0
        self.notified_stage1 = False
        self.notified_stage2 = False
        self.notified_exit = False

        self.stat_cards = {}
        self.stage_status = []
        self.kpi_labels = {}
        self.stage_rows = []
        self.operator_mode = True

        self.logo_img = None
        self._error_after = None

        self._load_logo()

        # UI
        self._build_ui()
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
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

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
        ttk.Label(badge_box, text="Interpolation 12 points", style="BadgeNeutral.TLabel").pack(side="left")
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

        subtitle = ttk.Label(
            hero,
            text="Modèle : T = d + K1/f1 + K2/f2 + K3/f3  (f = IHM/100). LS pour la répartition par tapis, interpolation exacte (12 essais) pour le temps total.",
            style="HeroSub.TLabel",
            wraplength=760,
            justify="left",
        )
        subtitle.grid(row=1, column=1, columnspan=2, sticky="w", pady=(8, 0))

        tagline = ttk.Label(
            hero,
            text="Tableau de bord visuel pour suivre la cuisson et les tapis en parallèle.",
            style="Subtle.TLabel",
            wraplength=760,
            justify="left",
        )
        tagline.grid(row=2, column=1, columnspan=2, sticky="w", pady=(6, 0))

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
        Tooltip(self.kpi_labels["total"][0], "Temps total corrigé par interpolation exacte (12 points)")
        Tooltip(self.kpi_labels["t1"][0], "Durée estimée sur le tapis 1 (pondérée par α)")
        Tooltip(self.kpi_labels["t2"][0], "Durée estimée sur le tapis 2 (pondérée par α)")
        Tooltip(self.kpi_labels["t3"][0], "Durée estimée sur le tapis 3 (pondérée par α)")

        body = VScrollFrame(self)
        body.pack(fill="both", expand=True)

        pcard = self._card(body.inner, fill="x", expand=False, padx=18, pady=8, padding=(24, 20))
        ttk.Label(
            pcard,
            text="Barres de chargement (temps réel, 3 cellules)",
            style="CardHeading.TLabel",
        ).pack(anchor="w", pady=(0, 12))
        self.lbl_bars_info = ttk.Label(pcard, text="", style="Hint.TLabel", wraplength=900, justify="left")
        self.lbl_bars_info.pack(anchor="w", pady=(0, 8))
        self._responsive_labels.append((self.lbl_bars_info, 0.85))
        pcard.bind("<Configure>", self._on_resize_wrapping)

        self.bars = []
        self.bar_texts = []
        self.stage_status = []

        for i in range(3):
            holder = ttk.Frame(pcard, style="CardInner.TFrame")
            holder.pack(fill="x", pady=10)
            title_row = ttk.Frame(holder, style="CardInner.TFrame")
            title_row.pack(fill="x")
            ttk.Label(title_row, text=f"Tapis {i+1}", style="Card.TLabel").pack(side="left")
            status_lbl = ttk.Label(title_row, text="⏳ En attente", style="BadgeIdle.TLabel")
            status_lbl.pack(side="left", padx=(12, 0))
            bar = SegmentedBar(holder, height=56)
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
            card_in,
            text="Astuce : 40.00 ou 4000 (IHM). >200 = IHM/100.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 12))

        self.err_box = ttk.Label(card_in, text="", style="Hint.TLabel")
        self.err_box.pack(anchor="w", pady=(0, 0))

        btns = ttk.Frame(card_in, style="CardInner.TFrame")
        btns.pack(fill="x", pady=(4, 8))
        btns.columnconfigure(4, weight=1)
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

        self.details = Collapsible(body.inner, title="Détails résultats & analyse", open=False)
        self.details.pack(fill="x", padx=18, pady=(8, 0))

        card_out = self._card(self.details.body, fill="both", expand=True)
        card_out.columnconfigure(0, weight=1)
        ttk.Label(card_out, text="Résultats", style="CardHeading.TLabel").pack(anchor="w", pady=(0, 12))
        self.lbl_total_big = ttk.Label(card_out, text="Temps total (interp. exacte) : --", style="Result.TLabel")
        self.lbl_total_big.pack(anchor="w", pady=(0, 10))

        export_row = ttk.Frame(card_out, style="CardInner.TFrame")
        export_row.pack(fill="x", pady=(0, 10))
        ttk.Button(export_row, text="⬇ Export CSV", command=self.export_csv, style="Ghost.TButton").pack(side="left")
        ttk.Button(export_row, text="🖨 Export PS", command=self.export_bars_ps, style="Ghost.TButton").pack(side="left", padx=(8, 0))

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

        ttk.Separator(card_out, style="Dark.TSeparator").pack(fill="x", pady=8)
        ttk.Label(card_out, text="Analyse modèle", style="Subtle.TLabel").pack(anchor="w")
        stats = ttk.Frame(card_out, style="CardInner.TFrame")
        stats.pack(fill="x", pady=(4, 16))
        stat_defs = [
            ("ls", "Total LS (4 paramètres)", "StatCard.TFrame", "StatTitle.TLabel", "StatValue.TLabel", "StatDetail.TLabel"),
            ("sum", "Somme t_i (LS)", "StatCard.TFrame", "StatTitle.TLabel", "StatValue.TLabel", "StatDetail.TLabel"),
            ("alpha", "Facteur alpha", "StatCard.TFrame", "StatTitle.TLabel", "StatValue.TLabel", "StatDetail.TLabel"),
            ("delta", "Delta exact - LS", "StatCardAccent.TFrame", "StatTitleAccent.TLabel", "StatValueAccent.TLabel", "StatDetailAccent.TLabel"),
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
        for row in self.stage_rows:
            row["freq"].config(text="-- Hz")
            row["time"].config(text="--")
            row["detail"].config(text="--")
        self.lbl_total_big.config(text="Temps total (interp. exacte) : --")
        self.lbl_bars_info.config(text="")
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

        t1, t2, t3, T_LS, (d, K1, K2, K3) = compute_times(f1, f2, f3)
        T_exp = predict_T_interp12(f1, f2, f3, THETA12)

        t1_base = K1_DIST / f1
        t2_base = K2_DIST / f2
        t3_base = K3_DIST / f3
        sum_base = t1_base + t2_base + t3_base
        if sum_base <= 1e-9:
            self._show_error("Somme des temps d'ancrage nulle.")
            return
        if T_exp <= 0:
            self._show_error("Temps modélisé ≤ 0 : vérifie les entrées et le calibrage.")
            return

        alpha = T_exp / sum_base
        t1s = alpha * t1_base
        t2s = alpha * t2_base
        t3s = alpha * t3_base

        for row, freq, ts in zip(self.stage_rows, (f1, f2, f3), (t1s, t2s, t3s)):
            row["freq"].config(text=f"{freq:.2f} Hz")
            row["time"].config(text=fmt_minutes(ts))
            row["detail"].config(text=f"{ts:.2f} min | {fmt_hms(ts * 60)}")

        self.lbl_total_big.config(text=f"Temps total (interp. exacte) : {fmt_minutes(T_exp)} | {fmt_hms(T_exp * 60)}")

        self.alpha = alpha
        self.seg_distances = [alpha * K1_DIST, alpha * K2_DIST, alpha * K3_DIST]
        self.seg_speeds = [f1, f2, f3]
        self.seg_durations = [t1s * 60.0, t2s * 60.0, t3s * 60.0]

        for i, (distance_eq, fi, duration) in enumerate(
            zip(self.seg_distances, self.seg_speeds, self.seg_durations)
        ):
            distance = max(1e-9, float(distance_eq))
            self.bars[i].set_total_distance(distance)
            self.bar_texts[i].config(
                text=f"0.0% | vitesse {fi:.2f} Hz | 00:00:00 / {fmt_hms(duration)} | en attente"
            )

        delta_total = T_exp - T_LS
        info = (
            "→ Barre = distance équivalente parcourue (min·Hz) | vitesse = Hz réel | progression = distance parcourue / distance cible\n"
            f"Exact : {fmt_hms(T_exp * 60)} ({T_exp:.2f} min) | LS : {fmt_hms(T_LS * 60)} ({T_LS:.2f} min)\n"
            f"Σ t_i (LS) : {fmt_hms((t1 + t2 + t3) * 60)} ({(t1 + t2 + t3):.2f} min) | d = {d:+.3f} min | α = {alpha:.3f}\n"
            f"Σ ancrage : {fmt_hms(sum_base * 60)} ({sum_base:.2f} min) | K1'={K1_DIST:.1f}  K2'={K2_DIST:.1f}  K3'={K3_DIST:.1f}"
        )
        self.lbl_bars_info.config(text=info)

        self._update_kpi("total", fmt_minutes(T_exp), f"{T_exp:.2f} min | {fmt_hms(T_exp * 60)}")
        self._update_kpi("t1", fmt_minutes(t1s), f"{t1s:.2f} min | {fmt_hms(t1s * 60)} | {f1:.2f} Hz")
        self._update_kpi("t2", fmt_minutes(t2s), f"{t2s:.2f} min | {fmt_hms(t2s * 60)} | {f2:.2f} Hz")
        self._update_kpi("t3", fmt_minutes(t3s), f"{t3s:.2f} min | {fmt_hms(t3s * 60)} | {f3:.2f} Hz")

        self._update_stat_card("ls", f"{T_LS:.2f} min", fmt_hms(T_LS * 60))
        self._update_stat_card("sum", f"{sum_base:.2f} min", fmt_hms(sum_base * 60))
        self._update_stat_card("alpha", f"{alpha:.3f}", f"{sum_base:.2f} → {T_exp:.2f}")
        self._update_stat_card("delta", f"{delta_total:+.2f} min", fmt_hms(abs(delta_total) * 60))

        self._set_stage_status(0, "ready")
        self._set_stage_status(1, "idle")
        self._set_stage_status(2, "idle")

        self.last_calc = dict(
            f1=f1, f2=f2, f3=f3,
            d=d, K1=K1, K2=K2, K3=K3,
            t1=t1, t2=t2, t3=t3,
            t1_base=t1_base, t2_base=t2_base, t3_base=t3_base,
            t1_star=t1s, t2_star=t2s, t3_star=t3s,
            T_LS=T_LS, T_exp=T_exp, alpha=alpha,
            sum_t=t1 + t2 + t3, sum_base=sum_base, delta=delta_total,
            K1_dist=K1_DIST, K2_dist=K2_DIST, K3_dist=K3_DIST,
        )

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

    def _tick(self):
        if not self.animating or self.paused:
            return

        i = self.seg_idx
        dur = max(1e-6, self.seg_durations[i])
        distance_totale = max(1e-9, self.seg_distances[i])
        vitesse = self.seg_speeds[i]
        now = time.perf_counter()
        elapsed = now - self.seg_start
        remaining_current = max(0.0, dur - elapsed)
        remaining_future = sum(self.seg_durations[j] for j in range(i + 1, 3))
        total_remaining = max(0.0, remaining_current + remaining_future)
        if (not self.notified_exit and self.total_duration > 5 * 60 and total_remaining <= 5 * 60):
            self.notified_exit = True
            self.toast("Le produit va sortir du four (≤ 5 min)")
        distance_parcourue = max(0.0, vitesse * (elapsed / 60.0))
        if distance_parcourue >= distance_totale:
            distance_parcourue = distance_totale
            prog = 1.0
        else:
            prog = distance_parcourue / distance_totale

        if prog >= 1.0:
            self.bars[i].set_progress(distance_totale)
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
                return
            self.seg_start = now
            j = self.seg_idx
            vitesse_j = self.seg_speeds[j]
            duree_j = self.seg_durations[j]
            distance_j = max(1e-9, self.seg_distances[j])
            self.bars[j].set_total_distance(distance_j)
            self.bar_texts[j].config(
                text=f"0.0% | vitesse {vitesse_j:.2f} Hz | 00:00:00 / {fmt_hms(duree_j)} | en cours"
            )
            self._set_stage_status(j, "active")
            if j + 1 < 3:
                self._set_stage_status(j + 1, "ready")
            self._schedule_tick()
            return

        pct = max(0.0, min(1.0, prog)) * 100.0
        self.bars[i].set_progress(distance_parcourue)
        self.bar_texts[i].config(
            text=f"{pct:5.1f}% | vitesse {vitesse:.2f} Hz | {fmt_hms(elapsed)} / {fmt_hms(dur)} | en cours"
        )

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
                t1, t2, t3, T_LS, (d, K1, K2, K3) = compute_times(f1, f2, f3)
                T_exp = predict_T_interp12(f1, f2, f3, THETA12)
                t1_base = K1_DIST / f1
                t2_base = K2_DIST / f2
                t3_base = K3_DIST / f3
                sum_base = t1_base + t2_base + t3_base
                alpha = T_exp / sum_base if sum_base > 0 else float('nan')
                if math.isfinite(alpha):
                    t1s, t2s, t3s = alpha * t1_base, alpha * t2_base, alpha * t3_base
                else:
                    t1s = t2s = t3s = float('nan')
                calc = dict(
                    f1=f1, f2=f2, f3=f3,
                    d=d, K1=K1, K2=K2, K3=K3,
                    t1=t1, t2=t2, t3=t3,
                    t1_base=t1_base, t2_base=t2_base, t3_base=t3_base,
                    t1_star=t1s, t2_star=t2s, t3_star=t3s,
                    T_LS=T_LS, T_exp=T_exp, alpha=alpha,
                    sum_t=t1 + t2 + t3,
                    sum_base=sum_base,
                    delta=T_exp - T_LS,
                    K1_dist=K1_DIST, K2_dist=K2_DIST, K3_dist=K3_DIST,
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
            T_LS = T_exp = alpha = sum_base = delta_total = float("nan")
            t1_base = t2_base = t3_base = float("nan")
            t1s = t2s = t3s = float("nan")
            sum_alpha = float("nan")

        if calc and all(math.isfinite(v) for v in (f1, f2, f3)):
            freq_line = f"   - Frequences tapis : f1 = {f1:.2f} Hz | f2 = {f2:.2f} Hz | f3 = {f3:.2f} Hz"
        elif calc:
            freq_line = "   - Frequences tapis : valeurs indisponibles"
        else:
            freq_line = "   - Pas encore de calcul (appuie sur Calculer)"

        lines = [
            "GUIDE SIMPLIFIE - MODELE FOUR 3 TAPIS",
            "",
            "1. Entrees saisies",
            freq_line,
            "",
        ]
        if calc:
            delta_text = f"{delta_total:+.2f} min" if math.isfinite(delta_total) else "n/a"
            sum_base_text = _fmt_val(sum_base)
            sum_alpha_text = _fmt_val(sum_alpha)
            alpha_text = f"{alpha:.3f}" if math.isfinite(alpha) else "n/a"
            lines.extend([
                "2. Resume minute",
                f"   - Temps exact (12 points) : {fmt_minutes(T_exp)} ({fmt_hms(T_exp * 60)})",
                f"   - Total LS (modele lineaire) : {fmt_minutes(T_LS)} ({fmt_hms(T_LS * 60)})",
                f"   - Ecart exact vs LS : {delta_text}",
                "",
                "3. Durees par tapis",
                f"   - Tapis 1 : {fmt_minutes(t1s)} | {_fmt_val(t1s)} (base : {_fmt_val(t1_base)})",
                f"   - Tapis 2 : {fmt_minutes(t2s)} | {_fmt_val(t2s)} (base : {_fmt_val(t2_base)})",
                f"   - Tapis 3 : {fmt_minutes(t3s)} | {_fmt_val(t3s)} (base : {_fmt_val(t3_base)})",
                "",
                "4. Comment lire les barres",
                f"   - Alpha = {alpha_text} (facteur d'equilibrage)",
                "   - Chaque barre represente une distance D_i = alpha x K_i' parcourue a la vitesse f_i",
                "   - Quand la barre atteint 100 %, le tapis a termine son passage",
                "",
                "5. Verifications rapides",
                f"   - Somme base : {sum_base_text} | Somme alpha : {sum_alpha_text}",
                f"   - Constantes K' : K1'={K1_DIST:.1f} | K2'={K2_DIST:.1f} | K3'={K3_DIST:.1f}",
            ])
        else:
            lines.extend([
                "2. Comment ca marche ?",
                "   - Saisis les frequences (affichage variateur ou IHM/100).",
                "   - Clique sur Calculer pour generer les indicateurs et activer la simulation.",
                "   - Les barres se lancent ensuite via le bouton Demarrer.",
            ])
        lines.extend([
            "",
            "6. Rappels modele",
            "   - T (min) = d + K1/f1 + K2/f2 + K3/f3 (regression sur 12 essais).",
            "   - Une interpolation exacte ajuste le total pour coller aux mesures terrain.",
            "   - Les constantes K' viennent des essais ancrage A/B/C/D.",
        ])
        text = "\n".join(lines)

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
