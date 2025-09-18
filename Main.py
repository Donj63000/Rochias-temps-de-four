# four_3_tapis_app_realtime_v3.py
# Four 3 tapis — TEMPS RÉEL + barres segmentées (3 cellules) + calibrage Ancrage‑4
# Auteur : ChatGPT (pour Val) — 2025

import math, os, sys, time, tkinter as tk
import ctypes
import csv
import json
from pathlib import Path
from tkinter import ttk
from tkinter import scrolledtext, filedialog  # pour la fenêtre Explications


def resource_path(relative: str) -> Path:
    """Retourne le chemin absolu d'une ressource en mode IDE ou PyInstaller."""

    if hasattr(sys, "_MEIPASS") and getattr(sys, "_MEIPASS"):
        base_path = Path(getattr(sys, "_MEIPASS"))
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / relative

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

# ================== Interpolation exacte (12 points) sur T ==================
def _phi_features(f1, f2, f3):
    # base en 1/f, termes quadratiques + interactions + qq cubiques
    inv1, inv2, inv3 = 1.0/f1, 1.0/f2, 1.0/f3
    return np.array([
        1.0,
        inv1, inv2, inv3,
        inv1**2, inv2**2, inv3**2,
        inv1*inv2, inv1*inv3, inv2*inv3,
        inv1**3, inv3**3
    ], float)

def calibrate_interp12(exps):
    """Interpole EXACTEMENT les 12 expériences: phi(f)^T theta = T."""
    X = np.array([_phi_features(e[0]/100.0, e[1]/100.0, e[2]/100.0) for e in exps], float)
    y = np.array([e[3] for e in exps], float)
    theta, *_ = np.linalg.lstsq(X, y, rcond=None)  # SVD, stable numériquement
    yhat = X @ theta
    resid = y - yhat
    mae = float(np.mean(np.abs(resid)))
    rmse = float(np.sqrt(np.mean(resid**2)))
    return theta, {"MAE": mae, "RMSE": rmse, "MAXABS": float(np.max(np.abs(resid)))}

def predict_T_interp12(f1, f2, f3, theta):
    return float(_phi_features(f1, f2, f3) @ theta)

# --- Calibrage global (scientifique)
PARAMS_REG, METRICS_REG = calibrate_regression(EXPS)
D_R, K1_R, K2_R, K3_R = PARAMS_REG


def calibrate_anchor_from_ABCD(exps, ref_ihm=9000):
    ref_hz = ref_ihm / 100.0
    T_ref = next(
        T for T1, T2, T3, T in exps if T1 == ref_ihm and T2 == ref_ihm and T3 == ref_ihm
    )

    def K_for_index(idx):
        for T1, T2, T3, T in exps:
            arr = [T1, T2, T3]
            if sum(1 for v in arr if v == ref_ihm) == 2 and arr[idx] != ref_ihm:
                f_var = arr[idx] / 100.0
                delta = (1.0 / f_var) - (1.0 / ref_hz)
                if abs(delta) <= 1e-12:
                    raise RuntimeError("Delta nul pour l'index %d" % idx)
                return (T - T_ref) / delta
        raise RuntimeError("Essai d'ancrage manquant pour l'index %d" % idx)

    K1 = K_for_index(0)
    K2 = K_for_index(1)
    K3 = K_for_index(2)
    d = T_ref - (K1 + K2 + K3) / ref_hz
    return K1, K2, K3, d


K1_DIST, K2_DIST, K3_DIST, D_ANCH = calibrate_anchor_from_ABCD(EXPS)


# --- Calibrage : theta_12 (exact sur la base de 12 points)
THETA12, METRICS_EXACT = calibrate_interp12(EXPS)  # MAE ~ 1e-12 ici

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

def compute_times(f1, f2, f3):
    """Retourne (t1,t2,t3,total_LS) en minutes avec la régression (LS) uniquement."""
    d, K1, K2, K3 = D_R, K1_R, K2_R, K3_R
    t1, t2, t3 = K1/f1, K2/f2, K3/f3         # convoyage “brut”
    total_LS = d + t1 + t2 + t3              # total 4-paramètres
    return t1, t2, t3, total_LS, (d, K1, K2, K3)

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

TICK_SECONDS = 0.5  # mise à jour 0,5 s pour une animation plus fluide
PREFS_PATH = Path.home() / ".four3_prefs.json"
DEFAULT_INPUTS = ("40.00", "50.00", "99.99")

