# src/domain/availability.py

"""
Disponibilité affichée sur le CV et dans la lettre.

Alternance : deux fenêtres possibles.
- Année de BUT en cours : on peut encore signer une alternance
  qui commence avant BUT_ALTERNANCE_DEADLINE.
  -> « Disponible immédiatement ».
- Master : alternance qui commence à MASTER_START ou après.
  -> « Disponible dès août 2027 », la lettre précise que
  l'alternance accompagnera la poursuite d'études en master.
Entre les deux, aucune formation ne couvre le contrat : un
avertissement est affiché (jamais au recruteur).

La plupart des offres ne donnent pas de date de début : la
fenêtre est alors choisie d'après la date du jour.

Stage : le stage de BUT se place dans STAGE_WINDOW. La date
préférée du candidat (mars) n'est jamais écrite, pour ne pas
fermer la porte à une offre qui commence plus tôt.
- Date de l'offre dans la fenêtre -> « Disponible dès <date> ».
- Pas de date -> STAGE_DEFAULT_LABEL.
- Date hors fenêtre -> STAGE_DEFAULT_LABEL et un avertissement.

La date de début est lue d'abord dans la colonne dédiée du CSV
(target.start_date), puis dans la description.
"""

import re
from dataclasses import dataclass
from datetime import date

from common.text_normalizer import normalize_text
from domain.models import ApplicationTarget


# (année, mois) : à partir de ce mois, une alternance ne peut
# plus commencer pendant l'année de BUT en cours.
BUT_ALTERNANCE_DEADLINE = (2027, 1)

# (année, mois) : début le plus tôt possible de l'alternance de
# master. Août plutôt que septembre : certains masters commencent
# plus tôt, et « dès août » n'exclut pas une offre de septembre.
MASTER_START = (2027, 8)

# (année, mois) : premier et dernier mois de début acceptables
# pour le stage de BUT.
STAGE_WINDOW = ((2027, 1), (2027, 6))

STAGE_DEFAULT_LABEL = "Disponible au premier semestre 2027"

NORMALIZED_MONTHS = [
    "janvier",
    "fevrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "aout",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
]

DISPLAY_MONTHS = [
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
]

# Expressions qui introduisent une date de début.
START_PREFIX = (
    r"(?:a partir (?:de|du|d')|des|debut|demarrage|date de debut|"
    r"date de demarrage(?: souhaitee)?|"
    r"date de prise de poste(?: souhaitee)?|prise de poste|"
    r"a pourvoir|poste a pourvoir)"
    r"\s*:?\s*(?:le\s+|en\s+|du\s+|des\s+(?:le\s+)?)?"
)


@dataclass(frozen=True)
class Availability:
    # Texte prêt à afficher, ex. « Disponible immédiatement ».
    label: str

    # Pour la lettre : dans quel cadre se fera l'alternance.
    frame: str = ""

    # Avertissement pour le candidat (jamais affiché au recruteur).
    warning: str = ""


def month_label(year_month: tuple[int, int]) -> str:
    year, month = year_month
    return f"{DISPLAY_MONTHS[month - 1]} {year}"


def detect_start_date(
    description: str,
) -> tuple[int, int] | None:
    """
    Cherche la date de début annoncée dans l'offre.
    Renvoie (année, mois) ou None.
    """

    text = normalize_text(description)

    month_pattern = "|".join(NORMALIZED_MONTHS)

    # « à partir de septembre 2027 », « démarrage : 1er mars 2027 »
    match = re.search(
        START_PREFIX
        + r"(?:\d{1,2}(?:er)?\s+)?"
        + rf"({month_pattern})\s+(\d{{4}})",
        text,
    )

    if match:
        return (
            int(match.group(2)),
            NORMALIZED_MONTHS.index(match.group(1)) + 1,
        )

    # « date de démarrage souhaitée : 01/09/2026 »
    match = re.search(
        START_PREFIX
        + r"\d{1,2}[/.-](\d{1,2})[/.-](\d{4})",
        text,
    )

    if match and 1 <= int(match.group(1)) <= 12:
        return (
            int(match.group(2)),
            int(match.group(1)),
        )

    # « rentrée 2027 », « rentrée de septembre 2027 »
    match = re.search(
        r"rentree\s+(?:de\s+)?(?:septembre\s+)?(\d{4})",
        text,
    )

    if match:
        return (
            int(match.group(1)),
            9,
        )

    return None


