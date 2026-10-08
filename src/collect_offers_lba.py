"""
collect_offers_lba.py

Collecte les offres d'alternance via l'API La Bonne Alternance
et les enregistre dans :

data/la_bonne_alternance/1_brutes/<type>/<date>/offres_lba_alternance_<date>_<heure>.csv

IMPORTANT
---------
L'API La Bonne Alternance fournit uniquement des opportunités
d'emploi en alternance/apprentissage.

Elle ne permet pas de collecter des offres de stage.

Pour les stages, utiliser :

python src\\collect_offers.py --type-candidature stage ...

Prérequis
---------
1. Créer un compte sur :
   https://api.apprentissage.beta.gouv.fr

2. Générer un jeton d'accès API.

3. Placer le jeton dans le fichier .env à la racine :

   LBA_API_TOKEN=xxxxx

Exemples
--------

Collecte classique :

python src\\collect_offers_lba.py

Collecte avec les codes ROME data :

python src\\collect_offers_lba.py ^
    --type-candidature alternance ^
    --romes M1419,M1403,M1805,M1802,M1810

Recherche autour d'une ville :

python src\\collect_offers_lba.py ^
    --type-candidature alternance ^
    --romes M1419,M1403,M1805,M1802,M1810 ^
    --ville "Perpignan" ^
    --distance 50

Détail d'une offre :

python src\\collect_offers_lba.py ^
    --offer-id "IDENTIFIANT_OFFRE"

Tentative de collecte de stages :

python src\\collect_offers_lba.py --type-candidature stage

Le script expliquera que cette source ne prend pas en charge les stages.
"""

import argparse
import csv
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Chemins et environnement
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

LBA_API_TOKEN = os.getenv("LBA_API_TOKEN")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

BASE_URL = "https://api.apprentissage.beta.gouv.fr/api"

SEARCH_ENDPOINT = f"{BASE_URL}/job/v1/search"

OFFER_DETAIL_ENDPOINT = (
    f"{BASE_URL}/job/v1/offer/{{id}}"
)

# API Adresse du gouvernement.
# Elle permet de convertir une ville en coordonnées GPS.
GEOCODE_ENDPOINT = (
    "https://api-adresse.data.gouv.fr/search/"
)


# ---------------------------------------------------------------------------
# Types de candidatures
# ---------------------------------------------------------------------------

TYPE_CANDIDATURE_ALTERNANCE = "alternance"
TYPE_CANDIDATURE_STAGE = "stage"

TYPES_CANDIDATURE = (
    TYPE_CANDIDATURE_ALTERNANCE,
    TYPE_CANDIDATURE_STAGE,
)


# ---------------------------------------------------------------------------
# Structure du CSV
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "id",
    "source",
    "type_candidature",
    "intitule",
    "entreprise",
    "lieu",
    "type_contrat",
    "teletravail",
    "date_debut",
    "date_creation",
    "duree_contrat_mois",
    "niveau_diplome",
    "nb_postes",
    "competences_attendues",
    "competences_a_acquerir",
    "description",
    "url_candidature",
    "telephone_candidature",
    "recipient_id",
    "is_delegated",
    "partner_label",
    "codes_rome",
]


# ---------------------------------------------------------------------------
# Limites et délais
# ---------------------------------------------------------------------------

# La recherche est limitée en nombre d'appels.
# Une pause est effectuée entre les codes ROME.
DELAI_ENTRE_ROMES_SEC = 1.1


# ---------------------------------------------------------------------------
# Codes ROME suggérés
# ---------------------------------------------------------------------------

ROME_SUGGERES = {
    "M1419": (
        "Data Analyst "
        "(code ROME 4.0 dédié)"
    ),
    "M1403": (
        "Études et prospectives socio-économiques "
        "(Data Scientist et Data Analyst)"
    ),
    "M1805": (
        "Études et développement informatique "
        "(Data Engineer et Machine Learning Engineer)"
    ),
    "M1802": (
        "Expertise et support en systèmes d'information "
        "(Business Intelligence)"
    ),
    "M1810": (
        "Production et exploitation "
        "de systèmes d'information"
    ),
}


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

