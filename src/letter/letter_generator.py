# job_automation/src/job_automation/letter/letter_generator.py

import re

from config.letter_profile import (
    LETTER_PROFILE,
)
from domain.models import (
    LetterContent,
    LetterContext,
)
from letter.letter_prompt_builder import (
    LetterPromptBuilder,
)
from llm.json_client import JsonLlmClient


STANDARD_CLOSING = (
    "Veuillez agréer, Madame, Monsieur, l'expression "
    "de mes salutations distinguées."
)


def clean_text(value: object) -> str:
    text = str(value or "").strip()

    text = text.replace("—", ",")
    text = text.replace("–", "-")

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


class LetterGenerator:
    def __init__(
        self,
        llm_client: JsonLlmClient,
        prompt_builder: LetterPromptBuilder,
    ) -> None:
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder

    def generate(
        self,
        context: LetterContext,
    ) -> LetterContent:
        prompt = (
            self.prompt_builder
            .build_generation_prompt(
                context=context
            )
        )

        response = self.llm_client.request(
            prompt=prompt,
            temperature=0.5,
            max_tokens=3000,
            system=self.prompt_builder.system_prompt,
        )

        return self._parse_response(
            response=response,
            context=context,
        )

    def review(
        self,
        context: LetterContext,
        content: LetterContent,
    ) -> LetterContent:
        prompt = (
            self.prompt_builder
            .build_review_prompt(
                context=context,
                content=content,
            )
        )

        response = self.llm_client.request(
            prompt=prompt,
            temperature=0.3,
            max_tokens=2500,
            system=self.prompt_builder.system_prompt,
        )

        reviewed = self._parse_response(
            response=response,
            context=context,
        )

        # Une relecture ratée (JSON incomplet) ne doit pas
        # remplacer un premier jet valable.
        if not reviewed.paragraphs:
            return content

        if not reviewed.analysis:
            reviewed.analysis = content.analysis

        return reviewed

    def correct(
        self,
        context: LetterContext,
        content: LetterContent,
        errors: list[str],
    ) -> LetterContent:
        prompt = (
            self.prompt_builder
            .build_correction_prompt(
                context=context,
                content=content,
                errors=errors,
            )
        )

        response = self.llm_client.request(
            prompt=prompt,
            temperature=0.2,
            max_tokens=2500,
            system=self.prompt_builder.system_prompt,
        )

        return self._parse_response(
            response=response,
            context=context,
        )

    def _parse_response(
        self,
        response: dict,
        context: LetterContext,
    ) -> LetterContent:
        paragraphs = response.get(
            "paragraphs",
            [],
        )

        if isinstance(paragraphs, str):
            paragraphs = [
                paragraph.strip()
                for paragraph in re.split(
                    r"\n\s*\n",
                    paragraphs,
                )
                if paragraph.strip()
            ]

        if not isinstance(paragraphs, list):
            paragraphs = []

        cleaned_paragraphs = [
            clean_text(paragraph)
            for paragraph in paragraphs
            if clean_text(paragraph)
        ]

        # Formule d'appel, politesse et signature sont connues
        # d'avance : on les fixe ici plutôt que de payer un appel
        # de correction si le modèle s'en écarte.
        closing = clean_text(
            response.get("closing", "")
        )

        if "madame, monsieur" not in closing.lower():
            closing = STANDARD_CLOSING

        analysis = response.get("analyse", {})

        if not isinstance(analysis, dict):
            analysis = {}

        return LetterContent(
            analysis=analysis,

            subject=clean_text(
                response.get("subject", "")
            ),

            greeting=context.recipient.greeting,

            paragraphs=cleaned_paragraphs,

            closing=closing,

            signature=LETTER_PROFILE.full_name,
        )