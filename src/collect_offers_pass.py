"""
collect_offers_pass.py

Collecte les offres d'apprentissage et de stage de la fonction publique
publiées sur PASS (https://www.pass.fonction-publique.gouv.fr) et les
enregistre dans :

data/pass/1_brutes/<type-candidature>/<date>/offres_pass_<type>_<date>_<heure>.csv

Le CSV a les mêmes colonnes principales que celui de collect_offers.py :
il passe ensuite dans filter_offers.py puis run_pipeline.ps1.

Fonctionnement
--------------
1. Une recherche est lancée sur le site pour chaque mot-clé.
2. Les offres trouvées sont fusionnées et dédoublonnées.
3. Les offres trop anciennes sont écartées.
4. La page de chaque offre restante est lue (description, lieu, contact...).
5. La recherche du site étant très large (« IA » trouve « social »), une
   offre n'est gardée que si un mot-clé apparaît comme mot entier dans
   son intitulé ou dans la description du poste.

Le site n'a pas d'API : le script lit les pages publiques, autorisées par
son robots.txt, avec une pause entre deux requêtes pour ne pas le surcharger.

Exemples
--------

python src\\collect_offers_pass.py --type-candidature alternance --max-anciennete-jours 7

python src\\collect_offers_pass.py ^
    --type-candidature stage ^
    --keywords-list "data,data scientist,statistique,IA" ^
    --max-anciennete-jours 7
"""

import argparse
import csv
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import lxml.html
import requests


BASE_DIR = Path(__file__).resolve().parent.parent

SITE_URL = "https://www.pass.fonction-publique.gouv.fr"
SEARCH_URL = f"{SITE_URL}/recherche-offre"

USER_AGENT = (
    "Mozilla/5.0 (compatible; job_automation/1.0; "
    "recherche personnelle d'alternance)"
)

TYPE_CANDIDATURE_ALTERNANCE = "alternance"
TYPE_CANDIDATURE_STAGE = "stage"
TYPE_CANDIDATURE_TOUS = "tous"

TYPES_CANDIDATURE = (
    TYPE_CANDIDATURE_ALTERNANCE,
    TYPE_CANDIDATURE_STAGE,
    TYPE_CANDIDATURE_TOUS,
)

# Valeurs du filtre « type de contrat » du site.
SITE_CONTRACT_TYPES = {
    TYPE_CANDIDATURE_ALTERNANCE: ("apprentissage",),
    TYPE_CANDIDATURE_STAGE: ("stage",),
    TYPE_CANDIDATURE_TOUS: ("apprentissage", "stage"),
}

DEFAULT_KEYWORDS = (
    "data,data analyst,data scientist,data engineer,data science,"
    "analyste de données,analyste data,chargé d'études,"
    "chargé d'études statistiques,statistique,statistic,statisticien,"
    "business intelligence,BI,power bi,big data,machine learning,"
    "intelligence artificielle,IA,AI,géomatique,SIG,télédétection"
)

ITEMS_PER_PAGE = 48
MAX_PAGES_PAR_MOT_CLE = 30
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
    "nature_contrat",
    "duree_contrat",
    "date_debut",
    "date_creation",
    "niveau_diplome",
    "domaine",
    "competences",
    "description",
    "recipient_email",
    "url",
]


# ---------------------------------------------------------------------------
# Outils texte
# ---------------------------------------------------------------------------

