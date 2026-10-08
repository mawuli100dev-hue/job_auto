# job_automation/src/job_automation/letter/letter_validator.py

import json
import re

from config.letter_profile import (
    LETTER_PROFILE,
)
from common.text_normalizer import (
    contains_whole_expression,
    normalize_text,
)
from domain.models import (
    LetterContent,
    LetterContext,
)
from config.letter_examples import (
    FREE_PHRASES,
    LETTER_EXAMPLES,
)
from letter.letter_prompt_builder import (
    BANNED_EXPRESSIONS,
)


# Appliqués au texte brut : normalize_text supprime
# les crochets et accolades.
RAW_PLACEHOLDER_PATTERNS = (
    r"\[[^\]]+\]",
    r"\{[^}]+\}",
    r"<[^>]+>",
)

# Appliqués au texte normalisé.
NORMALIZED_PLACEHOLDER_PATTERNS = (
    r"\bxxx+\b",
    r"\ba completer\b",
    r"\bnom de l'entreprise\b",
    r"\bnom du destinataire\b",
)

# Bornes sur les paragraphes seuls, alignées sur la
# consigne du prompt (360-470 mots) avec une marge.
MIN_BODY_WORDS = 320
MAX_BODY_WORDS = 500

# Une suite de mots aussi longue, identique à une lettre modèle
# et absente des données du CV, signifie que le LLM recopie au
# lieu d'imiter.
COPIED_SEQUENCE_WORDS = 10

# Longueur d'une suite de mots reconnue comme un fait du CV.
FACT_SEQUENCE_WORDS = 5

# Pour une alternance, ces expressions trahissent une
# lettre écrite pour un stage.
INTERNSHIP_EXPRESSIONS = (
    "stagiaire",
    "un stage",
    "ce stage",
    "de stage",
    "offre de stage",
)

SPONTANEOUS_FORBIDDEN_EXPRESSIONS = (
    "votre offre",
    "votre annonce",
    "l'offre publiee",
    "l'annonce publiee",
    "en reponse a votre",
)


# Outils que les recruteurs cherchent en priorité dans une
# lettre. Nom affiché -> variantes reconnues.
TOOL_KEYWORDS = {
    "Python": ("python",),
    "SQL": ("sql",),
    "Power BI": ("power bi", "powerbi"),
    "Excel": ("excel",),
    "R": ("langage r", "r studio", "rstudio"),
    "Streamlit": ("streamlit",),
    "Docker": ("docker",),
    "Git": ("git", "github"),
    "PostgreSQL": ("postgresql", "postgres"),
    "MongoDB": ("mongodb",),
    "QGIS": ("qgis",),
    "FME": ("fme",),
    "VBA": ("vba",),
    "DAX": ("dax",),
    "Azure": ("azure",),
    "Linux": ("linux",),
    "pandas": ("pandas",),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "TensorFlow": ("tensorflow",),
    "PyTorch": ("pytorch",),
}


def word_sequences(
    text: str,
    size: int,
) -> set[tuple[str, ...]]:
    words = normalize_text(text).split()

    return {
        tuple(words[index:index + size])
        for index in range(len(words) - size + 1)
    }


# Le dernier paragraphe des modèles (proposition d'échange)
# peut être repris tel quel.
EXAMPLE_SEQUENCES = set().union(
    *(
        word_sequences(paragraph, COPIED_SEQUENCE_WORDS)
        for example in LETTER_EXAMPLES
        for paragraph in example.paragraphs[:-1]
    )
)


def count_words(text: str) -> int:
    return len(
        re.findall(
            r"[\wÀ-ÿ'-]+",
            text,
        )
    )


