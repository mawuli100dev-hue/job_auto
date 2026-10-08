"""
collect_offers.py

Collecte des offres via l'API France Travail.

Types de candidatures pris en charge :
- alternance : apprentissage et contrat de professionnalisation ;
- stage      : recherche par mots-clés + vérification locale ;
- tous       : aucune restriction de nature de contrat.

Les résultats sont enregistrés dans :

data/
└── offres/
    ├── alternance/
    │   └── YYYY-MM-DD/
    ├── stage/
    │   └── YYYY-MM-DD/
    └── tous/
        └── YYYY-MM-DD/

Prérequis
---------
Créer un fichier .env à la racine du projet :

FT_CLIENT_ID=xxxxx
FT_CLIENT_SECRET=xxxxx

Installation :

pip install requests python-dotenv

Exemples
--------

Alternances, en conservant le comportement par défaut :

python src\\collect_offers.py ^
    --keywords-list "data,data analyst,data scientist,data engineer" ^
    --max-anciennete-jours 3

Alternances, en précisant explicitement le type :

python src\\collect_offers.py ^
    --type-candidature alternance ^
    --keywords-list "data,data analyst,data scientist,data engineer" ^
    --max-anciennete-jours 3

Stages :

python src\\collect_offers.py ^
    --type-candidature stage ^
    --keywords-list "data,data analyst,data scientist,data engineer" ^
    --max-anciennete-jours 3

Tous les types de contrats :

python src\\collect_offers.py ^
    --type-candidature tous ^
    --keywords-list "data,data analyst,data scientist,data engineer" ^
    --max-anciennete-jours 3
"""

import argparse
import csv
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Chemins et configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TOKEN_URL = (
    "https://entreprise.francetravail.fr/"
    "connexion/oauth2/access_token?realm=%2Fpartenaire"
)

API_URL = (
    "https://api.francetravail.io/"
    "partenaire/offresdemploi/v2/offres/search"
)

CLIENT_ID = os.getenv("FT_CLIENT_ID")
CLIENT_SECRET = os.getenv("FT_CLIENT_SECRET")


# ---------------------------------------------------------------------------
# Constantes métier
# ---------------------------------------------------------------------------

TYPE_CANDIDATURE_ALTERNANCE = "alternance"
TYPE_CANDIDATURE_STAGE = "stage"
TYPE_CANDIDATURE_TOUS = "tous"

TYPES_CANDIDATURE = (
    TYPE_CANDIDATURE_ALTERNANCE,
    TYPE_CANDIDATURE_STAGE,
    TYPE_CANDIDATURE_TOUS,
)

# Référentiel natureContrat de France Travail :
# E1 : contrat de travail classique (CDI, CDD, intérim) -> à exclure
# E2 : contrat d'apprentissage
# FS : contrat de professionnalisation
NATURES_ALTERNANCE = "E2,FS"

# Libellés natureContrat renvoyés par l'API pour une alternance.
ALTERNANCE_NATURE_LABELS = (
    "apprentissage",
    "professionnalisation",
)

STAGE_PATTERNS = (
    r"\bstage\b",
    r"\bstagiaire\b",
    r"\bstagiaires\b",
    r"\binternship\b",
    r"\bintern\b",
)

FIELDNAMES = [
    "id",
    "source",
    "type_candidature",
    "intitule",
    "entreprise",
    "lieu",
    "type_contrat",
    "nature_contrat",
    "duree_contrat",
    "date_creation",
    "salaire",
    "experience_exigee",
    "competences",
    "description",
    "url",
]

TAILLE_PAGE_MAX = 150
LIMITE_GLOBALE_API = 3000

DELAI_ENTRE_APPELS_SEC = 0.3
DELAI_ENTRE_MOTS_CLES_SEC = 0.5

ANCIENNETE_MAX_JOURS_DEFAUT = 21

SUGGESTION_KEYWORDS_LIST = (
    "data,data analyst,data scientist,data engineer,"
    "business intelligence,machine learning,"
    "intelligence artificielle,IA,AI,statistique,statistic"
)


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

