# job_automation/src/check_duplicate.py

"""
Vérifie si une offre a déjà une candidature préparée, venue d'une autre
source (même entreprise et même intitulé, identifiant différent).

Utilisé par run_pipeline.ps1 avant de générer le CV et la lettre.

Codes de sortie :
    0 : pas de doublon
    1 : doublon trouvé (le dossier existant est affiché)
    2 : erreur

Exemple :

python src\\check_duplicate.py --csv "data\\pass\\2_filtrees\\stage\\...csv" --offer-id S-2026-237511
"""

import argparse
import sys
from pathlib import Path

from offers.csv_repository import CsvOfferRepository
from offers.fingerprint import find_duplicate_application


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Cherche une candidature déjà préparée pour la même "
            "offre venue d'une autre source."
        )
    )

    parser.add_argument("--csv", required=True)
    parser.add_argument("--offer-id", required=True)

    args = parser.parse_args()

    try:
        row = CsvOfferRepository().find_by_id(
            csv_path=Path(args.csv).resolve(),
            offer_id=args.offer_id,
        )

        duplicate = find_duplicate_application(
            project_root=PROJECT_ROOT,
            company=row.get("entreprise", ""),
            title=row.get("intitule", ""),
            offer_id=args.offer_id,
            location=row.get("lieu", ""),
        )
    except Exception as error:
        print(f"Erreur : {error}")
        sys.exit(2)

    if duplicate is None:
        sys.exit(0)

    print(duplicate)
    sys.exit(1)


if __name__ == "__main__":
    main()
