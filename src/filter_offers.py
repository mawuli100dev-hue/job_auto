"""
filter_offers.py

Filtre un CSV d'offres collectées par collect_offers.py.

Types de candidatures pris en charge :
- alternance ;
- stage ;
- tous.

Le script privilégie les données structurées :
- type_candidature ;
- nature_contrat ;
- type_contrat ;
- intitule.

La description est utilisée seulement comme dernier recours.

Les résultats sont enregistrés dans le dossier de la source du CSV
d'entrée (déduite de son emplacement, sinon de la colonne « source ») :

data/<source>/2_filtrees/<type>/YYYY-MM-DD/

Exemples
--------

Alternances :

python src\\filter_offers.py ^
    --type-candidature alternance ^
    --input "data\\offres\\alternance\\2026-10-01\\offres.csv" ^
    --exclude-entreprises "ISCOD,OPENCLASSROOMS,Tetranergy Business School Rodez"

Stages :

python src\\filter_offers.py ^
    --type-candidature stage ^
    --input "data\\offres\\stage\\2026-10-01\\offres.csv" ^
    --exclude-entreprises "ISCOD,OPENCLASSROOMS,Tetranergy Business School Rodez"

Conserver tous les types de candidatures :

python src\\filter_offers.py ^
    --type-candidature tous ^
    --input "data\\offres\\tous\\2026-10-01\\offres.csv"
"""

import argparse
import csv
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from offers.fingerprint import (
    existing_applications,
    find_duplicate_application,
    location_words,
    offer_fingerprint,
)
from paths import (
    STAGE_FILTERED,
    source_from_path,
    source_from_value,
    source_stage_dir,
)
from domain.availability import (
    STAGE_WINDOW,
    detect_start_date,
    month_label,
    parse_start_field,
)


# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Types de candidatures
# ---------------------------------------------------------------------------

TYPE_CANDIDATURE_ALTERNANCE = "alternance"
TYPE_CANDIDATURE_STAGE = "stage"
TYPE_CANDIDATURE_TOUS = "tous"

TYPES_CANDIDATURE = (
    TYPE_CANDIDATURE_ALTERNANCE,
    TYPE_CANDIDATURE_STAGE,
    TYPE_CANDIDATURE_TOUS,
)


# ---------------------------------------------------------------------------
# Règles de détection de l'alternance
# ---------------------------------------------------------------------------

# Codes natureContrat de France Travail : E2 = apprentissage,
# FS = professionnalisation. E1 est un contrat de travail
# classique (CDI, CDD, intérim) et ne doit pas en faire partie.
ALTERNANCE_NATURE_CODES = {
    "e2",
    "fs",
}

ALTERNANCE_STRUCTURED_VALUES = {
    "apprentissage",
    "contrat apprentissage",
    "contrat d apprentissage",
    "professionnalisation",
    "contrat de professionnalisation",
    "alternance",
}

ALTERNANCE_TITLE_PATTERNS = (
    r"\balternan\w*\b",
    r"\balternance\b",
    r"\bapprenti\w*\b",
    r"\bapprentissage\b",
)

ALTERNANCE_DESCRIPTION_PATTERNS = (
    r"\bcontrat d.?apprentissage\b",
    r"\bcontrat de professionnalisation\b",
    r"\bposte en alternance\b",
    r"\brecrutons?.{0,30}\balternan\w*\b",
    r"\brecherch\w*.{0,30}\balternan\w*\b",
    r"\bcette offre est.{0,20}\balternance\b",
    r"\brythme d.?alternance\b",
)


# ---------------------------------------------------------------------------
# Règles de détection des stages
# ---------------------------------------------------------------------------

STAGE_STRUCTURED_VALUES = {
    "stage",
    "stagiaire",
    "internship",
    "intern",
}

STAGE_TITLE_PATTERNS = (
    r"\bstage\b",
    r"\bstagiaire\w*\b",
    r"\binternship\b",
    r"\bintern\b",
)

STAGE_DESCRIPTION_PATTERNS = (
    r"\bconvention de stage\b",
    r"\bstage conventionne\b",
    r"\bduree du stage\b",
    r"\bperiode de stage\b",
    r"\boffre de stage\b",
    r"\brecherch\w*.{0,30}\bstagiaire\w*\b",
    r"\brecrutons?.{0,30}\bstagiaire\w*\b",
    r"\ben tant que stagiaire\b",
    r"\binternship\b",
)


