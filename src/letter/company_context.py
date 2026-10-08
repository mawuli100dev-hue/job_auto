# job_automation/src/job_automation/letter/company_context.py

from domain.models import ApplicationTarget


MAX_DESCRIPTION_LENGTH = 4000


class CompanyContextBuilder:
    """
    Construit l'unique bloc décrivant la cible dans le prompt
    de la lettre (offre publiée ou entreprise visée en spontané).
    """

    def build(
        self,
        target: ApplicationTarget,
    ) -> str:
        contract_label = {
            "alternance": "alternance",
            "stage": "stage",
        }[target.contract_type]

        if target.source_type == "published":
            parts = [
                "Nature : offre publiée par l'entreprise.",
                f"Intitulé du poste : {target.job_title}",
            ]
        else:
            parts = [
                "Nature : candidature spontanée, aucune "
                "offre n'a été publiée.",
                f"Domaine visé par le candidat : {target.job_title}",
            ]

        parts.append(
            f"Contrat recherché : {contract_label}"
        )

        if target.has_known_company():
            parts.append(
                f"Entreprise : {target.company_name}"
            )
        else:
            parts.append(
                "Entreprise : nom non communiqué "
                "(ne pas nommer l'entreprise dans la lettre)."
            )

        if target.location:
            parts.append(
                f"Lieu : {target.location}"
            )

        if target.required_experience:
            parts.append(
                "Expérience demandée : "
                f"{target.required_experience}"
            )

        if target.requested_skills:
            parts.append(
                "Compétences demandées : "
                f"{target.requested_skills}"
            )

        if target.description:
            label = (
                "Description de l'offre"
                if target.source_type == "published"
                else "Informations disponibles sur l'entreprise"
            )

            parts.append(
                f"{label} :\n"
                f"{target.description[:MAX_DESCRIPTION_LENGTH]}"
            )

        return "\n".join(parts)
