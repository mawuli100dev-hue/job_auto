"""
preview_cv.py
Génère un CV de PRÉVISUALISATION avec des expériences STATIQUES (les 4 déjà sur ton
CV actuel), SANS AUCUN appel au LLM. Sert uniquement à itérer sur le visuel
(polices, marges, couleurs, mise en page) sans dépenser de crédit OpenRouter.

Usage :
    python preview_cv.py
    python preview_cv.py --experiences ../experiences.json --top-n 4
"""

import json
import argparse
from pathlib import Path

from cv_builder import fit_on_one_page, build_docx

BASE_DIR = Path(__file__).resolve().parent.parent

# Jeu de données statique par défaut : les 4 expériences déjà présentes sur le CV original
STATIC_EXPERIENCES = [
    {
        "titre": "Tuteur en informatique",
        "structure": "IUT de Perpignan, Antenne de Carcassonne",
        "periode": "Depuis septembre 2026",
        "bullets": [
            "Accompagnement pédagogique des étudiants de BUT SD en **programmation Python, R** et autres langages"
        ]
    },
    {
        "titre": "Analyse des flux de dépôt de poussières sahariennes - Golfe du Lion (1959-2024)",
        "structure_type": "Projet en climatologie et analyse de données",
        "structure": "CEFREM",
        "periode": "avril 2026 - juin 2026",
        "bullets": [
            "Construction d'un **pipeline Python** complet (xarray, pandas, matplotlib) pour croiser 3 sources de données hétérogènes : modèle régional ALADIN, réanalyse CAMS et observations terrain MOOSE",
            "Calcul des flux annuels de dépôt sec et humide sur 66 ans de données, et quantification des biais relatifs ALADIN vs observations aux stations Cap Bear et Cap Frioul (jusqu'à ±132%)",
            "Calcul de **tendance linéaire** sur la grille ALADIN et **cartographie spatiale** des résultats sur le domaine Golfe du Lion",
            "Production de figures (saisonnières, décennales, annuelles, ...) prêtes pour une publication scientifique"
        ]
    },
    {
        "titre": "Segmentation des morsures et cartographie des pits sur ossements",
        "structure_type": "Projet de recherche taphonomique",
        "structure": "CEFREM",
        "periode": "avril 2026 - juin 2026",
        "bullets": [
            "Développement d'un **pipeline de segmentation** automatique (SAM2 + CLAHE + filtres morphologiques) sur des images TIFF d'ossements de lycaon - taux de détection > 85 %",
            "Distinction de 3 zones fonctionnelles (contour, zone polie, zone broyée) par analyse de luminance LAB et variance locale",
            "Représentation géospatiale complète : chargement de shapefiles et GeoJSON (GeoPandas, Shapely), jointure avec mesures métriques Leica sur 4 types d'os longs",
            "Résultats présentés au **11th Postgraduate ZooArchaeology Forum**, Université de Lisbonne, du 16 au 19 juin 2026"
        ]
    },
    {
        "titre": "Projet ANTICI'PYR - Modélisation de niches écologiques et dashboard géospatial",
        "structure_type": "Stage en data science géospatiale",
        "structure": "CEFREM",
        "periode": "avril 2026 - mai 2026",
        "bullets": [
            "Développement d'un **dashboard interactif Streamlit** pour visualiser la distribution de 59 espèces floristiques pyrénéennes sous 4 scénarios climatiques SSP (2030-2090)",
            "Implémentation d'un système de cartographie raster géoréférencée (Cartopy, Folium, GeoPandas) avec rendu RGBA sans déformation de projection",
            "Conception d'une **interface multilingue** (FR, EN, ES, CAT) et d'un espace d'administration permettant l'ajout autonome d'espèces sans modification du code",
            "Intégration de l'interface à la plateforme FloraLab+"
        ]
    },
]


def main():
    parser = argparse.ArgumentParser(description="Prévisualise le CV sans appel LLM")
    parser.add_argument("--experiences", default=None, help="Optionnel: charger depuis experiences.json au lieu des données statiques")
    parser.add_argument("--top-n", type=int, default=4, help="Nombre d'expériences à afficher si --experiences est utilisé")
    args = parser.parse_args()

    if args.experiences:
        with open(args.experiences, encoding="utf-8") as f:
            all_exp = json.load(f)
        selected = [e for e in all_exp if e.get("on_cv")][:args.top_n]
    else:
        selected = STATIC_EXPERIENCES

    output_dir = Path(__file__).resolve().parent / "preview_output"
    output_dir.mkdir(exist_ok=True)

    pdf_path = output_dir / "preview_cv.pdf"
    html_path = output_dir / "preview_cv.html"
    docx_path = output_dir / "preview_cv.docx"

    scale = fit_on_one_page(selected, pdf_path, html_path)
    build_docx(selected, docx_path)

    print(f"Échelle de police utilisée : {scale:.2f}")
    print(f"PDF     : {pdf_path}")
    print(f"HTML    : {html_path}")
    print(f"Word    : {docx_path}")
    print("\nOuvre le PDF, ajuste le style dans cv_builder.py, relance ce script (gratuit, aucun appel API).")


if __name__ == "__main__":
    main()
