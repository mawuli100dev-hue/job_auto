# src/job_automation/cv/artifact_writer.py

from dataclasses import asdict
from pathlib import Path

from common.json_utils import save_json
from domain.models import (
    ApplicationTarget,
    CvContent,
)


class CvArtifactWriter:
    def write_offer_snapshot(
        self,
        target: ApplicationTarget,
        destination: Path,
    ) -> None:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        contract_label = {
            "alternance": "Alternance",
            "stage": "Stage",
        }[target.contract_type]

        with destination.open(
            mode="w",
            encoding="utf-8",
        ) as text_file:
            text_file.write(
                f"Identifiant : {target.external_id}\n"
            )

            text_file.write(
                f"Type : {contract_label}\n"
            )

            text_file.write(
                f"Source : {target.source_type}\n"
            )

            text_file.write(
                f"Intitulé : {target.job_title}\n"
            )

            text_file.write(
                f"Entreprise : {target.company_name}\n"
            )

            text_file.write(
                f"Lieu : {target.location}\n"
            )

            text_file.write(
                f"URL : {target.url}\n\n"
            )

            text_file.write(
                "--- Description complète ---\n"
            )

            text_file.write(
                target.description
            )

    def write_cv_data(
        self,
        target: ApplicationTarget,
        content: CvContent,
        destination: Path,
    ) -> None:
        data = {
            "schema_version": 2,

            # Champs conservés pour la compatibilité avec
            # generate_letter.py dans sa version actuelle.
            "offer_id": target.external_id,
            "offer": {
                "intitule": target.job_title,
                "entreprise": target.company_name,
                "lieu": target.location,
                "url": target.url,
            },
            "sous_titre_cv": content.subtitle,
            "experiences_sur_cv": content.experiences,
            "competences_sur_cv": content.skills,

            # Nouveau modèle plus général.
            "application": {
                "application_id": (
                    target.application_id
                ),
                "external_id": target.external_id,
                "source_type": target.source_type,
                "contract_type": (
                    target.contract_type
                ),
            },
            "target": asdict(target),
            "cv": {
                "subtitle": content.subtitle,
                "experiences": content.experiences,
                "skills": content.skills,
            },
        }

        save_json(
            path=destination,
            data=data,
        )