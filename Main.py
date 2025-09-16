# four_3_tapis_app_realtime_v3.py
# Four 3 tapis — TEMPS RÉEL + barres segmentées (3 cellules) + calibrage Ancrage‑4
# Auteur : ChatGPT (pour Val) — 2025

import math, time, tkinter as tk
from tkinter import ttk, messagebox

# ---- numpy pour l'algèbre ----
try:
    import numpy as np
except Exception as e:
    raise SystemExit("Installe numpy : pip install numpy\n" + str(e))

# ================== Données d'étalonnage (12 expériences) ==================
def hm(h, m): return 60*h + m
EXPS = [
    (4000, 5000, 9000, hm(2,36)),  # 1
    (4000, 5000, 8000, hm(3,11)),  # 2
    (2500, 3500, 8500, hm(3,26)),  # 3
    (8500, 4500, 4565, hm(4,30)),  # 4
    (9000, 9000, 9000, hm(0,57)),  # 5  <-- ancre A
    (9000, 9000, 5000, hm(3,18)),  # 6  <-- ancre D (tapis 3 lent)
    (5000, 9000, 9000, hm(1,39)),  # 7  <-- ancre B (tapis 1 lent)
    (9000, 5000, 9000, hm(1,43)),  # 8  <-- ancre C (tapis 2 lent)
    (5951, 4567, 8777, hm(2,28)),  # 9
    (5000, 2000, 3500, hm(6,13)),  # 10
    (4000, 5000, 9000, hm(2,36)),  # 11
    (4400, 5700, 9250, hm(2,24)),  # 12
]

# ================== Calibrages ==================
def _X_row(T1, T2, T3):
    # f = IHM/100 ; modèle linéaire en [1, 1/f1, 1/f2, 1/f3]
    return [1.0, 100.0/T1, 100.0/T2, 100.0/T3]

def calibrate_regression(exps):
    """Régression globale (LS) sur les 12 essais."""
    X = np.array([_X_row(*e[:3]) for e in exps], float)
    y = np.array([e[3] for e in exps], float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)  # d, K1, K2, K3
    d, K1, K2, K3 = beta.tolist()

    yhat = X @ beta
    resid = y - yhat
    mae = float(np.mean(np.abs(resid)))
    rmse = float(np.sqrt(np.mean(resid**2)))
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - y.mean())**2))
    r2 = 1.0 - ss_res/ss_tot if ss_tot > 0 else float("nan")
    return (d, K1, K2, K3), {"MAE": mae, "RMSE": rmse, "R2": r2}

def calibrate_anchor4(exps):
    """
    Calibre (d,K1,K2,K3) pour satisfaire EXACTEMENT 4 points d'ancrage :
      A  (90,90,90)  →  57 min
      B  (50,90,90)  →  99 min
      C  (90,50,90)  → 103 min
      D  (90,90,50)  → 198 min
    On les détecte automatiquement dans la base (EXPS).
    """
    # Cherche les essais avec 2 valeurs à 9000 et 1 différente, + l'essai 9000/9000/9000
    all90 = [e for e in exps if e[0]==9000 and e[1]==9000 and e[2]==9000]
    if not all90:
        raise RuntimeError("Ancre (90,90,90) introuvable dans la base.")
    A = all90[0]
    # variantes
    B = next((e for e in exps if e[1]==9000 and e[2]==9000 and e[0]!=9000), None)
    C = next((e for e in exps if e[0]==9000 and e[2]==9000 and e[1]!=9000), None)
    D = next((e for e in exps if e[0]==9000 and e[1]==9000 and e[2]!=9000), None)
    if not (B and C and D):
        raise RuntimeError("Ancres B/C/D introuvables (il faut les essais 50/90/90, 90/50/90 et 90/90/50).")

    anchors = [A, B, C, D]
    Aeq = np.array([_X_row(*e[:3]) for e in anchors], float)
    beq = np.array([e[3] for e in anchors], float)
    # 4 équations / 4 inconnues → solution exacte
    beta = np.linalg.solve(Aeq, beq)
    return beta.tolist(), {"anchors": anchors}

