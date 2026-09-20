"""
normalize_entreprises.py
Lit le fichier Excel multi-feuilles listant les entreprises de stage/alternance
STID (une feuille par année, colonnes différentes presque à chaque fois) et
produit un CSV UNIQUE et propre : data/entreprises/entreprises_uniques.csv

PROBLÈME RÉSOLU :
Le fichier source change de structure d'une feuille à l'autre :
- Noms de colonnes différents (ex: "Nom Etablissement d'accueil" en 2022-2023,
  "Entreprise de stage" en 2013-2014, "nom.entreprise" avant 2013).
- Parfois adresse, code postal et ville sont dans 3 colonnes séparées,
  parfois fusionnés dans une seule chaîne ("32 rue Aimé Ramond, 11835
  Carcassonne Cedex 9").
Ce script harmonise tout ça par une recherche de MOTS-CLÉS dans les en-têtes
de colonnes (pas des noms de colonnes fixes), et déduit le code postal/ville
par regex quand ils ne sont pas dans des colonnes séparées.

Usage :
    python src/normalize_entreprises.py --xlsx "Entreprises-stages-STID-de-2013-a-2023.xlsx"
"""

import re
import csv
import argparse
import unicodedata
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent

FIELDNAMES = ["nom", "adresse", "code_postal", "ville", "telephone", "siteweb", "service", "annees_vues"]

MOTS_CLES = {
    "nom": ["entreprise", "etablissement", "organisme", "nom.entreprise", "nom entreprise"],
    "adresse": ["adresse", "voie", "rue"],
    "code_postal": ["code postal", "cp"],
    "ville": ["commune", "ville", "nom_ville"],
    "telephone": ["tel", "telephone"],
    "siteweb": ["site", "web"],
    "service": ["service", "fonction", "secteur", "sujet"],
}


def normalize_txt(s) -> str:
    if s is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(s).lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def find_column(columns, keywords):
    for col in columns:
        col_norm = normalize_txt(col)
        for kw in keywords:
            if normalize_txt(kw) in col_norm:
                return col
    return None


def extract_cp_ville_from_text(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    m = re.search(r"(\d{5})\s+([A-Za-zÀ-ÿ'\- ]{2,})", text)
    if m:
        return m.group(1), m.group(2).strip(" ,.")
    return "", ""


def _clean(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none") else s


def normalize_sheet(df: pd.DataFrame, sheet_name: str) -> list[dict]:
    columns = list(df.columns)
    col_map = {champ: find_column(columns, kws) for champ, kws in MOTS_CLES.items()}

    rows = []
    for _, row in df.iterrows():
        nom = _clean(row[col_map["nom"]]) if col_map["nom"] else ""
        if not nom:
            continue

        adresse = _clean(row[col_map["adresse"]]) if col_map["adresse"] else ""
        cp = _clean(row[col_map["code_postal"]]) if col_map["code_postal"] else ""
        ville = _clean(row[col_map["ville"]]) if col_map["ville"] else ""
        tel = _clean(row[col_map["telephone"]]) if col_map["telephone"] else ""
        site = _clean(row[col_map["siteweb"]]) if col_map["siteweb"] else ""
        service = _clean(row[col_map["service"]]) if col_map["service"] else ""

        cp = re.sub(r"\.0$", "", cp)  # colonnes CP parfois lues comme float (11000.0)

        if not cp or not ville:
            cp_deduit, ville_deduite = extract_cp_ville_from_text(adresse)
            cp = cp or cp_deduit
            ville = ville or ville_deduite

        rows.append({
            "nom": nom, "adresse": adresse, "code_postal": cp, "ville": ville,
            "telephone": tel, "siteweb": site, "service": service,
            "annees_vues": sheet_name,
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Normalise le fichier Excel multi-feuilles des entreprises en 1 CSV propre")
    parser.add_argument("--xlsx", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.is_absolute():
        xlsx_path = Path.cwd() / xlsx_path

    print(f"Lecture de {xlsx_path}...")
    sheets = pd.read_excel(xlsx_path, sheet_name=None, dtype=str)

    toutes_lignes = []
    for sheet_name, df in sheets.items():
        lignes = normalize_sheet(df, sheet_name)
        print(f"  Feuille '{sheet_name}' : {len(lignes)} ligne(s) exploitable(s).")
        toutes_lignes.extend(lignes)

    print(f"\n{len(toutes_lignes)} ligne(s) au total avant dédoublonnage.")

    par_nom: dict[str, dict] = {}
    for ligne in toutes_lignes:
        cle = re.sub(r"[^a-z0-9]+", " ", normalize_txt(ligne["nom"])).strip()
        if not cle:
            continue
        if cle not in par_nom:
            par_nom[cle] = ligne
        else:
            existant = par_nom[cle]
            annees = existant["annees_vues"] + f", {ligne['annees_vues']}"
            score_existant = sum(len(v) for k, v in existant.items() if k != "annees_vues")
            score_nouveau = sum(len(v) for k, v in ligne.items() if k != "annees_vues")
            meilleur = ligne if score_nouveau > score_existant else existant
            meilleur = dict(meilleur)
            meilleur["annees_vues"] = annees
            par_nom[cle] = meilleur

    uniques = list(par_nom.values())
    print(f"{len(uniques)} entreprise(s) UNIQUE(S) après dédoublonnage par nom.")

    output_path = Path(args.output) if args.output else BASE_DIR / "data" / "entreprises" / "entreprises_uniques.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(uniques)

    print(f"\nFichier enregistré : {output_path}")
    print("Vérifie ce fichier avant de lancer build_offres_spontanees.py : "
          "certaines lignes (associations, mairies, etc.) ne seront peut-être "
          "pas pertinentes pour une candidature spontanée en data/IA.")


if __name__ == "__main__":
    main()
