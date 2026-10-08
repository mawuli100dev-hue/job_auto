# src/cv/keyword_matcher.py

from common.text_normalizer import (
    contains_whole_expression,
    normalize_text,
)


KEYWORD_SYNONYMS = {
    "dashboard": [
        "dashboard",
        "tableau de bord",
        "tableaux de bord",
    ],
    "streamlit": [
        "streamlit",
    ],
    "power bi": [
        "power bi",
        "powerbi",
    ],
    "sql": [
        "sql",
    ],
    "etl": [
        "etl",
    ],
    "nlp": [
        "nlp",
        "traitement du langage",
        "traitement de texte",
    ],
    "machine learning": [
        "machine learning",
        "apprentissage automatique",
        "intelligence artificielle",
        "ia",
    ],
    "geospatial": [
        "geospatial",
        "géospatial",
        "cartographie",
        "sig",
        "qgis",
        "arcgis",
    ],
    "automatisation": [
        "automatisation",
        "automatisée",
        "automatisées",
        "automatisé",
    ],
}


def keyword_bonus(
    tags: list[str],
    target_text: str,
) -> float:
    normalized_target = normalize_text(
        target_text
    )

    bonus = 0.0

    for tag in tags:
        normalized_tag = normalize_text(tag)

        synonyms = KEYWORD_SYNONYMS.get(
            normalized_tag,
            [normalized_tag],
        )

        found = any(
            contains_whole_expression(
                expression=synonym,
                normalized_text=normalized_target,
            )
            for synonym in synonyms
        )

        if found:
            bonus += 2.0

    return min(
        bonus,
        6.0,
    )