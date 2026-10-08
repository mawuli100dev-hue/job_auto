"""
collect_offers_engagement_jeunes.py

Collecte les offres de stage et d'alternance publiées sur Engagement Jeunes
(https://www.engagement-jeunes.com) et les enregistre dans :

data/engagement_jeunes/1_brutes/<type>/<date>/offres_engagement_jeunes_<type>_<date>_<heure>.csv

Le CSV a les mêmes colonnes principales que celui de collect_offers_pass.py :
il passe ensuite dans filter_offers.py puis run_pipeline.ps1.

Fonctionnement
--------------
1. Une recherche est lancée sur le site pour chaque mot-clé, filtrée sur le
   contrat (stage, ou apprentissage et professionnalisation) et sur
   l'ancienneté.
2. Les offres trouvées sont fusionnées et dédoublonnées.
3. La page de chaque offre est lue : elle contient un bloc structuré
   « JobPosting » (intitulé, entreprise, lieu, date, description).
4. Une offre n'est gardée que si un mot-clé apparaît comme mot entier dans
   son intitulé ou sa description.

Le robots.txt du site autorise toutes les pages (« Allow: / »). Le script
fait une pause entre deux requêtes pour ne pas le surcharger.

Exemples
--------

python src\\collect_offers_engagement_jeunes.py --type-candidature stage --max-anciennete-jours 7

python src\\collect_offers_engagement_jeunes.py ^
    --type-candidature alternance ^
    --keywords-list "data,data analyst,statistique" ^
    --max-anciennete-jours 31
"""

import argparse
import csv
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import lxml.html
import requests

from collect_offers_pass import (
    DEFAULT_KEYWORDS,
    PassClient,
    clean_spaces,
    is_recent,
    matches_keywords,
    parse_keywords,
)


BASE_DIR = Path(__file__).resolve().parent.parent

SITE_URL = "https://www.engagement-jeunes.com"
SEARCH_URL = f"{SITE_URL}/fr/offres-emploi.html"

TYPE_CANDIDATURE_ALTERNANCE = "alternance"
TYPE_CANDIDATURE_STAGE = "stage"

TYPES_CANDIDATURE = (
    TYPE_CANDIDATURE_ALTERNANCE,
    TYPE_CANDIDATURE_STAGE,
)

# Codes du filtre « contrat[] » du site.
SITE_CONTRACT_CODES = {
    TYPE_CANDIDATURE_STAGE: ("3",),
    # 5 : contrat d'apprentissage, 7 : contrat de professionnalisation.
    TYPE_CANDIDATURE_ALTERNANCE: ("5", "7"),
}

# Valeurs du filtre « fraicheur » du site, en jours.
SITE_FRESHNESS_DAYS = (1, 2, 7, 31, 92)

MAX_PAGES_PAR_MOT_CLE = 15
ANCIENNETE_MAX_JOURS_DEFAUT = 21
DELAI_ENTRE_REQUETES_SEC = 1.0

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
    "niveau_diplome",
    "competences",
    "description",
    "url",
]

OFFER_LINK_PATTERN = re.compile(r"^/fr/detail-offre/(\d+)/")


# ---------------------------------------------------------------------------
# Pages de résultats
# ---------------------------------------------------------------------------

def site_freshness(max_age_days: int) -> str:
    """
    Plus petit filtre du site qui couvre max_age_days ; "" = toutes.
    Le filtrage exact se fait ensuite sur la date de chaque offre.
    """

    for days in SITE_FRESHNESS_DAYS:
        if max_age_days <= days:
            return str(days)

    return ""


def search_keyword(
    client: PassClient,
    keyword: str,
    contract_codes: tuple[str, ...],
    freshness: str,
) -> list[str]:
    """
    URLs des offres trouvées pour un mot-clé, toutes pages comprises.
    """

    urls: list[str] = []

    for page in range(1, MAX_PAGES_PAR_MOT_CLE + 1):
        params = [("q", keyword)]
        params += [("contrat[]", code) for code in contract_codes]

        if freshness:
            params.append(("fraicheur", freshness))

        if page > 1:
            params.append(("page", str(page)))

        document = client.get_document(SEARCH_URL, params=params)

        page_urls = []

        for href in document.xpath("//a/@href"):
            match = OFFER_LINK_PATTERN.match(href)

            if match:
                url = urljoin(SITE_URL, href)

                if url not in urls and url not in page_urls:
                    page_urls.append(url)

        if not page_urls:
            break

        urls.extend(page_urls)

    return urls


# ---------------------------------------------------------------------------
# Page d'une offre
# ---------------------------------------------------------------------------