class LetterValidator:
    """
    validate() : erreurs bloquantes (la lettre ne doit pas partir).
    validate_style() : défauts de qualité, corrigés si possible
    mais qui ne font pas échouer la candidature.
    """

    def validate(
        self,
        content: LetterContent,
        context: LetterContext,
    ) -> list[str]:
        errors: list[str] = []

        if not content.subject:
            errors.append(
                "L'objet de la lettre est vide."
            )

        if (
            normalize_text(content.greeting)
            != normalize_text(context.recipient.greeting)
        ):
            errors.append(
                "La formule d'appel doit être exactement "
                f"« {context.recipient.greeting} »."
            )

        if not 4 <= len(content.paragraphs) <= 8:
            errors.append(
                "La lettre doit contenir 5 à 7 paragraphes "
                f"(actuellement {len(content.paragraphs)})."
            )

        if not content.closing:
            errors.append(
                "La formule de politesse finale est vide."
            )
        elif not contains_whole_expression(
            expression="madame monsieur",
            normalized_text=normalize_text(content.closing),
        ):
            errors.append(
                "La formule de politesse doit reprendre "
                "« Madame, Monsieur »."
            )

        if (
            normalize_text(content.signature)
            != normalize_text(LETTER_PROFILE.full_name)
        ):
            errors.append(
                "La signature doit être exactement "
                f"« {LETTER_PROFILE.full_name} »."
            )

        body = " ".join(content.paragraphs)

        full_text = " ".join(
            [
                content.subject,
                content.greeting,
                body,
                content.closing,
                content.signature,
            ]
        )

        normalized_text = normalize_text(
            full_text
        )

        if "**" in full_text or "```" in full_text:
            errors.append(
                "La lettre contient du Markdown."
            )

        if re.search(r"https?://|www\.", full_text):
            errors.append(
                "La lettre contient une URL."
            )

        has_placeholder = any(
            re.search(pattern, full_text)
            for pattern in RAW_PLACEHOLDER_PATTERNS
        ) or any(
            re.search(pattern, normalized_text)
            for pattern in NORMALIZED_PLACEHOLDER_PATTERNS
        )

        if has_placeholder:
            errors.append(
                "La lettre contient une variable "
                "ou un champ non remplacé."
            )

        if (
            not context.target.has_known_company()
            and contains_whole_expression(
                expression=context.target.company_name,
                normalized_text=normalized_text,
            )
        ):
            errors.append(
                "Le nom de l'entreprise n'est pas connu : "
                f"ne pas écrire « {context.target.company_name} »."
            )

        if context.target.contract_type == "stage":
            if contains_whole_expression(
                expression="alternance",
                normalized_text=normalized_text,
            ):
                errors.append(
                    "La lettre parle d'alternance alors "
                    "que la candidature concerne un stage."
                )

            if not contains_whole_expression(
                expression="stage",
                normalized_text=normalized_text,
            ):
                errors.append(
                    "La lettre ne mentionne pas clairement "
                    "la recherche d'un stage."
                )

        if context.target.contract_type == "alternance":
            if any(
                contains_whole_expression(
                    expression=expression,
                    normalized_text=normalized_text,
                )
                for expression in INTERNSHIP_EXPRESSIONS
            ):
                errors.append(
                    "La lettre semble parler d'un stage alors "
                    "que la candidature concerne une alternance."
                )

            if not contains_whole_expression(
                expression="alternance",
                normalized_text=normalized_text,
            ):
                errors.append(
                    "La lettre ne mentionne pas clairement "
                    "la recherche d'une alternance."
                )

        if (
            context.target.source_type
            == "spontaneous"
        ):
            if any(
                contains_whole_expression(
                    expression=expression,
                    normalized_text=normalized_text,
                )
                for expression in SPONTANEOUS_FORBIDDEN_EXPRESSIONS
            ):
                errors.append(
                    "Une candidature spontanée ne doit pas "
                    "prétendre répondre à une offre publiée."
                )

        return errors

    def validate_style(
        self,
        content: LetterContent,
        context: LetterContext,
    ) -> list[str]:
        errors: list[str] = []

        body = " ".join(content.paragraphs)

        body_words = count_words(body)

        if body_words < MIN_BODY_WORDS:
            errors.append(
                f"Les paragraphes sont trop courts "
                f"({body_words} mots, minimum {MIN_BODY_WORDS})."
            )

        if body_words > MAX_BODY_WORDS:
            errors.append(
                f"Les paragraphes sont trop longs "
                f"({body_words} mots, maximum {MAX_BODY_WORDS})."
            )

        normalized_text = normalize_text(
            " ".join([body, content.closing])
        )

        used_banned = [
            expression
            for expression in BANNED_EXPRESSIONS
            if contains_whole_expression(
                expression=expression,
                normalized_text=normalized_text,
            )
        ]

        if used_banned:
            errors.append(
                "Formules creuses à remplacer par un fait "
                "concret : "
                + ", ".join(
                    f"« {expression} »"
                    for expression in used_banned
                )
                + "."
            )

        copied = self._copied_from_examples(
            body=body,
            context=context,
        )

        if copied:
            errors.append(
                "Passages recopiés d'une lettre modèle, "
                "à réécrire avec les faits de cette candidature : "
                + " / ".join(
                    f"« {sequence} »"
                    for sequence in copied[:3]
                )
                + "."
            )

        missing_tools = self._missing_required_tools(
            content=content,
            context=context,
        )

        if missing_tools:
            errors.append(
                "Outils exigés par l'offre et présents sur le CV, "
                "mais absents de la lettre : "
                + ", ".join(missing_tools)
                + ". Cite-les dans une preuve concrète."
            )

        return errors

    @staticmethod
    def _copied_from_examples(
        body: str,
        context: LetterContext,
    ) -> list[str]:
        """
        Suites de mots reprises d'une lettre modèle. Les mots qui
        décrivent un fait du CV (formation, projet, outils) peuvent
        être identiques : seule la reprise du style est signalée.
        """

        facts_sequences = word_sequences(
            json.dumps(
                [
                    LETTER_PROFILE.formation,
                    LETTER_PROFILE.previous_background,
                    *FREE_PHRASES,
                    context.selected_experiences,
                    context.selected_skills,
                ],
                ensure_ascii=False,
            ),
            FACT_SEQUENCE_WORDS,
        )

        words = normalize_text(body).split()
        covered = [False] * len(words)

        for index in range(len(words) - FACT_SEQUENCE_WORDS + 1):
            sequence = tuple(
                words[index:index + FACT_SEQUENCE_WORDS]
            )

            if sequence in facts_sequences:
                for position in range(
                    index,
                    index + FACT_SEQUENCE_WORDS,
                ):
                    covered[position] = True

        copied = []

        for index in range(len(words) - COPIED_SEQUENCE_WORDS + 1):
            positions = range(
                index,
                index + COPIED_SEQUENCE_WORDS,
            )
            sequence = tuple(words[index:index + COPIED_SEQUENCE_WORDS])

            style_words = sum(
                not covered[position]
                for position in positions
            )

            if (
                sequence in EXAMPLE_SEQUENCES
                and style_words > COPIED_SEQUENCE_WORDS // 2
            ):
                copied.append(" ".join(sequence))

        return copied

    @staticmethod
    def _missing_required_tools(
        content: LetterContent,
        context: LetterContext,
    ) -> list[str]:
        """
        Outils cités par l'offre ET présents sur le CV que la
        lettre ne mentionne pas : ce sont les mots que le
        recruteur cherche en premier.
        """

        target = context.target

        offer_text = normalize_text(
            " ".join(
                [
                    target.job_title,
                    target.requested_skills,
                    target.description,
                ]
            )
        )

        cv_text = normalize_text(
            json.dumps(
                [
                    context.selected_experiences,
                    context.selected_skills,
                ],
                ensure_ascii=False,
            )
        )

        letter_text = normalize_text(
            " ".join(content.paragraphs)
        )

        def mentions(tool: str, text: str) -> bool:
            return any(
                contains_whole_expression(
                    expression=variant,
                    normalized_text=text,
                )
                for variant in TOOL_KEYWORDS[tool]
            )

        return [
            tool
            for tool in TOOL_KEYWORDS
            if mentions(tool, offer_text)
            and mentions(tool, cv_text)
            and not mentions(tool, letter_text)
        ]