# ---------------------------------------------------------------------------
# Contrats incompatibles
# ---------------------------------------------------------------------------

ALTERNANCE_EXCLUDED_CONTRACTS = {
    "cdi",
    "interim",
    "mission interim",
    "saisonnier",
}

STAGE_EXCLUDED_CONTRACTS = {
    "cdi",
    "interim",
    "mission interim",
    "saisonnier",
    "apprentissage",
    "professionnalisation",
}


# ---------------------------------------------------------------------------
# Entreprises exclues par défaut
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDED_ENTREPRISES = [
    "ISCOD",
]


# ---------------------------------------------------------------------------
# Normalisation du texte
# ---------------------------------------------------------------------------

def normalize(text: object) -> str:
    """
    Normalise une valeur pour faciliter les comparaisons :

    - conversion en chaîne ;
    - suppression des accents ;
    - passage en minuscules ;
    - remplacement de la ponctuation par des espaces ;
    - suppression des espaces multiples.
    """

    if text is None:
        return ""

    text = str(text).strip()

    if not text:
        return ""

    normalized_text = unicodedata.normalize(
        "NFKD",
        text,
    )

    without_accents = "".join(
        character
        for character in normalized_text
        if not unicodedata.combining(character)
    )

    without_punctuation = re.sub(
        r"[^a-zA-Z0-9]+",
        " ",
        without_accents,
    )

    return re.sub(
        r"\s+",
        " ",
        without_punctuation,
    ).strip().lower()


# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

def contains_pattern(
    text: str,
    patterns: tuple[str, ...],
) -> bool:
    """
    Retourne True si au moins une expression régulière correspond.
    """

    return any(
        re.search(pattern, text)
        for pattern in patterns
    )


def contains_structured_value(
    text: str,
    accepted_values: set[str],
) -> bool:
    """
    Vérifie si une valeur structurée correspond à l'une
    des valeurs reconnues.

    La vérification accepte :
    - une égalité exacte ;
    - une valeur présente dans une liste séparée par des virgules ;
    - une expression contenue dans une valeur plus longue.
    """

    normalized_text = normalize(text)

    if not normalized_text:
        return False

    if normalized_text in accepted_values:
        return True

    return any(
        accepted_value in normalized_text
        for accepted_value in accepted_values
        if len(accepted_value) > 2
    )


def contract_is_excluded(
    contract_value: str,
    excluded_contracts: set[str],
) -> bool:
    """
    Vérifie si le contrat est explicitement incompatible.

    Une égalité ou une expression complète est privilégiée afin
    d'éviter les exclusions accidentelles.
    """

    normalized_contract = normalize(contract_value)

    if not normalized_contract:
        return False

    return any(
        normalized_contract == excluded
        or normalized_contract.startswith(f"{excluded} ")
        or normalized_contract.endswith(f" {excluded}")
        for excluded in excluded_contracts
    )


# ---------------------------------------------------------------------------
# Détection de l'alternance
# ---------------------------------------------------------------------------

def is_alternance(row: dict) -> bool:
    """
    Détermine si une offre correspond à une alternance.
    """

    declared_type = normalize(
        row.get("type_candidature", "")
    )

    type_contrat = normalize(
        row.get("type_contrat", "")
    )

    nature_contrat = normalize(
        row.get("nature_contrat", "")
    )

    intitule = normalize(
        row.get("intitule", "")
    )

    description = normalize(
        row.get("description", "")
    )

    # type_candidature indique ce que le collecteur a CHERCHÉ,
    # pas la nature réelle de l'offre : il ne suffit pas à
    # accepter une offre, seulement à écarter un stage.
    if declared_type == TYPE_CANDIDATURE_STAGE:
        return False

    # La nature du contrat, quand France Travail la fournit,
    # est le signal le plus fiable.
    if nature_contrat in ALTERNANCE_NATURE_CODES:
        return True

    if contains_structured_value(
        nature_contrat,
        ALTERNANCE_STRUCTURED_VALUES,
    ):
        return True

    # Nature renseignée mais différente (« Contrat travail ») :
    # c'est un emploi classique, sauf si l'intitulé annonce
    # explicitement une alternance.
    if nature_contrat:
        return contains_pattern(
            intitule,
            ALTERNANCE_TITLE_PATTERNS,
        )

    if contains_structured_value(
        type_contrat,
        ALTERNANCE_STRUCTURED_VALUES,
    ):
        return True

    if contains_pattern(
        intitule,
        ALTERNANCE_TITLE_PATTERNS,
    ):
        return True

    # Un CDI clairement annoncé sans autre indication
    # d'alternance doit être écarté.
    if contract_is_excluded(
        type_contrat,
        ALTERNANCE_EXCLUDED_CONTRACTS,
    ):
        return False

    return contains_pattern(
        description,
        ALTERNANCE_DESCRIPTION_PATTERNS,
    )