def normalize(text: object) -> str:
    """
    Minuscules, sans accents, ponctuation remplacée par des espaces.
    """

    value = unicodedata.normalize(
        "NFKD",
        str(text or "").lower(),
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = re.sub(r"[^a-z0-9]+", " ", value)

    return value.strip()


def clean_spaces(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)

    return text.strip()


BLOCK_TAGS_PATTERN = re.compile(
    r"<br\s*/?>|</(?:p|li|div|h[1-6]|tr|ul|ol)>",
    flags=re.IGNORECASE,
)


def element_text(element: lxml.html.HtmlElement) -> str:
    """
    Texte d'un élément HTML en gardant un retour à la ligne par
    paragraphe, ligne de liste ou <br> (text_content() les colle).
    """

    markup = lxml.html.tostring(
        element,
        encoding="unicode",
    )

    markup = BLOCK_TAGS_PATTERN.sub("\n", markup)

    return clean_spaces(
        lxml.html.fromstring(f"<div>{markup}</div>").text_content()
    )


def parse_keywords(value: str) -> list[str]:
    keywords = []

    for keyword in value.split(","):
        keyword = keyword.strip()

        if keyword and keyword not in keywords:
            keywords.append(keyword)

    return keywords


def matches_keywords(
    text: str,
    keywords: list[str],
) -> list[str]:
    """
    Mots-clés présents comme mots entiers dans le texte.
    """

    normalized_text = f" {normalize(text)} "

    return [
        keyword
        for keyword in keywords
        if f" {normalize(keyword)} " in normalized_text
    ]


# ---------------------------------------------------------------------------
# Accès au site
# ---------------------------------------------------------------------------

class PassClient:
    def __init__(
        self,
        delay_sec: float,
    ) -> None:
        self.delay_sec = delay_sec
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.last_request = 0.0

    def get_document(
        self,
        url: str,
        params: list[tuple[str, str]] | None = None,
    ) -> lxml.html.HtmlElement:
        for attempt in range(1, 4):
            wait = self.delay_sec - (time.time() - self.last_request)

            if wait > 0:
                time.sleep(wait)

            self.last_request = time.time()

            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                response.encoding = "utf-8"

                return lxml.html.fromstring(response.text)

            except requests.RequestException as error:
                # Page absente ou expirée (404, 410...) : inutile de réessayer.
                status = getattr(error.response, "status_code", None)

                if attempt == 3 or (status is not None and status < 500):
                    raise

                print(
                    f"  Erreur réseau ({error}), "
                    f"nouvel essai dans {attempt * 5} s..."
                )
                time.sleep(attempt * 5)

        raise RuntimeError("Inaccessible.")


# ---------------------------------------------------------------------------
# Pages de résultats
# ---------------------------------------------------------------------------

def parse_result_rows(
    document: lxml.html.HtmlElement,
) -> list[dict]:
    """
    Une ligne du tableau de résultats : lien, intitulé, date, entité.
    """

    rows = []

    # La ligne d'en-tête contient aussi un lien (tri par titre) :
    # seules les lignes dont le lien mène à une offre sont gardées.
    for row in document.xpath("//table//tr[th[contains(@class, 'views-field-title')]]"):
        links = row.xpath(
            ".//th[contains(@class, 'views-field-title')]"
            "//a[starts-with(@href, '/offre/')]"
        )

        if not links:
            continue

        times = row.xpath(".//time/@datetime")

        rows.append(
            {
                "url": urljoin(SITE_URL, links[0].get("href")),
                "intitule": clean_spaces(links[0].text_content()),
                "date_creation": times[0] if times else "",
            }
        )

    return rows


def search_keyword(
    client: PassClient,
    keyword: str,
    site_contract_types: tuple[str, ...],
) -> list[dict]:
    results = []

    for page in range(MAX_PAGES_PAR_MOT_CLE):
        params = [
            (
                f"field_type_de_contrat_value[{contract}]",
                contract,
            )
            for contract in site_contract_types
        ]

        params += [
            ("combine", keyword),
            ("field_niveau_de_diplome_prepare_target_id", "All"),
            ("items_per_page", str(ITEMS_PER_PAGE)),
            ("page", str(page)),
        ]

        document = client.get_document(
            SEARCH_URL,
            params=params,
        )

        rows = parse_result_rows(document)

        if not rows:
            break

        results.extend(rows)

        if len(rows) < ITEMS_PER_PAGE:
            break

    return results


def is_recent(
    date_creation: str,
    max_age_days: int,
) -> bool:
    if not date_creation:
        return True

    try:
        created = datetime.fromisoformat(date_creation)
    except ValueError:
        return True

    limit = datetime.now(created.tzinfo) - timedelta(days=max_age_days)

    return created >= limit


# ---------------------------------------------------------------------------
# Page d'une offre
# ---------------------------------------------------------------------------

def field_text(
    document: lxml.html.HtmlElement,
    field_name: str,
    separator: str = "\n",
) -> str:
    """
    Texte d'un champ Drupal (« field--name-field-... »), sans son libellé.
    """

    containers = document.xpath(
        f"//*[contains(concat(' ', normalize-space(@class), ' '), "
        f"' field--name-{field_name} ')]"
    )

    if not containers:
        return ""

    container = containers[0]

    items = container.xpath(
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' field__item ')]"
    )

    if items:
        texts = [element_text(item) for item in items]
    else:
        for label in container.xpath(
            ".//*[contains(@class, 'field__label')]"
        ):
            label.drop_tree()

        texts = [element_text(container)]

    return separator.join(text for text in texts if text)


def parse_offer_page(
    document: lxml.html.HtmlElement,
) -> dict:
    return {
        "numero": field_text(document, "field-numero-d-offre"),
        "type_contrat": field_text(document, "field-type-de-contrat"),
        "niveau_diplome": field_text(document, "field-niveau-de-diplome-prepare"),
        "domaine": field_text(document, "field-domaine-d-activite", ", "),
        "administration": field_text(document, "field-administration-de-rattache"),
        "entite": field_text(document, "field-entite"),
        "service": field_text(document, "field-service-d-affectation"),
        "ville": field_text(document, "field-ville"),
        "departement": field_text(document, "field-departement"),
        "description_employeur": field_text(document, "field-description-de-l-employeur"),
        "description_poste": field_text(document, "field-description-du-poste"),
        "informations": field_text(document, "field-informations-complementair"),
        "date_debut": field_text(document, "field-debut-du-contrat"),
        "duree": field_text(document, "field-duree-du-contrat", " "),
        "duree_option": field_text(document, "field-option-duree-du-contrat", " "),
        "contact_email": field_text(document, "field-contact-email"),
    }


def candidature_type_from_contract(
    contract: str,
) -> str:
    if "stage" in normalize(contract):
        return TYPE_CANDIDATURE_STAGE

    return TYPE_CANDIDATURE_ALTERNANCE