# ================== Conteneur scrollable vertical ==================
class VScrollFrame(ttk.Frame):
    """Cadre scrollable vertical pour empiler des cartes sans rien couper."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=BG, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = ttk.Frame(self.canvas, style="TFrame")
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        # Ajuste la largeur du contenu à celle du canvas et met à jour la scrollregion
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Molette (Windows/macOS) et boutons 4/5 (Linux)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-4>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-5>", self._on_mousewheel, add="+")

    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        # Force la largeur du cadre intérieur = largeur visible du canvas
        self.canvas.itemconfigure(self._inner_id, width=event.width)

    def _on_mousewheel(self, event):
        # Normalise le défilement
        if getattr(event, "delta", 0) > 0 or getattr(event, "num", None) == 4:
            self.canvas.yview_scroll(-1, "units")
        elif getattr(event, "delta", 0) < 0 or getattr(event, "num", None) == 5:
            self.canvas.yview_scroll(+1, "units")

# ================== Barre Canvas segmentée ==================
class SegmentedBar(tk.Canvas):
    """
    Barre de progression custom :
      - fond sombre
      - remplissage coloré
      - repères verticaux configurables
    Méthodes :
      - set_total_distance(distance)
      - set_progress(distance_elapsed)
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
        self.show_ticks = True
        self._markers = [(1 / 3, "1/3"), (2 / 3, "2/3")]
        self.bind("<Configure>", lambda e: self.redraw())

    def set_total_distance(self, distance: float):
        self.total = max(0.0, float(distance))
        self.elapsed = 0.0
        self.redraw()

    # rétro-compatibilité
    set_total = set_total_distance

    def set_progress(self, seconds_elapsed: float):
        self.elapsed = max(0.0, float(seconds_elapsed))
        self.redraw()

    def reset(self):
        self.total = 0.0
        self.elapsed = 0.0
        self.redraw()

    def set_markers(self, percentages, labels=None):
        markers = []
        if labels is None:
            labels = ["" for _ in percentages]
        for pct, text in zip(percentages, labels):
            try:
                pct_float = float(pct)
            except (TypeError, ValueError):
                continue
            markers.append((pct_float, text))
        self._markers = markers
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
        self.create_rectangle(track_left, track_top, track_right, track_bot, fill=TRACK, outline=ACCENT, width=1)

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

        # Repères (ticks)
        if inner_width > 0 and self.show_ticks:
            for pct, text in self._markers:
                x = track_left + max(0.0, min(1.0, pct)) * inner_width
                self.create_line(int(x), track_top, int(x), track_bot, fill=RED, width=2)
                if text:
                    self.create_text(
                        int(x) + 2,
                        track_top - 6,
                        text=text,
                        anchor="w",
                        fill=SUBTEXT,
                        font=("Consolas", 9),
                    )


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event=None):
        if self.tip is not None:
            return
        tip = tk.Toplevel(self.widget)
        tip.overrideredirect(True)
        try:
            tip.attributes("-alpha", 0.95)
        except Exception:
            pass
        tk.Label(tip, text=self.text, bg="#111111", fg="#ffffff", font=("Segoe UI", 9), padx=8, pady=4).pack()
        tip.update_idletasks()
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip.geometry(f"+{x}+{y}")
        self.tip = tip

    def hide(self, _event=None):
        if self.tip is None:
            return
        try:
            self.tip.destroy()
        except Exception:
            pass
        self.tip = None

# ================== Widgets réutilisables ==================
class Collapsible(ttk.Frame):
    """Cadre repliable type 'disclosure' (► / ▼)."""

    def __init__(self, master, title="Détails", open=False):
        super().__init__(master, style="CardInner.TFrame")
        self._open = bool(open)
        self._title = title
        hdr = ttk.Frame(self, style="CardInner.TFrame")
        hdr.pack(fill="x")
        self._btn = ttk.Button(
            hdr,
            text=self._label_text(),
            style="Ghost.TButton",
            command=self.toggle,
            padding=(8, 4),
        )
        self._btn.pack(side="left")
        self.body = ttk.Frame(self, style="CardInner.TFrame")
        if self._open:
            self.body.pack(fill="both", expand=True, pady=(6, 0))

    def _label_text(self):
        return ("▼ " if self._open else "► ") + self._title

    def toggle(self):
        self._open = not self._open
        self._btn.config(text=self._label_text())
        if self._open:
            self.body.pack(fill="both", expand=True, pady=(6, 0))
        else:
            self.body.forget()

    def set_open(self, open_: bool):
        if bool(open_) != self._open:
            self.toggle()