# ---------------------------------------------------------------------------
# Détection des stages
# ---------------------------------------------------------------------------

def is_stage(row: dict) -> bool:
    """
    Détermine si une offre correspond à un stage.
    """

    declared_type = normalize(
        row.get("type_candidature", "")
    )

    type_contrat = normalize(
        row.get("type_contrat", "")
    )

    nature_contrat = normalize(
        row.get("nature_contrat", "")
    )

    intitule = normalize(
        row.get("intitule", "")
    )

    description = normalize(
        row.get("description", "")
    )

    # La colonne renseignée par le collecteur est prioritaire.
    if declared_type == TYPE_CANDIDATURE_STAGE:
        return True

    if declared_type == TYPE_CANDIDATURE_ALTERNANCE:
        return False

    if contains_structured_value(
        nature_contrat,
        STAGE_STRUCTURED_VALUES,
    ):
        return True

    if contains_structured_value(
        type_contrat,
        STAGE_STRUCTURED_VALUES,
    ):
        return True

    if contains_pattern(
        intitule,
        STAGE_TITLE_PATTERNS,
    ):
        return True

    # Si aucun signal de stage n'a été détecté et que le contrat
    # est explicitement incompatible, l'offre est écartée.
    if contract_is_excluded(
        type_contrat,
        STAGE_EXCLUDED_CONTRACTS,
    ):
        return False

    return contains_pattern(
        description,
        STAGE_DESCRIPTION_PATTERNS,
    )


# ---------------------------------------------------------------------------
# Sélection selon le type demandé
# ---------------------------------------------------------------------------

def matches_candidature_type(
    row: dict,
    candidature_type: str,
) -> bool:
    """
    Retourne True si la ligne correspond au type demandé.
    """

    if candidature_type == TYPE_CANDIDATURE_ALTERNANCE:
        return is_alternance(row)

    if candidature_type == TYPE_CANDIDATURE_STAGE:
        return is_stage(row)

    if candidature_type == TYPE_CANDIDATURE_TOUS:
        return True

    raise ValueError(
        f"Type de candidature inconnu : {candidature_type}"
    )


# ---------------------------------------------------------------------------
# Exclusion des entreprises
# ---------------------------------------------------------------------------

def is_excluded_entreprise(
    row: dict,
    excluded_names: list[str],
) -> bool:
    """
    Vérifie si une entreprise fait partie des exclusions.

    Le contrôle est insensible à la casse et aux accents.
    """

    entreprise = normalize(
        row.get("entreprise", "")
    )

    if not entreprise:
        return False

    return any(
        normalize(excluded_name) in entreprise
        for excluded_name in excluded_names
        if normalize(excluded_name)
    )


# ---------------------------------------------------------------------------
# Exclusion par intitulé (métiers hors data)
# ---------------------------------------------------------------------------

# Toujours écartés : métiers commerciaux ou comptables, même s'ils
# citent la data ou l'IA (« Business Developer Data & IA »).
ALWAYS_EXCLUDED_TITLE_TERMS = (
    "business developer",
    "business developpeur",
    "business development",
    "comptable",
    # Postes salariés ou expérimentés, pas des contrats étudiants.
    "cdi",
    "cdd",
    "interim",
    "senior",
    "confirme",
    "confirmee",
    "experimente",
    "experimentee",
    # Métiers du droit (« Appui juridique ... des données »).
    "juridique",
    "juriste",
)

