"""
collect_offers_letudiant.py

Collecte les offres de stage et d'alternance de L'Étudiant Jobs & Stages
(https://jobs-stages.letudiant.fr) et les enregistre dans :

data/letudiant/1_brutes/<type>/<date>/offres_letudiant_<type>_<date>_<heure>.csv

Le CSV a les mêmes colonnes principales que les autres collecteurs :
il passe ensuite dans filter_offers.py puis run_pipeline.ps1.

Fonctionnement
--------------
Le site charge ses résultats de recherche dans le navigateur, et son
robots.txt interdit les recherches filtrées (« /offres? »). Le script passe
donc par les sitemaps publiés pour les moteurs de recherche (autorisés) :

1. Lecture des sitemaps d'offres (environ 85 000 adresses, 20 Mo).
2. Sélection des adresses mises à jour récemment dont l'intitulé (présent
   dans l'adresse) contient un mot-clé.
3. Lecture de la page de chaque offre retenue : elle contient un bloc
   structuré « JobPosting ». Une offre expirée (410) est ignorée.
4. Le type de contrat vient du bloc (stage = « INTERN ») et de l'intitulé
   (« stage », « alternance », « apprenti »...).

Exemples
--------

python src\\collect_offers_letudiant.py --type-candidature stage --max-anciennete-jours 7

python src\\collect_offers_letudiant.py ^
    --type-candidature alternance ^
    --keywords-list "data,data analyst,statistique" ^
    --max-anciennete-jours 14
"""

import argparse
import csv
import html
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from collect_offers_engagement_jeunes import (
    html_to_text,
    read_job_posting,
)
from collect_offers_pass import (
    DEFAULT_KEYWORDS,
    PassClient,
    clean_spaces,
    parse_keywords,
)


BASE_DIR = Path(__file__).resolve().parent.parent

SITE_URL = "https://jobs-stages.letudiant.fr"
SITEMAP_INDEX_URL = f"{SITE_URL}/sitemap.xml"

TYPE_CANDIDATURE_ALTERNANCE = "alternance"
TYPE_CANDIDATURE_STAGE = "stage"

TYPES_CANDIDATURE = (
    TYPE_CANDIDATURE_ALTERNANCE,
    TYPE_CANDIDATURE_STAGE,
)

ANCIENNETE_MAX_JOURS_DEFAUT = 14
DELAI_ENTRE_REQUETES_SEC = 1.0

# Mots de l'intitulé (dans l'adresse) qui indiquent le contrat.
STAGE_SLUG_WORDS = ("stage", "stagiaire", "stagiaires", "internship", "intern")
ALTERNANCE_SLUG_WORDS = (
    "alternance", "alternant", "alternante", "apprenti", "apprentie",
    "apprentissage", "professionnalisation",
)

FIELDNAMES = [
    "id",
    "source",
    "type_candidature",
    "intitule",
    "entreprise",
    "lieu",
    "type_contrat",
    "date_creation",
    "date_expiration",
    "competences",
    "description",
    "url",
]


# ---------------------------------------------------------------------------
# Sitemaps
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.lower())
    value = "".join(char for char in value if not unicodedata.combining(char))

    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def slug_words(url: str) -> str:
    """
    Intitulé de l'offre tel qu'il apparaît dans l'adresse, entouré de
    tirets : « -stagiaire-data-et-analyse-massy-france-10- ».
    """

    return f"-{url.rsplit('/offres/', 1)[-1]}-"


def contains_slug_word(slug: str, words: tuple[str, ...]) -> bool:
    return any(f"-{word}-" in slug for word in words)


def read_sitemap_offers(
    session: requests.Session,
) -> list[tuple[str, datetime]]:
    """
    (adresse, date de mise à jour) de toutes les offres des sitemaps.
    """

    index = session.get(SITEMAP_INDEX_URL, timeout=60)
    index.raise_for_status()

    sitemap_urls = [
        url
        for url in re.findall(r"<loc>([^<]+)</loc>", index.text)
        if "/sitemaps/jobs-" in url
    ]

    offers = []

    for sitemap_url in sitemap_urls:
        print(f"Lecture de {sitemap_url.rsplit('/', 1)[-1]}...")

        response = session.get(sitemap_url, timeout=180)
        response.raise_for_status()

        for url, lastmod in re.findall(
            r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>",
            response.text,
        ):
            if "/offres/" not in url:
                continue

            try:
                updated = datetime.fromisoformat(lastmod.replace("Z", "+00:00"))
            except ValueError:
                continue

            offers.append((url, updated))

    return offers


# ---------------------------------------------------------------------------
# Page d'une offre
# ---------------------------------------------------------------------------

def offer_type(
    posting: dict,
    slug: str,
) -> str:
    """
    stage, alternance, ou "" (CDI, CDD... : ignoré).
    """

    employment_types = posting.get("employmentType") or []

    if isinstance(employment_types, str):
        employment_types = [employment_types]

    if contains_slug_word(slug, ALTERNANCE_SLUG_WORDS):
        return TYPE_CANDIDATURE_ALTERNANCE

    if "INTERN" in employment_types or contains_slug_word(slug, STAGE_SLUG_WORDS):
        return TYPE_CANDIDATURE_STAGE

    return ""


