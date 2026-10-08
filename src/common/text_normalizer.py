# job_automation/src/job_automation/common/text_normalizer.py

import re
import unicodedata


def remove_accents(
    value: object,
) -> str:
    """
    Supprime les accents d'une valeur convertie en texte.
    """

    if value is None:
        return ""

    text = str(value)

    normalized = unicodedata.normalize(
        "NFKD",
        text,
    )

    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def normalize_text(
    value: object,
) -> str:
    """
    Normalise un texte pour effectuer des comparaisons :

    - conversion en chaîne ;
    - suppression des accents ;
    - passage en minuscules ;
    - normalisation des apostrophes ;
    - remplacement de la ponctuation par des espaces ;
    - suppression des espaces multiples.
    """

    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    text = remove_accents(
        text
    ).lower()

    text = text.replace(
        "’",
        "'",
    )

    text = text.replace(
        "œ",
        "oe",
    )

    text = re.sub(
        r"[^a-z0-9+#.'/-]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def clean_generated_text(
    value: object,
) -> str:
    """
    Nettoie un texte produit par le LLM sans supprimer
    les accents ni modifier sa casse.
    """

    if value is None:
        return ""

    text = str(value).strip()

    text = text.replace(
        "\r\n",
        "\n",
    )

    text = text.replace(
        "\r",
        "\n",
    )

    text = text.replace(
        "—",
        ",",
    )

    text = text.replace(
        "–",
        "-",
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r" *\n *",
        "\n",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    text = re.sub(
        r"\s+,",
        ",",
        text,
    )

    return text.strip()


def contains_whole_expression(
    expression: object,
    normalized_text: str,
) -> bool:
    """
    Vérifie qu'une expression apparaît comme une expression
    complète dans un texte déjà normalisé.

    Cette fonction évite notamment que le tag « r » corresponde
    à chaque mot contenant la lettre r.
    """

    normalized_expression = normalize_text(
        expression
    )

    if not normalized_expression:
        return False

    if not normalized_text:
        return False

    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(normalized_expression)
        + r"(?![a-z0-9])"
    )

    return (
        re.search(
            pattern,
            normalized_text,
        )
        is not None
    )


def contains_any_expression(
    expressions: list[str] | tuple[str, ...],
    text: object,
) -> bool:
    """
    Vérifie si au moins une expression apparaît
    dans le texte.
    """

    normalized_text = normalize_text(
        text
    )

    return any(
        contains_whole_expression(
            expression=expression,
            normalized_text=normalized_text,
        )
        for expression in expressions
    )