# Métiers de développement ou d'informatique précis : écartés sauf si
# l'intitulé contient aussi un vrai terme data.
DEV_TITLE_TERMS = (
    # Métiers commerciaux : gardés seulement avec un terme data
    # (« Data Analyst – Commercial Data Performance »).
    "commercial",
    "commerciale",
    "commerciales",
    "sales",
    "web",
    "full stack",
    "fullstack",
    "front",
    "frontend",
    "front end",
    "backend",
    "back end",
    "php",
    "java",
    "javascript",
    "symfony",
    "react",
    "angular",
    "net",
    "mobile",
    "android",
    "ios",
    "embarque",
    "embarques",
    "logiciel",
    "logiciels",
    "software",
    "devops",
    "programmeur",
    "integrateur",
    "support",
    "administrateur systeme",
    "administrateur systemes",
    "administrateur reseau",
    "administrateur reseaux",
    "technicien informatique",
    "technicienne informatique",
    # « Technicien(ne) » devient « technicien ne » une fois normalisé.
    "technicien ne informatique",
)

# Le mot « développeur » seul : écarté sauf si l'intitulé contient
# un terme data ou IA (« Développeur IA » reste).
GENERIC_DEV_TITLE_TERMS = (
    "developpeur",
    "developpeuse",
    "developpeurs",
    "developpement",
    "developper",
    "developer",
    "developers",
    "dev",
)

DATA_TITLE_TERMS = (
    "data",
    "donnee",
    "donnees",
    "machine learning",
    "deep learning",
    "business intelligence",
    "bi",
    "power bi",
    "analytics",
    "statistique",
    "statistiques",
    "statisticien",
    "statisticienne",
    "geomatique",
    "sig",
    "teledetection",
    "computer vision",
    "vision par ordinateur",
)

AI_TITLE_TERMS = (
    "ia",
    "ai",
    "intelligence artificielle",
)


def contains_term(
    normalized_text: str,
    terms: tuple[str, ...],
) -> bool:
    """
    Vrai si un terme apparaît comme mot ou groupe de mots entier.
    """

    padded_text = f" {normalized_text} "

    return any(
        f" {term} " in padded_text
        for term in terms
    )


def is_excluded_title(
    row: dict,
    extra_terms: tuple[str, ...] = (),
) -> bool:
    """
    Écarte les offres de développement web ou logiciel, de support
    informatique ou de commerce, qui ne relèvent pas de la data.
    """

    title = normalize(
        row.get("intitule", "")
    )

    if not title:
        return False

    if contains_term(title, ALWAYS_EXCLUDED_TITLE_TERMS):
        return True

    has_data_term = contains_term(title, DATA_TITLE_TERMS)

    if contains_term(title, DEV_TITLE_TERMS + extra_terms):
        return not has_data_term

    if contains_term(title, GENERIC_DEV_TITLE_TERMS):
        return not (
            has_data_term
            or contains_term(title, AI_TITLE_TERMS)
        )

    return False


# ---------------------------------------------------------------------------
# Pertinence data (liste blanche)
# ---------------------------------------------------------------------------

# Un intitulé qui contient l'un de ces termes suffit.
RELEVANT_TITLE_TERMS = DATA_TITLE_TERMS + AI_TITLE_TERMS + (
    "analyst",
    "analyste",
    "analystes",
)

# Sinon, la description doit citer au moins
# MIN_RELEVANT_DESCRIPTION_GROUPS groupes différents. « Données »,
# « tableaux de bord » ou « analyse des données » ne comptent pas :
# on les trouve aussi dans des postes de finance ou de gestion.
RELEVANT_DESCRIPTION_GROUPS = (
    ("python", "pandas", "jupyter"),
    ("sql", "postgresql", "mysql"),
    ("power bi", "bi", "business intelligence", "dataviz", "tableau software", "qlik"),
    ("machine learning", "deep learning", "apprentissage automatique", "intelligence artificielle"),
    ("statistique", "statistiques", "econometrie", "modelisation statistique"),
    ("etl", "data engineering", "pipeline de donnees", "big data"),
    ("data science", "data scientist", "data analyst", "data analyse"),
    ("langage r", "rstudio", "sas"),
)

MIN_RELEVANT_DESCRIPTION_GROUPS = 2

# Domaines officiels PASS (colonne « domaine ») proches de la data.
# Un poste d'un autre domaine (« Ressources humaines », « Droit »...)
# n'est gardé que si son intitulé parle de data : quelques tableaux
# Power BI dans la description ne suffisent pas.
DATA_DOMAIN_TERMS = (
    "big data",
    "statistiques",
    "systemes d information",
    "intelligence artificielle",
    "numerique",
    "etudes",
)


