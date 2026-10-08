# job_automation/src/migrate_data_layout.py

"""
Range les anciens fichiers de data/ dans l'organisation par source :

    data/<source>/1_brutes/<type>/<date>/
    data/<source>/2_filtrees/<type>/<date>/
    data/<source>/3_candidatures/<date>/<dossier>/

Anciens emplacements traités :
    data/offres/            -> france_travail/1_brutes
    data/offres_lba/        -> la_bonne_alternance/1_brutes
    data/offres_pass/       -> pass/1_brutes
    data/offres_manuelles/  -> manuelles/1_brutes
    data/offres_filtrees/   -> <source>/2_filtrees (source lue dans le CSV)
    data/candidatures/      -> <source>/3_candidatures (source lue dans offre.txt)

Par défaut, le script affiche seulement ce qu'il ferait. Avec --appliquer,
il déplace les fichiers, n'écrase jamais un fichier existant et écrit un
journal data/migration_<date>.csv (ancien chemin, nouveau chemin).

python src\\migrate_data_layout.py
python src\\migrate_data_layout.py --appliquer
"""

import argparse
import csv
import re
import shutil
from datetime import datetime
from pathlib import Path

from paths import (
    SOURCE_FRANCE_TRAVAIL,
    SOURCE_LBA,
    SOURCE_MANUAL,
    SOURCE_PASS,
    SOURCE_SPONTANEOUS,
    STAGE_APPLICATIONS,
    STAGE_FILTERED,
    STAGE_RAW,
    source_from_value,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TYPES = ("alternance", "stage", "tous")


def date_from_name(name: str, fallback_path: Path) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", name)

    if match:
        return match.group(1)

    return datetime.fromtimestamp(
        fallback_path.stat().st_mtime
    ).strftime("%Y-%m-%d")


def csv_source(path: Path) -> str:
    """
    Source d'un CSV d'offres d'après sa colonne « source ».
    """

    try:
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            row = next(csv.DictReader(csv_file), None) or {}
    except (OSError, UnicodeDecodeError):
        return SOURCE_FRANCE_TRAVAIL

    return source_from_value(row.get("source", ""))


def csv_ids(path: Path, column: str) -> set[str]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            return {
                str(row.get(column, "")).strip()
                for row in csv.DictReader(csv_file)
            }
    except (OSError, UnicodeDecodeError):
        return set()


def application_source(directory: Path) -> str:
    """
    Source d'un dossier de candidature d'après offre.txt.
    """

    snapshot = directory / "offre.txt"
    text = ""

    if snapshot.exists():
        text = snapshot.read_text(encoding="utf-8", errors="ignore")

    if "Source : spontaneous" in text:
        return SOURCE_SPONTANEOUS

    url = ""

    for line in text.splitlines():
        if line.startswith("URL"):
            url = line.lower()
            break

    if "francetravail" in url or "pole-emploi" in url:
        return SOURCE_FRANCE_TRAVAIL

    if "pass.fonction-publique" in url:
        return SOURCE_PASS

    if "labonnealternance" in url or "apprentissage.beta" in url:
        return SOURCE_LBA

    if not url and re.search(r"_\d{6}[0-9a-z]$", directory.name):
        return SOURCE_FRANCE_TRAVAIL

    return SOURCE_MANUAL


def plan_moves() -> list[tuple[Path, Path]]:
    moves: list[tuple[Path, Path]] = []

    def stage_dir(source: str, stage: str) -> Path:
        return DATA_DIR / source / stage

    # --- Offres brutes datées : data/<ancien>/<type>/<date>/ ou <date>/
    for old_name, source in (
        ("offres", SOURCE_FRANCE_TRAVAIL),
        ("offres_lba", SOURCE_LBA),
        ("offres_pass", SOURCE_PASS),
    ):
        old_root = DATA_DIR / old_name

        if not old_root.exists():
            continue

        for file in old_root.rglob("*"):
            if not file.is_file():
                continue

            parts = file.relative_to(old_root).parts
            type_name = next(
                (part for part in parts[:-1] if part in TYPES),
                None,
            )

            if type_name is None:
                # La Bonne Alternance mettait le type dans le nom.
                match = re.search(r"_(alternance|stage)_", file.name)
                type_name = match.group(1) if match else "alternance"

            date_value = next(
                (part for part in parts[:-1] if DATE_PATTERN.match(part)),
                None,
            ) or date_from_name(file.name, file)

            moves.append(
                (
                    file,
                    stage_dir(source, STAGE_RAW) / type_name / date_value / file.name,
                )
            )

    # --- Offres manuelles : data/offres_manuelles/<type>/<fichier>
    manual_root = DATA_DIR / "offres_manuelles"

    if manual_root.exists():
        for file in manual_root.rglob("*"):
            if not file.is_file():
                continue

            parts = file.relative_to(manual_root).parts
            type_name = parts[0] if parts[0] in TYPES else "alternance"
            date_value = date_from_name(file.name, file)

            moves.append(
                (
                    file,
                    stage_dir(SOURCE_MANUAL, STAGE_RAW) / type_name / date_value / file.name,
                )
            )

    # --- Offres filtrées : la source est lue dans chaque CSV
    filtered_root = DATA_DIR / "offres_filtrees"

    if filtered_root.exists():
        for folder in sorted({path.parent for path in filtered_root.rglob("*.csv")}):
            parts = folder.relative_to(filtered_root).parts
            type_name = next((part for part in parts if part in TYPES), "alternance")
            date_value = next(
                (part for part in parts if DATE_PATTERN.match(part)),
                None,
            )

            offers_files = sorted(folder.glob("offres_filtrees_*.csv"))
            source_by_file = {path: csv_source(path) for path in offers_files}

            for file in sorted(folder.glob("*.csv")):
                if file in source_by_file:
                    source = source_by_file[file]
                else:
                    # Résumé du pipeline : même source que le CSV filtré
                    # qui contient ses identifiants.
                    ids = csv_ids(file, "Id") - {""}
                    source = next(
                        (
                            source_by_file[path]
                            for path in offers_files
                            if ids & csv_ids(path, "id")
                        ),
                        SOURCE_FRANCE_TRAVAIL,
                    )

                moves.append(
                    (
                        file,
                        stage_dir(source, STAGE_FILTERED)
                        / type_name
                        / (date_value or date_from_name(file.name, file))
                        / file.name,
                    )
                )

    # --- Candidatures : data/candidatures/<date>/<dossier>/
    applications_root = DATA_DIR / "candidatures"

    if applications_root.exists():
        for date_folder in sorted(applications_root.iterdir()):
            if not date_folder.is_dir():
                continue

            for application in sorted(date_folder.iterdir()):
                if not application.is_dir():
                    continue

                source = application_source(application)
                destination_dir = (
                    stage_dir(source, STAGE_APPLICATIONS)
                    / date_folder.name
                    / application.name
                )

                for file in application.rglob("*"):
                    if file.is_file():
                        moves.append(
                            (
                                file,
                                destination_dir / file.relative_to(application),
                            )
                        )

    return moves


def remove_empty_dirs(root: Path) -> None:
    if not root.exists():
        return

    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if not any(directory.iterdir()):
            directory.rmdir()

    if not any(root.iterdir()):
        root.rmdir()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Range data/ par source (1_brutes, 2_filtrees, 3_candidatures)."
    )
    parser.add_argument(
        "--appliquer",
        action="store_true",
        help="Déplace réellement les fichiers (sinon : simulation).",
    )
    args = parser.parse_args()

    moves = plan_moves()

    summary: dict[str, int] = {}

    for _, destination in moves:
        relative = destination.relative_to(DATA_DIR).parts
        key = f"{relative[0]}/{relative[1]}"
        summary[key] = summary.get(key, 0) + 1

    print(f"{len(moves)} fichier(s) à ranger :")

    for key in sorted(summary):
        print(f"  {key:40} {summary[key]:5} fichier(s)")

    conflicts = [
        (source, destination)
        for source, destination in moves
        if destination.exists()
    ]

    if conflicts:
        print(f"\n{len(conflicts)} fichier(s) existent déjà à destination et seront laissés en place :")

        for source, destination in conflicts[:20]:
            print(f"  {source.relative_to(DATA_DIR)} -> {destination.relative_to(DATA_DIR)}")

    if not args.appliquer:
        print("\nSimulation uniquement. Relance avec --appliquer pour déplacer les fichiers.")
        return

    log_path = DATA_DIR / f"migration_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    moved = 0

    with log_path.open("w", newline="", encoding="utf-8-sig") as log_file:
        writer = csv.writer(log_file)
        writer.writerow(["ancien_chemin", "nouveau_chemin"])

        for source, destination in moves:
            if destination.exists():
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            writer.writerow(
                [
                    str(source.relative_to(PROJECT_ROOT)),
                    str(destination.relative_to(PROJECT_ROOT)),
                ]
            )
            moved += 1

    for old_name in (
        "offres",
        "offres_lba",
        "offres_pass",
        "offres_manuelles",
        "offres_filtrees",
        "candidatures",
    ):
        remove_empty_dirs(DATA_DIR / old_name)

    print(f"\n{moved} fichier(s) déplacé(s). Journal : {log_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