def get_access_token() -> str:
    """
    Récupère un token OAuth2 avec le mécanisme client_credentials.
    """

    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "FT_CLIENT_ID et FT_CLIENT_SECRET doivent être définis "
            "dans le fichier .env situé à la racine du projet."
        )

    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "api_offresdemploiv2 o2dsoffre",
    }

    response = requests.post(
        TOKEN_URL,
        data=data,
        timeout=15,
    )

    if response.status_code != 200:
        print("Échec de l'authentification France Travail.")
        print("Réponse :", response.text[:1000])

    response.raise_for_status()

    response_data = response.json()

    if "access_token" not in response_data:
        raise RuntimeError(
            "La réponse d'authentification ne contient pas d'access_token."
        )

    return response_data["access_token"]


# ---------------------------------------------------------------------------
# Normalisation des offres
# ---------------------------------------------------------------------------

def _normalize_offer(raw_offer: dict) -> dict:
    """
    Transforme une offre brute de l'API en dictionnaire compatible
    avec le fichier CSV de l'application.
    """

    lieu = raw_offer.get("lieuTravail", {}) or {}
    entreprise = raw_offer.get("entreprise", {}) or {}
    salaire = raw_offer.get("salaire", {}) or {}
    origine = raw_offer.get("origineOffre", {}) or {}

    competences = ", ".join(
        competence.get("libelle", "")
        for competence in raw_offer.get("competences", []) or []
        if competence.get("libelle")
    )

    description = (
        raw_offer.get("description", "") or ""
    ).replace("\n", " ").replace("\r", " ").strip()

    entreprise_nom = entreprise.get("nom")

    if not entreprise_nom or not entreprise_nom.strip():
        entreprise_nom = "Non precise"

    return {
        "id": raw_offer.get("id", ""),
        "source": "france_travail",
        "type_candidature": "",
        "intitule": raw_offer.get("intitule", ""),
        "entreprise": entreprise_nom,
        "lieu": lieu.get("libelle", ""),
        "type_contrat": raw_offer.get("typeContratLibelle", ""),
        "nature_contrat": raw_offer.get("natureContrat", ""),
        "duree_contrat": raw_offer.get("dureeTravailLibelle", ""),
        "date_creation": raw_offer.get("dateCreation", ""),
        "salaire": salaire.get("libelle", ""),
        "experience_exigee": raw_offer.get("experienceLibelle", ""),
        "competences": competences,
        "description": description,
        "url": origine.get("urlOrigine", ""),
    }


# ---------------------------------------------------------------------------
# Dates et pagination
# ---------------------------------------------------------------------------

def _parse_total_disponible(headers: dict) -> int | None:
    """
    Extrait le nombre total d'offres depuis l'en-tête Content-Range.
    """

    content_range = headers.get("Content-Range")

    if not content_range or "/" not in content_range:
        return None

    try:
        return int(content_range.rsplit("/", 1)[-1])
    except ValueError:
        return None


def _parse_date_creation(date_string: str) -> datetime | None:
    """
    Convertit une date France Travail en datetime UTC.
    """

    if not date_string:
        return None

    formats_possibles = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ]

    for date_format in formats_possibles:
        try:
            parsed_date = datetime.strptime(
                date_string,
                date_format,
            )

            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(
                    tzinfo=timezone.utc
                )

            return parsed_date

        except ValueError:
            continue

    return None


def _fetch_page(
    token: str,
    params: dict,
    start: int,
    end: int,
) -> tuple[list[dict], int | None, str]:
    """
    Récupère une page d'offres.

    Retourne :
    - les offres brutes ;
    - le nombre total d'offres disponibles ;
    - le token courant, éventuellement renouvelé.
    """

    headers = {
        "Authorization": f"Bearer {token}",
    }

    page_params = dict(params)
    page_params["range"] = f"{start}-{end}"

    response = requests.get(
        API_URL,
        headers=headers,
        params=page_params,
        timeout=30,
    )

    if response.status_code == 401:
        print(
            "Token expiré pendant la pagination : "
            "renouvellement du token..."
        )

        token = get_access_token()

        headers = {
            "Authorization": f"Bearer {token}",
        }

        response = requests.get(
            API_URL,
            headers=headers,
            params=page_params,
            timeout=30,
        )

    if response.status_code == 204:
        return (
            [],
            _parse_total_disponible(response.headers),
            token,
        )

    if response.status_code not in (200, 206):
        print("Erreur retournée par l'API France Travail :")
        print(response.text[:1000])

    response.raise_for_status()

    total_disponible = _parse_total_disponible(
        response.headers
    )

    response_data = response.json()
    raw_offers = response_data.get("resultats", []) or []

    return raw_offers, total_disponible, token