def is_data_relevant(
    row: dict,
) -> bool:
    """
    Garde une offre si elle parle de data : par son intitulé, ou par
    au moins deux outils ou méthodes data dans sa description.
    """

    title = normalize(
        row.get("intitule", "")
    )

    if contains_term(title, RELEVANT_TITLE_TERMS):
        return True

    domain = normalize(
        row.get("domaine", "")
    )

    if domain and not contains_term(domain, DATA_DOMAIN_TERMS):
        return False

    description = normalize(
        row.get("description", "")
    )

    matched_groups = sum(
        contains_term(description, group)
        for group in RELEVANT_DESCRIPTION_GROUPS
    )

    return matched_groups >= MIN_RELEVANT_DESCRIPTION_GROUPS


# ---------------------------------------------------------------------------
# Exclusion des employeurs de la défense
# ---------------------------------------------------------------------------

# Ces employeurs demandent une habilitation ou une enquête de sécurité,
# en pratique hors de portée d'un étudiant de nationalité hors UE.
DEFENSE_EMPLOYER_TERMS = (
    "ministere des armees",
    # « DGA » seul est ambigu (« DGA/DRH » des Affaires étrangères) :
    # les offres de la DGA sont reconnues par « Ministère des Armées ».
    "direction generale de l armement",
    "drsd",
    "direction du renseignement et de la securite de la defense",
    "drm",
    "direction du renseignement militaire",
    "dgse",
    "direction generale de la securite exterieure",
    "armee de terre",
    "armee de l air",
    "armee de l air et de l espace",
    "marine nationale",
    "service de sante des armees",
)

# Préfixe des intitulés de l'Armée de l'Air et de l'Espace sur PASS
# (« AAE- Data scientist »).
DEFENSE_TITLE_PREFIXES = (
    "aae",
)


def is_defense_employer(
    row: dict,
) -> bool:
    """
    Regarde l'entreprise, l'intitulé et la ligne « Employeur : »
    que collect_offers_pass.py place dans la description.
    """

    employer_line = ""

    for line in str(row.get("description", "")).splitlines():
        if line.startswith("Employeur :"):
            employer_line = line
            break

    employer_text = normalize(
        f"{row.get('entreprise', '')} {employer_line}"
    )

    if contains_term(employer_text, DEFENSE_EMPLOYER_TERMS):
        return True

    title_words = normalize(
        row.get("intitule", "")
    ).split()

    return bool(title_words) and title_words[0] in DEFENSE_TITLE_PREFIXES


# ---------------------------------------------------------------------------
# Offres réservées à un public auquel le candidat n'appartient pas
# ---------------------------------------------------------------------------

# Cherchées dans l'intitulé et la description (texte normalisé :
# sans accents, apostrophes remplacées par des espaces).
RESERVED_OFFER_TERMS = (
    # Publics réservés
    "reserve aux eleves",
    "reservee aux eleves",
    "reserve aux eleves fonctionnaires",
    "eleves fonctionnaires",
    "reserve aux fonctionnaires",
    "reservee aux fonctionnaires",
    "reserve aux agents",
    "reservee aux agents",
    "reserve aux titulaires",
    "reservee aux titulaires",
    "reserve aux militaires",
    "reservee aux militaires",
    # Nationalité exigée
    "nationalite francaise exigee",
    "nationalite francaise obligatoire",
    "etre de nationalite francaise",
    "etre ressortissant francais",
    "de nationalite francaise uniquement",
    "ressortissant de l union europeenne",
    "ressortissants de l union europeenne",
    "nationalite d un pays de l union europeenne",
    "nationalite europeenne",
)


def reserved_offer_reason(
    row: dict,
) -> str:
    """
    Expression qui réserve l'offre à un autre public, ou "".
    """

    text = normalize(
        f"{row.get('intitule', '')} {row.get('description', '')}"
    )

    padded_text = f" {text} "

    for term in RESERVED_OFFER_TERMS:
        if f" {term} " in padded_text:
            return term

    return ""


# ---------------------------------------------------------------------------
# Stages qui commencent trop tôt
# ---------------------------------------------------------------------------

def early_stage_start(
    row: dict,
) -> tuple[int, int] | None:
    """
    Date de début d'un stage qui commence avant la période de stage
    du candidat (STAGE_WINDOW, dans domain/availability.py), ou None.

    Même lecture de la date que pour le CV : colonne date_debut,
    puis description. Une offre sans date est gardée.
    """

    start = (
        parse_start_field(str(row.get("date_debut", "")))
        or detect_start_date(str(row.get("description", "")))
    )

    if start is not None and start < STAGE_WINDOW[0]:
        return start

    return None


