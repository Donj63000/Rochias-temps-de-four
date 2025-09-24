Rochias – Temps de Four (3 tapis)

Application de bureau (Tkinter) pour estimer et suivre en temps réel les temps de passage sur un four à 3 tapis, en s’appuyant exclusivement sur la méthode maintenance “tableur (L/v)”.
Le logiciel reprend les constantes et la logique calculées par la maintenance dans le classeur et fournit :

POUR TELECHARGER LE .EXE CLIQUEZ SUR "ACTIONS" en haut à gauche, et selectionnez la dernière version, vous pourrez téléchargez directement le .EXE d'ici ! ;)

le temps total et les temps par tapis ;

des barres de progression par tapis avec marquage des cellules ;

un graphe h(t) donnant une vision continue de l’épaisseur de couche sur le temps ;

la simulation en temps réel (pause/reprise) et l’annotation des arrêts d’alimentation (trous) ;

des exports CSV (résultats) et PS (barres).

🟩 Méthode retenue = Référence maintenance (L/v).
Toutes les autres approches (régressions, “synergie”, etc.) ont été retirées de l’interface pour éviter toute ambiguïté.

Sommaire

Aperçu

Installation

Lancer l’application

Utilisation

Détails des calculs (TXT)

Paramétrage / Maintenance

Structure du projet

Raccourcis clavier

FAQ

Crédits

Aperçu

Entrées : fréquences variateur des 3 tapis (en Hz ou IHM×100), et épaisseur d’entrée h₀ en cm pour l’affichage de l’épaisseur de couche.

Sorties : t₁, t₂, t₃ (min & h:m:s) et total ; barres par tapis ; graphe h(t).

L’interface affiche “Méthode tableur (L/v)” pour rappeler que c’est la source de vérité.

Installation

Prérequis : Python 3.10+ (3.11 recommandé) et pip.

git clone https://github.com/Donj63000/Rochias-temps-de-four.git
cd Rochias-temps-de-four
python -m venv .venv
# Windows
.venv\Scripts\pip install -r requirements.txt
# Linux/Mac
source .venv/bin/activate && pip install -r requirements.txt


💡 Un workflow GitHub Actions (workflows/build.yml) permet de générer un exécutable via PyInstaller.

Lancer l’application
# Depuis la racine du dépôt
python -m rochias_four
# ou
python Main.py

Utilisation

Saisir les vitesses des tapis :

en Hz (ex. 40.00)

ou en IHM×100 (ex. 4000).
Toute valeur > 200 est automatiquement interprétée comme une entrée IHM et divisée par 100 pour obtenir les Hz.

(Optionnel) h₀ (cm) : épaisseur en entrée ; sert uniquement aux indicateurs/graph de couche.

Cliquer Calculer.
L’application affiche t₁, t₂, t₃, le total et prépare les barres.

Démarrer (temps réel) pour animer les barres.

Arrêt alimentation / Reprise : enregistre des arrêts de chargement ; des “trous” sont visualisés sur les barres.

Pause met en pause la simulation.

Graphiques : ouvre le graphe épaisseur h(t) vs temps partitionné par tapis.

Export CSV / Export PS (barres) dans le panneau “Détails résultats”.

Détails des calculs (TXT)

Source de vérité : le tableur maintenance.
La logique ci-dessous reproduit exactement la feuille “L/v”.

ENTRÉES

  f1, f2, f3 : vitesses tapis 1–3 (Hz).
               Règle d’entrée : si valeur > 200 → on considère une saisie IHM×100
               et on convertit en Hz par f = valeur / 100.

  h0 : épaisseur d’entrée (cm) – optionnelle, utile pour la visualisation de couche.


MODÈLE TEMPS (référence maintenance “L/v”)

  Pour chaque tapis i ∈ {1,2,3} :

    ti(sec) = Ki / fi
           = (Lconv_i × Ci) / fi

  où :
   - fi est la vitesse en Hz (après conversion IHM → Hz si besoin),
   - Ki est une constante globale (en s·Hz) propre au tapis i,
     équivalente à la somme des segments du tableur (distance × coefficient),
   - Lconv_i et Ci sont les constantes maintenance regroupées par tapis.

  L’application retourne :
    ti(min) = ti(sec) / 60
    T_total(min) = t1(min) + t2(min) + t3(min)

  Les constantes Ki (ou Lconv_i et Ci) sont définies dans le code de
  référence maintenance (voir maintenance_ref.py).