def parse_start_field(
    value: str,
) -> tuple[int, int] | None:
    """
    Date d'une colonne dédiée : « Janvier 2027 », « 2027-01-15 »,
    « 2027-01-15T00:00:00Z », « 15/01/2027 » ou « 01/2027 ».
    """

    text = normalize_text(value)

    if not text:
        return None

    month_pattern = "|".join(NORMALIZED_MONTHS)

    match = re.search(rf"({month_pattern})\s+(\d{{4}})", text)

    if match:
        return (
            int(match.group(2)),
            NORMALIZED_MONTHS.index(match.group(1)) + 1,
        )

    # Formats numériques, lus sur le texte brut.
    raw = value.strip()

    # « 2027-01-15 », « 2027-01-15T00:00:00Z »
    match = re.match(r"(\d{4})[-/.](\d{1,2})\b", raw)

    if match and 1 <= int(match.group(2)) <= 12:
        return (int(match.group(1)), int(match.group(2)))

    # « 15/01/2027 », « 01/2027 »
    match = re.search(r"(?:\b\d{1,2}[-/.])?(\d{1,2})[-/.](\d{4})\b", raw)

    if match and 1 <= int(match.group(1)) <= 12:
        return (int(match.group(2)), int(match.group(1)))

    return None


def resolve_availability(
    target: ApplicationTarget,
    today: date | None = None,
) -> Availability:
    today = today or date.today()
    now = (today.year, today.month)

    start = (
        parse_start_field(target.start_date)
        or detect_start_date(target.description)
    )

    if target.contract_type == "alternance":
        return _resolve_alternance(
            start=start,
            now=now,
        )

    return _resolve_stage(start=start)


def _resolve_stage(
    start: tuple[int, int] | None,
) -> Availability:
    earliest, latest = STAGE_WINDOW

    if start is None:
        return Availability(label=STAGE_DEFAULT_LABEL)

    if earliest <= start <= latest:
        return Availability(
            label=f"Disponible dès {month_label(start)}"
        )

    return Availability(
        label=STAGE_DEFAULT_LABEL,
        warning=(
            f"Ce stage commence en {month_label(start)}, hors de ta "
            f"période de stage ({month_label(earliest)} - "
            f"{month_label(latest)}). Le CV indique « "
            f"{STAGE_DEFAULT_LABEL} » ; vérifie avec l'employeur "
            "si un démarrage décalé est possible."
        ),
    )


def _resolve_alternance(
    start: tuple[int, int] | None,
    now: tuple[int, int],
) -> Availability:
    but_frame = (
        "Alternance pendant la troisième année de BUT "
        "(année en cours), avec un démarrage immédiat."
    )

    master_frame = (
        "Alternance pour la poursuite d'études en master à la "
        f"rentrée {MASTER_START[0]}, après l'obtention du BUT, avec "
        f"un démarrage possible dès {month_label(MASTER_START)}. "
        "Le master n'est pas encore choisi : ne nomme aucun "
        "établissement ni intitulé de master, ni sa date de rentrée."
    )

    # Sans date dans l'offre, ou avec une date déjà passée,
    # le contrat commencerait maintenant.
    effective_start = max(start or now, now)

    if effective_start < BUT_ALTERNANCE_DEADLINE:
        return Availability(
            label="Disponible immédiatement",
            frame=but_frame,
        )

    if effective_start >= MASTER_START:
        return Availability(
            label=f"Disponible dès {month_label(effective_start)}",
            frame=master_frame,
        )

    # Démarrage entre la date limite du BUT et le master.
    if start is None:
        # Plus aucune alternance de BUT possible : on se
        # positionne sur le master.
        return Availability(
            label=f"Disponible dès {month_label(MASTER_START)}",
            frame=master_frame,
        )

    return Availability(
        label=f"Disponible dès {month_label(MASTER_START)}",
        frame=master_frame,
        warning=(
            f"Cette alternance commence en {month_label(start)} : "
            "trop tard pour l'année de BUT, trop tôt pour le "
            f"master ({month_label(MASTER_START)}). Le CV indique "
            f"« dès {month_label(MASTER_START)} » ; vérifie avec "
            "l'entreprise si un démarrage décalé est possible."
        ),
    )
