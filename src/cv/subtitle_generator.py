# src/cv/subtitle_generator.py

import re

from common.text_normalizer import (
    clean_generated_text,
)
from domain.availability import (
    resolve_availability,
)
from domain.models import ApplicationTarget
from llm.json_client import JsonLlmClient


class SubtitleGenerator:
    """
    Sous-titre du CV : « <poste visé> | <disponibilité> ».

    Le LLM ne rédige que la partie poste ; la disponibilité est
    calculée par domain.availability pour être toujours présente
    et toujours exacte.
    """

    def __init__(
        self,
        llm_client: JsonLlmClient,
    ) -> None:
        self.llm_client = llm_client

    def generate(
        self,
        target: ApplicationTarget,
    ) -> str:
        availability = resolve_availability(target)

        if availability.warning:
            print(f"ATTENTION : {availability.warning}")

        role = self._generate_role(target)

        return clean_generated_text(
            f"{role} | {availability.label}"
        )

    def _generate_role(
        self,
        target: ApplicationTarget,
    ) -> str:
        contract_word = {
            "alternance": "alternance",
            "stage": "stage",
        }[target.contract_type]

        prompt = f"""
Tu rédiges le sous-titre d'un CV, juste sous le nom du candidat, pour une candidature en {contract_word}.

INTITULÉ BRUT DE L'OFFRE :
"{target.job_title}"

CONSIGNES :
1. Format : « {contract_word.capitalize()} <métier> », par exemple « Alternance Data Analyst » ou « Stage Data Engineer - Données de production ».
2. Garde le métier de l'intitulé ; tu peux ajouter un domaine court s'il figure dans l'intitulé.
3. Supprime H/F, F/H, « offre de », les parenthèses et les majuscules inutiles.
4. 2 à 8 mots, sans point final, sans tiret cadratin ni demi-cadratin.
5. N'invente aucun métier absent de l'intitulé.
6. N'indique aucune date ni disponibilité.

Réponds uniquement en JSON :

{{"sous_titre": "..."}}
""".strip()

        try:
            response = self.llm_client.request(
                prompt=prompt,
                temperature=0,
                max_tokens=80,
            )

            role = clean_generated_text(
                response.get("sous_titre", "")
            ).rstrip(" .")

            if role:
                return role

        except Exception as error:
            print(
                "ATTENTION : génération du sous-titre "
                f"impossible ({error}). "
                "Utilisation du sous-titre de secours."
            )

        return self._fallback(
            target=target,
        )

    def _fallback(
        self,
        target: ApplicationTarget,
    ) -> str:
        title = target.job_title or "Data Analyst"

        title = re.sub(
            r"\((?:H\s*/\s*F|F\s*/\s*H)\)",
            "",
            title,
            flags=re.IGNORECASE,
        )

        title = re.sub(
            r"(?i)\(?\b(?:offre\s+d['’]?)?(?:alternance|stage)\b\)?\s*[-:]?\s*",
            "",
            title,
        )

        title = re.sub(
            r"\s+",
            " ",
            title,
        ).strip(" -,")

        if len(title) > 60:
            title = title[:60].rsplit(
                " ",
                1,
            )[0]

        prefix = (
            "Stage"
            if target.contract_type == "stage"
            else "Alternance"
        )

        return clean_generated_text(
            f"{prefix} {title}"
        )
