"""
completer_offres.py

Complète la description des offres repérées par les alertes e-mail
(collect_alerts_gmail.py), une par une :

1. le script affiche l'offre et l'ouvre dans ton navigateur ;
2. tu sélectionnes la description sur la page (« À propos de l'offre
   d'emploi ») et tu la copies (Ctrl+C) ;
3. tu appuies sur Entrée : le script lit le texte copié et range l'offre
   complétée dans data/linkedin/1_brutes/<type>/<date>/.

Tu restes maître de chaque page consultée : aucune page n'est lue
automatiquement.

Commandes pendant la saisie :
    Entrée  lire la description copiée
    p       passer cette offre (elle reste à compléter)
    x       offre sans intérêt (elle ne sera plus proposée)
    q       quitter (la progression est enregistrée)

Exemples
--------

python src\\completer_offres.py
python src\\completer_offres.py --fichier "data\\linkedin\\0_a_completer\\2026-10-08\\offres_linkedin_a_completer_2026-10-08_151356.csv"
"""

import argparse
import csv
import re
import sys
import tkinter
import webbrowser
from datetime import datetime
from pathlib import Path

from paths import (
    SOURCE_LINKEDIN,
    STAGE_RAW,
    STAGE_TO_COMPLETE,
    source_stage_dir,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

STATUS_FIELD = "statut"
STATUS_DONE = "complétée"
STATUS_REJECTED = "sans intérêt"

MIN_DESCRIPTION_LENGTH = 300


def read_clipboard() -> str:
    root = tkinter.Tk()
    root.withdraw()

    try:
        return root.clipboard_get()
    except tkinter.TclError:
        return ""
    finally:
        root.destroy()


def clean_description(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


def ask(prompt: str, choices: dict[str, str]) -> str:
    while True:
        answer = input(prompt).strip().lower()

        if answer in choices:
            return choices[answer]

        print("  Réponse non reconnue.")


def latest_to_complete_file() -> Path | None:
    folder = source_stage_dir(PROJECT_ROOT, SOURCE_LINKEDIN, STAGE_TO_COMPLETE)

    files = sorted(
        folder.rglob("offres_*.csv") if folder.exists() else [],
        key=lambda path: path.stat().st_mtime,
    )

    return files[-1] if files else None


def save_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_completed(row: dict, fieldnames: list[str]) -> Path:
    """
    Ajoute l'offre complétée au CSV du jour dans 1_brutes/<type>/<date>/.
    """

    today = datetime.now().strftime("%Y-%m-%d")
    contract_type = row["type_candidature"]

    folder = (
        source_stage_dir(PROJECT_ROOT, SOURCE_LINKEDIN, STAGE_RAW)
        / contract_type
        / today
    )
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / f"offres_linkedin_{contract_type}_{today}.csv"
    output_fields = [field for field in fieldnames if field != STATUS_FIELD]

    is_new = not path.exists()

    with path.open("a", encoding="utf-8-sig" if is_new else "utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=output_fields, extrasaction="ignore")

        if is_new:
            writer.writeheader()

        writer.writerow(row)

    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Complète la description des offres repérées par les alertes."
    )

    parser.add_argument(
        "--fichier",
        default=None,
        help="Liste à compléter (défaut : la plus récente de data/linkedin/0_a_completer).",
    )

    args = parser.parse_args()

    path = Path(args.fichier).resolve() if args.fichier else latest_to_complete_file()

    if path is None or not path.exists():
        sys.exit("Aucune liste à compléter. Lance d'abord : python src\\collect_alerts_gmail.py")

    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if STATUS_FIELD not in fieldnames:
        fieldnames.append(STATUS_FIELD)

    pending = [row for row in rows if not row.get(STATUS_FIELD)]

    print("==============================================")
    print("Compléter les offres")
    print("==============================================")
    print(f"Liste : {path}")
    print(f"{len(pending)} offre(s) à compléter sur {len(rows)}.\n")
    print("Pour chaque offre : la page s'ouvre dans ton navigateur. Sélectionne la")
    print("description (« À propos de l'offre d'emploi »), copie-la (Ctrl+C), puis")
    print("reviens ici et appuie sur Entrée.\n")

    previous_clipboard = read_clipboard()
    completed = 0

    for index, row in enumerate(pending, start=1):
        print("----------------------------------------------")
        print(f"[{index}/{len(pending)}] {row['intitule']}")
        print(f"   {row['entreprise']} - {row['lieu']}")
        print(f"   {row['url']}")

        webbrowser.open(row["url"])

        while True:
            action = input("   Entrée = lire la description copiée | p = passer | x = sans intérêt | q = quitter : ").strip().lower()

            if action == "q":
                save_rows(path, rows, fieldnames)
                print(f"\nProgression enregistrée : {completed} offre(s) complétée(s).")
                return

            if action == "p":
                break

            if action == "x":
                row[STATUS_FIELD] = STATUS_REJECTED
                save_rows(path, rows, fieldnames)
                break

            if action != "":
                print("   Réponse non reconnue.")
                continue

            text = clean_description(read_clipboard())

            if not text or text == clean_description(previous_clipboard):
                print("   Le presse-papiers n'a pas changé : copie la description, puis Entrée.")
                continue

            if len(text) < MIN_DESCRIPTION_LENGTH:
                keep = ask(
                    f"   Texte court ({len(text)} caractères). Le garder ? (o/n) : ",
                    {"o": "oui", "n": "non"},
                )

                if keep == "non":
                    continue

            if not row.get("type_candidature"):
                row["type_candidature"] = ask(
                    "   Type de contrat ? (s = stage, a = alternance) : ",
                    {"s": "stage", "a": "alternance"},
                )

            row["description"] = text
            row[STATUS_FIELD] = STATUS_DONE

            output = append_completed(row, fieldnames)
            save_rows(path, rows, fieldnames)

            previous_clipboard = text
            completed += 1

            print(f"   Enregistrée ({len(text)} caractères) dans {output.relative_to(PROJECT_ROOT)}")
            break

    print(f"\nTerminé : {completed} offre(s) complétée(s).")
    print("Étape suivante : filtre puis pipeline (voir guide\\source_linkedin.md).")


if __name__ == "__main__":
    main()
