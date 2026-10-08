# job_automation/src/job_automation/domain/models.py

from dataclasses import dataclass, field
from typing import Any, Literal


SourceType = Literal[
    "published",
    "spontaneous",
]

ContractType = Literal[
    "alternance",
    "stage",
]


@dataclass(frozen=True)
class ApplicationTarget:
    application_id: str
    external_id: str
    source_type: SourceType
    contract_type: ContractType

    company_name: str
    job_title: str
    description: str

    location: str = ""
    url: str = ""
    requested_skills: str = ""
    required_experience: str = ""

    recipient_name: str = ""
    recipient_role: str = ""
    recipient_email: str = ""
    company_address: str = ""

    # Date de début donnée dans une colonne du CSV (PASS, La Bonne
    # Alternance), ex. « Janvier 2027 » ou « 2027-01-15 ».
    start_date: str = ""

    # Colonne « source » du CSV (france_travail, pass, linkedin...).
    origin: str = ""

    def build_summary(
        self,
        max_description_length: int = 3500,
    ) -> str:
        source_label = {
            "published": "offre publiée",
            "spontaneous": "candidature spontanée",
        }[self.source_type]

        contract_label = {
            "alternance": "alternance",
            "stage": "stage",
        }[self.contract_type]

        return (
            f"Source : {source_label}\n"
            f"Contrat recherché : {contract_label}\n"
            f"Intitulé ciblé : {self.job_title}\n"
            f"Entreprise : {self.company_name}\n"
            f"Lieu : {self.location}\n"
            f"Expérience demandée : "
            f"{self.required_experience}\n"
            f"Compétences demandées : "
            f"{self.requested_skills}\n"
            f"Description : "
            f"{self.description[:max_description_length]}"
        )

    def has_known_company(self) -> bool:
        # normalizer.py remplace un nom absent par "Non precise".
        return bool(self.company_name) and (
            self.company_name.strip().lower()
            not in {"non precise", "non précisé", "non precisé"}
        )

    def searchable_text(self) -> str:
        return " ".join(
            [
                self.job_title,
                self.description,
                self.requested_skills,
                self.required_experience,
            ]
        )


@dataclass
class CvContent:
    subtitle: str
    experiences: list[dict[str, Any]]
    skills: dict[str, list[str]]


@dataclass(frozen=True)
class CvGenerationResult:
    pdf_path: str
    docx_path: str
    cv_data_path: str
    scale_used: float


@dataclass(frozen=True)
class RecipientInfo:
    greeting: str
    name: str = ""
    role: str = ""
    email: str = ""
    postal_lines: tuple[str, ...] = field(
        default_factory=tuple
    )

    @property
    def attention_line(self) -> str:
        if self.name:
            return f"À l'attention de {self.name}"

        return "À l'attention de l'équipe de recrutement"


@dataclass(frozen=True)
class LetterContext:
    target: ApplicationTarget

    cv_subtitle: str
    selected_experiences: list[dict[str, Any]]
    selected_skills: dict[str, list[str]]

    recipient: RecipientInfo
    company_context: str
    date_label: str

    # Même valeur que sur le CV (domain.availability).
    availability: str = ""

    # Cadre de l'alternance (année de BUT ou master).
    availability_frame: str = ""


@dataclass
class LetterContent:
    subject: str
    greeting: str
    paragraphs: list[str]
    closing: str
    signature: str

    # Besoins de l'offre et preuves retenues par le LLM avant
    # rédaction ; non affiché, sauvegardé pour le contrôle.
    analysis: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class LetterGenerationResult:
    pdf_path: str
    docx_path: str
    letter_data_path: str
    scale_used: float