def build_csv_row(
    result: dict,
    details: dict,
) -> dict:
    entreprise = (
        details["entite"]
        or details["administration"]
        or "Non precise"
    )

    lieu = details["ville"].title()

    if details["departement"]:
        lieu = f"{lieu} ({details['departement']})" if lieu else details["departement"]

    # La lettre lit au plus 4 000 caractères : le poste d'abord,
    # puis ce qui présente l'employeur.
    description_parts = [
        details["description_poste"],
        (
            "Employeur : "
            + " / ".join(
                part
                for part in (
                    details["administration"],
                    details["entite"],
                    details["service"],
                )
                if part
            )
        ),
        details["description_employeur"],
    ]

    description = "\n\n".join(
        part
        for part in description_parts
        if part and part != "Employeur : "
    )

    duree = " ".join(
        part
        for part in (details["duree_option"], details["duree"])
        if part
    )

    offer_id = details["numero"] or result["url"].rstrip("/").rsplit("/", 1)[-1]

    return {
        "id": offer_id,
        "source": "pass",
        "type_candidature": candidature_type_from_contract(details["type_contrat"]),
        "intitule": result["intitule"],
        "entreprise": entreprise,
        "lieu": lieu,
        "type_contrat": details["type_contrat"],
        "nature_contrat": details["type_contrat"],
        "duree_contrat": duree,
        "date_debut": details["date_debut"],
        "date_creation": result["date_creation"],
        "niveau_diplome": details["niveau_diplome"],
        "domaine": details["domaine"],
        "competences": details["domaine"],
        "description": description,
        "recipient_email": details["contact_email"],
        "url": result["url"],
    }


# ---------------------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------------------

def save_offers(
    rows: list[dict],
    candidature_type: str,
) -> Path:
    """
    data/pass/1_brutes/<type-candidature>/YYYY-MM-DD/
    """

    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")

    output_folder = (
        BASE_DIR
        / "data"
        / "pass"
        / "1_brutes"
        / candidature_type
        / today
    )

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    filepath = output_folder / (
        f"offres_pass_{candidature_type}_{today}_{timestamp}.csv"
    )

    with filepath.open(
        mode="w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=FIELDNAMES,
        )
        writer.writeheader()
        writer.writerows(rows)

    return filepath


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collecte les offres d'apprentissage et de stage "
            "de la fonction publique (site PASS)."
        )
    )

    parser.add_argument(
        "--type-candidature",
        choices=TYPES_CANDIDATURE,
        default=TYPE_CANDIDATURE_ALTERNANCE,
        help=(
            "alternance (apprentissage), stage ou tous. "
            "Défaut : alternance."
        ),
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

    site_contract_types = SITE_CONTRACT_TYPES[args.type_candidature]

    print("==============================================")
    print("Collecte PASS (fonction publique)")
    print("==============================================")
    print(f"Type : {args.type_candidature} ({', '.join(site_contract_types)})")
    print(f"Mots-clés : {len(keywords)}")
    print(f"Ancienneté maximale : {args.max_anciennete_jours} jours")

    results_by_url: dict[str, dict] = {}

    for index, keyword in enumerate(keywords, start=1):
        results = search_keyword(
            client=client,
            keyword=keyword,
            site_contract_types=site_contract_types,
        )

        new_results = 0

        for result in results:
            if result["url"] not in results_by_url:
                results_by_url[result["url"]] = result
                new_results += 1

        print(
            f"[{index}/{len(keywords)}] '{keyword}' : "
            f"{len(results)} offre(s), {new_results} nouvelle(s)"
        )

    recent_results = [
        result
        for result in results_by_url.values()
        if is_recent(result["date_creation"], args.max_anciennete_jours)
    ]

    print(
        f"\n{len(results_by_url)} offre(s) unique(s), "
        f"{len(recent_results)} publiée(s) depuis "
        f"{args.max_anciennete_jours} jours."
    )

    if recent_results:
        print("Lecture du détail de chaque offre...")

    rows = []
    rejected = 0

    for index, result in enumerate(recent_results, start=1):
        try:
            details = parse_offer_page(
                client.get_document(result["url"])
            )
        except requests.RequestException as error:
            print(f"  [{index}] Ignorée (erreur réseau) : {result['url']} ({error})")
            continue

        row = build_csv_row(result, details)

        matched = matches_keywords(
            f"{row['intitule']}\n{details['description_poste']}",
            keywords,
        )

        if not matched and not args.sans_filtre_mots_cles:
            rejected += 1
            continue

        rows.append(row)

        print(
            f"  [{index}/{len(recent_results)}] {row['intitule'][:70]} "
            f"- {row['entreprise'][:40]}"
        )

    print(
        f"\n{len(rows)} offre(s) gardée(s), {rejected} écartée(s) "
        "car aucun mot-clé n'apparaît dans l'intitulé ou le poste."
    )

    filepath = save_offers(
        rows=rows,
        candidature_type=args.type_candidature,
    )

    print(f"\nFichier : {filepath}")


if __name__ == "__main__":
    main()