MODÈLE ÉPAISSEUR (affichage & graph h(t))

  On utilise des « ancrages » K'i (min·Hz) pour définir des capacités relatives :

    ui = fi / K'i

  puis, à partir de l’épaisseur d’entrée h0 :

    h1 = h0
    h2 = h0 × (u1 / u2)  si u2 > 0
    h3 = h0 × (u1 / u3)  si u3 > 0

  Les variations affichées dans l’UI :
    Δ12% = ((u1/u2) - 1) × 100
    Δ23% = ((u2/u3) - 1) × 100

  Ces K'i ne modifient PAS les temps (ils ne servent qu’à la visualisation
  de couche/cohérence d’épaisseur). Ils sont configurables (voir calibration_overrides).


AFFICHAGE / SIMULATION

  • Barres : durées cibles = (t1, t2, t3) en secondes.
  • Marqueurs « Cellule 1..9 » pour repères visuels.
  • Boutons Arrêt/Reprise = enregistre des gaps sur la chronologie ;
    des trous sont dessinés sur les barres du/des tapis concernés.

Paramétrage / Maintenance

Constantes de calcul temps (L/v)
Fichier : rochias_four/maintenance_ref.py
Ce module regroupe les constantes Kᵢ ou, selon l’implémentation choisie, les couples Lconvᵢ et Cᵢ.
→ Ce sont les seules valeurs qui impactent les temps.
Toute mise à jour du tableur se répercute ici.

Ancrages K′ᵢ (épaisseur/graph)
Fichier : rochias_four/calibration_overrides.py (+ éventuel JSON de persistance)
Sert uniquement aux indicateurs d’épaisseur et au graphe h(t).
N’influe pas sur les temps.

Seuil IHM↔Hz
La règle “> 200 ⇒ IHM×100” est codée au niveau de la lecture des entrées.

Structure du projet
rochias_four/
├── app.py                   # Application Tkinter (UI, simulation temps réel)
├── graphs.py                # Fenêtre & tracé du graphe d’épaisseur h(t)
├── maintenance_ref.py       # *** Référence maintenance : calcul L/v ***
├── calculations.py          # Outils d’épaisseur (uᵢ, hᵢ) & indicateurs
├── calibration_overrides.py # Ancrages K′ᵢ (visualisation)
├── widgets.py               # SegmentedBar & composants UI
├── theme*.py                # Thèmes & styles
├── utils.py                 # parse des vitesses, formats (hh:mm:ss,…)
├── flow.py                  # Calcul des « trous » (arrêts alimentation)
└── config.py                # valeurs par défaut & tick simulation


Les anciennes approches (régressions, “synergie”) ont été retirées de l’UI.
Le code restant se concentre sur la méthode maintenance.

Raccourcis clavier

Entrée : Calculer

F5 : Démarrer la simulation

Espace : Pause/Reprise

Ctrl+R : Réinitialiser

F1 : Ouvrir l’aide (explications)

FAQ

Q. Les temps diffèrent légèrement du tableur.
R. Vérifier les constantes dans maintenance_ref.py (Kᵢ / Lconvᵢ / Cᵢ) et la conversion IHM→Hz. Sur notre banc d’essai, l’écart est de l’ordre de quelques secondes, ce qui est conforme (arrondis min/Hz/h:m:s).

Q. L’épaisseur affichée ne correspond pas à une mesure physique.
R. Normal : c’est une cohérence relative (capacités uᵢ) pour piloter les vitesses. Seules les constantes maintenance influencent les temps.

Q. Puis‑je remettre la méthode “synergie” ?
R. Le projet présent est verrouillé sur la référence maintenance (L/v) pour éviter toute ambiguïté de calcul.

Crédits

Application & intégration : équipe Rochias

Méthode de calcul : Maintenance Rochias (référence “tableur L/v”)

Dédicace : Romain & Taha — Rochias. Merci pour le travail de fond et les données qui rendent ces estimations robustes et opérationnelles.
- 
ochias_four/utils.py : fonctions de formatage et de parsing.
- 
ochias_four/config.py : valeurs de configuration partagees.
- 
ochias_four/theme.py : palette de couleurs.