def discover_total(
    token: str,
    params: dict,
) -> tuple[int | None, str]:
    """
    Demande une seule offre afin de connaître le nombre total
    d'offres disponibles.
    """

    _, total_disponible, token = _fetch_page(
        token=token,
        params=params,
        start=0,
        end=0,
    )

    return total_disponible, token


# ---------------------------------------------------------------------------
# Paramètres de recherche
# ---------------------------------------------------------------------------

def _build_base_params(
    keywords: str,
    commune: str | None,
    distance_km: int,
    contract_type: str | None,
    contract_nature: str | None,
    anciennete_max_jours: int,
) -> tuple[dict, datetime | None]:
    """
    Construit les paramètres envoyés à l'API France Travail.
    """

    params = {
        "motsCles": keywords,
        "sort": 1,
    }

    if commune:
        params["commune"] = commune
        params["distance"] = distance_km

    if contract_type:
        params["typeContrat"] = contract_type

    if contract_nature:
        params["natureContrat"] = contract_nature

    seuil_date = None

    if anciennete_max_jours and anciennete_max_jours > 0:
        maintenant = datetime.now(timezone.utc)

        seuil_date = maintenant - timedelta(
            days=anciennete_max_jours
        )

        # L'API demande que les dates minimale et maximale
        # soient fournies ensemble.
        params["minCreationDate"] = seuil_date.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        params["maxCreationDate"] = maintenant.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    return params, seuil_date


def resolve_contract_nature(
    candidature_type: str,
    manual_nature: str | None,
) -> str | None:
    """
    Détermine automatiquement le filtre natureContrat.

    Un --nature fourni manuellement est prioritaire.
    """

    if manual_nature is not None:
        manual_nature = manual_nature.strip()

        if manual_nature:
            return manual_nature

    if candidature_type == TYPE_CANDIDATURE_ALTERNANCE:
        return NATURES_ALTERNANCE

    return None


# ---------------------------------------------------------------------------
# Recherche d'offres
# ---------------------------------------------------------------------------

