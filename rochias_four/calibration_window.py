# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from .calibration_overrides import (
    get_current_anchor, set_current_anchor, reset_anchor_to_default,
    load_anchor_from_disk, save_anchor_to_disk,
    fit_anchor_from_direct, fit_anchor_from_points, AnchorParams,
)
from .speed_overrides import (
    load_speed_from_disk, save_speed_to_disk, reset_speed_to_default,
    get_current_speedset, set_current_speedset,
    fit_line_through_origin, fit_line_with_intercept, estimate_speed_mps,
    SpeedParams, SpeedSet
)

class CalibrationWindow(tk.Toplevel):
    """
    Fenêtre modale de calibration (simple & intuitive).
    - Onglet 1 : Ancrage simple (1 triplet de fréquences + 3 temps + total)
    - Onglet 2 : Par points (liste de runs (f1,f2,f3,T) -> OLS)
    - Boutons : Aperçu, Appliquer, Sauver, Réinitialiser, Fermer
    """
    def __init__(self, master):
        super().__init__(master)
        self.title("Calibration — Ancrages (temps par tapis)")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        nb = ttk.Notebook(self)
        self.nb = nb
        self.tab_simple = ttk.Frame(nb)
        self.tab_points = ttk.Frame(nb)
        self.tab_speed = ttk.Frame(nb)
        nb.add(self.tab_simple, text="Ancrage simple")
        nb.add(self.tab_points, text="Par mesures (points)")
        nb.add(self.tab_speed, text="Vitesses (m/s)")
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_tab_simple()
        self._build_tab_points()
        self._build_tab_speed()

        # Boutons bas
        frm_btn = ttk.Frame(self)
        frm_btn.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(frm_btn, text="Aperçu", command=self._on_preview).pack(side="left")
        ttk.Button(frm_btn, text="Appliquer", command=self._on_apply).pack(side="left", padx=6)
        ttk.Button(frm_btn, text="Sauver", command=self._on_save).pack(side="left")
        ttk.Button(frm_btn, text="Réinitialiser", command=self._on_reset).pack(side="left", padx=6)
        ttk.Button(frm_btn, text="Fermer", command=self.destroy).pack(side="right")

        self.lbl_info = ttk.Label(self, text="", foreground="#2a5")
        self.lbl_info.pack(fill="x", padx=8, pady=(0,8))

        # charge d'éventuels paramètres déjà sauvegardés
        load_anchor_from_disk()
        load_speed_from_disk()

    def _build_tab_speed(self):
        f = self.tab_speed
        # Checkbox modèle
        self.cb_force_through_origin = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Forcer b=0 (v = a·f)", variable=self.cb_force_through_origin).grid(
            row=0, column=0, columnspan=6, sticky="w", pady=(6,4))

        # 3 tableaux: T1, T2, T3
        self._speed_tables = []
        for i, name in enumerate(("Tapis 1", "Tapis 2", "Tapis 3")):
            row = 1 + i*4
            ttk.Label(f, text=name, font=("TkDefaultFont", 10, "bold")).grid(row=row, column=0, sticky="w", pady=(8,2))
            cols = ("Hz", "t_1m (s)", "v (m/s)")
            tv = ttk.Treeview(f, columns=cols, show="headings", height=4)
            for c in cols:
                tv.heading(c, text=c); tv.column(c, width=90, anchor="center")
            tv.grid(row=row+1, column=0, columnspan=6, sticky="nsew")

            # Inputs
            ttk.Label(f, text="Hz").grid(row=row+2, column=0, sticky="e")
            e_f = ttk.Entry(f, width=8); e_f.grid(row=row+2, column=1, sticky="w")
            ttk.Label(f, text="t_1m (s)").grid(row=row+2, column=2, sticky="e")
            e_t = ttk.Entry(f, width=8); e_t.grid(row=row+2, column=3, sticky="w")
            ttk.Label(f, text="ou v (m/s)").grid(row=row+2, column=4, sticky="e")
            e_v = ttk.Entry(f, width=8); e_v.grid(row=row+2, column=5, sticky="w")

            def add_point(tv=tv, e_f=e_f, e_t=e_t, e_v=e_v):
                hf = e_f.get().strip(); ht = e_t.get().strip(); hv = e_v.get().strip()
                if not hf:
                    return
                tv.insert("", "end", values=(hf, ht, hv))
                e_f.delete(0,"end"); e_t.delete(0,"end"); e_v.delete(0,"end")

            ttk.Button(f, text="Ajouter", command=add_point).grid(row=row+3, column=1, sticky="w")
            ttk.Button(f, text="Supprimer", command=lambda tv=tv: [tv.delete(i) for i in tv.selection()]).grid(row=row+3, column=2, sticky="w")
            # Label de preview
            lbl = ttk.Label(f, text="Prévisualisation: --")
            lbl.grid(row=row+3, column=3, columnspan=3, sticky="w")
            self._speed_tables.append((tv, lbl))

        # Boutons bas (spécifiques vitesses)
        frm = ttk.Frame(f); frm.grid(row=20, column=0, columnspan=6, sticky="ew", pady=(8,6))
        ttk.Button(frm, text="Aperçu vitesses", command=self._on_speed_preview).pack(side="left")
        ttk.Button(frm, text="Appliquer vitesses", command=self._on_speed_apply).pack(side="left", padx=6)
        ttk.Button(frm, text="Sauver vitesses", command=self._on_speed_save).pack(side="left")
        ttk.Button(frm, text="Réinitialiser vitesses", command=self._on_speed_reset).pack(side="left", padx=6)

    def _collect_speed_points(self, tv) -> list[tuple[float,float]]:
        """Lit un Treeview -> liste de (f, v) en m/s."""
        pts = []
        for it in tv.get_children():
            f_str, t_str, v_str = tv.item(it, "values")
            f = float(f_str)
            t = float(t_str) if t_str not in ("", None) else None
            v = float(v_str) if v_str not in ("", None) else None
            # conversion -> (f, v)
            if v is None:
                if t is None:
                    continue
                if t <= 0:
                    continue
                v = 1.0 / t
            pts.append((f, v))
        return pts

    def _fit_for_table(self, tv, force_b_zero: bool) -> SpeedParams | None:
        pts = self._collect_speed_points(tv)
        if len(pts) == 0:
            return None
        if force_b_zero:
            return fit_line_through_origin(pts)
        else:
            return fit_line_with_intercept(pts)

    def _on_speed_preview(self):
        force0 = self.cb_force_through_origin.get()
        previews: list[SpeedParams | None] = []
        for tv, lbl in self._speed_tables:
            p = self._fit_for_table(tv, force0)
            previews.append(p)
            if p is None:
                lbl.config(text="Prévisualisation: --")
            else:
                v50 = estimate_speed_mps(p, 50.0)
                v80 = estimate_speed_mps(p, 80.0)
                lbl.config(text=f"Prévisualisation: v = {p.a:.5f}·f {'+' if p.b>=0 else '-'} {abs(p.b):.5f}  → v(50)={v50:.3f} m/s, v(80)={v80:.3f} m/s")

        # Si 0 point sur un tapis, on affiche “--” et on n'écrase rien

    def _on_speed_apply(self):
        force0 = self.cb_force_through_origin.get()
        params = []
        for tv, _ in self._speed_tables:
            p = self._fit_for_table(tv, force0)
            if p is None:
                # pas de points => on garde l'existant si il existe
                cur = get_current_speedset()
                if cur is None:
                    # rien d'existant -> neutre (n'influencera rien si non utilisé)
                    p = SpeedParams(a=0.0, b=0.0)
                else:
                    # conserve la valeur déjà en mémoire
                    # (on reconstruira SpeedSet plus bas)
                    params.append(None)
                    continue
            params.append(p)

        cur = get_current_speedset()
        t1 = params[0] if params[0] is not None else (cur.t1 if cur else SpeedParams(0.0,0.0))
        t2 = params[1] if params[1] is not None else (cur.t2 if cur else SpeedParams(0.0,0.0))
        t3 = params[2] if params[2] is not None else (cur.t3 if cur else SpeedParams(0.0,0.0))
        set_current_speedset(SpeedSet(t1=t1, t2=t2, t3=t3))
        self.lbl_info.config(text="Vitesses appliquées (session). Total/répartition inchangés.")
        if hasattr(self.master, "refresh_after_calibration"):
            self.master.refresh_after_calibration()

    def _on_speed_save(self):
        if get_current_speedset() is None:
            self.lbl_info.config(text="Aucune vitesse à sauver (applique d'abord).")
            return
        save_speed_to_disk()
        self.lbl_info.config(text="Vitesses sauvegardées (persistant).")

    def _on_speed_reset(self):
        reset_speed_to_default()
        self.lbl_info.config(text="Vitesses réinitialisées.")
        if hasattr(self.master, "refresh_after_calibration"):
            self.master.refresh_after_calibration()

    # ---------- Onglet 1 : ancrage simple ----------
    def _build_tab_simple(self):
        f = self.tab_simple

        # Ligne de fréquences de référence
        row = 0
        ttk.Label(f, text="Fréquences de référence (Hz affichés)").grid(row=row, column=0, columnspan=6, sticky="w", pady=(4,2))
        self.e_f1 = ttk.Entry(f, width=8); self.e_f1.insert(0, "60")
        self.e_f2 = ttk.Entry(f, width=8); self.e_f2.insert(0, "60")
        self.e_f3 = ttk.Entry(f, width=8); self.e_f3.insert(0, "60")
        ttk.Label(f, text="T1:").grid(row=row+1, column=0, sticky="e"); self.e_f1.grid(row=row+1, column=1, sticky="w")
        ttk.Label(f, text="T2:").grid(row=row+1, column=2, sticky="e"); self.e_f2.grid(row=row+1, column=3, sticky="w")
        ttk.Label(f, text="T3:").grid(row=row+1, column=4, sticky="e"); self.e_f3.grid(row=row+1, column=5, sticky="w")

        # Ligne des temps par tapis pour ces Hz
        row += 2
        ttk.Label(f, text="Temps mesurés (minutes) à ces fréquences").grid(row=row, column=0, columnspan=6, sticky="w", pady=(8,2))
        self.e_t1 = ttk.Entry(f, width=8); self.e_t1.insert(0, "50.0")
        self.e_t2 = ttk.Entry(f, width=8); self.e_t2.insert(0, "50.0")
        self.e_t3 = ttk.Entry(f, width=8); self.e_t3.insert(0, "50.0")
        ttk.Label(f, text="T1:").grid(row=row+1, column=0, sticky="e"); self.e_t1.grid(row=row+1, column=1, sticky="w")
        ttk.Label(f, text="T2:").grid(row=row+1, column=2, sticky="e"); self.e_t2.grid(row=row+1, column=3, sticky="w")
        ttk.Label(f, text="T3:").grid(row=row+1, column=4, sticky="e"); self.e_t3.grid(row=row+1, column=5, sticky="w")

        # Temps total constaté pour ce triplet (optionnel, sinon déduit)
        row += 2
        ttk.Label(f, text="Temps total observé (min) pour ce triplet (optionnel)").grid(row=row, column=0, columnspan=6, sticky="w", pady=(8,2))
        self.e_T = ttk.Entry(f, width=10); self.e_T.insert(0, "")
        self.e_T.grid(row=row+1, column=1, sticky="w")
        ttk.Label(f, text="(Si vide, on prend T = t1+t2+t3)").grid(row=row+1, column=2, columnspan=4, sticky="w")

        # Affichage courant
        row += 2
        self.lbl_current = ttk.Label(f, text="Ancrages actuels : ")
        self.lbl_current.grid(row=row, column=0, columnspan=6, sticky="w", pady=(10,0))
        self._refresh_current_label()

    def _refresh_current_label(self):
        a = get_current_anchor()
        self.lbl_current.config(text=f"Ancrages actuels → K1={a.K1:.2f}, K2={a.K2:.2f}, K3={a.K3:.2f}, B={a.B:.2f}")

    # ---------- Onglet 2 : fit par points ----------
    def _build_tab_points(self):
        f = self.tab_points
        ttk.Label(f, text="Mesures (f1,f2,f3 → T en min)").grid(row=0, column=0, columnspan=6, sticky="w", pady=(4,2))
        cols = ("f1", "f2", "f3", "T")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=6)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=80, anchor="center")
        self.tree.grid(row=1, column=0, columnspan=6, sticky="nsew")

        # Entrées pour ajouter un point
        ttk.Label(f, text="f1").grid(row=2, column=0, sticky="e"); self.p_f1 = ttk.Entry(f, width=8); self.p_f1.grid(row=2, column=1, sticky="w")
        ttk.Label(f, text="f2").grid(row=2, column=2, sticky="e"); self.p_f2 = ttk.Entry(f, width=8); self.p_f2.grid(row=2, column=3, sticky="w")
        ttk.Label(f, text="f3").grid(row=2, column=4, sticky="e"); self.p_f3 = ttk.Entry(f, width=8); self.p_f3.grid(row=2, column=5, sticky="w")
        ttk.Label(f, text="T (min)").grid(row=3, column=0, sticky="e"); self.p_T = ttk.Entry(f, width=8); self.p_T.grid(row=3, column=1, sticky="w")
        ttk.Button(f, text="Ajouter", command=self._add_point).grid(row=3, column=2, sticky="w", padx=4)
        ttk.Button(f, text="Supprimer", command=self._del_point).grid(row=3, column=3, sticky="w")

        f.grid_rowconfigure(1, weight=1)
        f.grid_columnconfigure(5, weight=1)

    def _add_point(self):
        try:
            f1 = float(self.p_f1.get()); f2 = float(self.p_f2.get()); f3 = float(self.p_f3.get()); T = float(self.p_T.get())
        except Exception:
            messagebox.showerror("Erreur", "Valeurs numériques invalides.")
            return
        self.tree.insert("", "end", values=(f1, f2, f3, T))
        self.p_f1.delete(0, "end"); self.p_f2.delete(0, "end"); self.p_f3.delete(0, "end"); self.p_T.delete(0, "end")

    def _del_point(self):
        for sel in self.tree.selection():
            self.tree.delete(sel)

    # ---------- Boutons bas ----------
    def _on_preview(self):
        try:
            # Onglet courant
            idx = self.nb.index("current")
        except Exception:
            idx = 0

        if idx == 2:
            self._on_speed_preview()
            return

        if idx == 0:
            # Simple
            try:
                f1 = float(self.e_f1.get()); f2 = float(self.e_f2.get()); f3 = float(self.e_f3.get())
                t1 = float(self.e_t1.get()); t2 = float(self.e_t2.get()); t3 = float(self.e_t3.get())
                T  = float(self.e_T.get()) if self.e_T.get().strip() else (t1 + t2 + t3)
            except Exception:
                messagebox.showerror("Erreur", "Entrées invalides.")
                return
            params = fit_anchor_from_direct(f1, f2, f3, t1, t2, t3, T)
        else:
            # Points
            pts = []
            for it in self.tree.get_children():
                f1, f2, f3, T = self.tree.item(it, "values")
                pts.append((float(f1), float(f2), float(f3), float(T)))
            if len(pts) < 4:
                messagebox.showwarning("Info", "Ajoute au moins 4 points pour un fit robuste.")
                return
            params = fit_anchor_from_points(pts)

        self.lbl_info.config(text=f"Prévisualisation → K1={params.K1:.2f}, K2={params.K2:.2f}, K3={params.K3:.2f}, B={params.B:.2f}")

    def _on_apply(self):
        # Applique (runtime) sans écriture disque
        txt = self.lbl_info.cget("text")
        if "K1=" not in txt:
            # si pas d'aperçu, on applique les actuels (ou recalcule depuis simple)
            try:
                f1 = float(self.e_f1.get()); f2 = float(self.e_f2.get()); f3 = float(self.e_f3.get())
                t1 = float(self.e_t1.get()); t2 = float(self.e_t2.get()); t3 = float(self.e_t3.get())
                T  = float(self.e_T.get()) if self.e_T.get().strip() else (t1 + t2 + t3)
                params = fit_anchor_from_direct(f1, f2, f3, t1, t2, t3, T)
            except Exception:
                messagebox.showerror("Erreur", "Entrées invalides.")
                return
        else:
            # parse ce qu'on vient d'afficher
            try:
                part = txt.split("→",1)[1]
                d = dict(s.split("=") for s in part.replace(" ", "").split(","))
                params = AnchorParams(K1=float(d["K1"]), K2=float(d["K2"]), K3=float(d["K3"]), B=float(d["B"]))
            except Exception:
                messagebox.showerror("Erreur", "Impossible de lire la prévisualisation.")
                return

        set_current_anchor(params)
        self._refresh_current_label()
        messagebox.showinfo("OK", "Ancrages appliqués (session en cours).\n"
                                  "Le total reste au modèle synergie par défaut.\n"
                                  "La répartition et les hauteurs h1/h2/h3 utilisent ces ancrages.")

        # demande au master de rafraîchir l'écran si il expose une méthode
        if hasattr(self.master, "refresh_after_calibration"):
            self.master.refresh_after_calibration()

    def _on_save(self):
        save_anchor_to_disk()
        messagebox.showinfo("Sauvé", "Ancrages sauvegardés (persistants).")

    def _on_reset(self):
        reset_anchor_to_default()
        self._refresh_current_label()
        self.lbl_info.config(text="")
        messagebox.showinfo("Réinitialisé", "Ancrages remis aux valeurs par défaut.")
        if hasattr(self.master, "refresh_after_calibration"):
            self.master.refresh_after_calibration()
