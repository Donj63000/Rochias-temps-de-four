# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from .calibration_overrides import (
    get_current_anchor, set_current_anchor, reset_anchor_to_default,
    load_anchor_from_disk, save_anchor_to_disk,
    fit_anchor_from_direct, fit_anchor_from_points, AnchorParams,
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
        self.tab_simple = ttk.Frame(nb)
        self.tab_points = ttk.Frame(nb)
        nb.add(self.tab_simple, text="Ancrage simple")
        nb.add(self.tab_points, text="Par mesures (points)")
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_tab_simple()
        self._build_tab_points()

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
            idx = self.nametowidget(self.children["!notebook"]).index("current")
        except Exception:
            idx = 0

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