def search_offers(
    token: str,
    keywords: str = "",
    commune: str | None = None,
    distance_km: int = 30,
    contract_type: str | None = None,
    contract_nature: str | None = None,
    max_results: int | None = None,
    anciennete_max_jours: int = ANCIENNETE_MAX_JOURS_DEFAUT,
) -> tuple[list[dict], int | None, int]:
    """
    Recherche les offres pour un seul mot-clé.

    La fonction :
    - applique les filtres API ;
    - découvre le nombre total d'offres ;
    - pagine automatiquement ;
    - revérifie localement la date de création.
    """

    params, seuil_date = _build_base_params(
        keywords=keywords,
        commune=commune,
        distance_km=distance_km,
        contract_type=contract_type,
        contract_nature=contract_nature,
        anciennete_max_jours=anciennete_max_jours,
    )

    if seuil_date is not None:
        print(
            "Filtre d'ancienneté actif : "
            f"offres depuis le "
            f"{seuil_date.strftime('%d/%m/%Y %H:%M')} "
            f"({anciennete_max_jours} jour(s) maximum)."
        )
    else:
        print("Filtre d'ancienneté désactivé.")

    total_disponible, token = discover_total(
        token=token,
        params=params,
    )

    if max_results is None:
        if total_disponible is None:
            objectif = LIMITE_GLOBALE_API
        else:
            objectif = min(
                total_disponible,
                LIMITE_GLOBALE_API,
            )

            if total_disponible > LIMITE_GLOBALE_API:
                print(
                    f"{total_disponible} offre(s) disponible(s), "
                    f"mais la collecte est plafonnée à "
                    f"{LIMITE_GLOBALE_API}."
                )
    else:
        objectif = max_results

        if total_disponible is not None:
            objectif = min(
                max_results,
                total_disponible,
            )

    print(
        f"{total_disponible if total_disponible is not None else '?'} "
        f"offre(s) disponible(s), objectif : {objectif}."
    )

    if objectif <= 0:
        return [], total_disponible, 0

    all_offers: list[dict] = []
    ecartees_anciennete = 0
    start = 0

    while len(all_offers) < objectif:
        end = min(
            start + TAILLE_PAGE_MAX,
            objectif,
        ) - 1

        raw_offers, page_total, token = _fetch_page(
            token=token,
            params=params,
            start=start,
            end=end,
        )

        if page_total is not None:
            total_disponible = page_total

        if not raw_offers:
            break

        for raw_offer in raw_offers:
            offer = _normalize_offer(raw_offer)

            if seuil_date is not None:
                date_creation = _parse_date_creation(
                    offer["date_creation"]
                )

                if (
                    date_creation is not None
                    and date_creation < seuil_date
                ):
                    ecartees_anciennete += 1
                    continue

            all_offers.append(offer)

            if len(all_offers) >= objectif:
                break

        print(
            f"Page {start}-{end} : "
            f"{len(raw_offers)} reçue(s), "
            f"{len(all_offers)} retenue(s)"
            + (
                f" / {total_disponible} disponible(s)"
                if total_disponible is not None
                else ""
            )
        )

        start += TAILLE_PAGE_MAX

        if (
            total_disponible is not None
            and start >= total_disponible
        ):
            break

        if len(all_offers) < objectif:
            time.sleep(DELAI_ENTRE_APPELS_SEC)

    return (
        all_offers[:objectif],
        total_disponible,
        ecartees_anciennete,
    )


def search_offers_multi_keywords(
    token: str,
    keywords_list: list[str],
    commune: str | None = None,
    distance_km: int = 30,
    contract_type: str | None = None,
    contract_nature: str | None = None,
    max_results_par_mot_cle: int | None = None,
    anciennete_max_jours: int = ANCIENNETE_MAX_JOURS_DEFAUT,
) -> tuple[list[dict], dict]:
    """
    Effectue une recherche complète pour chaque mot-clé.

    Les offres sont ensuite fusionnées et dédoublonnées par identifiant.
    """

    offres_par_id: dict[str, dict] = {}
    statistiques: dict[str, dict] = {}

    nombre_mots_cles = len(keywords_list)

    for index, mot_cle in enumerate(
        keywords_list,
        start=1,
    ):
        mot_cle = mot_cle.strip()

        if not mot_cle:
            continue

        print(
            f"\n[{index}/{nombre_mots_cles}] "
            f"Recherche pour le mot-clé : '{mot_cle}'"
        )

        offres, total_disponible, ecartees = search_offers(
            token=token,
            keywords=mot_cle,
            commune=commune,
            distance_km=distance_km,
            contract_type=contract_type,
            contract_nature=contract_nature,
            max_results=max_results_par_mot_cle,
            anciennete_max_jours=anciennete_max_jours,
        )

        nouvelles_offres = 0

        for offre in offres:
            offer_id = offre.get("id")

            if not offer_id:
                continue

            if offer_id not in offres_par_id:
                offres_par_id[offer_id] = offre
                nouvelles_offres += 1

        statistiques[mot_cle] = {
            "trouvees": len(offres),
            "nouvelles_apres_dedoublonnage": nouvelles_offres,
            "total_disponible_api": total_disponible,
            "ecartees_anciennete": ecartees,
        }

        print(
            f"-> {len(offres)} offre(s) trouvée(s) "
            f"pour '{mot_cle}', dont "
            f"{nouvelles_offres} nouvelle(s) après "
            f"dédoublonnage."
        )

        if index < nombre_mots_cles:
            time.sleep(DELAI_ENTRE_MOTS_CLES_SEC)

    return list(offres_par_id.values()), statistiques