def _get_headers() -> dict:
    """
    Retourne les en-têtes HTTP nécessaires pour appeler l'API.
    """

    if not LBA_API_TOKEN:
        raise RuntimeError(
            "LBA_API_TOKEN doit être défini dans le fichier .env "
            "situé à la racine du projet."
        )

    return {
        "Authorization": f"Bearer {LBA_API_TOKEN}",
        "Accept": "application/json",
    }


# ---------------------------------------------------------------------------
# Validation du type demandé
# ---------------------------------------------------------------------------

def validate_candidature_type(
    candidature_type: str,
) -> None:
    """
    Vérifie que le type demandé est compatible avec cette source.

    La Bonne Alternance ne fournit que des opportunités d'alternance.
    """

    if candidature_type == TYPE_CANDIDATURE_STAGE:
        raise RuntimeError(
            "\n"
            "La source « La Bonne Alternance » ne fournit pas "
            "d'offres de stage.\n\n"
            "Pour rechercher des stages, utilise plutôt :\n\n"
            "python src\\collect_offers.py "
            "--type-candidature stage "
            "--keywords-list "
            "\"data,data analyst,data scientist,data engineer,"
            "business intelligence,machine learning,"
            "intelligence artificielle,IA,AI,statistique,statistic\" "
            "--max-anciennete-jours 3\n"
        )


# ---------------------------------------------------------------------------
# Géocodage
# ---------------------------------------------------------------------------

def geocode_ville(
    ville: str,
) -> tuple[float, float] | None:
    """
    Convertit un nom de ville en latitude et longitude.

    Retourne None si aucune localisation n'est trouvée.
    """

    response = requests.get(
        GEOCODE_ENDPOINT,
        params={
            "q": ville,
            "limit": 1,
        },
        timeout=15,
    )

    response.raise_for_status()

    response_data = response.json()
    features = response_data.get("features", []) or []

    if not features:
        return None

    geometry = features[0].get("geometry", {}) or {}
    coordinates = geometry.get("coordinates", [])

    if len(coordinates) < 2:
        return None

    longitude, latitude = coordinates

    properties = features[0].get("properties", {}) or {}
    label = properties.get("label", ville)

    print(
        f"Géocodage de '{ville}' : "
        f"{label} "
        f"(latitude={latitude}, longitude={longitude})"
    )

    return latitude, longitude


# ---------------------------------------------------------------------------
# Appels HTTP
# ---------------------------------------------------------------------------