# --- Calibrage par défaut : Ancrage‑4 (pour coller à ton tableur)
PARAMS_ANCHOR4, ANCHOR_INFO = calibrate_anchor4(EXPS)
D_A, K1_A, K2_A, K3_A = PARAMS_ANCHOR4

# --- Calibrage global (scientifique)
PARAMS_REG, METRICS_REG = calibrate_regression(EXPS)
D_R, K1_R, K2_R, K3_R = PARAMS_REG

# ================== Utilitaires ==================
def parse_hz(s: str) -> float:
    """Accepte 40.00 (Hz) ou 4000 (IHM). >200 => IHM/100."""
    s = (s or "").strip().replace(",", ".")
    if not s:
        raise ValueError("Champ vide")
    f = float(s)
    return (f/100.0) if f > 200.0 else f

def fmt_minutes(m: float) -> str:
    if m is None or not math.isfinite(m): return "—"
    if m < 0: m = 0.0
    sec = int(round(m*60))
    h = sec // 3600; sec %= 3600
    mn = sec // 60; ss = sec % 60
    return f"{h}h {mn:02d}min {ss:02d}s" if h else f"{mn}min {ss:02d}s"

def fmt_hms(seconds: float) -> str:
    seconds = max(0, int(seconds + 0.5))
    h = seconds // 3600; m = (seconds % 3600) // 60; s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def compute_times(f1, f2, f3, mode="anchor"):
    """Retourne (t1,t2,t3,total) en minutes selon le mode."""
    if mode == "reg":
        d, K1, K2, K3 = D_R, K1_R, K2_R, K3_R
    else:
        d, K1, K2, K3 = D_A, K1_A, K2_A, K3_A
    t1, t2, t3 = K1/f1, K2/f2, K3/f3
    total = d + t1 + t2 + t3
    return t1, t2, t3, total, (d, K1, K2, K3)

# ================== Thème ==================
BG               = "#020a06"
CARD             = "#062016"
BORDER           = "#0f3c26"
ACCENT           = "#22c55e"
ACCENT_HOVER     = "#16a34a"
ACCENT_DISABLED  = "#113923"
SECONDARY        = "#134e4a"
SECONDARY_HOVER  = "#166656"
FIELD            = "#0b2916"
FIELD_FOCUS      = "#134127"
TEXT             = "#ecfdf5"
SUBTEXT          = "#86efac"
RED              = "#f87171"   # séparateurs fixes
FILL             = ACCENT
TRACK            = "#04160c"
GLOW             = "#34d399"

TICK_SECONDS = 1.0  # mise à jour 1 s (temps réel)
SIM_TARGET_REAL_SECONDS = 30.0  # durée visée pour le tapis le plus long (en secondes réelles)

