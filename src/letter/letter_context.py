# job_automation/src/job_automation/letter/letter_context.py

from datetime import datetime

from domain.availability import (
    resolve_availability,
)
from domain.models import (
    ApplicationTarget,
    LetterContext,
)
from letter.company_context import (
    CompanyContextBuilder,
)
from letter.recipient_resolver import (
    RecipientResolver,
)


FRENCH_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def current_date_label() -> str:
    now = datetime.now()

    return (
        f"{now.day} "
        f"{FRENCH_MONTHS[now.month - 1]} "
        f"{now.year}"
    )


class LetterContextBuilder:
    def __init__(
        self,
        recipient_resolver: RecipientResolver,
        company_context_builder: CompanyContextBuilder,
    ) -> None:
        self.recipient_resolver = (
            recipient_resolver
        )

        self.company_context_builder = (
            company_context_builder
        )

    def build(
        self,
        target: ApplicationTarget,
        cv_data: dict,
    ) -> LetterContext:
        cv_section = cv_data.get(
            "cv",
            {},
        )

        if not isinstance(cv_section, dict):
            cv_section = {}

        subtitle = (
            cv_section.get("subtitle")
            or cv_data.get("sous_titre_cv")
            or ""
        )

        experiences = (
            cv_section.get("experiences")
            or cv_data.get(
                "experiences_sur_cv",
                [],
            )
        )

        skills = (
            cv_section.get("skills")
            or cv_data.get(
                "competences_sur_cv",
                {},
            )
        )

        if not isinstance(experiences, list):
            experiences = []

        if not isinstance(skills, dict):
            skills = {}

        recipient = (
            self.recipient_resolver.resolve(
                target=target
            )
        )

        company_context = (
            self.company_context_builder.build(
                target=target
            )
        )

        availability = resolve_availability(target)

        if availability.warning:
            print(f"ATTENTION : {availability.warning}")

        return LetterContext(
            target=target,
            cv_subtitle=str(subtitle),
            selected_experiences=experiences,
            selected_skills=skills,
            recipient=recipient,
            company_context=company_context,
            date_label=current_date_label(),
            availability=availability.label,
            availability_frame=availability.frame,
        )