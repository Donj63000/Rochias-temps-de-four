from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .segments import GEOM, breakdown_for_belt
from .utils import fmt_hms


class DetailsWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Détails par tapis — décomposition segments")
        self.geometry("880x620")
        self.configure(bg=getattr(app, "BG", "#ffffff"))

        if hasattr(app, "theme"):
            try:
                app.theme.apply_matplotlib  # no-op guard
            except Exception:
                pass

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.tabs = {}
        for i in (1, 2, 3):
            frame = ttk.Frame(self.nb)
            self.nb.add(frame, text=f"Tapis {i}")
            self.tabs[i] = self._build_tab(frame, i)

        self._populate()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_tab(self, parent, belt_index: int):
        # Bandeau supérieur (fréquence & rappel s/m)
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=12, pady=(12, 6))
        lbl_freq = ttk.Label(top, text="f = -- Hz")
        lbl_freq.pack(side="left")
        lbl_sperm = ttk.Label(top, text=" | Temps pour 1 m = -- s")
        lbl_sperm.pack(side="left")

        # >>> Rappel explicite pour éviter toute confusion
        legend = ttk.Label(
            parent,
            text=(
                "RAPPEL : le temps de CHAUFFE (∑ cellules) est inclus dans le temps de CONVOYAGE "
                "(pré + chauffe + transfert). Le TOTAL de ligne = somme des temps de CONVOYAGE des 3 tapis."
            ),
            justify="left",
        )
        legend.pack(fill="x", padx=12, pady=(0, 6))

        cols = ("segment", "longueur_cm", "temps_s", "temps_hms")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=12)
        tree.pack(fill="both", expand=True, padx=12, pady=6)

        headers = {
            "segment": "Segment",
            "longueur_cm": "Longueur (cm)",
            "temps_s": "Temps (s)",
            "temps_hms": "Temps (h:m:s)",
        }
        widths = {"segment": 200, "longueur_cm": 120, "temps_s": 120, "temps_hms": 140}
        for c in cols:
            tree.heading(c, text=headers[c])
            tree.column(c, width=widths[c], anchor="center")

        footer = ttk.Frame(parent)
        footer.pack(fill="x", padx=12, pady=(0, 12))
        lbl_resume = ttk.Label(footer, text="--")
        lbl_resume.pack(anchor="e")

        return {
            "lbl_freq": lbl_freq,
            "lbl_sperm": lbl_sperm,
            "tree": tree,
            "lbl_resume": lbl_resume,
        }

    def _populate(self):
        calc = getattr(self.app, "last_calc", None)
        if not calc:
            return

        # secondes de CONVOYAGE par tapis (déjà calculées par l’app)
        t1 = float(self.app.seg_durations[0]) if self.app.seg_durations else float(calc["t1_hms"].split("|")[0])
        t2 = float(self.app.seg_durations[1]) if self.app.seg_durations else 0.0
        t3 = float(self.app.seg_durations[2]) if self.app.seg_durations else 0.0
        conv_secs = {1: t1, 2: t2, 3: t3}

        freqs = {1: float(calc["f1"]), 2: float(calc["f2"]), 3: float(calc["f3"])}

        for i in (1, 2, 3):
            tab = self.tabs[i]
            tree: ttk.Treeview = tab["tree"]
            for r in tree.get_children():
                tree.delete(r)

            br = breakdown_for_belt(i, conv_secs[i])
            g = br["geom"]

            tab["lbl_freq"].config(text=f"f = {freqs[i]:.2f} Hz")
            tab["lbl_sperm"].config(
                text=f" | Temps pour 1 m = {br['s_per_m']:.2f} s/m ({fmt_hms(br['s_per_m'])} par m)"
            )

            def add(seg, Lcm, sec):
                tree.insert("", "end", values=(seg, f"{Lcm:.1f}", f"{sec:.2f}", fmt_hms(sec)))

            add("Pré‑entrée", g.pre_cm, br["pre_sec"])
            for idx, (Lcm, sec) in enumerate(zip(g.cells_cm, br["cell_secs"]), start=1):
                add(f"Cellule {idx}", Lcm, sec)
            add("Transfert", g.transfer_cm, br["transfer_sec"])

            tree.insert("", "end", values=("", "", "", ""))  # ligne vide
            add("Sous‑total CHAUFFE (∑ cellules)", g.chauffe_cm, br["chauffe_sec"])
            add("Total CONVOYAGE (pré + chauffe + transfert)", g.convoy_cm, br["convoy_sec"])

            # Contrôle d’écart (numérique)
            diff = br["convoy_sec"] - br["convoy_rebuilt_sec"]
            tab["lbl_resume"].config(
                text=(
                    f"Contrôle: somme segments = {fmt_hms(br['convoy_rebuilt_sec'])} | "
                    f"officiel convoyage = {fmt_hms(br['convoy_sec'])} | écart = {diff:.3f} s"
                )
            )

    def refresh_from_app(self):
        self._populate()

    def _on_close(self):
        try:
            if hasattr(self.app, "details_window") and self.app.details_window is self:
                self.app.details_window = None
        except Exception:
            pass
        self.destroy()
