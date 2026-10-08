# job_automation/src/common/slug.py

import re
import unicodedata


def slugify(
    value: object,
    max_length: int = 60,
) -> str:
    """
    Transforme une valeur en nom utilisable pour un dossier.

    Exemple :
        "Direction des Systèmes d'Information"
        devient :
        "direction_des_systemes_d_information"
    """

    if value is None:
        return "non_precise"

    text = str(value).strip()

    if not text:
        return "non_precise"

    normalized = unicodedata.normalize(
        "NFKD",
        text,
    )

    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    slug = re.sub(
        r"[^a-zA-Z0-9]+",
        "_",
        without_accents,
    )

    slug = slug.strip("_").lower()

    if not slug:
        return "non_precise"

    return slug[:max_length].rstrip("_")