# ================== Barre Canvas segmentée ==================
class SegmentedBar(tk.Canvas):
    """
    Barre de progression custom :
      - fond sombre
      - remplissage coloré
      - 2 traits rouges verticaux (1/3 et 2/3)
    Méthodes :
      - set_total(seconds)
      - set_progress(seconds_elapsed)
      - reset()
    """
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
        self.bind("<Configure>", lambda e: self.redraw())

    def set_total(self, seconds: float):
        self.total = max(0.0, float(seconds))
        self.elapsed = 0.0
        self.redraw()

    def set_progress(self, seconds_elapsed: float):
        self.elapsed = max(0.0, float(seconds_elapsed))
        self.redraw()

    def reset(self):
        self.total = 0.0
        self.elapsed = 0.0
        self.redraw()

    def redraw(self):
        w = self.winfo_width() or 120
        h = self.winfo_height() or self.height
        self.delete("all")

        r = h // 2
        outer_top = max(0, r - 14)
        outer_bot = min(h, r + 14)
        self.create_rectangle(0, outer_top, w, outer_bot, fill=BORDER, outline=BORDER)

        track_left = 4
        track_right = max(track_left, w - 4)
        track_top = max(outer_top + 2, r - 10)
        track_bot = min(outer_bot - 2, r + 10)
        self.create_rectangle(track_left, track_top, track_right, track_bot, fill=TRACK, outline=TRACK)

        pct = 0.0 if self.total <= 1e-9 else min(1.0, self.elapsed / self.total)
        inner_width = max(0, track_right - track_left)
        fill_w = int(pct * inner_width)
        if fill_w > 0:
            self.create_rectangle(
                track_left,
                track_top,
                track_left + fill_w,
                track_bot,
                fill=FILL,
                outline=FILL,
            )
            self.create_line(
                track_left,
                track_top,
                track_left + fill_w,
                track_top,
                fill=GLOW,
                width=2,
            )

        # Séparateurs rouges à 1/3 et 2/3 (toujours visibles)
        if inner_width > 0:
            x1 = track_left + inner_width / 3
            x2 = track_left + 2 * inner_width / 3
            self.create_line(int(x1), track_top, int(x1), track_bot, fill=RED, width=2)
            self.create_line(int(x2), track_top, int(x2), track_bot, fill=RED, width=2)

