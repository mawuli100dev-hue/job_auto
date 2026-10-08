# job_automation/src/job_automation/offers/normalizer.py

from common.text_normalizer import normalize_text
from domain.models import ApplicationTarget


VALID_CONTRACT_TYPES = {
    "alternance",
    "stage",
}

VALID_SOURCE_TYPES = {
    "published",
    "spontaneous",
}


def _first_non_empty(
    row: dict,
    *keys: str,
) -> str:
    for key in keys:
        value = row.get(key)

        if value is None:
            continue

        value = str(value).strip()

        if value:
            return value

    return ""


def _resolve_contract_type(
    row: dict,
    requested_contract_type: str | None,
) -> str:
    if requested_contract_type:
        normalized = normalize_text(
            requested_contract_type
        )

        if normalized not in VALID_CONTRACT_TYPES:
            raise ValueError(
                "Le type de candidature doit être "
                "'alternance' ou 'stage'."
            )

        return normalized

    declared_type = normalize_text(
        row.get("type_candidature", "")
    )

    if declared_type in VALID_CONTRACT_TYPES:
        return declared_type

    # Compatibilité avec les anciens CSV.
    return "alternance"


def normalize_published_offer(
    row: dict,
    requested_contract_type: str | None = None,
) -> ApplicationTarget:
    offer_id = _first_non_empty(
        row,
        "id",
        "offer_id",
        "external_id",
    )

    if not offer_id:
        raise ValueError(
            "L'offre ne possède aucun identifiant."
        )

    contract_type = _resolve_contract_type(
        row=row,
        requested_contract_type=(
            requested_contract_type
        ),
    )

    company_name = _first_non_empty(
        row,
        "entreprise",
        "company_name",
        "company",
        "nom_entreprise",
    )

    if not company_name:
        company_name = "Non precise"

    requested_skills_parts = [
        _first_non_empty(
            row,
            "competences",
        ),
        _first_non_empty(
            row,
            "competences_attendues",
        ),
        _first_non_empty(
            row,
            "competences_a_acquerir",
        ),
    ]

    requested_skills = ", ".join(
        part
        for part in requested_skills_parts
        if part
    )

    return ApplicationTarget(
        application_id=(
            f"published_{offer_id}"
        ),
        external_id=offer_id,
        source_type="published",
        contract_type=contract_type,

        company_name=company_name,

        job_title=_first_non_empty(
            row,
            "intitule",
            "title",
            "poste",
        ),

        description=_first_non_empty(
            row,
            "description",
        ),

        location=_first_non_empty(
            row,
            "lieu",
            "location",
        ),

        url=_first_non_empty(
            row,
            "url",
            "url_candidature",
        ),

        requested_skills=requested_skills,

        required_experience=_first_non_empty(
            row,
            "experience_exigee",
            "experience",
        ),

        recipient_name=_first_non_empty(
            row,
            "recipient_name",
            "nom_contact",
            "contact_name",
        ),

        recipient_role=_first_non_empty(
            row,
            "recipient_role",
            "fonction_contact",
            "contact_role",
        ),

        recipient_email=_first_non_empty(
            row,
            "recipient_email",
            "email_contact",
        ),

        company_address=_first_non_empty(
            row,
            "adresse_entreprise",
            "company_address",
        ),

        start_date=_first_non_empty(
            row,
            "date_debut",
            "start_date",
        ),

        origin=_first_non_empty(
            row,
            "source",
        ),
    )


def normalize_spontaneous_target(
    row: dict,
    requested_contract_type: str | None = None,
) -> ApplicationTarget:
    company_name = _first_non_empty(
        row,
        "entreprise",
        "nom_entreprise",
        "company_name",
        "company",
        "nom",
    )

    if not company_name:
        raise ValueError(
            "La cible spontanée ne possède "
            "aucun nom d'entreprise."
        )

    external_id = _first_non_empty(
        row,
        "id",
        "company_id",
        "siret",
        "siren",
    )

    if not external_id:
        external_id = normalize_text(
            company_name
        ).replace(" ", "_")

    contract_type = _resolve_contract_type(
        row=row,
        requested_contract_type=(
            requested_contract_type
        ),
    )

    activity_parts = [
        _first_non_empty(
            row,
            "description",
        ),
        _first_non_empty(
            row,
            "activite",
            "activité",
        ),
        _first_non_empty(
            row,
            "presentation",
        ),
        _first_non_empty(
            row,
            "secteur",
            "secteur_activite",
        ),
    ]

    description = "\n".join(
        part
        for part in activity_parts
        if part
    )

    job_title = _first_non_empty(
        row,
        "poste_cible",
        "job_title",
        "poste",
        "metier_cible",
    )

    if not job_title:
        job_title = "Data Analyst"

    return ApplicationTarget(
        application_id=(
            f"spontaneous_{external_id}_"
            f"{contract_type}"
        ),
        external_id=external_id,
        source_type="spontaneous",
        contract_type=contract_type,

        company_name=company_name,
        job_title=job_title,
        description=description,

        location=_first_non_empty(
            row,
            "lieu",
            "ville",
            "location",
        ),

        url=_first_non_empty(
            row,
            "site_web",
            "website",
            "url",
        ),

        requested_skills=_first_non_empty(
            row,
            "competences_cibles",
            "competences",
        ),

        recipient_name=_first_non_empty(
            row,
            "recipient_name",
            "nom_contact",
            "contact_name",
        ),

        recipient_role=_first_non_empty(
            row,
            "recipient_role",
            "fonction_contact",
            "contact_role",
        ),

        recipient_email=_first_non_empty(
            row,
            "recipient_email",
            "email_contact",
            "email",
        ),

        company_address=_first_non_empty(
            row,
            "adresse",
            "adresse_entreprise",
            "company_address",
        ),

        start_date=_first_non_empty(
            row,
            "date_debut",
            "start_date",
        ),

        origin=_first_non_empty(
            row,
            "source",
        ),
    )