# ================== Application ==================
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
        path = resource_path("rochias.png")
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
            bar = SegmentedBar(holder, height=30)
            bar.pack(fill="x", expand=True, pady=(8, 4))
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
                    K1_dist=K1_DIST, K2_dist=K2_DIST, K3_dist=K3_DIST,
                )
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
            f1, f2, f3 = calc['f1'], calc['f2'], calc['f3']
            K1, K2, K3 = calc['K1'], calc['K2'], calc['K3']
            d = calc['d']
            t1, t2, t3 = calc['t1'], calc['t2'], calc['t3']
            t1_base = calc.get('t1_base', K1_DIST / f1)
            t2_base = calc.get('t2_base', K2_DIST / f2)
            t3_base = calc.get('t3_base', K3_DIST / f3)
            t1s = calc.get('t1_star', float('nan'))
            t2s = calc.get('t2_star', float('nan'))
            t3s = calc.get('t3_star', float('nan'))
            T_LS = calc.get('T_LS', t1 + t2 + t3 + d)
            T_exp = calc.get('T_exp', predict_T_interp12(f1, f2, f3, THETA12))
            sum_t = calc.get('sum_t', t1 + t2 + t3)
            sum_base = calc.get('sum_base', t1_base + t2_base + t3_base)
            alpha = calc.get('alpha', (T_exp / sum_base if sum_base > 0 else float('nan')))

            lines.append("2) Données calculées (en minutes)")
            lines.append(f"   Paramètres (LS) : d = {d:+.3f} min ;  K1 = {K1:.3f} ; K2 = {K2:.3f} ; K3 = {K3:.3f} (min·Hz)")
            lines.append(f"   Entrées : f1 = {f1:.2f} Hz ; f2 = {f2:.2f} Hz ; f3 = {f3:.2f} Hz")
            lines.append(f"   Temps convoyage pur : t1 = {t1:.3f} ; t2 = {t2:.3f} ; t3 = {t3:.3f}  (Σt = {sum_t:.3f})")
            lines.append(f"   Total LS 4-paramètres : T_LS = {T_LS:.3f} min ({fmt_hms(T_LS*60)})")
            lines.append(f"   Total corrigé (interp. exacte 12 pts) : T = {T_exp:.3f} min ({fmt_hms(T_exp*60)})")
            lines.append("")
            lines.append("3) Constantes d'ancrage (tapis isolés)")
            lines.append(
                f"   • K1' = {K1_DIST:.2f} ; K2' = {K2_DIST:.2f} ; K3' = {K3_DIST:.2f} (min·Hz) — issus des essais A/B/C/D"
            )
            lines.append(
                f"   • Durées brutes : t1' = {t1_base:.3f} ; t2' = {t2_base:.3f} ; t3' = {t3_base:.3f}  (Σt' = {sum_base:.3f})"
            )
            lines.append("")
            lines.append("4) Répartition utilisée dans l'appli")
            lines.append("   • Total exact : interpolation 12 pts (voir ci-dessus)")
            if math.isfinite(alpha):
                lines.append(f"   • Facteur α = {alpha:.6f} = T / Σt'")
                lines.append(f"     → t1* = {t1s:.3f} min ({fmt_hms(t1s*60)})")
                lines.append(f"     → t2* = {t2s:.3f} min ({fmt_hms(t2s*60)})")
                lines.append(f"     → t3* = {t3s:.3f} min ({fmt_hms(t3s*60)})")
            else:
                lines.append("   • Facteur α non défini (division par 0)")
            lines.append("")
            lines.append("5) Interprétation des barres (Canvas)")
            lines.append("   • On anime une « distance » D_i (min·Hz) parcourue à la vitesse f_i (Hz) :")
            lines.append("       distance_parcourue = f_i · (temps_écoulé / 60)")
            lines.append("       fin de la barre quand distance_parcourue ≥ D_i")
            lines.append("   • Pour durer t_i*, on prend D_i = α · K_i' ; durée = (D_i/f_i)·60 = α·(K_i'/f_i)·60 = t_i*·60.")
            lines.append("")
            lines.append("6) Méthode et précision")
            lines.append("   • Régression globale (LS) : moindres carrés sur les 12 essais pour estimer d et K_i.")
            lines.append("   • Interpolation exacte (12 pts) : corrige T pour retrouver les durées mesurées sur la base.")
            lines.append("   • Répartition : ancrage A/B/C/D → ratios réalistes, puis α pour recoller au total exact.")
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

# ---------- Lancement ----------
if __name__ == "__main__":
    app = FourApp()
    app.mainloop()