# ================== Application ==================
class FourApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Four • 3 Tapis — Calcul & Barres (Temps réel)")
        self.configure(bg=BG)
        self.geometry("1180x760")
        self.minsize(1100, 700)

        self._init_styles()
        self.option_add("*TButton.Cursor", "hand2")
        self.option_add("*TRadiobutton.Cursor", "hand2")
        self.option_add("*Entry.insertBackground", TEXT)
        self.option_add("*Entry.selectBackground", ACCENT)
        self.option_add("*Entry.selectForeground", BG)

        # États animation
        self.animating = False
        self.paused = False
        self.seg_idx = 0
        self.seg_durations = [0.0, 0.0, 0.0]   # secondes réelles (t1,t2,t3)
        self.seg_speeds = [0.0, 0.0, 0.0]      # vitesses (Hz) des 3 tapis
        self.seg_elapsed = 0.0                 # secondes simulées écoulées sur le segment courant
        self.last_tick = 0.0                   # horodatage réel du dernier tick
        self.sim_speedup = 1.0                 # facteur d'accélération de la simulation
        self.mode = tk.StringVar(value="anchor")  # 'anchor' ou 'reg'

        # UI
        self._build_ui()

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
        style.configure("Title.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 16))
        style.configure("CardHeading.TLabel", background=CARD, foreground=ACCENT, font=("Segoe UI Semibold", 13))
        style.configure("Subtle.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI", 10))
        style.configure("Hint.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI", 10, "italic"))
        style.configure("TableHead.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI Semibold", 11))
        style.configure("Big.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI", 20, "bold"))
        style.configure("Result.TLabel", background=CARD, foreground=ACCENT, font=("Segoe UI", 20, "bold"))
        style.configure("Mono.TLabel", background=CARD, foreground=SUBTEXT, font=("Consolas", 11))
        style.configure("Status.TLabel", background=CARD, foreground=SUBTEXT, font=("Consolas", 11))
        style.configure("Dark.TSeparator", background=BORDER)
        style.configure("TSeparator", background=BORDER)
        style.configure("Footer.TLabel", background=BG, foreground=SUBTEXT, font=("Segoe UI", 10))

        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground=BG,
            padding=10,
            borderwidth=0,
            focusthickness=0,
            relief="flat",
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_HOVER), ("disabled", ACCENT_DISABLED)],
            foreground=[("disabled", "#4b5563")],
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
            background=[("active", SECONDARY_HOVER), ("disabled", ACCENT_DISABLED)],
            foreground=[("disabled", "#4b5563")],
        )

        style.configure(
            "Dark.TEntry",
            fieldbackground=FIELD,
            background=FIELD,
            foreground=TEXT,
            bordercolor=BORDER,
            insertcolor=TEXT,
        )
        style.map("Dark.TEntry", fieldbackground=[("focus", FIELD_FOCUS)])

        style.configure(
            "Accent.TRadiobutton",
            background=CARD,
            foreground=TEXT,
            indicatorcolor=SECONDARY,
            focuscolor=ACCENT,
            padding=4,
            font=base_font,
        )
        style.map(
            "Accent.TRadiobutton",
            indicatorcolor=[("selected", ACCENT), ("!selected", SECONDARY)],
            foreground=[("disabled", "#4b5563")],
        )

        self.style = style

    def _card(self, parent, *, padding=(20, 16), **pack_kwargs):
        wrapper = tk.Frame(
            parent,
            bg=BORDER,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1,
            bd=0,
        )
        wrapper.pack_propagate(False)
        inner = ttk.Frame(wrapper, style="Card.TFrame", padding=padding)
        inner.pack(fill="both", expand=True)
        wrapper.pack(**pack_kwargs)
        return inner

    def _build_ui(self):
        header = self._card(self, fill="x", padx=18, pady=(16, 8), padding=(24, 18))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="Simulation de four — 3 tapis (temps réel)",
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Modèle : T = d + K1/f1 + K2/f2 + K3/f3   (f = IHM/100)",
            style="Subtle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        top = ttk.Frame(self, style="TFrame")
        top.pack(fill="both", expand=True, padx=18, pady=6)

        card_in = self._card(top, side="left", fill="both", expand=True, padx=(0, 8))
        ttk.Label(
            card_in,
            text="Entrées (fréquences des variateurs)",
            style="CardHeading.TLabel",
        ).pack(anchor="w", pady=(0, 12))
        g = ttk.Frame(card_in, style="CardInner.TFrame")
        g.pack(anchor="w", pady=(12, 6))
        g.columnconfigure(1, weight=1)
        ttk.Label(g, text="Tapis 1 : Hz =", style="Card.TLabel").grid(row=0, column=0, sticky="e", padx=(0, 12), pady=6)
        self.e1 = ttk.Entry(g, width=12, font=("Consolas", 12), style="Dark.TEntry")
        self.e1.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(g, text="Tapis 2 : Hz =", style="Card.TLabel").grid(row=1, column=0, sticky="e", padx=(0, 12), pady=6)
        self.e2 = ttk.Entry(g, width=12, font=("Consolas", 12), style="Dark.TEntry")
        self.e2.grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(g, text="Tapis 3 : Hz =", style="Card.TLabel").grid(row=2, column=0, sticky="e", padx=(0, 12), pady=6)
        self.e3 = ttk.Entry(g, width=12, font=("Consolas", 12), style="Dark.TEntry")
        self.e3.grid(row=2, column=1, sticky="w", pady=6)

        ttk.Label(
            card_in,
            text="Astuce : 40.00 ou 4000 (IHM). >200 = IHM/100.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 12))

        mode_row = ttk.Frame(card_in, style="CardInner.TFrame")
        mode_row.pack(anchor="w", pady=(0, 14))
        ttk.Label(mode_row, text="Calibration :", style="Card.TLabel").grid(row=0, column=0, padx=(0, 12))
        ttk.Radiobutton(
            mode_row,
            text="Ancrage‑4 (colle au tableur)",
            variable=self.mode,
            value="anchor",
            style="Accent.TRadiobutton",
        ).grid(row=0, column=1, padx=(0, 18))
        ttk.Radiobutton(
            mode_row,
            text="Régression globale (LS)",
            variable=self.mode,
            value="reg",
            style="Accent.TRadiobutton",
        ).grid(row=0, column=2)

        btns = ttk.Frame(card_in, style="CardInner.TFrame")
        btns.pack(anchor="w", pady=(4, 4))
        ttk.Button(btns, text="Calculer", command=self.on_calculer, style="Accent.TButton").grid(row=0, column=0, padx=(0, 12), pady=2)
        self.btn_start = ttk.Button(
            btns,
            text="Démarrer (temps réel)",
            command=self.on_start,
            state="disabled",
            style="Accent.TButton",
        )
        self.btn_start.grid(row=0, column=1, padx=(0, 12), pady=2)
        self.btn_pause = ttk.Button(
            btns,
            text="Pause",
            command=self.on_pause,
            state="disabled",
            style="Ghost.TButton",
        )
        self.btn_pause.grid(row=0, column=2, padx=(0, 12), pady=2)
        ttk.Button(btns, text="Reset", command=self.on_reset, style="Ghost.TButton").grid(row=0, column=3, pady=2)

        card_out = self._card(top, side="left", fill="both", expand=True, padx=(8, 0))
        ttk.Label(card_out, text="Résultats", style="CardHeading.TLabel").pack(anchor="w", pady=(0, 12))
        table = ttk.Frame(card_out, style="CardInner.TFrame")
        table.pack(anchor="w", pady=(12, 8))
        ttk.Label(table, text="Tapis", style="TableHead.TLabel").grid(row=0, column=0, padx=6, pady=4)
        ttk.Label(table, text="f (Hz)", style="TableHead.TLabel").grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(table, text="t_i (convoyage pur)", style="TableHead.TLabel").grid(row=0, column=2, padx=6, pady=4)

        self.row_labels = []
        for i in range(3):
            r = i + 1
            ttk.Label(table, text=f"{i+1}", style="Card.TLabel").grid(row=r, column=0, padx=6, pady=6, sticky="e")
            lf = ttk.Label(table, text="—", style="Status.TLabel")
            lf.grid(row=r, column=1, padx=6, pady=6, sticky="w")
            lt = ttk.Label(table, text="—", style="Status.TLabel")
            lt.grid(row=r, column=2, padx=6, pady=6, sticky="w")
            self.row_labels.append((lf, lt))

        ttk.Separator(card_out, style="Dark.TSeparator").pack(fill="x", pady=8)
        self.lbl_total_big = ttk.Label(card_out, text="Temps total (modèle) : —", style="Result.TLabel")
        self.lbl_total_big.pack(anchor="w", pady=(0, 6))
        self.lbl_model = ttk.Label(card_out, text="", style="Hint.TLabel")
        self.lbl_model.pack(anchor="w", pady=(0, 8))

        ttk.Separator(card_out, style="Dark.TSeparator").pack(fill="x", pady=8)
        params_txt = (
            f"[Ancrage‑4] d={D_A:+.3f}  K1={K1_A:.3f}  K2={K2_A:.3f}  K3={K3_A:.3f} (min·Hz)\n"
            f"[Régression] d={D_R:+.3f}  K1={K1_R:.3f}  K2={K2_R:.3f}  K3={K3_R:.3f}  "
            f"(MAE≈{METRICS_REG['MAE']:.2f} min ; RMSE≈{METRICS_REG['RMSE']:.2f} min ; R²≈{METRICS_REG['R2']:.3f})"
        )
        ttk.Label(card_out, text=params_txt, style="Mono.TLabel").pack(anchor="w")

        pcard = self._card(self, fill="x", padx=18, pady=8, padding=(20, 16))
        ttk.Label(
            pcard,
            text="Barres de chargement (temps réel, 3 cellules)",
            style="CardHeading.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        self.bars = []
        self.bar_texts = []
        for i in range(3):
            row = ttk.Frame(pcard, style="CardInner.TFrame")
            row.pack(fill="x", pady=8)
            row.columnconfigure(1, weight=1)
            ttk.Label(row, text=f"Tapis {i+1}", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
            bar = SegmentedBar(row, height=28)
            bar.grid(row=0, column=1, sticky="ew")
            txt = ttk.Label(row, text="—", style="Status.TLabel")
            txt.grid(row=0, column=2, sticky="e", padx=(12, 0))
            self.bars.append(bar)
            self.bar_texts.append(txt)

        self.lbl_speed = ttk.Label(
            pcard,
            text="Facteur de simulation : — (en attente)",
            style="Hint.TLabel",
        )
        self.lbl_speed.pack(anchor="w", pady=(4, 0))

        footer = ttk.Frame(self, style="TFrame")
        footer.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Label(
            footer,
            text="Astuce : lance un calcul pour activer la simulation en temps réel.",
            style="Footer.TLabel",
        ).pack(anchor="w")

        self.mode.trace_add("write", lambda *_: self._update_model_label())
        self._update_model_label()

    def _update_model_label(self):
        mode = self.mode.get()
        if mode == "anchor":
            text = "Modèle utilisé : Ancrage‑4 — calibrage verrouillé sur les repères A/B/C/D."
        else:
            text = "Modèle utilisé : Régression globale — moindres carrés sur les 12 expériences."
        if hasattr(self, "lbl_model"):
            self.lbl_model.config(text=text)

    def _compute_speedup(self) -> float:
        if not self.seg_durations:
            return 1.0
        max_dur = max(self.seg_durations)
        if max_dur <= 0.0:
            return 1.0
        return max(1.0, max_dur / SIM_TARGET_REAL_SECONDS)

    def _update_speed_label(self):
        if not hasattr(self, "lbl_speed"):
            return
        factor = float(getattr(self, "sim_speedup", 1.0))
        if not math.isfinite(factor) or factor <= 0:
            factor = 1.0
        if factor <= 1.05:
            text = "Facteur de simulation : ×1.0  (temps réel)"
        else:
            text = f"Facteur de simulation : ×{factor:.1f}  (1 s réel = {fmt_hms(factor)} simulé)"
        self.lbl_speed.config(text=text)

    # ---------- Actions ----------
    def on_reset(self):
        self.animating = False
        self.paused = False
        self.seg_idx = 0
        for b, t in zip(self.bars, self.bar_texts):
            b.reset(); t.config(text="—")
        for lf, lt in self.row_labels:
            lf.config(text="—"); lt.config(text="—")
        self.lbl_total_big.config(text="Temps total (modèle) : —")
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="disabled", text="Pause")
        self.seg_durations = [0.0, 0.0, 0.0]
        self.seg_speeds = [0.0, 0.0, 0.0]
        self.seg_elapsed = 0.0
        self.last_tick = 0.0
        self.sim_speedup = 1.0
        if hasattr(self, "lbl_speed"):
            self.lbl_speed.config(text="Facteur de simulation : — (en attente)")
        self._update_model_label()

    def on_calculer(self):
        try:
            f1 = parse_hz(self.e1.get()); f2 = parse_hz(self.e2.get()); f3 = parse_hz(self.e3.get())
            if f1<=0 or f2<=0 or f3<=0: raise ValueError("Les fréquences doivent être > 0.")
        except Exception as e:
            messagebox.showerror("Entrées invalides", f"Saisie invalide : {e}"); return

        self.animating = False
        self.paused = False
        t1, t2, t3, Ttot, (d,K1,K2,K3) = compute_times(f1, f2, f3, self.mode.get())

        # Affichage
        for (lf, lt), f, t in zip(self.row_labels, (f1,f2,f3), (t1,t2,t3)):
            lf.config(text=f"{f:.2f} Hz"); lt.config(text=f"{fmt_minutes(t)}  ({t:.2f} min)")
        self.lbl_total_big.config(text=f"Temps total (modèle) : {fmt_minutes(Ttot)}  ({Ttot:.2f} min)")

        # Barres : init temps réels (secondes) + texte
        self.seg_durations = [t1*60.0, t2*60.0, t3*60.0]
        self.seg_speeds = [f1, f2, f3]
        self.seg_idx = 0
        self.seg_elapsed = 0.0
        self.last_tick = 0.0
        self.sim_speedup = self._compute_speedup()
        self._update_speed_label()
        for i in range(3):
            duree = self.seg_durations[i]
            vitesse = self.seg_speeds[i]
            self.bars[i].set_total(max(duree, 0.0))
            self.bars[i].set_progress(0.0)
            self.bar_texts[i].config(
                text=(
                    f"0%  •  vitesse {vitesse:.2f} Hz  •  00:00:00 / {fmt_hms(duree)}  •  en attente"
                )
            )
        self.btn_start.config(state="normal"); self.btn_pause.config(state="disabled")

    def on_start(self):
        if self.animating: return
        if sum(self.seg_durations) <= 0:
            messagebox.showwarning("Calcul manquant", "Clique d'abord sur « Calculer »."); return
        self.animating = True
        self.paused = False
        self.seg_idx = 0
        self.seg_elapsed = 0.0
        self.last_tick = time.perf_counter()
        if self.sim_speedup <= 0 or not math.isfinite(self.sim_speedup):
            self.sim_speedup = 1.0
        self.btn_pause.config(state="normal", text="Pause")
        self._tick()

    def on_pause(self):
        if not self.animating: return
        if not self.paused:
            self.paused = True
            self.last_tick = time.perf_counter()
            self.btn_pause.config(text="Reprendre")
        else:
            self.paused = False
            self.last_tick = time.perf_counter()
            self.btn_pause.config(text="Pause")
            self._tick()

    def _tick(self):
        if not self.animating: return
        if self.paused:
            self.after(int(TICK_SECONDS*1000), self._tick); return

        now = time.perf_counter()
        delta_reel = now - self.last_tick
        if delta_reel < 0:
            delta_reel = 0.0
        self.last_tick = now
        self.seg_elapsed += delta_reel * self.sim_speedup

        while True:
            i = self.seg_idx
            if i >= 3:
                self.animating = False
                self.btn_pause.config(state="disabled", text="Pause")
                return

            duree = self.seg_durations[i]
            vitesse = self.seg_speeds[i]

            if duree <= 1e-9:
                self.bars[i].set_total(1.0)
                self.bars[i].set_progress(1.0)
                self.bar_texts[i].config(
                    text=(
                        f"100%  •  vitesse {vitesse:.2f} Hz  •  00:00:00 / 00:00:00  •  terminé"
                    )
                )
                self.seg_idx += 1
                continue

            if self.seg_elapsed + 1e-9 < duree:
                pct = max(0.0, min(1.0, self.seg_elapsed / duree)) * 100.0
                self.bars[i].set_progress(self.seg_elapsed)
                self.bar_texts[i].config(
                    text=(
                        f"{pct:5.1f}%  •  vitesse {vitesse:.2f} Hz  •  {fmt_hms(self.seg_elapsed)} / {fmt_hms(duree)}  •  en cours…"
                    )
                )
                break

            # Terminer ce segment et transférer le reliquat au suivant
            self.bars[i].set_progress(duree)
            self.bar_texts[i].config(
                text=(
                    f"100%  •  vitesse {vitesse:.2f} Hz  •  {fmt_hms(duree)} / {fmt_hms(duree)}  •  terminé"
                )
            )
            self.seg_idx += 1
            self.seg_elapsed = max(0.0, self.seg_elapsed - duree)
            if self.seg_idx >= 3:
                self.animating = False
                self.btn_pause.config(state="disabled", text="Pause")
                return

        self.after(int(TICK_SECONDS*1000), self._tick)

# ---------- Lancement ----------
if __name__ == "__main__":
    app = FourApp()
    app.e1.insert(0, "40.00")   # 40 Hz
    app.e2.insert(0, "50.00")   # 50 Hz
    app.e3.insert(0, "99.99")   # 99.99 Hz
    app.mainloop()