def _request_json(
    url: str,
    headers: dict,
    params: dict | None = None,
) -> dict:
    """
    Exécute une requête GET et retourne son contenu JSON.
    """

    response = requests.get(
        url,
        headers=headers,
        params=params or {},
        timeout=30,
    )

    print(f"    -> GET {response.url}")
    print(
        f"    -> Statut HTTP : {response.status_code}"
        f" | Content-Type : "
        f"{response.headers.get('Content-Type', '?')}"
    )

    if response.status_code == 401:
        raise RuntimeError(
            "401 Unauthorized : vérifie LBA_API_TOKEN "
            "dans le fichier .env."
        )

    if response.status_code == 403:
        raise RuntimeError(
            "403 Forbidden : le jeton est invalide ou ne possède "
            "pas les habilitations nécessaires."
        )

    if response.status_code == 404:
        raise RuntimeError(
            f"404 Not Found sur {response.url} : "
            "la ressource est introuvable."
        )

    if response.status_code == 419:
        raise RuntimeError(
            "419 Too Many Requests : la limite d'appels "
            "par minute a été atteinte. Attends avant de relancer."
        )

    if response.status_code == 429:
        raise RuntimeError(
            "429 Too Many Requests : la limite d'appels "
            "a été atteinte. Attends avant de relancer."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        response_preview = (
            response.text[:1000]
            if response.text
            else "(réponse vide)"
        )

        raise RuntimeError(
            "Erreur pendant l'appel à La Bonne Alternance.\n"
            f"URL : {response.url}\n"
            f"Code HTTP : {response.status_code}\n"
            f"Réponse :\n{response_preview}"
        ) from error

    try:
        return response.json()

    except requests.exceptions.JSONDecodeError as error:
        response_preview = (
            response.text[:1000]
            if response.text
            else "(corps de réponse vide)"
        )

        raise RuntimeError(
            "Impossible de convertir la réponse en JSON.\n"
            f"URL : {response.url}\n"
            f"Code HTTP : {response.status_code}\n"
            f"Réponse :\n{response_preview}"
        ) from error


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _join_values(values) -> str:
    """
    Transforme une liste, une chaîne ou une valeur quelconque
    en texte compatible avec le CSV.
    """

    if values is None:
        return ""

    if isinstance(values, list):
        normalized_values = []

        for value in values:
            if isinstance(value, dict):
                label = (
                    value.get("label")
                    or value.get("name")
                    or value.get("value")
                    or ""
                )

                if label:
                    normalized_values.append(str(label))

            elif value is not None:
                normalized_values.append(str(value))

        return ", ".join(normalized_values)

    return str(values)


def _normalize_offer(
    raw_offer: dict,
    candidature_type: str = TYPE_CANDIDATURE_ALTERNANCE,
) -> dict:
    """
    Transforme une offre brute en une ligne normalisée pour le CSV.

    La structure utilisée est :
    identifier / contract / offer / workplace / apply.
    """

    identifier = raw_offer.get("identifier", {}) or {}
    contract = raw_offer.get("contract", {}) or {}
    offer = raw_offer.get("offer", {}) or {}
    workplace = raw_offer.get("workplace", {}) or {}
    apply_block = raw_offer.get("apply", {}) or {}
    location = workplace.get("location", {}) or {}
    target_diploma = offer.get("target_diploma", {}) or {}
    publication = offer.get("publication", {}) or {}

    type_contrat = _join_values(
        contract.get("type", [])
    )

    desired_skills = _join_values(
        offer.get("desired_skills", [])
    )

    acquired_skills = _join_values(
        offer.get("to_be_acquired_skills", [])
    )

    rome_codes = _join_values(
        offer.get("rome_codes", [])
    )

    offer_id = (
        identifier.get("id", "")
        or identifier.get("partner_job_id", "")
    )

    entreprise = workplace.get("name", "")

    if not entreprise or not str(entreprise).strip():
        entreprise = "Non precise"

    description = (
        offer.get("description", "") or ""
    ).replace("\n", " ").replace("\r", " ").strip()

    address = location.get("address", "")

    if isinstance(address, dict):
        address = (
            address.get("label")
            or address.get("street")
            or ""
        )

    niveau_diplome = ""

    if isinstance(target_diploma, dict):
        niveau_diplome = (
            target_diploma.get("label", "")
            or target_diploma.get("value", "")
        )

    elif target_diploma:
        niveau_diplome = str(target_diploma)

    return {
        "id": offer_id,
        "source": "la_bonne_alternance",
        "type_candidature": candidature_type,
        "intitule": offer.get("title", ""),
        "entreprise": entreprise,
        "lieu": address,
        "type_contrat": type_contrat,
        "teletravail": contract.get("remote", ""),
        "date_debut": contract.get("start", ""),
        "date_creation": publication.get("creation", ""),
        "duree_contrat_mois": contract.get("duration", ""),
        "niveau_diplome": niveau_diplome,
        "nb_postes": offer.get("opening_count", ""),
        "competences_attendues": desired_skills,
        "competences_a_acquerir": acquired_skills,
        "description": description,
        "url_candidature": apply_block.get("url", ""),
        "telephone_candidature": apply_block.get("phone", ""),
        "recipient_id": apply_block.get("recipient_id", ""),
        "is_delegated": raw_offer.get("is_delegated", ""),
        "partner_label": identifier.get("partner_label", ""),
        "codes_rome": rome_codes,
    }


# ---------------------------------------------------------------------------
# Détail d'une offre
# ---------------------------------------------------------------------------

def get_offer_detail(
    offer_id: str,
    candidature_type: str = TYPE_CANDIDATURE_ALTERNANCE,
    debug: bool = False,
) -> dict:
    """
    Récupère le détail complet d'une offre précise.
    """

    headers = _get_headers()

    url = OFFER_DETAIL_ENDPOINT.format(
        id=offer_id
    )

    raw_offer = _request_json(
        url=url,
        headers=headers,
    )

    if debug:
        print(
            "\n--- DEBUG : JSON brut de l'offre ---"
        )

        print(
            json.dumps(
                raw_offer,
                indent=2,
                ensure_ascii=False,
            )[:5000]
        )

        print("--- FIN DEBUG ---\n")

    return _normalize_offer(
        raw_offer=raw_offer,
        candidature_type=candidature_type,
    )


# ---------------------------------------------------------------------------
# Recherche par code ROME
# ---------------------------------------------------------------------------

def search_offers_for_rome(
    rome: str,
    latitude: float | None,
    longitude: float | None,
    distance_km: int,
    diploma_level: str | None,
    rncp: str | None,
    candidature_type: str = TYPE_CANDIDATURE_ALTERNANCE,
    debug: bool = False,
) -> list[dict]:
    """
    Recherche les offres correspondant à un code ROME.

    Une seule requête est effectuée pour cette combinaison
    de paramètres.
    """

    headers = _get_headers()

    params: dict = {
        "romes": rome,
        "radius": distance_km,
    }

    if (
        latitude is not None
        and longitude is not None
    ):
        params["latitude"] = latitude
        params["longitude"] = longitude

    if diploma_level:
        params["target_diploma_level"] = diploma_level

    if rncp:
        params["rncp"] = rncp

    payload = _request_json(
        url=SEARCH_ENDPOINT,
        headers=headers,
        params=params,
    )

    raw_offers = payload.get("jobs", []) or []
    warnings = payload.get("warnings", []) or []

    for warning in warnings:
        if isinstance(warning, dict):
            warning_message = warning.get(
                "message",
                str(warning),
            )
        else:
            warning_message = str(warning)

        print(
            f"    AVERTISSEMENT API : "
            f"{warning_message}"
        )

    if debug and raw_offers:
        print(
            "\n--- DEBUG : première offre brute ---"
        )

        print(
            json.dumps(
                raw_offers[0],
                indent=2,
                ensure_ascii=False,
            )[:5000]
        )

        print("--- FIN DEBUG ---\n")

    offers = [
        _normalize_offer(
            raw_offer=raw_offer,
            candidature_type=candidature_type,
        )
        for raw_offer in raw_offers
    ]

    print(
        f"    ROME {rome} : "
        f"{len(offers)} offre(s) reçue(s)."
    )

    return offers


# ---------------------------------------------------------------------------
# Ancienneté des offres
# ---------------------------------------------------------------------------

def is_recent(
    date_creation: str,
    max_age_days: int,
) -> bool:
    """
    Vrai si l'offre a été publiée depuis moins de max_age_days jours.
    Une offre sans date lisible est gardée.
    """

    if not date_creation:
        return True

    try:
        created = datetime.fromisoformat(
            str(date_creation).replace("Z", "+00:00")
        )
    except ValueError:
        return True

    limit = datetime.now(created.tzinfo) - timedelta(
        days=max_age_days
    )

    return created >= limit


# ---------------------------------------------------------------------------
# Recherche multi-ROME
# ---------------------------------------------------------------------------

def search_offers_multi_romes(
    romes: list[str],
    latitude: float | None,
    longitude: float | None,
    distance_km: int,
    diploma_level: str | None,
    rncp: str | None,
    candidature_type: str = TYPE_CANDIDATURE_ALTERNANCE,
    debug: bool = False,
) -> tuple[list[dict], dict]:
    """
    Recherche les offres pour plusieurs codes ROME.

    Les résultats sont fusionnés et dédoublonnés par identifiant.
    """

    offres_par_id: dict[str, dict] = {}
    statistiques: dict[str, dict] = {}

    nombre_romes = len(romes)

    for index, rome in enumerate(
        romes,
        start=1,
    ):
        rome = rome.strip().upper()

        if not rome:
            continue

        libelle = ROME_SUGGERES.get(rome, "")

        print(
            f"\n[{index}/{nombre_romes}] "
            f"Recherche pour le code ROME '{rome}'"
            + (
                f" ({libelle})"
                if libelle
                else ""
            )
        )

        offres = search_offers_for_rome(
            rome=rome,
            latitude=latitude,
            longitude=longitude,
            distance_km=distance_km,
            diploma_level=diploma_level,
            rncp=rncp,
            candidature_type=candidature_type,
            debug=debug,
        )

        nouvelles_offres = 0
        offres_sans_identifiant = 0

        for offre in offres:
            offer_id = offre.get("id", "")

            if not offer_id:
                offres_sans_identifiant += 1
                continue

            if offer_id not in offres_par_id:
                offres_par_id[offer_id] = offre
                nouvelles_offres += 1

        statistiques[rome] = {
            "trouvees": len(offres),
            "nouvelles_apres_dedoublonnage": nouvelles_offres,
            "sans_identifiant": offres_sans_identifiant,
        }

        print(
            f" -> {len(offres)} offre(s) trouvée(s), "
            f"dont {nouvelles_offres} nouvelle(s) "
            f"après dédoublonnage."
        )

        if offres_sans_identifiant > 0:
            print(
                f" -> {offres_sans_identifiant} offre(s) "
                f"ignorée(s), car aucun identifiant n'était présent."
            )

        if index < nombre_romes:
            time.sleep(DELAI_ENTRE_ROMES_SEC)

    return (
        list(offres_par_id.values()),
        statistiques,
    )


# ---------------------------------------------------------------------------
# Enregistrement CSV
# ---------------------------------------------------------------------------

def save_to_csv(
    offers: list[dict],
    candidature_type: str,
    base_dir: Path | None = None,
) -> str:
    """
    Enregistre les offres dans :

    data/la_bonne_alternance/1_brutes/<type>/<date>/

    Le type de candidature est aussi ajouté au nom du fichier.
    """

    if base_dir is None:
        base_dir = (
            BASE_DIR
            / "data"
            / "la_bonne_alternance"
            / "1_brutes"
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
        f"offres_lba_{candidature_type}_"
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
            "Collecte d'offres d'alternance depuis "
            "La Bonne Alternance."
        )
    )

    parser.add_argument(
        "--type-candidature",
        choices=TYPES_CANDIDATURE,
        default=TYPE_CANDIDATURE_ALTERNANCE,
        help=(
            "Type de candidature demandé. "
            "Cette source prend uniquement en charge "
            "'alternance'. Si 'stage' est demandé, le script "
            "indique d'utiliser collect_offers.py."
        ),
    )

    parser.add_argument(
        "--romes",
        default=",".join(
            ROME_SUGGERES.keys()
        ),
        help=(
            "Codes ROME séparés par des virgules. "
            "Défaut : codes orientés data, BI, "
            "machine learning et IA."
        ),
    )

    parser.add_argument(
        "--ville",
        default=None,
        help=(
            "Nom de ville à géocoder automatiquement. "
            "Exemple : 'Perpignan'. "
            "Alternative à --latitude et --longitude."
        ),
    )

    parser.add_argument(
        "--latitude",
        type=float,
        default=None,
        help="Latitude du centre de recherche.",
    )

    parser.add_argument(
        "--longitude",
        type=float,
        default=None,
        help="Longitude du centre de recherche.",
    )

    parser.add_argument(
        "--distance",
        type=int,
        default=30,
        help=(
            "Rayon de recherche en kilomètres. "
            "Valeur autorisée : 0 à 200. "
            "Défaut : 30."
        ),
    )

    parser.add_argument(
        "--diploma-level",
        default=None,
        choices=[
            "3",
            "4",
            "5",
            "6",
            "7",
        ],
        help=(
            "Niveau de diplôme ciblé : "
            "3, 4, 5, 6 ou 7."
        ),
    )

    parser.add_argument(
        "--rncp",
        default=None,
        help="Code RNCP à rechercher.",
    )

    parser.add_argument(
        "--offer-id",
        default=None,
        help=(
            "Si cet argument est fourni, la recherche multi-ROME "
            "est ignorée et le script récupère uniquement "
            "le détail de cette offre."
        ),
    )

    parser.add_argument(
        "--max-anciennete-jours",
        type=int,
        default=None,
        help=(
            "Ne garde que les offres publiées depuis ce nombre "
            "de jours. Défaut : aucune limite. Les offres sans "
            "date de publication sont gardées."
        ),
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Affiche une partie des données JSON brutes "
            "retournées par l'API."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    if not 0 <= args.distance <= 200:
        parser.error(
            "--distance doit être comprise entre 0 et 200."
        )

    try:
        validate_candidature_type(
            candidature_type=args.type_candidature
        )

    except RuntimeError as error:
        print(error)
        return

    print("==============================================")
    print("Collecte La Bonne Alternance")
    print("==============================================")
    print(
        f"Type de candidature : "
        f"{args.type_candidature}"
    )

    # -----------------------------------------------------------------------
    # Mode détail d'une offre
    # -----------------------------------------------------------------------

    if args.offer_id:
        print(
            f"\nRécupération du détail de l'offre "
            f"'{args.offer_id}'..."
        )

        try:
            offre = get_offer_detail(
                offer_id=args.offer_id,
                candidature_type=args.type_candidature,
                debug=args.debug,
            )

        except RuntimeError as error:
            print(f"\nERREUR : {error}")
            return

        print(
            json.dumps(
                offre,
                indent=2,
                ensure_ascii=False,
            )
        )

        filepath = save_to_csv(
            offers=[offre],
            candidature_type=args.type_candidature,
        )

        print(
            f"\nFichier enregistré : {filepath}"
        )

        return

    # -----------------------------------------------------------------------
    # Mode recherche multi-ROME
    # -----------------------------------------------------------------------

    romes = []

    for rome in args.romes.split(","):
        normalized_rome = rome.strip().upper()

        if (
            normalized_rome
            and normalized_rome not in romes
        ):
            romes.append(normalized_rome)

    if not romes:
        parser.error(
            "Aucun code ROME valide n'a été fourni."
        )

    print(
        f"\nRecherche sur {len(romes)} code(s) ROME : "
        f"{', '.join(romes)}"
    )

    latitude = args.latitude
    longitude = args.longitude

    # Si une seule coordonnée est fournie, la recherche
    # géolocalisée serait incohérente.
    if (
        (latitude is None and longitude is not None)
        or (latitude is not None and longitude is None)
    ):
        parser.error(
            "--latitude et --longitude doivent être "
            "fournies ensemble."
        )

    # Les coordonnées fournies manuellement sont prioritaires.
    if (
        args.ville
        and latitude is None
        and longitude is None
    ):
        try:
            geocode_result = geocode_ville(
                ville=args.ville
            )

        except requests.RequestException as error:
            print(
                f"ATTENTION : le géocodage de "
                f"'{args.ville}' a échoué : {error}"
            )

            geocode_result = None

        if geocode_result is None:
            print(
                f"ATTENTION : impossible de géocoder "
                f"'{args.ville}'."
            )
            print(
                "La recherche sera effectuée sans "
                "restriction géographique."
            )

        else:
            latitude, longitude = geocode_result

    if latitude is None or longitude is None:
        print(
            "\nATTENTION : aucune géolocalisation fournie."
        )
        print(
            "La recherche sera effectuée sur toute la France."
        )
    else:
        print(
            f"\nCentre de recherche : "
            f"latitude={latitude}, "
            f"longitude={longitude}"
        )
        print(
            f"Rayon : {args.distance} km"
        )

    try:
        offers, stats = search_offers_multi_romes(
            romes=romes,
            latitude=latitude,
            longitude=longitude,
            distance_km=args.distance,
            diploma_level=args.diploma_level,
            rncp=args.rncp,
            candidature_type=args.type_candidature,
            debug=args.debug,
        )

    except RuntimeError as error:
        print(f"\nERREUR : {error}")
        return

    print("\n=== Résumé par code ROME ===")

    for rome, statistics in stats.items():
        print(
            f"'{rome}' : "
            f"{statistics['trouvees']} trouvée(s), "
            f"{statistics['nouvelles_apres_dedoublonnage']} "
            f"nouvelle(s) après dédoublonnage"
        )

    print(
        f"\n{len(offers)} offre(s) unique(s) "
        f"après fusion et dédoublonnage."
    )

    if args.max_anciennete_jours is not None:
        total_before = len(offers)

        offers = [
            offer
            for offer in offers
            if is_recent(
                offer.get("date_creation", ""),
                args.max_anciennete_jours,
            )
        ]

        print(
            f"{len(offers)} offre(s) publiée(s) depuis "
            f"{args.max_anciennete_jours} jour(s) "
            f"({total_before - len(offers)} plus ancienne(s) écartée(s))."
        )

    filepath = save_to_csv(
        offers=offers,
        candidature_type=args.type_candidature,
    )

    print("\n==============================================")
    print("Collecte terminée")
    print("==============================================")
    print(
        f"Type de candidature : "
        f"{args.type_candidature}"
    )
    print(
        f"Nombre final d'offres : {len(offers)}"
    )
    print(
        f"Fichier enregistré : {filepath}"
    )


if __name__ == "__main__":
    main()