# ---------------------------------------------------------------------------
# Gestion du type de candidature
# ---------------------------------------------------------------------------

def prepare_keywords(
    keywords: list[str],
    candidature_type: str,
) -> list[str]:
    """
    Nettoie les mots-clés.

    Pour les stages, ajoute le mot 'stage' à chaque requête afin
    d'améliorer la pertinence des résultats retournés par l'API.
    """

    cleaned_keywords: list[str] = []

    for keyword in keywords:
        cleaned_keyword = keyword.strip()

        if not cleaned_keyword:
            continue

        if cleaned_keyword not in cleaned_keywords:
            cleaned_keywords.append(cleaned_keyword)

    if candidature_type != TYPE_CANDIDATURE_STAGE:
        return cleaned_keywords

    stage_queries: list[str] = []

    for keyword in cleaned_keywords:
        normalized_keyword = keyword.casefold()

        already_contains_stage_term = any(
            stage_term in normalized_keyword
            for stage_term in (
                "stage",
                "stagiaire",
                "internship",
            )
        )

        if already_contains_stage_term:
            stage_query = keyword
        else:
            stage_query = f"{keyword} stage"

        if stage_query not in stage_queries:
            stage_queries.append(stage_query)

    return stage_queries


def is_stage_offer(offer: dict) -> bool:
    """
    Vérifie localement qu'une offre semble réellement correspondre
    à un stage.

    La vérification s'effectue sur :
    - l'intitulé ;
    - la description ;
    - le type de contrat ;
    - la nature du contrat.
    """

    searchable_text = " ".join(
        [
            str(offer.get("intitule", "")),
            str(offer.get("description", "")),
            str(offer.get("type_contrat", "")),
            str(offer.get("nature_contrat", "")),
        ]
    ).casefold()

    return any(
        re.search(pattern, searchable_text)
        for pattern in STAGE_PATTERNS
    )


def is_alternance_offer(offer: dict) -> bool:
    """
    Vérifie que la nature du contrat est un apprentissage ou
    un contrat de professionnalisation.
    """

    nature = str(
        offer.get("nature_contrat", "")
    ).casefold()

    return any(
        label in nature
        for label in ALTERNANCE_NATURE_LABELS
    )


def filter_offers_by_candidature_type(
    offers: list[dict],
    candidature_type: str,
) -> tuple[list[dict], int]:
    """
    Applique le filtre local correspondant au type demandé.

    L'alternance est déjà filtrée par natureContrat=E2,FS au niveau
    de l'API ; le contrôle local sert de garde-fou si le filtre de
    l'API est ignoré ou si --nature a été forcé.
    """

    if candidature_type == TYPE_CANDIDATURE_ALTERNANCE:
        keep = is_alternance_offer
    elif candidature_type == TYPE_CANDIDATURE_STAGE:
        keep = is_stage_offer
    else:
        return offers, 0

    filtered_offers = [
        offer
        for offer in offers
        if keep(offer)
    ]

    rejected_count = len(offers) - len(filtered_offers)

    return filtered_offers, rejected_count


def add_candidature_type(
    offers: list[dict],
    candidature_type: str,
) -> list[dict]:
    """
    Ajoute le type de candidature à chaque ligne du futur CSV.
    """

    for offer in offers:
        offer["type_candidature"] = candidature_type

    return offers


# ---------------------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------------------