# ---------------------------------------------------------------------------
# Lecture et filtrage
# ---------------------------------------------------------------------------

def filter_csv(
    input_path: Path,
    candidature_type: str,
    excluded_entreprises: list[str],
    exclude_titles: bool = True,
    extra_title_terms: tuple[str, ...] = (),
    exclude_defense: bool = True,
    exclude_reserved: bool = True,
    exclude_early_stages: bool = True,
    require_data_relevance: bool = True,
    remove_duplicates: bool = True,
) -> tuple[list[dict], list[str], dict]:
    """
    Lit le CSV et applique les filtres.

    Retourne :
    - les lignes conservées ;
    - les noms des colonnes ;
    - les statistiques du filtrage.
    """

    with input_path.open(
        mode="r",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        fieldnames = reader.fieldnames

        if not fieldnames:
            raise ValueError(
                "Le fichier CSV ne contient pas d'en-tête."
            )

        rows = list(reader)

    required_columns = {
        "id",
        "intitule",
        "entreprise",
    }

    missing_columns = required_columns.difference(
        fieldnames
    )

    if missing_columns:
        missing_columns_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            "Le CSV ne contient pas toutes les colonnes "
            f"obligatoires. Colonnes manquantes : "
            f"{missing_columns_text}"
        )

    matching_rows = [
        row
        for row in rows
        if matches_candidature_type(
            row=row,
            candidature_type=candidature_type,
        )
    ]

    removed_wrong_type = (
        len(rows) - len(matching_rows)
    )

    company_rows = [
        row
        for row in matching_rows
        if not is_excluded_entreprise(
            row=row,
            excluded_names=excluded_entreprises,
        )
    ]

    removed_enterprise = (
        len(matching_rows) - len(company_rows)
    )

    kept_rows = []
    removed_titles = []
    removed_defense = []
    removed_reserved = []
    removed_early = []
    removed_irrelevant = []

    for row in company_rows:
        reserved_reason = (
            reserved_offer_reason(row)
            if exclude_reserved
            else ""
        )

        early_start = (
            early_stage_start(row)
            if (
                exclude_early_stages
                and candidature_type == TYPE_CANDIDATURE_STAGE
            )
            else None
        )

        if early_start:
            removed_early.append(
                f"{row.get('intitule', '')} - {row.get('entreprise', '')} "
                f"(début : {month_label(early_start)})"
            )
        elif reserved_reason:
            removed_reserved.append(
                f"{row.get('intitule', '')} - {row.get('entreprise', '')} "
                f"(« {reserved_reason} »)"
            )
        elif exclude_defense and is_defense_employer(row):
            removed_defense.append(
                f"{row.get('intitule', '')} - {row.get('entreprise', '')}"
            )
        elif exclude_titles and is_excluded_title(
            row=row,
            extra_terms=extra_title_terms,
        ):
            removed_titles.append(
                row.get("intitule", "")
            )
        elif require_data_relevance and not is_data_relevant(row):
            removed_irrelevant.append(
                f"{row.get('intitule', '')} - {row.get('entreprise', '')}"
            )
        else:
            kept_rows.append(row)

    # Même offre deux fois dans le fichier, ou déjà préparée depuis
    # une autre source (même entreprise, même intitulé).
    removed_duplicates = []

    if remove_duplicates:
        applications = existing_applications(BASE_DIR)
        seen_fingerprints = set()
        unique_rows = []

        for row in kept_rows:
            fingerprint = offer_fingerprint(
                row.get("entreprise", ""),
                row.get("intitule", ""),
            )

            label = (
                f"{row.get('intitule', '')} - {row.get('entreprise', '')}"
            )

            # Même intitulé dans deux villes : deux postes différents.
            place_key = (
                fingerprint,
                " ".join(sorted(location_words(row.get("lieu", "")))),
            )

            if fingerprint and place_key in seen_fingerprints:
                removed_duplicates.append(f"{label} (en double dans ce fichier)")
                continue

            duplicate = find_duplicate_application(
                project_root=BASE_DIR,
                company=row.get("entreprise", ""),
                title=row.get("intitule", ""),
                offer_id=str(row.get("id", "")),
                applications=applications,
                location=row.get("lieu", ""),
            )

            if duplicate is not None:
                removed_duplicates.append(
                    f"{label} (déjà préparée : {duplicate.parent.parent.parent.name}"
                    f"/{duplicate.parent.name}/{duplicate.name})"
                )
                continue

            if fingerprint:
                seen_fingerprints.add(place_key)

            unique_rows.append(row)

        kept_rows = unique_rows

    statistics = {
        "total": len(rows),
        "removed_wrong_type": removed_wrong_type,
        "removed_enterprise": removed_enterprise,
        "removed_title": len(removed_titles),
        "removed_titles": removed_titles,
        "removed_defense": removed_defense,
        "removed_reserved": removed_reserved,
        "removed_early": removed_early,
        "removed_irrelevant": removed_irrelevant,
        "removed_duplicates": removed_duplicates,
        "kept": len(kept_rows),
    }

    return kept_rows, fieldnames, statistics


