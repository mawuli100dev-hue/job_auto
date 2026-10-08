# src/offers/csv_repository.py

import csv
from pathlib import Path


class CsvOfferRepository:
    def find_by_id(
        self,
        csv_path: Path,
        offer_id: str,
    ) -> dict:
        if not csv_path.exists():
            raise FileNotFoundError(
                f"CSV introuvable : {csv_path}"
            )

        with csv_path.open(
            mode="r",
            newline="",
            encoding="utf-8-sig",
        ) as csv_file:
            reader = csv.DictReader(csv_file)

            if not reader.fieldnames:
                raise ValueError(
                    "Le CSV ne contient aucun en-tête."
                )

            if "id" not in reader.fieldnames:
                raise ValueError(
                    "Le CSV ne contient pas de colonne 'id'."
                )

            for row in reader:
                if str(row.get("id", "")).strip() == offer_id:
                    return row

        raise ValueError(
            f"Offre id={offer_id} introuvable "
            f"dans {csv_path}"
        )