def save_to_csv(
    offers: list[dict],
    candidature_type: str,
    base_dir: Path | None = None,
) -> str:
    """
    Enregistre les offres dans un fichier CSV.

    Structure :

    data/france_travail/1_brutes/<type-candidature>/YYYY-MM-DD/
    """

    if base_dir is None:
        base_dir = (
            BASE_DIR
            / "data"
            / "france_travail"
            / "1_brutes"
            / candidature_type
        )

    today = datetime.now().strftime("%Y-%m-%d")

    output_folder = base_dir / today
    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime("%H%M%S")

    filename = (
        f"offres_{candidature_type}_"
        f"{today}_{timestamp}.csv"
    )

    filepath = output_folder / filename

    with filepath.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=FIELDNAMES,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(offers)

    return str(filepath)


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    """
    Construit le parseur des arguments du script.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Collecte d'offres France Travail pour des "
            "alternances, des stages ou tous les contrats."
        )
    )

    parser.add_argument(
        "--type-candidature",
        choices=TYPES_CANDIDATURE,
        default=TYPE_CANDIDATURE_ALTERNANCE,
        help=(
            "Type de candidature à collecter : "
            "'alternance', 'stage' ou 'tous'. "
            "Défaut : alternance."
        ),
    )

    parser.add_argument(
        "--keywords",
        default="data",
        help=(
            "Mot-clé de recherche unique. "
            "Défaut : 'data'. Cet argument est ignoré "
            "si --keywords-list est fourni."
        ),
    )

    parser.add_argument(
        "--keywords-list",
        default=None,
        help=(
            "Liste de mots-clés séparés par des virgules. "
            "Une recherche complète est effectuée pour chaque "
            "mot-clé, puis les résultats sont fusionnés et "
            "dédoublonnés. Exemple : "
            f"\"{SUGGESTION_KEYWORDS_LIST}\""
        ),
    )

    parser.add_argument(
        "--commune",
        default=None,
        help=(
            "Code INSEE de la commune. "
            "Exemple : 11069 pour Carcassonne."
        ),
    )

    parser.add_argument(
        "--distance",
        type=int,
        default=30,
        help=(
            "Rayon de recherche en kilomètres. "
            "Utilisé uniquement lorsque --commune est fourni. "
            "Défaut : 30."
        ),
    )

    parser.add_argument(
        "--contrat",
        default=None,
        help=(
            "Filtre manuel typeContrat de France Travail. "
            "Exemples : CDI, CDD, MIS, SAI."
        ),
    )

    parser.add_argument(
        "--nature",
        default=None,
        help=(
            "Filtre manuel natureContrat. "
            "S'il n'est pas précisé, la valeur est déterminée "
            "automatiquement selon --type-candidature. "
            "Pour l'alternance : E1,E2."
        ),
    )

    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help=(
            "Nombre maximal d'offres récupérées par mot-clé. "
            "Sans cette option, le script récupère automatiquement "
            "toutes les offres disponibles dans la limite de l'API."
        ),
    )

    parser.add_argument(
        "--max-anciennete-jours",
        type=int,
        default=ANCIENNETE_MAX_JOURS_DEFAUT,
        help=(
            "Ancienneté maximale des offres en jours. "
            f"Défaut : {ANCIENNETE_MAX_JOURS_DEFAUT}. "
            "Utiliser 0 pour désactiver ce filtre."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.max is not None and args.max <= 0:
        parser.error("--max doit être supérieur à 0.")

    if args.max_anciennete_jours < 0:
        parser.error(
            "--max-anciennete-jours doit être positif ou égal à 0."
        )

    if args.distance < 0:
        parser.error("--distance doit être positive ou égale à 0.")

    contract_nature = resolve_contract_nature(
        candidature_type=args.type_candidature,
        manual_nature=args.nature,
    )

    print("==============================================")
    print("Collecte des offres France Travail")
    print("==============================================")
    print(
        f"Type de candidature : {args.type_candidature}"
    )

    if contract_nature:
        print(
            f"Filtre natureContrat : {contract_nature}"
        )
    else:
        print("Filtre natureContrat : aucun")

    print(
        f"Ancienneté maximale : "
        f"{args.max_anciennete_jours} jour(s)"
        if args.max_anciennete_jours > 0
        else "Ancienneté maximale : filtre désactivé"
    )

    print("\nAuthentification auprès de France Travail...")
    token = get_access_token()
    print("Authentification réussie.")

    if args.keywords_list:
        raw_keywords = args.keywords_list.split(",")
    else:
        raw_keywords = [args.keywords]

    keywords_list = prepare_keywords(
        keywords=raw_keywords,
        candidature_type=args.type_candidature,
    )

    if not keywords_list:
        parser.error(
            "Aucun mot-clé valide n'a été fourni."
        )

    if len(keywords_list) > 1:
        print(
            f"\nRecherche multi-mots-clés "
            f"({len(keywords_list)} terme(s)) :"
        )

        for keyword in keywords_list:
            print(f"- {keyword}")

        offers, stats = search_offers_multi_keywords(
            token=token,
            keywords_list=keywords_list,
            commune=args.commune,
            distance_km=args.distance,
            contract_type=args.contrat,
            contract_nature=contract_nature,
            max_results_par_mot_cle=args.max,
            anciennete_max_jours=args.max_anciennete_jours,
        )

        print("\n=== Résumé par mot-clé ===")

        for mot_cle, statistics in stats.items():
            print(
                f"'{mot_cle}' : "
                f"{statistics['trouvees']} trouvée(s), "
                f"{statistics['nouvelles_apres_dedoublonnage']} "
                f"nouvelle(s) après dédoublonnage, "
                f"{statistics['ecartees_anciennete']} "
                f"écartée(s) pour ancienneté."
            )

        print(
            f"\n{len(offers)} offre(s) unique(s) "
            f"après fusion et dédoublonnage."
        )

    else:
        keyword = keywords_list[0]

        print(
            f"\nRecherche d'offres pour : '{keyword}'"
        )

        if args.max is None:
            print("Objectif : récupérer toutes les offres.")
        else:
            print(
                f"Plafond volontaire : "
                f"{args.max} offre(s)."
            )

        offers, total_disponible, ecartees_anciennete = (
            search_offers(
                token=token,
                keywords=keyword,
                commune=args.commune,
                distance_km=args.distance,
                contract_type=args.contrat,
                contract_nature=contract_nature,
                max_results=args.max,
                anciennete_max_jours=args.max_anciennete_jours,
            )
        )

        print(
            f"\n{len(offers)} offre(s) récupérée(s)."
        )

        if ecartees_anciennete > 0:
            print(
                f"{ecartees_anciennete} offre(s) écartée(s) "
                f"par le contrôle local d'ancienneté."
            )

        if (
            total_disponible is not None
            and args.max is not None
            and total_disponible > len(offers)
        ):
            nombre_non_collecte = (
                total_disponible - len(offers)
            )

            print(
                "ATTENTION : "
                f"{nombre_non_collecte} offre(s) supplémentaire(s) "
                f"existent, mais n'ont pas été récupérées à cause "
                f"du plafond --max {args.max}."
            )

    nombre_avant_filtrage = len(offers)

    offers, rejected_count = (
        filter_offers_by_candidature_type(
            offers=offers,
            candidature_type=args.type_candidature,
        )
    )

    if args.type_candidature == TYPE_CANDIDATURE_STAGE:
        print("\n=== Vérification locale des stages ===")
        print(
            f"{nombre_avant_filtrage} offre(s) examinée(s)."
        )
        print(
            f"{len(offers)} offre(s) de stage conservée(s)."
        )
        print(
            f"{rejected_count} offre(s) écartée(s), car aucune "
            f"mention claire de stage ou stagiaire n'a été détectée."
        )

    if (
        args.type_candidature == TYPE_CANDIDATURE_ALTERNANCE
        and rejected_count
    ):
        print("\n=== Vérification locale des alternances ===")
        print(
            f"{rejected_count} offre(s) écartée(s), car leur nature "
            f"de contrat n'est ni un apprentissage ni un contrat "
            f"de professionnalisation."
        )

    offers = add_candidature_type(
        offers=offers,
        candidature_type=args.type_candidature,
    )

    filepath = save_to_csv(
        offers=offers,
        candidature_type=args.type_candidature,
    )

    print("\n==============================================")
    print("Collecte terminée")
    print("==============================================")
    print(
        f"Type de candidature : {args.type_candidature}"
    )
    print(
        f"Nombre final d'offres : {len(offers)}"
    )
    print(f"Fichier enregistré : {filepath}")


if __name__ == "__main__":
    main()