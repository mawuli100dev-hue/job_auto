# job_automation/src/job_automation/config/letter_profile.py

from dataclasses import dataclass

from config.candidate_profile import (
    CANDIDATE_PROFILE,
)


@dataclass(frozen=True)
class LetterProfile:
    full_name: str
    address_lines: tuple[str, ...]
    phone: str
    email: str
    portfolio: str
    github: str
    city: str
    formation: str

    # Ce qui précède le BUT : utile pour expliquer la reconversion
    # et les réflexes du candidat (documentation, collaboration).
    previous_background: str = ""

    # Personne que la lettre peut citer comme témoin du travail
    # du candidat. Laisser vide pour ne jamais la mentionner.
    referee: str = ""

    # Facultatif : laissé vide, il n'est jamais mentionné dans
    # la lettre (le LLM ne doit pas l'inventer).
    # Exemple : "3 semaines en entreprise / 1 semaine à l'IUT".
    # La disponibilité, elle, est calculée par domain.availability.
    alternance_rhythm: str = ""


# Les coordonnées viennent de CANDIDATE_PROFILE pour qu'une
# modification soit faite à un seul endroit (CV et lettre).
LETTER_PROFILE = LetterProfile(
    full_name=CANDIDATE_PROFILE.name,

    address_lines=(
        CANDIDATE_PROFILE.location,
    ),

    phone=CANDIDATE_PROFILE.phone,

    email=CANDIDATE_PROFILE.email,

    portfolio=CANDIDATE_PROFILE.portfolio,

    github=CANDIDATE_PROFILE.github,

    # Ville utilisée dans « Carcassonne, le 4 octobre 2026 ».
    city=CANDIDATE_PROFILE.location.split(",")[0].strip(),

    formation=(
        "Étudiant en troisième année de BUT "
        "Science des Données, parcours Exploration "
        "et Modélisation Statistique, IUT de Perpignan "
        "(antenne de Carcassonne)"
    ),

    previous_background=(
        "Licence Professionnelle en Ingénierie Logicielle "
        "(niveau 3e année), École Polytechnique de Lomé, Togo : "
        "reconversion de l'ingénierie logicielle vers la "
        "science des données"
    ),

    referee=(
        "M. Sébastien Pinel, enseignant-chercheur, qui a encadré "
        "les projets du candidat au CEFREM"
    ),
)
