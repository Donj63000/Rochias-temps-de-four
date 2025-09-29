from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str              # fenêtre
    surface: str         # cartes, panneaux
    surface_muted: str   # panneaux secondaires
    text: str
    text_muted: str
    primary: str         # boutons principaux
    success: str         # "Prêt"
    warning: str         # "En cours"
    danger: str          # erreurs
    stroke: str          # bordures/spines
    grid: str            # grille de graph
    curve: str           # couleur TRAIT de la couche
    curve_fill: str      # couleur REMPLISSAGE de la couche
    curve_fill_alpha: float


LIGHT = Theme(
    name="light",
    bg="#ffffff",
    surface="#eef2ff",
    surface_muted="#f7f7fb",
    text="#0f172a",
    text_muted="#475569",
    primary="#3b82f6",
    success="#16a34a",
    warning="#f59e0b",
    danger="#dc2626",
    stroke="#cbd5e1",
    grid="#94a3b8",
    curve="#1d4ed8",
    curve_fill="#60a5fa",
    curve_fill_alpha=0.25,
)


DARK = Theme(
    name="dark",
    bg="#0f172a",
    surface="#1f2937",
    surface_muted="#111827",
    text="#e5e7eb",
    text_muted="#9ca3af",
    primary="#22c55e",
    success="#22c55e",
    warning="#f59e0b",
    danger="#ef4444",
    stroke="#374151",
    grid="#334155",
    curve="#22c55e",
    curve_fill="#22c55e",
    curve_fill_alpha=0.20,
)


ORANGE = Theme(
    name="orange",
    bg="#2A1E17",            # fond brun foncé (contraste élevé)
    surface="#3A2820",       # panneaux
    surface_muted="#241A14",
    text="#FDEAD7",
    text_muted="#F3C8A6",
    primary="#FF8C00",       # boutons
    success="#27AE60",
    warning="#FFA500",
    danger="#E74C3C",
    stroke="#5C4033",
    grid="#6B4D3B",
    curve="#FFA500",         # TRAIT bien contrasté
    curve_fill="#FFA500",    # REMPLISSAGE orange
    curve_fill_alpha=0.25,    # assez visible mais pas agressif
)


THEMES = {
    "light": LIGHT,
    "dark": DARK,
    "orange": ORANGE,
}
