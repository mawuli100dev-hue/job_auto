"""
filter_alternance.py
Filtre un CSV d'offres (généré par collect_offers.py) pour ne garder que celles
qui sont réellement en alternance, en s'appuyant d'abord sur les champs structurés
(type_contrat, nature_contrat, intitule) plutôt que sur la description en texte libre.
Permet aussi d'exclure certaines entreprises (ex: organismes de formation type ISCOD).

Enregistre le résultat dans data/offres_filtrees/<date_du_jour>/offres_filtrees_<date>_<heure>.csv

Usage :
    python filter_alternance.py --input "data/offres/2026-09-10/offres_2026-09-10_122818.csv"
    python filter_alternance.py --input "data\offres\2026-09-10\offres_2026-09-10_202954.csv" --exclude-entreprises "ISCOD,OPENCLASSROOMS"
"""

import csv
import re
import argparse
import unicodedata
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

ALTERNANCE_ROOTS = [r"altern", r"apprent"]

STRONG_DESCRIPTION_PATTERNS = [
    r"contrat d.?apprentissage",
    r"contrat de professionnalisation",
    r"poste en alternance",
    r"recrutons?.{0,30}alternance",
    r"recherch\w+.{0,30}alternant",
    r"cette offre est.{0,20}alternance",
]

EXCLUDED_TYPE_CONTRAT = {"cdi"}

# Entreprises à exclure par défaut (organismes de formation qui postent au nom
# de leurs futurs apprenants plutôt que l'employeur réel)
DEFAULT_EXCLUDED_ENTREPRISES = ["ISCOD"]


def normalize(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return without_accents.lower()


def is_alternance(row: dict) -> bool:
    type_contrat = normalize(row.get("type_contrat", ""))
    nature_contrat = normalize(row.get("nature_contrat", ""))
    intitule = normalize(row.get("intitule", ""))
    description = normalize(row.get("description", ""))

    if any(excl in type_contrat for excl in EXCLUDED_TYPE_CONTRAT):
        return False

    if any(re.search(p, intitule) for p in ALTERNANCE_ROOTS):
        return True

    if any(re.search(p, nature_contrat) for p in ALTERNANCE_ROOTS):
        return True

    if any(re.search(p, description) for p in STRONG_DESCRIPTION_PATTERNS):
        return True

    return False


def is_excluded_entreprise(row: dict, excluded_names: list[str]) -> bool:
    entreprise = normalize(row.get("entreprise", ""))
    return any(normalize(name) in entreprise for name in excluded_names)


def filter_csv(input_path: Path, excluded_entreprises: list[str]) -> tuple[list[dict], list[str], int, int, int]:
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    alternance_rows = [row for row in rows if is_alternance(row)]
    removed_non_alternance = len(rows) - len(alternance_rows)

    kept = [row for row in alternance_rows if not is_excluded_entreprise(row, excluded_entreprises)]
    removed_entreprise = len(alternance_rows) - len(kept)

    return kept, fieldnames, len(rows), removed_non_alternance, removed_entreprise


def save_filtered(kept: list[dict], fieldnames: list[str], base_dir: Path | None = None) -> str:
    if base_dir is None:
        base_dir = BASE_DIR / "data" / "offres_filtrees"

    today = datetime.now().strftime("%Y-%m-%d")
    folder = base_dir / today
    folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"offres_filtrees_{today}_{timestamp}.csv"
    filepath = folder / filename

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="Filtre les offres réellement en alternance")
    parser.add_argument("--input", required=True, help="Chemin vers le CSV à filtrer")
    parser.add_argument(
        "--exclude-entreprises",
        default=",".join(DEFAULT_EXCLUDED_ENTREPRISES),
        help="Noms d'entreprises à exclure, séparés par des virgules (ex: 'ISCOD,OPENCLASSROOMS')",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = Path.cwd() / input_path

    if not input_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {input_path}")

    excluded_entreprises = [e.strip() for e in args.exclude_entreprises.split(",") if e.strip()]

    print(f"Lecture de {input_path}...")
    print(f"Entreprises exclues : {excluded_entreprises}")

    kept, fieldnames, total, removed_non_alt, removed_ent = filter_csv(input_path, excluded_entreprises)

    print(f"Total initial                        : {total} offre(s)")
    print(f"Écartées (hors alternance)            : {removed_non_alt} offre(s)")
    print(f"Écartées (entreprise exclue)          : {removed_ent} offre(s)")
    print(f"Conservées                            : {len(kept)} offre(s)")

    filepath = save_filtered(kept, fieldnames)
    print(f"Fichier filtré enregistré : {filepath}")


if __name__ == "__main__":
    main()