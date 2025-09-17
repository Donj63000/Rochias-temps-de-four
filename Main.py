# four_3_tapis_app_realtime_v3.py
# Four 3 tapis — TEMPS RÉEL + barres segmentées (3 cellules) + calibrage Ancrage‑4
# Auteur : ChatGPT (pour Val) — 2025

import math, time, tkinter as tk
from tkinter import ttk, messagebox
from tkinter import scrolledtext, filedialog  # pour la fenêtre Explications

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
BG               = "#f6fbf7"
CARD             = "#ffffff"
BORDER           = "#cde8d9"
ACCENT           = "#16a34a"
ACCENT_HOVER     = "#15803d"
ACCENT_DISABLED  = "#9dd6b5"
SECONDARY        = "#e7f6ed"
SECONDARY_HOVER  = "#d1eddb"
FIELD            = "#ffffff"
FIELD_FOCUS      = "#e2f4e8"
TEXT             = "#065f46"
SUBTEXT          = "#1b8f5a"
RED              = "#dc2626"   # séparateurs fixes
FILL             = ACCENT
TRACK            = "#dcfce7"
GLOW             = "#86efac"

TICK_SECONDS = 1.0  # mise à jour 1 s (temps réel)

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
        fill_w = 0
        if pct > 0.0 and inner_width > 0:
            fill_w = max(1, min(inner_width, math.ceil(pct * inner_width)))

        if fill_w > 0:
            fill_right = min(track_right, track_left + fill_w)
            self.create_rectangle(
                track_left,
                track_top,
                fill_right,
                track_bot,
                fill=FILL,
                outline=FILL,
            )
            self.create_line(
                track_left,
                track_top,
                fill_right,
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
        self.option_add("*Entry.selectForeground", "#ffffff")

        # États animation
        self.animating = False
        self.paused = False
        self.seg_idx = 0
        self.seg_start = 0.0
        self.seg_durations = [0.0, 0.0, 0.0]   # secondes réelles (t1,t2,t3)
        self.seg_distances = [0.0, 0.0, 0.0]   # longueurs équivalentes (K1,K2,K3)
        self.seg_speeds = [0.0, 0.0, 0.0]      # vitesses (Hz) des 3 tapis
        self.mode = tk.StringVar(value="anchor")  # 'anchor' ou 'reg'
        self._after_id = None       # gestion propre du timer Tk
        self.alpha = 1.0            # facteur d’échelle des barres : T / (t1+t2+t3)
        self.last_calc = None       # stockage du dernier calcul pour Explications

        # UI
        self._build_ui()

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
        style.configure("Title.TLabel", background=CARD, foreground=ACCENT, font=("Segoe UI Semibold", 16))
        style.configure("CardHeading.TLabel", background=CARD, foreground=ACCENT, font=("Segoe UI Semibold", 13))
        style.configure("Subtle.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI", 10))
        style.configure("Hint.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI", 10, "italic"))
        style.configure("TableHead.TLabel", background=CARD, foreground=SUBTEXT, font=("Segoe UI Semibold", 11))
        style.configure("Big.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI", 20, "bold"))
        style.configure("Result.TLabel", background=CARD, foreground=ACCENT, font=("Segoe UI", 20, "bold"))
        style.configure("Mono.TLabel", background=CARD, foreground="#3b7e63", font=("Consolas", 11))
        style.configure("Status.TLabel", background=CARD, foreground=SUBTEXT, font=("Consolas", 11))
        style.configure("Dark.TSeparator", background=BORDER)
        style.configure("TSeparator", background=BORDER)
        style.configure("Footer.TLabel", background=BG, foreground=SUBTEXT, font=("Segoe UI", 10))

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
        ttk.Button(btns, text="Explications", command=self.on_explanations, style="Ghost.TButton")\
           .grid(row=0, column=4, padx=(12, 0), pady=2)

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

        pcard = self._card(self, fill="x", expand=True, padx=18, pady=8, padding=(20, 16))
        ttk.Label(
            pcard,
            text="Barres de chargement (temps réel, 3 cellules)",
            style="CardHeading.TLabel",
        ).pack(anchor="w", pady=(0, 12))
        self.lbl_bars_info = ttk.Label(pcard, text="", style="Hint.TLabel")
        self.lbl_bars_info.pack(anchor="w", pady=(0, 8))

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

    # ---------- Actions ----------
    def on_reset(self):
        self._cancel_after()
        self.animating = False
        self.paused = False
        self.seg_idx = 0
        self.seg_start = 0.0
        for b, t in zip(self.bars, self.bar_texts):
            b.reset(); t.config(text="—")
        for lf, lt in self.row_labels:
            lf.config(text="—"); lt.config(text="—")
        self.lbl_total_big.config(text="Temps total (modèle) : —")
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="disabled", text="Pause")
        self.seg_durations = [0.0, 0.0, 0.0]
        self.seg_distances = [0.0, 0.0, 0.0]
        self.seg_speeds = [0.0, 0.0, 0.0]
        self._update_model_label()

    def on_calculer(self):
        try:
            f1 = parse_hz(self.e1.get()); f2 = parse_hz(self.e2.get()); f3 = parse_hz(self.e3.get())
            if f1<=0 or f2<=0 or f3<=0: raise ValueError("Les fréquences doivent être > 0.")
        except Exception as e:
            messagebox.showerror("Entrées invalides", f"Saisie invalide : {e}"); return

        t1, t2, t3, Ttot, (d,K1,K2,K3) = compute_times(f1, f2, f3, self.mode.get())

        # Affichage
        for (lf, lt), f, t in zip(self.row_labels, (f1,f2,f3), (t1,t2,t3)):
            lf.config(text=f"{f:.2f} Hz"); lt.config(text=f"{fmt_minutes(t)}  ({t:.2f} min)")
        self.lbl_total_big.config(text=f"Temps total (modèle) : {fmt_minutes(Ttot)}  ({Ttot:.2f} min)")

        # ---- Barres : calage sur le temps modèle T ----
        sum_t = t1 + t2 + t3
        if sum_t <= 1e-9:
            messagebox.showerror("Entrées invalides", "Somme des temps Σt_i nulle."); return
        if Ttot <= 0:
            messagebox.showerror("Temps modèle négatif", "T ≤ 0 — vérifier les entrées et le calibrage."); return

        alpha = Ttot / sum_t
        self.alpha = alpha

        # Distances équivalentes sur la Canvas (min·Hz)
        # (on garde f_i en Hz ; durée d’une barre = (distance/f)×60 = (K_i*alpha/f_i)×60 = alpha×t_i×60)
        self.seg_distances = [K1*alpha, K2*alpha, K3*alpha]
        self.seg_speeds    = [f1, f2, f3]
        self.seg_durations = [t1*60.0*alpha, t2*60.0*alpha, t3*60.0*alpha]

        for i in range(3):
            distance = max(1e-9, float(self.seg_distances[i]))
            duree    = self.seg_durations[i]
            vitesse  = self.seg_speeds[i]
            self.bars[i].set_total(distance)
            self.bar_texts[i].config(
                text=(f"0%  •  vitesse {vitesse:.2f} Hz  •  00:00:00 / {fmt_hms(duree)}  •  en attente")
            )

        # Résumé visible pour l’opérateur : Σt, d, T, alpha
        delta = Ttot - sum_t  # = d
        sign  = "−" if delta < 0 else "+"
        self.lbl_bars_info.config(
            text=(
                f"Σt = {fmt_hms(sum_t*60)}  •  d {sign} {fmt_hms(abs(delta)*60)}  •  "
                f"T = {fmt_hms(Ttot*60)}  •  barres calées sur T (α = {alpha:.3f})"
            )
        )

        # Mémorise le calcul pour la fenêtre Explications
        self.last_calc = dict(
            mode=self.mode.get(), f1=f1, f2=f2, f3=f3,
            d=d, K1=K1, K2=K2, K3=K3,
            t1=t1, t2=t2, t3=t3, T=Ttot, alpha=alpha
        )

        self.btn_start.config(state="normal"); self.btn_pause.config(state="disabled")

    def on_start(self):
        if self.animating: return
        if sum(self.seg_durations) <= 0:
            messagebox.showwarning("Calcul manquant", "Clique d'abord sur « Calculer »."); return
        self.animating = True
        self.paused = False
        self.seg_idx = 0
        self.seg_start = time.perf_counter()
        self.btn_pause.config(state="normal", text="Pause")
        self._cancel_after()  # évite tout timer résiduel
        self._tick()

    def on_pause(self):
        if not self.animating:
            return
        if not self.paused:
            # Passage en pause
            self.paused = True
            self.pause_t0 = time.perf_counter()
            self._cancel_after()
            self.btn_pause.config(text="Reprendre")
        else:
            # Reprise
            delta = time.perf_counter() - self.pause_t0
            self.seg_start += delta
            self.paused = False
            self.btn_pause.config(text="Pause")
            self._tick()  # relance immédiate ; _tick() replanifie proprement

    def _tick(self):
        if not self.animating:
            return
        if self.paused:
            return  # ne pas replanifier en pause

        i = self.seg_idx
        dur = max(1e-6, self.seg_durations[i])
        distance_totale = max(1e-9, self.seg_distances[i])
        vitesse = self.seg_speeds[i]
        now = time.perf_counter()
        elapsed = now - self.seg_start
        distance_parcourue = max(0.0, vitesse * (elapsed / 60.0))
        if distance_parcourue >= distance_totale:
            distance_parcourue = distance_totale
            prog = 1.0
        else:
            prog = distance_parcourue / distance_totale

        if prog >= 1.0:
            # Terminer ce segment
            self.bars[i].set_progress(distance_totale)
            self.bar_texts[i].config(
                text=(
                    f"100%  •  vitesse {vitesse:.2f} Hz  •  {fmt_hms(dur)} / {fmt_hms(dur)}  •  terminé"
                )
            )
            self.seg_idx += 1
            if self.seg_idx >= 3:
                self.animating = False
                self.btn_pause.config(state="disabled", text="Pause"); return
            # suivant
            self.seg_start = now
            j = self.seg_idx
            vitesse_j = self.seg_speeds[j]
            duree_j = self.seg_durations[j]
            distance_j = max(1e-9, self.seg_distances[j])
            self.bars[j].set_total(distance_j)
            self.bar_texts[j].config(
                text=(
                    f"0%  •  vitesse {vitesse_j:.2f} Hz  •  00:00:00 / {fmt_hms(duree_j)}  •  en cours…"
                )
            )
            self._schedule_tick()
            return

        pct = max(0.0, min(1.0, prog)) * 100.0
        self.bars[i].set_progress(distance_parcourue)
        self.bar_texts[i].config(
            text=(
                f"{pct:5.1f}%  •  vitesse {vitesse:.2f} Hz  •  {fmt_hms(elapsed)} / {fmt_hms(dur)}  •  en cours…"
            )
        )

        self._schedule_tick()

    def on_explanations(self):
        # Récupérer les dernières valeurs ; sinon tenter un calcul rapide
        calc = self.last_calc
        try:
            if calc is None:
                f1 = parse_hz(self.e1.get()); f2 = parse_hz(self.e2.get()); f3 = parse_hz(self.e3.get())
                mode = self.mode.get()
                t1, t2, t3, Ttot, (d, K1, K2, K3) = compute_times(f1, f2, f3, mode)
                sum_t = t1 + t2 + t3
                alpha = Ttot / sum_t if sum_t > 0 else float('nan')
                calc = dict(mode=mode, f1=f1,f2=f2,f3=f3, d=d, K1=K1,K2=K2,K3=K3,
                            t1=t1,t2=t2,t3=t3, T=Ttot, alpha=alpha)
        except Exception:
            pass

        # Construire le texte d'explication
        lines = []
        lines.append("EXPlications détaillées — Modèle du four (3 tapis)\n")
        lines.append("1) Modèle mathématique\n")
        lines.append("   T = d + K1/f1 + K2/f2 + K3/f3\n")
        lines.append("   • f_i : fréquence variateur (Hz) — si l’IHM affiche 4000, on prend f=40.00 Hz (IHM/100)\n")
        lines.append("   • K_i : constantes (min·Hz) — longueur équivalente/chemin thermique du tapis i\n")
        lines.append("   • d   : intercepte global (min) — capte les effets non linéaires/constantes (chevauchements, zones fixes, etc.)\n")
        lines.append("")
        if calc:
            f1,f2,f3 = calc['f1'], calc['f2'], calc['f3']
            K1,K2,K3 = calc['K1'], calc['K2'], calc['K3']
            d = calc['d']; t1,t2,t3 = calc['t1'], calc['t2'], calc['t3']; T = calc['T']
            sum_t = t1+t2+t3
            alpha = calc['alpha']
            mode = "Ancrage‑4" if calc['mode']=="anchor" else "Régression globale (LS)"

            lines.append("2) Données calculées (en minutes)")        
            lines.append(f"   Mode : {mode}")
            lines.append(f"   Paramètres : d = {d:+.3f} min ;  K1 = {K1:.3f} ; K2 = {K2:.3f} ; K3 = {K3:.3f} (min·Hz)")
            lines.append(f"   Entrées : f1 = {f1:.2f} Hz ; f2 = {f2:.2f} Hz ; f3 = {f3:.2f} Hz")
            lines.append(f"   Temps convoyage pur : t1 = {t1:.3f} ; t2 = {t2:.3f} ; t3 = {t3:.3f}  (Σt = {sum_t:.3f})")
            lines.append(f"   Temps total modèle : T = d + Σt = {d:+.3f} + {sum_t:.3f} = {T:.3f} min  ({fmt_hms(T*60)})")
            lines.append("")
            lines.append("3) Pourquoi les barres finissent en T (et non Σt)")
            lines.append("   • d ne s’attache à aucun tapis ; pour une visualisation opérationnelle, on le redistribue")
            lines.append("     proportionnellement aux t_i. Cela revient à appliquer un facteur commun α = T / Σt.")
            lines.append("   • Durées animées : t_i* = α · t_i  ⇒  Σ t_i* = T.")
            lines.append(f"   • Dans cette simulation : α = {alpha:.6f}")
            lines.append(f"     → t1* = {alpha*t1:.3f} min ({fmt_hms(alpha*t1*60)})")
            lines.append(f"     → t2* = {alpha*t2:.3f} min ({fmt_hms(alpha*t2*60)})")
            lines.append(f"     → t3* = {alpha*t3:.3f} min ({fmt_hms(alpha*t3*60)})")
            lines.append("")
            lines.append("4) Interprétation des barres (Canvas)")
            lines.append("   • On anime une « distance » D_i (min·Hz) parcourue à la vitesse f_i (Hz) :")
            lines.append("       distance_parcourue = f_i · (temps_écoulé / 60)")
            lines.append("       fin de la barre quand distance_parcourue ≥ D_i")
            lines.append("   • Pour caler la durée à t_i* minutes, on prend D_i = α · K_i ; le temps vaut (D_i/f_i)·60 = α·t_i·60.")
            lines.append("")
            lines.append("5) Choix de calibrage")
            lines.append("   • Ancrage‑4 : paramètres (d,K_i) calculés pour coller EXACTEMENT aux 4 points repères A/B/C/D.")
            lines.append("   • Régression globale (LS) : moindres carrés sur les 12 essais, métriques affichées (MAE, RMSE, R²).")
            lines.append("")
            lines.append("6) Bonnes pratiques / limites")
            lines.append("   • Si T <= 0, vérifier les entrées et le calibrage (cas non physique).")
            lines.append("   • α peut être < 1 (d négatif) ou > 1 (d positif) ; les proportions entre tapis sont conservées.")
            lines.append("   • Le ré‑échelonnage n’altère pas la part relative de chaque tapis ; il assure seulement Σ barres = T.")
        else:
            lines.append("Aucun calcul disponible. Lancez « Calculer » pour générer les valeurs spécifiques (f1,f2,f3, t_i, T, α).")

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
                    messagebox.showinfo("Export", f"Explications exportées :\n{path}")
                except Exception as e:
                    messagebox.showerror("Export", f"Erreur d'export : {e}")
        ttk.Button(bar, text="Copier dans le presse-papiers", command=_copy, style="Ghost.TButton").pack(side="left")
        ttk.Button(bar, text="Exporter en .txt", command=_export, style="Ghost.TButton").pack(side="left", padx=(8,0))

# ---------- Lancement ----------
if __name__ == "__main__":
    app = FourApp()
    app.e1.insert(0, "40.00")   # 40 Hz
    app.e2.insert(0, "50.00")   # 50 Hz
    app.e3.insert(0, "99.99")   # 99.99 Hz
    app.mainloop()
