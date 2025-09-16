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
BG      = "#0b1020"
CARD    = "#121a34"
ACCENT  = "#3b82f6"
TEXT    = "#e5e7eb"
SUBTEXT = "#93c5fd"
RED     = "#ef4444"   # séparateurs
FILL    = ACCENT
TRACK   = "#0f172a"

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
        super().__init__(master, bg=CARD, highlightthickness=0, height=height, **kwargs)
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
        w = self.winfo_width() or 100
        h = self.winfo_height() or self.height
        self.delete("all")
        # Piste
        r = h//2
        self.create_rectangle(0, r-8, w, r+8, fill=TRACK, outline=TRACK)

        # Remplissage
        pct = 0.0 if self.total <= 1e-9 else min(1.0, self.elapsed / self.total)
        fill_w = int(pct * w)
        self.create_rectangle(0, r-8, fill_w, r+8, fill=FILL, outline=FILL)

        # Séparateurs rouges à 1/3 et 2/3 (toujours visibles)
        x1 = int(w/3); x2 = int(2*w/3)
        self.create_line(x1, r-10, x1, r+10, fill=RED, width=2)
        self.create_line(x2, r-10, x2, r+10, fill=RED, width=2)

# ================== Application ==================
class FourApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Four • 3 Tapis — Calcul & Barres (Temps réel)")
        self.configure(bg=BG)
        self.geometry("1180x760")
        self.minsize(1100, 700)

        # États animation
        self.animating = False
        self.paused = False
        self.seg_idx = 0
        self.seg_start = 0.0
        self.seg_totals = [0.0, 0.0, 0.0]   # secondes réelles (t1,t2,t3)
        self.mode = tk.StringVar(value="anchor")  # 'anchor' ou 'reg'

        # UI
        self._build_ui()

    def _build_ui(self):
        # Header
        header = ttk.Frame(self, style="TFrame"); header.pack(fill="x", padx=18, pady=(16,8))
        ttk.Style().configure("TFrame", background=BG)
        ttk.Style().configure("Card.TFrame", background=CARD)
        ttk.Style().configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 11))
        ttk.Style().configure("Card.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI", 11))
        ttk.Style().configure("Header.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 13))
        ttk.Style().configure("Big.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI", 20, "bold"))
        ttk.Style().configure("Mono.TLabel", background=CARD, foreground=TEXT, font=("Consolas", 11))
        ttk.Style().configure("TButton", font=("Segoe UI", 11, "bold"))

        ttk.Label(header, text="Simulation de four — 3 tapis (temps réel)", style="TLabel").pack(side="left")
        ttk.Label(header, text="Modèle : T = d + K1/f1 + K2/f2 + K3/f3   (f = IHM/100)", style="TLabel").pack(side="right")

        top = ttk.Frame(self, style="TFrame"); top.pack(fill="x", padx=18, pady=6)

        # --- Entrées
        card_in = ttk.Frame(top, style="Card.TFrame"); card_in.pack(side="left", fill="both", expand=True, padx=(0,8))
        ttk.Label(card_in, text="Entrées (fréquences des variateurs)", style="Header.TLabel").pack(anchor="w", padx=16, pady=(14,6))
        g = ttk.Frame(card_in, style="Card.TFrame"); g.pack(anchor="w", padx=16, pady=8)

        ttk.Label(g, text="Tapis 1 : Hz =", style="Card.TLabel").grid(row=0, column=0, sticky="e", padx=(0,8), pady=6)
        self.e1 = ttk.Entry(g, width=12, font=("Consolas", 12)); self.e1.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(g, text="Tapis 2 : Hz =", style="Card.TLabel").grid(row=1, column=0, sticky="e", padx=(0,8), pady=6)
        self.e2 = ttk.Entry(g, width=12, font=("Consolas", 12)); self.e2.grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(g, text="Tapis 3 : Hz =", style="Card.TLabel").grid(row=2, column=0, sticky="e", padx=(0,8), pady=6)
        self.e3 = ttk.Entry(g, width=12, font=("Consolas", 12)); self.e3.grid(row=2, column=1, sticky="w", pady=6)
        ttk.Label(card_in, text="Astuce : 40.00 ou 4000 (IHM). >200 = IHM/100.", style="Card.TLabel").pack(anchor="w", padx=16, pady=(2,8))

        # Mode de calcul
        mode_row = ttk.Frame(card_in, style="Card.TFrame"); mode_row.pack(anchor="w", padx=16, pady=(0,10))
        ttk.Label(mode_row, text="Calibration :", style="Card.TLabel").grid(row=0, column=0, padx=(0,8))
        ttk.Radiobutton(mode_row, text="Ancrage‑4 (colle au tableur)", variable=self.mode, value="anchor").grid(row=0, column=1, padx=(0,12))
        ttk.Radiobutton(mode_row, text="Régression globale (LS)", variable=self.mode, value="reg").grid(row=0, column=2)

        # Boutons
        btns = ttk.Frame(card_in, style="Card.TFrame"); btns.pack(anchor="w", padx=16, pady=(0,14))
        ttk.Button(btns, text="Calculer", command=self.on_calculer).grid(row=0, column=0, padx=(0,10))
        self.btn_start = ttk.Button(btns, text="Démarrer (temps réel)", command=self.on_start, state="disabled"); self.btn_start.grid(row=0, column=1, padx=(0,10))
        self.btn_pause = ttk.Button(btns, text="Pause", command=self.on_pause, state="disabled"); self.btn_pause.grid(row=0, column=2, padx=(0,10))
        ttk.Button(btns, text="Reset", command=self.on_reset).grid(row=0, column=3)

        # --- Résultats
        card_out = ttk.Frame(top, style="Card.TFrame"); card_out.pack(side="left", fill="both", expand=True, padx=(8,0))
        ttk.Label(card_out, text="Résultats", style="Header.TLabel").pack(anchor="w", padx=16, pady=(14,6))
        table = ttk.Frame(card_out, style="Card.TFrame"); table.pack(anchor="w", padx=16, pady=(6,2))
        ttk.Label(table, text="Tapis", style="Card.TLabel").grid(row=0, column=0, padx=6, pady=4)
        ttk.Label(table, text="f (Hz)", style="Card.TLabel").grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(table, text="t_i (convoyage pur)", style="Card.TLabel").grid(row=0, column=2, padx=6, pady=4)

        self.row_labels = []
        for i in range(3):
            r = i+1
            ttk.Label(table, text=f"{i+1}", style="Card.TLabel").grid(row=r, column=0, padx=6, pady=6, sticky="e")
            lf = ttk.Label(table, text="—", style="Card.TLabel"); lf.grid(row=r, column=1, padx=6, pady=6, sticky="w")
            lt = ttk.Label(table, text="—", style="Card.TLabel"); lt.grid(row=r, column=2, padx=6, pady=6, sticky="w")
            self.row_labels.append((lf, lt))

        ttk.Separator(card_out).pack(fill="x", padx=16, pady=6)
        self.lbl_total_big = ttk.Label(card_out, text="Temps total (modèle) : —", style="Big.TLabel")
        self.lbl_total_big.pack(anchor="w", padx=16, pady=2)

        # Affiche les paramètres (info)
        ttk.Separator(card_out).pack(fill="x", padx=16, pady=6)
        params_txt = (f"[Ancrage‑4] d={D_A:+.3f}  K1={K1_A:.3f}  K2={K2_A:.3f}  K3={K3_A:.3f} (min·Hz)\n"
                      f"[Régression] d={D_R:+.3f}  K1={K1_R:.3f}  K2={K2_R:.3f}  K3={K3_R:.3f}  (MAE≈{METRICS_REG['MAE']:.2f} min ; RMSE≈{METRICS_REG['RMSE']:.2f} min ; R²≈{METRICS_REG['R2']:.3f})")
        ttk.Label(card_out, text=params_txt, style="Mono.TLabel").pack(anchor="w", padx=16, pady=(0,8))

        # --- Barres segmentées
        pcard = ttk.Frame(self, style="Card.TFrame"); pcard.pack(fill="x", padx=18, pady=8)
        ttk.Label(pcard, text="Barres de chargement (temps réel, 3 cellules)", style="Header.TLabel").pack(anchor="w", padx=16, pady=(14,10))

        self.bars = []
        self.bar_texts = []
        for i in range(3):
            row = ttk.Frame(pcard, style="Card.TFrame")
            row.pack(fill="x", padx=16, pady=6)
            row.columnconfigure(1, weight=1)
            ttk.Label(row, text=f"Tapis {i+1}", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0,10))
            bar = SegmentedBar(row, height=24)
            bar.grid(row=0, column=1, sticky="ew")
            txt = ttk.Label(row, text="—", style="Card.TLabel")
            txt.grid(row=0, column=2, sticky="e", padx=(10,0))
            self.bars.append(bar); self.bar_texts.append(txt)

    # ---------- Actions ----------
    def on_reset(self):
        self.animating = False
        self.paused = False
        self.seg_idx = 0
        self.seg_start = 0.0
        for b, t in zip(self.bars, self.bar_texts):
            b.reset(); t.config(text="—")
        for lf, lt in self.row_labels:
            lf.config(text="—"); lt.config(text="—")
        self.lbl_total_big.config(text="Temps total (modèle) : —")
        self.btn_start.config(state="disabled"); self.btn_pause.config(state="disabled")

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

        # Barres : init temps réels (secondes) + texte
        self.seg_totals = [t1*60.0, t2*60.0, t3*60.0]
        for i in range(3):
            tot = self.seg_totals[i]
            self.bars[i].set_total(tot)
            self.bar_texts[i].config(text=f"0%  •  00:00:00 / {fmt_hms(tot)}  •  en attente")
        self.btn_start.config(state="normal"); self.btn_pause.config(state="disabled")

    def on_start(self):
        if self.animating: return
        if sum(self.seg_totals) <= 0:
            messagebox.showwarning("Calcul manquant", "Clique d'abord sur « Calculer »."); return
        self.animating = True
        self.paused = False
        self.seg_idx = 0
        self.seg_start = time.perf_counter()
        self.btn_pause.config(state="normal", text="Pause")
        self._tick()

    def on_pause(self):
        if not self.animating: return
        if not self.paused:
            self.paused = True
            self.pause_t0 = time.perf_counter()
            self.btn_pause.config(text="Reprendre")
        else:
            delta = time.perf_counter() - self.pause_t0
            self.seg_start += delta
            self.paused = False
            self.btn_pause.config(text="Pause")
            self._tick()

    def _tick(self):
        if not self.animating: return
        if self.paused:
            self.after(int(TICK_SECONDS*1000), self._tick); return

        i = self.seg_idx
        dur = max(1e-6, self.seg_totals[i])
        now = time.perf_counter()
        elapsed = now - self.seg_start
        prog = elapsed / dur

        if prog >= 1.0:
            # Terminer ce segment
            self.bars[i].set_progress(dur)
            self.bar_texts[i].config(text=f"100%  •  {fmt_hms(dur)} / {fmt_hms(dur)}  •  terminé")
            self.seg_idx += 1
            if self.seg_idx >= 3:
                self.animating = False
                self.btn_pause.config(state="disabled", text="Pause"); return
            # suivant
            self.seg_start = now
            j = self.seg_idx
            self.bar_texts[j].config(text=f"0%  •  00:00:00 / {fmt_hms(self.seg_totals[j])}  •  en cours…")
            self.after(int(TICK_SECONDS*1000), self._tick)
            return

        pct = max(0.0, min(1.0, prog)) * 100.0
        self.bars[i].set_progress(elapsed)
        self.bar_texts[i].config(text=f"{pct:5.1f}%  •  {fmt_hms(elapsed)} / {fmt_hms(dur)}  •  en cours…")

        self.after(int(TICK_SECONDS*1000), self._tick)

# ---------- Lancement ----------
if __name__ == "__main__":
    app = FourApp()
    app.e1.insert(0, "40.00")   # 40 Hz
    app.e2.insert(0, "50.00")   # 50 Hz
    app.e3.insert(0, "99.99")   # 99.99 Hz
    app.mainloop()
