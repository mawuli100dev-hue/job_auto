# job_automation/src/letter/advanced_level.py

"""
Offres destinées à des étudiants de master (M1/M2) ou d'école d'ingénieurs,
alors que le candidat termine sa 3e année de BUT.

Pour ces offres, la lettre doit contenir la phrase de
advanced_level_sentence() : le candidat reconnaît l'écart de niveau et
affirme qu'il peut prendre le sujet en main. LetterValidator vérifie
qu'elle est présente.
"""

import re
import unicodedata

from domain.models import ApplicationTarget


# Cherchés dans le niveau de diplôme, l'intitulé, les compétences et la
# description (texte en minuscules, sans accents).
ADVANCED_LEVEL_PATTERNS = (
    r"bac\s*\+\s*[45]\b",
    r"bac\s*\+\s*4\s*/\s*5",
    r"niveau\s*7\b",
    r"\bm1\b",
    r"\bm2\b",
    r"\bmaster\s*(1|2|i|ii)?\b(?!\s*data)",
    r"ecoles?\s+d\s*'?\s*ingenieurs?",
    r"grandes?\s+ecoles?",
    r"eleves?\s+ingenieurs?",
    r"cycle\s+ingenieur",
    r"stage\s+de\s+fin\s+d\s*'?\s*etudes?",
    r"\bfin\s+d\s*'?\s*etudes?\b",
    r"\bpfe\b",
    r"postgraduate",
    r"engineering\s+school",
    r"master'?s\s+(degree|student)",
)

# « Scrum Master », « Master Data » : ce ne sont pas des diplômes.
FALSE_POSITIVE_PATTERNS = (
    r"scrum\s+master",
    r"master\s+data",
    r"data\s+master",
    r"master\s+class",
)


# L'offre accepte explicitement un Bac+2 ou Bac+3 (« Bac+3 à Bac+5 »,
# « Niveau 6 – Bac+3 ou 4 ») : le candidat a le niveau, pas de phrase.
ACCEPTS_BUT_LEVEL_PATTERNS = (
    r"bac\s*\+\s*[23]\b",
    r"niveau\s*6\b",
)


def _normalize(text: object) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    value = "".join(char for char in value if not unicodedata.combining(char))

    return value.replace("’", "'")


def targets_advanced_students(target: ApplicationTarget) -> bool:
    text = _normalize(
        " ".join(
            [
                target.education_level,
                target.job_title,
                target.requested_skills,
                target.description,
            ]
        )
    )

    for pattern in FALSE_POSITIVE_PATTERNS:
        text = re.sub(pattern, " ", text)

    if any(re.search(pattern, text) for pattern in ACCEPTS_BUT_LEVEL_PATTERNS):
        return False

    return any(re.search(pattern, text) for pattern in ADVANCED_LEVEL_PATTERNS)


def advanced_level_sentence(contract_type: str) -> str:
    contract = "cette alternance" if contract_type == "alternance" else "ce stage"

    return (
        f"Je suis conscient que {contract} s'adresse à des étudiants de M1/M2 "
        "ou d'écoles d'ingénieurs, alors que je termine ma 3e année de BUT "
        "Science des Données. Je me sens cependant capable de prendre en main "
        "ce sujet, et mon parcours me permet de l'affirmer."
    )


def needs_advanced_level_sentence(
    target: ApplicationTarget,
    availability_frame: str,
) -> bool:
    """
    Vrai si la lettre doit contenir la phrase. Une alternance qui commence
    avec le master (cadre « master ») n'est pas concernée : le candidat sera
    alors lui-même en master.
    """

    if target.contract_type == "alternance" and "master" in availability_frame.lower():
        return False

    return targets_advanced_students(target)