# ---------------------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------------------

def save_filtered(
    kept_rows: list[dict],
    fieldnames: list[str],
    candidature_type: str,
    source: str,
    base_dir: Path | None = None,
) -> str:
    """
    Enregistre les offres filtrées dans le dossier de leur source :

    data/<source>/2_filtrees/<type>/YYYY-MM-DD/
    """

    if base_dir is None:
        base_dir = (
            source_stage_dir(BASE_DIR, source, STAGE_FILTERED)
            / candidature_type
        )

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    output_folder = base_dir / today

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%H%M%S"
    )

    filename = (
        f"offres_filtrees_{candidature_type}_"
        f"{today}_{timestamp}.csv"
    )

    filepath = output_folder / filename

    with filepath.open(
        mode="w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(kept_rows)

    return str(filepath)


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    """
    Construit le parseur d'arguments.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Filtre les offres selon le type de candidature "
            "et les entreprises à exclure."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Chemin du fichier CSV à filtrer.",
    )

    parser.add_argument(
        "--type-candidature",
        choices=TYPES_CANDIDATURE,
        default=TYPE_CANDIDATURE_ALTERNANCE,
        help=(
            "Type d'offres à conserver : "
            "'alternance', 'stage' ou 'tous'. "
            "Défaut : alternance."
        ),
    )

    parser.add_argument(
        "--exclude-entreprises",
        default=",".join(
            DEFAULT_EXCLUDED_ENTREPRISES
        ),
        help=(
            "Entreprises à exclure, séparées par des virgules. "
            "Défaut : ISCOD."
        ),
    )

    parser.add_argument(
        "--exclude-intitules",
        default="",
        help=(
            "Mots supplémentaires qui écartent une offre s'ils sont "
            "dans l'intitulé sans terme data, séparés par des "
            "virgules. Exemple : \"cybersecurite,reseaux\"."
        ),
    )

    parser.add_argument(
        "--garder-doublons",
        action="store_true",
        help=(
            "Garde les offres en double (même entreprise et même "
            "intitulé) dans le fichier ou déjà préparées depuis une "
            "autre source."
        ),
    )

    parser.add_argument(
        "--sans-filtre-data",
        action="store_true",
        help=(
            "Garde aussi les offres qui ne parlent pas de data "
            "(ni dans l'intitulé, ni par au moins deux outils "
            "ou méthodes data dans la description)."
        ),
    )

    parser.add_argument(
        "--garder-stages-precoces",
        action="store_true",
        help=(
            "Garde les stages qui commencent avant la période de "
            "stage du candidat (avant janvier 2027), écartés par défaut."
        ),
    )

    parser.add_argument(
        "--garder-reservees",
        action="store_true",
        help=(
            "Garde les offres réservées à un autre public (élèves "
            "fonctionnaires, agents titulaires...) ou exigeant la "
            "nationalité française ou européenne."
        ),
    )

    parser.add_argument(
        "--garder-defense",
        action="store_true",
        help=(
            "Garde les offres des employeurs de la défense "
            "(Ministère des Armées, DGA, DRSD, DRM...), écartées "
            "par défaut car soumises à habilitation."
        ),
    )

    parser.add_argument(
        "--garder-tous-intitules",
        action="store_true",
        help=(
            "Désactive l'exclusion des métiers hors data "
            "(développeur web, logiciel, support, commercial...)."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()

    if not input_path.is_absolute():
        input_path = Path.cwd() / input_path

    input_path = input_path.resolve()

    if not input_path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {input_path}"
        )

    if not input_path.is_file():
        raise ValueError(
            f"Le chemin n'est pas un fichier : {input_path}"
        )

    excluded_entreprises = [
        entreprise.strip()
        for entreprise in args.exclude_entreprises.split(",")
        if entreprise.strip()
    ]

    print("==============================================")
    print("Filtrage des offres")
    print("==============================================")
    print(f"Fichier : {input_path}")
    print(
        f"Type de candidature : "
        f"{args.type_candidature}"
    )

    if excluded_entreprises:
        print(
            "Entreprises exclues : "
            f"{', '.join(excluded_entreprises)}"
        )
    else:
        print("Entreprises exclues : aucune")

    extra_title_terms = tuple(
        normalize(term)
        for term in args.exclude_intitules.split(",")
        if normalize(term)
    )

    kept_rows, fieldnames, statistics = filter_csv(
        input_path=input_path,
        candidature_type=args.type_candidature,
        excluded_entreprises=excluded_entreprises,
        exclude_titles=not args.garder_tous_intitules,
        extra_title_terms=extra_title_terms,
        exclude_defense=not args.garder_defense,
        exclude_reserved=not args.garder_reservees,
        exclude_early_stages=not args.garder_stages_precoces,
        require_data_relevance=not args.sans_filtre_data,
        remove_duplicates=not args.garder_doublons,
    )

    print("\n=== Résultat ===")
    print(
        f"Total initial                  : "
        f"{statistics['total']} offre(s)"
    )
    print(
        f"Écartées (mauvais type)        : "
        f"{statistics['removed_wrong_type']} offre(s)"
    )
    print(
        f"Écartées (entreprise exclue)   : "
        f"{statistics['removed_enterprise']} offre(s)"
    )
    print(
        f"Écartées (stage trop tôt)      : "
        f"{len(statistics['removed_early'])} offre(s)"
    )
    print(
        f"Écartées (réservées)           : "
        f"{len(statistics['removed_reserved'])} offre(s)"
    )
    print(
        f"Écartées (défense)             : "
        f"{len(statistics['removed_defense'])} offre(s)"
    )
    print(
        f"Écartées (métier hors data)    : "
        f"{statistics['removed_title']} offre(s)"
    )
    print(
        f"Écartées (ne parle pas de data): "
        f"{len(statistics['removed_irrelevant'])} offre(s)"
    )
    print(
        f"Écartées (doublons)            : "
        f"{len(statistics['removed_duplicates'])} offre(s)"
    )
    print(
        f"Conservées                     : "
        f"{statistics['kept']} offre(s)"
    )

    # Listes affichées pour vérifier qu'aucune bonne offre n'est perdue.
    if statistics["removed_early"]:
        print("\nStages écartés (commencent avant ta période de stage) :")

        for offer in statistics["removed_early"]:
            print(f"  - {offer}")

    if statistics["removed_reserved"]:
        print("\nOffres écartées (réservées à un autre public) :")

        for offer in statistics["removed_reserved"]:
            print(f"  - {offer}")

    if statistics["removed_defense"]:
        print("\nOffres écartées (employeur de la défense) :")

        for offer in statistics["removed_defense"]:
            print(f"  - {offer}")

    if statistics["removed_titles"]:
        print("\nIntitulés écartés (métier hors data) :")

        for title in statistics["removed_titles"]:
            print(f"  - {title}")

    if statistics["removed_duplicates"]:
        print("\nOffres écartées (doublons) :")

        for offer in statistics["removed_duplicates"]:
            print(f"  - {offer}")

    if statistics["removed_irrelevant"]:
        print("\nOffres écartées (ne parlent pas de data) :")

        for offer in statistics["removed_irrelevant"]:
            print(f"  - {offer}")

    # Source : dossier du CSV d'entrée (data/<source>/1_brutes/...),
    # sinon colonne « source » des offres.
    source = source_from_path(BASE_DIR, input_path)

    if source is None:
        with input_path.open(encoding="utf-8-sig", newline="") as csv_file:
            first_row = next(csv.DictReader(csv_file), {}) or {}

        source = source_from_value(first_row.get("source", ""))

    print(f"Source : {source}")

    filepath = save_filtered(
        kept_rows=kept_rows,
        fieldnames=fieldnames,
        candidature_type=args.type_candidature,
        source=source,
    )

    print(
        f"\nFichier filtré enregistré : "
        f"{filepath}"
    )


if __name__ == "__main__":
    main()