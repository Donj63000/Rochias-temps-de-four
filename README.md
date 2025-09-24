Rochias – Temps de Four (3 tapis)

Application de bureau (Tkinter) pour estimer et suivre en temps réel les temps de passage dans un four industriel à 3 tapis.

👉 La méthode utilisée est exclusivement la méthode maintenance “tableur (L/v)”, validée et entretenue par la maintenance de Rochias.
Toutes les autres approches (régressions, “synergie”…) ont été retirées pour éviter toute ambiguïté.

📌 Dédicace spéciale à Romain et Taha de la maintenance Rochias, dont le travail minutieux sur les données et le tableur est la base de ce logiciel.

Fonctionnalités principales

Calcul du temps total et du temps par tapis (t₁, t₂, t₃).

Barres de progression dynamiques avec repères par cellules.

Graphe épaisseur h(t) pour visualiser la couche produit dans le temps.

Simulation temps réel (pause, reprise).

Gestion des arrêts d’alimentation → affichage de “trous” sur les barres.

Export des résultats en CSV et PostScript (PS).

Comment ça marche (vue simple)

L’utilisateur saisit la vitesse de chaque tapis :

Soit en Hz (ex. 40.00)

Soit en IHM × 100 (ex. 4000 → 40 Hz).
Règle : toute valeur > 200 est automatiquement interprétée comme une saisie IHM et divisée par 100.

Le logiciel applique les formules du tableur maintenance (référence L/v).

Les temps par tapis et le temps total sont calculés exactement comme dans le fichier Excel d’origine.

En option, si l’épaisseur d’entrée h₀ est renseignée, l’application calcule aussi l’évolution d’épaisseur de la couche (indicateur visuel, n’influe pas sur les temps).

Les formules (référence maintenance L/v)
1. Temps par tapis

Pour chaque tapis i :

t_i (secondes) = K_i / f_i


où :

f_i = vitesse du tapis i en Hz (après conversion IHM → Hz si besoin)

K_i = constante maintenance du tapis i (en s·Hz), qui dépend de :

Lconv_i = longueur de convoyage du tapis (en m ou cm selon le relevé)

C_i = coefficient associé à ce tapis (sans dimension, fourni par la maintenance)

Ainsi :

K_i = Lconv_i × C_i


Conversion en minutes :

t_i (minutes) = t_i (secondes) / 60


Temps total :

T_total = t1 + t2 + t3

2. Épaisseur de couche (visualisation)

On introduit des constantes d’ancrage K’_i (min·Hz), issues des calibrations maintenance.
Elles ne modifient pas les temps, seulement l’affichage de la cohérence d’épaisseur.

On calcule des capacités relatives :

u_i = f_i / K’_i


Puis, à partir de l’épaisseur d’entrée h₀ (cm) :

h1 = h0
h2 = h0 × (u1 / u2)   (si u2 > 0)
h3 = h0 × (u1 / u3)   (si u3 > 0)


On en déduit les variations affichées dans l’UI :

Δ1→2 (%) = ((u1 / u2) - 1) × 100
Δ2→3 (%) = ((u2 / u3) - 1) × 100

3. Simulation temps réel

Chaque barre correspond à un tapis avec une durée cible (t₁, t₂, t₃).

Les barres sont divisées en 3 cellules pour correspondre aux zones physiques du four.

Les arrêts d’alimentation (boutons “Arrêt” / “Reprise”) introduisent des “trous” dans la progression.

Exemple pratique

Entrées :

Tapis 1 : 4000 IHM (→ 40 Hz)
Tapis 2 : 5000 IHM (→ 50 Hz)
Tapis 3 : 9000 IHM (→ 90 Hz)
h₀ : 2.0 cm


Sorties (selon tableur maintenance) :

Tapis 1 : 63 min 40 s
Tapis 2 : 35 min 42 s
Tapis 3 : 109 min 21 s
Temps total : 3 h 08 min 43 s


Affichage des variations d’épaisseur :

Δ1→2 = +174 % (h2 ≈ 5.47 cm)
Δ2→3 = +53 %  (h3 ≈ 8.39 cm)

Structure du projet
rochias_four/
│── app.py                # Application Tkinter (UI principale)
│── graphs.py             # Graphe h(t) par tapis
│── maintenance_ref.py    # Formules de référence L/v + constantes K_i
│── calculations.py       # Fonctions d’épaisseur et variations Δ
│── calibration_overrides.py # Ancrages K’_i (visualisation épaisseur)
│── widgets.py            # Barres segmentées & composants UI
│── theme.py / theme_manager.py # Gestion des thèmes (clair/sombre)
│── utils.py              # Parsing vitesses, formatage temps
│── flow.py               # Gestion des arrêts (trous alimentation)
│── config.py             # Valeurs par défaut et tick simulation

Raccourcis clavier

Entrée : Calculer

F5 : Démarrer simulation

Espace : Pause / Reprise

Ctrl+R : Réinitialiser

F1 : Aide / Explications

FAQ

Q. Pourquoi mes résultats diffèrent légèrement du tableur ?
R. Vérifier les constantes dans maintenance_ref.py et la conversion IHM↔Hz. Les écarts de quelques secondes sont normaux (arrondis).

Q. L’épaisseur affichée ne correspond pas à une mesure réelle ?
R. Normal. Elle sert uniquement à représenter la cohérence relative entre tapis.

Q. Puis-je réactiver la méthode “synergie” ?
R. Non. Le projet est verrouillé sur la référence maintenance L/v pour éviter toute confusion.

Crédits

Application & intégration : Équipe Rochias

Méthode de calcul : Maintenance Rochias (référence tableur L/v)

Dédicace : Romain & Taha (Maintenance Rochias) pour leur travail de fond sur les constantes et le tableur.
