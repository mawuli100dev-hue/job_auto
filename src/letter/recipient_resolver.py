# job_automation/src/job_automation/letter/recipient_resolver.py

from domain.models import (
    ApplicationTarget,
    RecipientInfo,
)


class RecipientResolver:
    def resolve(
        self,
        target: ApplicationTarget,
    ) -> RecipientInfo:
        recipient_name = (
            target.recipient_name.strip()
        )

        recipient_role = (
            target.recipient_role.strip()
        )

        recipient_email = (
            target.recipient_email.strip()
        )

        # « Madame, Monsieur Dupont, » est incorrect en français et
        # le genre du destinataire est inconnu : la formule reste
        # neutre, le nom apparaît dans le bloc adresse.
        greeting = "Madame, Monsieur,"

        postal_lines = []

        if target.has_known_company():
            postal_lines.append(
                target.company_name
            )

        if recipient_name:
            postal_lines.append(
                recipient_name
            )

        if recipient_role:
            postal_lines.append(
                recipient_role
            )

        if target.company_address:
            postal_lines.append(
                target.company_address
            )
        elif target.location:
            postal_lines.append(
                target.location
            )

        return RecipientInfo(
            greeting=greeting,
            name=recipient_name,
            role=recipient_role,
            email=recipient_email,
            postal_lines=tuple(postal_lines),
        )