def build_csv_row(
    url: str,
    posting: dict,
    row_type: str,
) -> dict:
    organization = posting.get("hiringOrganization") or {}
    location = posting.get("jobLocation") or {}

    if isinstance(location, list):
        location = location[0] if location else {}

    address = location.get("address") or {}

    city = str(address.get("addressLocality", "")).strip()
    postal_code = str(address.get("postalCode", "")).strip()
    lieu = f"{city} ({postal_code[:2]})" if city and postal_code else city

    company = str(organization.get("name", "")).strip()
    company_slug = url.split("/entreprises/", 1)[-1].split("/", 1)[0]

    skills = html_to_text(posting.get("skills") or posting.get("qualifications"))

    description_parts = [
        html_to_text(posting.get("description")),
        f"Profil recherché :\n{skills}" if skills else "",
    ]

    return {
        "id": f"LE-{company_slug}-{url.rsplit('/', 1)[-1]}"[:120],
        "source": "letudiant",
        "type_candidature": row_type,
        "intitule": clean_spaces(html.unescape(str(posting.get("title", "")))),
        "entreprise": company or "Non precise",
        "lieu": lieu,
        "type_contrat": "Stage" if row_type == TYPE_CANDIDATURE_STAGE else "Alternance",
        "date_creation": posting.get("datePosted", ""),
        "date_expiration": posting.get("validThrough", ""),
        "competences": skills,
        "description": "\n\n".join(part for part in description_parts if part),
        "url": url,
    }


# ---------------------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------------------

def save_offers(
    rows: list[dict],
    candidature_type: str,
) -> Path:
    """
    data/letudiant/1_brutes/<type>/YYYY-MM-DD/
    """

    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")

    output_folder = (
        BASE_DIR
        / "data"
        / "letudiant"
        / "1_brutes"
        / candidature_type
        / today
    )

    output_folder.mkdir(parents=True, exist_ok=True)

    filepath = output_folder / (
        f"offres_letudiant_{candidature_type}_{today}_{timestamp}.csv"
    )

    with filepath.open(mode="w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    return filepath


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collecte les offres de stage et d'alternance "
            "de L'Étudiant Jobs & Stages."
        )
    )

    parser.add_argument(
        "--type-candidature",
        choices=TYPES_CANDIDATURE,
        default=TYPE_CANDIDATURE_ALTERNANCE,
        help="alternance ou stage. Défaut : alternance.",
    )

    parser.add_argument(
        "--keywords-list",
        default=DEFAULT_KEYWORDS,
        help=(
            "Mots-clés séparés par des virgules, cherchés dans "
            "l'intitulé de l'offre."
        ),
    )

    parser.add_argument(
        "--max-anciennete-jours",
        type=int,
        default=ANCIENNETE_MAX_JOURS_DEFAUT,
        help=(
            "Ne garde que les offres mises à jour depuis ce nombre "
            f"de jours. Défaut : {ANCIENNETE_MAX_JOURS_DEFAUT}."
        ),
    )

    parser.add_argument(
        "--delai",
        type=float,
        default=DELAI_ENTRE_REQUETES_SEC,
        help=(
            "Pause en secondes entre deux pages d'offre lues. "
            f"Défaut : {DELAI_ENTRE_REQUETES_SEC}."
        ),
    )

    return parser


def main() -> None:
    args = build_argument_parser().parse_args()

    keywords = parse_keywords(args.keywords_list)

    if not keywords:
        sys.exit("Aucun mot-clé fourni.")

    keyword_slugs = tuple(slugify(keyword) for keyword in keywords)

    client = PassClient(delay_sec=args.delai)

    print("==============================================")
    print("Collecte L'Étudiant Jobs & Stages")
    print("==============================================")
    print(f"Type : {args.type_candidature}")
    print(f"Mots-clés : {len(keywords)}")
    print(f"Ancienneté maximale : {args.max_anciennete_jours} jours\n")

    sitemap_offers = read_sitemap_offers(client.session)

    limit = datetime.now(timezone.utc) - timedelta(days=args.max_anciennete_jours)

    candidates = [
        url
        for url, updated in sitemap_offers
        if updated >= limit
        and contains_slug_word(slug_words(url), keyword_slugs)
    ]

    print(
        f"\n{len(sitemap_offers)} offre(s) dans les sitemaps, "
        f"{len(candidates)} récente(s) avec un mot-clé dans l'intitulé."
    )

    if candidates:
        print("Lecture du détail de chaque offre...")

    rows = []
    expired = 0
    other_contracts = 0

    for index, url in enumerate(candidates, start=1):
        try:
            document = client.get_document(url)
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code in (404, 410):
                expired += 1
                continue

            print(f"  [{index}] Ignorée (erreur) : {url} ({error})")
            continue
        except requests.RequestException as error:
            print(f"  [{index}] Ignorée (erreur réseau) : {url} ({error})")
            continue

        posting = read_job_posting(document)

        if not posting:
            expired += 1
            continue

        row_type = offer_type(posting, slug_words(url))

        if row_type != args.type_candidature:
            other_contracts += 1
            continue

        row = build_csv_row(url, posting, row_type)
        rows.append(row)

        print(
            f"  [{index}/{len(candidates)}] {row['intitule'][:70]} "
            f"- {row['entreprise'][:40]}"
        )

    print(
        f"\n{len(rows)} offre(s) gardée(s), {expired} expirée(s), "
        f"{other_contracts} d'un autre contrat (CDI, CDD, autre type)."
    )

    filepath = save_offers(rows=rows, candidature_type=args.type_candidature)

    print(f"\nFichier : {filepath}")


if __name__ == "__main__":
    main()
