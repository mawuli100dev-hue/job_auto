# src/common/text.py

import re
import unicodedata


def normalize_text(value: object) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    normalized = unicodedata.normalize(
        "NFKD",
        text,
    )

    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    return without_accents.lower()


def slugify(
    value: object,
    max_length: int = 40,
) -> str:
    normalized = normalize_text(value)

    slug = re.sub(
        r"[^a-z0-9]+",
        "_",
        normalized,
    ).strip("_")

    if not slug:
        slug = "entreprise"

    return slug[:max_length]


def clean_generated_text(text: str) -> str:
    if not text:
        return ""

    cleaned = text.replace("—", ",")
    cleaned = cleaned.replace("–", "-")

    cleaned = re.sub(
        r"\s+,",
        ",",
        cleaned,
    )

    cleaned = re.sub(
        r"\s+",
        " ",
        cleaned,
    )

    return cleaned.strip()


def contains_whole_expression(
    expression: str,
    normalized_text: str,
) -> bool:
    normalized_expression = normalize_text(expression)

    if not normalized_expression:
        return False

    pattern = (
        r"(?<!\w)"
        + re.escape(normalized_expression)
        + r"(?!\w)"
    )

    return (
        re.search(pattern, normalized_text)
        is not None
    )