def html_to_text(value: object) -> str:
    """
    Texte d'un champ HTML du bloc JobPosting, un paragraphe par ligne.
    """

    text = str(value or "")
    text = re.sub(r"<br\s*/?>|</(?:p|li|div|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)

    return clean_spaces(html.unescape(text))


def read_job_posting(
    document: lxml.html.HtmlElement,
) -> dict:
    for script in document.xpath("//script[@type='application/ld+json']/text()"):
        try:
            data = json.loads(script)
        except ValueError:
            continue

        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item

    return {}


def contract_from_url(url: str) -> str:
    slug = url.rsplit("/", 1)[-1]

    for prefix, label in (
        ("stage-", "Stage"),
        ("contrat-d-apprentissage-", "Contrat d'apprentissage"),
        ("contrat-de-professionnalisation-", "Contrat de professionnalisation"),
    ):
        if slug.startswith(prefix):
            return label

    return ""


def build_csv_row(
    url: str,
    posting: dict,
    candidature_type: str,
) -> dict:
    organization = posting.get("hiringOrganization") or {}
    location = posting.get("jobLocation") or {}

    if isinstance(location, list):
        location = location[0] if location else {}

    address = location.get("address") or {}

    city = str(address.get("addressLocality", "")).strip()
    postal_code = str(address.get("postalCode", "")).strip()
    lieu = f"{city} ({postal_code[:2]})" if city and postal_code else city

    employment_types = posting.get("employmentType") or []

    if isinstance(employment_types, str):
        employment_types = [employment_types]

    row_type = (
        TYPE_CANDIDATURE_STAGE
        if "INTERN" in employment_types
        else candidature_type
    )

    skills = html_to_text(posting.get("skills"))
    company_overview = html_to_text(posting.get("employerOverview"))

    # La lettre lit au plus 4 000 caractères : le poste d'abord.
    description_parts = [
        html_to_text(
            posting.get("responsibilities")
            or posting.get("description")
        ),
        f"Profil recherché :\n{skills}" if skills else "",
        f"Entreprise : {company_overview}" if company_overview else "",
    ]

    education = posting.get("educationRequirements") or {}

    match = OFFER_LINK_PATTERN.match(url.replace(SITE_URL, ""))

    return {
        "id": f"EJ-{match.group(1)}" if match else url,
        "source": "engagement_jeunes",
        "type_candidature": row_type,
        "intitule": clean_spaces(html.unescape(str(posting.get("title", "")))),
        "entreprise": str(organization.get("name", "")).strip() or "Non precise",
        "lieu": lieu,
        "type_contrat": contract_from_url(url),
        "date_creation": posting.get("datePosted", ""),
        "date_expiration": posting.get("validThrough", ""),
        "niveau_diplome": (
            education.get("credentialCategory", "")
            if isinstance(education, dict)
            else ""
        ),
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
    data/engagement_jeunes/1_brutes/<type>/YYYY-MM-DD/
    """

    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")

    output_folder = (
        BASE_DIR
        / "data"
        / "engagement_jeunes"
        / "1_brutes"
        / candidature_type
        / today
    )

    output_folder.mkdir(parents=True, exist_ok=True)

    filepath = output_folder / (
        f"offres_engagement_jeunes_{candidature_type}_{today}_{timestamp}.csv"
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
            "d'Engagement Jeunes."
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
            "Mots-clés séparés par des virgules. Une recherche est "
            "lancée pour chacun, puis les offres sont fusionnées."
        ),
    )

    parser.add_argument(
        "--max-anciennete-jours",
        type=int,
        default=ANCIENNETE_MAX_JOURS_DEFAUT,
        help=(
            "Ne garde que les offres publiées depuis ce nombre "
            f"de jours. Défaut : {ANCIENNETE_MAX_JOURS_DEFAUT}."
        ),
    )

    parser.add_argument(
        "--delai",
        type=float,
        default=DELAI_ENTRE_REQUETES_SEC,
        help=(
            "Pause en secondes entre deux pages lues. "
            f"Défaut : {DELAI_ENTRE_REQUETES_SEC}."
        ),
    )

    parser.add_argument(
        "--sans-filtre-mots-cles",
        action="store_true",
        help=(
            "Garde toutes les offres trouvées par le site, même "
            "si aucun mot-clé n'apparaît comme mot entier."
        ),
    )

    return parser


def main() -> None:
    args = build_argument_parser().parse_args()

    keywords = parse_keywords(args.keywords_list)

    if not keywords:
        sys.exit("Aucun mot-clé fourni.")

    client = PassClient(delay_sec=args.delai)
    contract_codes = SITE_CONTRACT_CODES[args.type_candidature]
    freshness = site_freshness(args.max_anciennete_jours)

    print("==============================================")
    print("Collecte Engagement Jeunes")
    print("==============================================")
    print(f"Type : {args.type_candidature}")
    print(f"Mots-clés : {len(keywords)}")
    print(f"Ancienneté maximale : {args.max_anciennete_jours} jours")

    all_urls: list[str] = []

    for index, keyword in enumerate(keywords, start=1):
        urls = search_keyword(
            client=client,
            keyword=keyword,
            contract_codes=contract_codes,
            freshness=freshness,
        )

        new_urls = [url for url in urls if url not in all_urls]
        all_urls.extend(new_urls)

        print(
            f"[{index}/{len(keywords)}] '{keyword}' : "
            f"{len(urls)} offre(s), {len(new_urls)} nouvelle(s)"
        )

    print(f"\n{len(all_urls)} offre(s) unique(s). Lecture du détail de chaque offre...")

    rows = []
    rejected_keywords = 0
    rejected_age = 0

    for index, url in enumerate(all_urls, start=1):
        try:
            posting = read_job_posting(client.get_document(url))
        except requests.RequestException as error:
            print(f"  [{index}] Ignorée (erreur réseau) : {url} ({error})")
            continue

        if not posting:
            print(f"  [{index}] Ignorée (pas de bloc JobPosting) : {url}")
            continue

        row = build_csv_row(url, posting, args.type_candidature)

        if not is_recent(row["date_creation"], args.max_anciennete_jours):
            rejected_age += 1
            continue

        matched = matches_keywords(
            f"{row['intitule']}\n{row['description']}",
            keywords,
        )

        if not matched and not args.sans_filtre_mots_cles:
            rejected_keywords += 1
            continue

        rows.append(row)

        print(
            f"  [{index}/{len(all_urls)}] {row['intitule'][:70]} "
            f"- {row['entreprise'][:40]}"
        )

    print(
        f"\n{len(rows)} offre(s) gardée(s), {rejected_age} trop ancienne(s), "
        f"{rejected_keywords} sans mot-clé dans l'intitulé ou la description."
    )

    filepath = save_offers(rows=rows, candidature_type=args.type_candidature)

    print(f"\nFichier : {filepath}")


if __name__ == "__main__":
    main()
