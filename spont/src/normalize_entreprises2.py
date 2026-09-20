"""
normalize_entreprises.py
Lit UN OU PLUSIEURS fichiers Excel multi-feuilles listant des entreprises de
stage/alternance (formats tous différents d'une source à l'autre) et produit
UN SEUL CSV propre et dédoublonné : data/entreprises/entreprises_uniques.csv

CORRECTIF v2 (2026-09-14 - fusion de 3 sources différentes) :
1. --xlsx accepte désormais PLUSIEURS fichiers (nargs='+'), ex:
   --xlsx fichier1.xlsx fichier2.xlsx fichier3.xlsx
   Chaque fichier peut avoir un nombre de feuilles et des colonnes différentes,
   tout est fusionné et dédoublonné ensemble à la fin.
2. Nouveaux mots-clés de colonne "nom" ajoutés : "raison sociale",
   "nom structure" (rencontrés dans une nouvelle source).
3. Nouvelle règle d'extraction : quand la colonne "ville" contient un format
   du type "Toulouse (31)" ou "Toulouse (31700)" (ville et code postal/dépt
   fusionnés entre parenthèses), le script sépare automatiquement les deux
   si aucune colonne "code_postal" dédiée n'a donné de résultat.
4. Capture optionnelle du type de contrat observé (apprentissage/stage) si
   une colonne "type contrat" ou "statut" existe dans la source, pour
   information (non exploité automatiquement par build_offres_spontanees.py
   mais utile pour filtrer/trier le CSV final à la main).

Usage :
    python src/normalize_entreprises.py --xlsx "Entreprises-stages-STID-de-2013-a-2023.xlsx" "2025-Liste-entreprises-apprentissage-ou-stage-BUT-2.xlsx" "liste_entreprise_plus.xlsx"
"""

import re
import csv
import argparse
import unicodedata
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent

FIELDNAMES = [
    "nom", "adresse", "code_postal", "ville", "telephone", "siteweb",
    "service", "type_contrat_observe", "sources",
]

MOTS_CLES = {
    "nom": ["entreprise", "etablissement", "organisme", "raison sociale", "nom structure"],
    "adresse": ["adresse", "voie", "rue"],
    "code_postal": ["code postal", "cp"],
    "ville": ["commune", "ville", "nom_ville"],
    "telephone": ["tel", "telephone"],
    "siteweb": ["site", "web"],
    "service": ["service", "fonction", "secteur", "sujet"],
    "type_contrat_observe": ["type contrat", "statut", "nature"],
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


def split_ville_code_parenthese(ville_brut: str) -> tuple[str, str]:
    """Sépare 'Toulouse (31)' ou 'Toulouse (31700)' en ('Toulouse', '31'/'31700').
    Retourne (ville_brut, '') si le format ne correspond pas."""
    if not ville_brut:
        return "", ""
    m = re.match(r"^(.*?)\s*\((\d{2,5})\)\s*$", ville_brut.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return ville_brut.strip(), ""


def _clean(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none") else s


def normalize_sheet(df: pd.DataFrame, source_label: str) -> list[dict]:
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
        type_contrat = _clean(row[col_map["type_contrat_observe"]]) if col_map["type_contrat_observe"] else ""

        cp = re.sub(r"\.0$", "", cp)  # colonnes CP parfois lues comme float (11000.0)

        # Cas "Toulouse (31)" : ville et code fusionnés dans le même champ
        ville_split, cp_depuis_parenthese = split_ville_code_parenthese(ville)
        if cp_depuis_parenthese:
            ville = ville_split
            cp = cp or cp_depuis_parenthese

        if not cp or not ville:
            cp_deduit, ville_deduite = extract_cp_ville_from_text(adresse)
            cp = cp or cp_deduit
            ville = ville or ville_deduite

        rows.append({
            "nom": nom, "adresse": adresse, "code_postal": cp, "ville": ville,
            "telephone": tel, "siteweb": site, "service": service,
            "type_contrat_observe": type_contrat, "sources": source_label,
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Fusionne plusieurs fichiers Excel d'entreprises en 1 CSV propre et dédoublonné")
    parser.add_argument("--xlsx", required=True, nargs="+", help="Un ou plusieurs chemins de fichiers .xlsx")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    toutes_lignes = []

    for xlsx_arg in args.xlsx:
        xlsx_path = Path(xlsx_arg)
        if not xlsx_path.is_absolute():
            xlsx_path = Path.cwd() / xlsx_path

        print(f"\nLecture de {xlsx_path.name}...")
        sheets = pd.read_excel(xlsx_path, sheet_name=None, dtype=str)

        for sheet_name, df in sheets.items():
            source_label = f"{xlsx_path.stem} / {sheet_name}"
            lignes = normalize_sheet(df, source_label)
            print(f"  Feuille '{sheet_name}' : {len(lignes)} ligne(s) exploitable(s).")
            toutes_lignes.extend(lignes)

    print(f"\n{len(toutes_lignes)} ligne(s) au total (toutes sources confondues) avant dédoublonnage.")

    par_nom: dict[str, dict] = {}
    for ligne in toutes_lignes:
        cle = re.sub(r"[^a-z0-9]+", " ", normalize_txt(ligne["nom"])).strip()
        if not cle:
            continue
        if cle not in par_nom:
            par_nom[cle] = ligne
        else:
            existant = par_nom[cle]
            sources = existant["sources"] + f", {ligne['sources']}"
            score_existant = sum(len(v) for k, v in existant.items() if k != "sources")
            score_nouveau = sum(len(v) for k, v in ligne.items() if k != "sources")
            meilleur = dict(ligne if score_nouveau > score_existant else existant)
            meilleur["sources"] = sources
            par_nom[cle] = meilleur

    uniques = list(par_nom.values())
    print(f"{len(uniques)} entreprise(s) UNIQUE(S) après dédoublonnage par nom (toutes sources fusionnées).")

    output_path = Path(args.output) if args.output else BASE_DIR / "data" / "entreprises" / "entreprises_uniques.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(uniques)

    print(f"\nFichier enregistré : {output_path}")
    print("Vérifie ce fichier avant de lancer build_offres_spontanees.py : "
          "certaines lignes (associations, mairies, écoles, etc.) ne seront "
          "peut-être pas pertinentes pour une candidature spontanée en data/IA.")
    print("\nÉtape suivante :")
    print(f'  python src/build_offres_spontanees.py --csv "{output_path}" --limit 10')


if __name__ == "__main__":
    main()