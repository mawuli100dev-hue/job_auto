"""
collect_offers_sfds.py

Collecte les offres de stage publiées par la Société Française de Statistique
(SFdS, https://www.sfds.asso.fr) et les enregistre dans :

data/sfds/1_brutes/stage/<date>/offres_sfds_stage_<date>_<heure>.csv

Le CSV a les mêmes colonnes principales que les autres collecteurs : il
passe ensuite dans filter_offers.py puis run_pipeline.ps1.

Fonctionnement
--------------
1. Lecture de la page des offres de stage (une seule page, sans pagination).
   Chaque offre y figure en entier, y compris le bloc qui s'affiche au clic :
   organisme, niveau, sujet, date de début, durée, description, liens et
   contact.
2. Téléchargement des PDF joints hébergés par la SFdS (« sdoc-...pdf ») et
   extraction de leur texte : c'est la description détaillée de l'offre.
   Les liens vers d'autres sites sont conservés mais pas visités.
3. L'adresse e-mail du contact devient le destinataire de la lettre.

Le site autorise les robots sur toutes ses pages (robots.txt « Allow: / »).
Le script fait une pause entre deux téléchargements.

Les offres sont de niveau master ou doctorat : la lettre contient alors la
phrase sur l'écart de niveau (letter/advanced_level.py).

Exemples
--------

python src\\collect_offers_sfds.py
python src\\collect_offers_sfds.py --max-anciennete-jours 14
"""

import argparse
import csv
import io
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import lxml.html
import requests
from pypdf import PdfReader

from collect_offers_pass import (
    USER_AGENT,
    clean_spaces,
)


BASE_DIR = Path(__file__).resolve().parent.parent

# pypdf signale certaines polices des PDF (« fontTools is required ») sans
# que le texte extrait en souffre : ces avertissements encombrent la console.
logging.getLogger("pypdf").setLevel(logging.ERROR)

SITE_URL = "https://www.sfds.asso.fr"
OFFERS_URL = f"{SITE_URL}/fr/n/506-consulter_les_offres_demploi/"

ANCIENNETE_MAX_JOURS_DEFAUT = 30
DELAI_ENTRE_REQUETES_SEC = 1.0

# Au-delà, le texte du PDF est tronqué : la lettre lit au plus 4 000
# caractères de description.
MAX_PDF_TEXT_LENGTH = 6000

FIELDNAMES = [
    "id",
    "source",
    "type_candidature",
    "intitule",
    "entreprise",
    "lieu",
    "type_contrat",
    "duree_contrat",
    "date_debut",
    "date_creation",
    "niveau_diplome",
    "domaine",
    "description",
    "recipient_email",
    "url",
    "pdf",
]


# ---------------------------------------------------------------------------
# Accès au site
# ---------------------------------------------------------------------------

class SfdsClient:
    def __init__(self, delay_sec: float) -> None:
        self.delay_sec = delay_sec
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.last_request = 0.0

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        wait = self.delay_sec - (time.time() - self.last_request)

        if wait > 0:
            time.sleep(wait)

        self.last_request = time.time()

        response = self.session.get(url, params=params, timeout=60)
        response.raise_for_status()

        return response


# ---------------------------------------------------------------------------
# Page des offres
# ---------------------------------------------------------------------------

def cell_text(cell: lxml.html.HtmlElement) -> str:
    for br in cell.xpath(".//br"):
        br.tail = "\n" + (br.tail or "")

    return clean_spaces(cell.text_content())


def parse_published(text: str) -> str:
    """
    « Publiée le 12/10/2026 13:31. » -> « 2026-10-12T13:31:00 ».
    """

    match = re.search(r"(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}))?", text)

    if not match:
        return ""

    day, month, year, hour, minute = match.groups()

    return f"{year}-{month}-{day}T{hour or '00'}:{minute or '00'}:00"


def parse_offers(document: lxml.html.HtmlElement) -> list[dict]:
    offers = []

    for job in document.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' job ')]"):
        job_id = (job.get("id") or "").replace("job", "")

        title = job.xpath(".//td[contains(@class, 'jobLabel')]")
        published = job.xpath(".//td[contains(@class, 'jobPublished')]")
        resume = job.xpath(".//td[contains(@class, 'jobResume')]")

        if not title or not job_id:
            continue

        # « Stage, Vannes. » : contrat puis lieu (avant le bloc de détails).
        resume_text = clean_spaces(resume[0].text or "") if resume else ""
        contract, _, place = resume_text.partition(",")

        fields: dict[str, str] = {}
        links: list[str] = []
        emails: list[str] = []

        for row in job.xpath(".//tr[td[contains(@class, 'jobListLabel')]]"):
            label = clean_spaces(row.xpath("./td[contains(@class, 'jobListLabel')]")[0].text_content())
            label = label.replace("\xa0", " ").rstrip(" :").strip()
            value_cell = row.xpath("./td[contains(@class, 'jobListValue')]")[0]

            for href in value_cell.xpath(".//a/@href"):
                href = href.strip()

                if href.startswith("mailto:"):
                    emails.append(href.removeprefix("mailto:").strip())
                elif href.startswith(("http://", "https://", "/")):
                    # Le site affiche « No link » quand l'annonceur n'a
                    # pas donné de lien : ce texte n'est pas une adresse.
                    links.append(urljoin(SITE_URL, href))

            fields[label] = cell_text(value_cell)

        offers.append(
            {
                "job_id": job_id,
                "title": clean_spaces(title[0].text_content()),
                "published": parse_published(published[0].text_content() if published else ""),
                "contract": contract.strip(),
                "place": place.strip().rstrip("."),
                "fields": fields,
                "links": links,
                "emails": emails,
            }
        )

    return offers


# ---------------------------------------------------------------------------
# PDF joints
# ---------------------------------------------------------------------------

def is_sfds_pdf(url: str) -> bool:
    parsed = urlparse(url)

    return parsed.netloc.endswith("sfds.asso.fr") and parsed.path.lower().endswith(".pdf")


def pdf_text(client: SfdsClient, url: str) -> str:
    response = client.get(url)
    reader = PdfReader(io.BytesIO(response.content))

    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    # Numéros de page (« 1 sur 2 ») et lignes vides en série.
    text = re.sub(r"(?m)^\s*\d+\s+sur\s+\d+\s*$", "", text)
    text = clean_spaces(text)

    return text[:MAX_PDF_TEXT_LENGTH]


# ---------------------------------------------------------------------------
# Ligne du CSV
# ---------------------------------------------------------------------------

def build_csv_row(offer: dict, pdf_texts: list[str]) -> dict:
    fields = offer["fields"]
    sector = fields.get("Secteur d'activité", "")

    external_links = [link for link in offer["links"] if not is_sfds_pdf(link)]
    pdf_links = [link for link in offer["links"] if is_sfds_pdf(link)]

    # Les liens restent visibles dans offre.txt (fin de la description) :
    # le PDF joint est la fiche complète de l'offre.
    link_lines = [
        *(f"Fiche de l'offre (PDF) : {link}" for link in pdf_links),
        *(f"Site de l'organisme : {link}" for link in external_links),
    ]

    description_parts = [
        f"Sujet : {fields['Sujet']}" if fields.get("Sujet") else "",
        fields.get("Description", ""),
        *(f"Description détaillée (document joint) :\n{text}" for text in pdf_texts if text),
        f"Secteur d'activité : {sector}" if sector else "",
        "\n".join(link_lines),
    ]

    return {
        "id": f"SFDS-{offer['job_id']}",
        "source": "sfds",
        "type_candidature": "stage",
        "intitule": offer["title"],
        "entreprise": fields.get("Entreprise/Organisme", "") or "Non precise",
        "lieu": offer["place"],
        "type_contrat": offer["contract"] or "Stage",
        "duree_contrat": fields.get("Durée du contrat", ""),
        "date_debut": fields.get("Date de début", ""),
        "date_creation": offer["published"],
        "niveau_diplome": fields.get("Niveau d'études", ""),
        "domaine": fields.get("Secteur d'activité", ""),
        "description": "\n\n".join(part for part in description_parts if part),
        "recipient_email": offer["emails"][0] if offer["emails"] else "",
        "url": (pdf_links or external_links or [f"{OFFERS_URL}#job{offer['job_id']}"])[0],
        "pdf": " ".join(pdf_links),
    }


def save_offers(rows: list[dict]) -> Path:
    """
    data/sfds/1_brutes/stage/YYYY-MM-DD/
    """

    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")

    folder = BASE_DIR / "data" / "sfds" / "1_brutes" / "stage" / today
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / f"offres_sfds_stage_{today}_{timestamp}.csv"

    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    return path


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collecte les offres de stage de la Société Française de Statistique."
    )

    parser.add_argument(
        "--type-candidature",
        choices=["stage"],
        default="stage",
        help="Le site ne publie pas d'alternances : stage uniquement.",
    )

    parser.add_argument(
        "--max-anciennete-jours",
        type=int,
        default=ANCIENNETE_MAX_JOURS_DEFAUT,
        help=f"Ne garde que les offres publiées depuis ce nombre de jours. Défaut : {ANCIENNETE_MAX_JOURS_DEFAUT}.",
    )

    parser.add_argument(
        "--delai",
        type=float,
        default=DELAI_ENTRE_REQUETES_SEC,
        help=f"Pause en secondes entre deux téléchargements. Défaut : {DELAI_ENTRE_REQUETES_SEC}.",
    )

    args = parser.parse_args()

    client = SfdsClient(delay_sec=args.delai)

    print("==============================================")
    print("Collecte SFdS (Société Française de Statistique)")
    print("==============================================")

    response = client.get(OFFERS_URL, params={"jcon": "STAGE", "jedu": ""})
    response.encoding = "utf-8"
    offers = parse_offers(lxml.html.fromstring(response.text))

    limit = datetime.now() - timedelta(days=args.max_anciennete_jours)

    recent = [
        offer
        for offer in offers
        if not offer["published"] or datetime.fromisoformat(offer["published"]) >= limit
    ]

    print(
        f"{len(offers)} offre(s) de stage, {len(recent)} publiée(s) depuis "
        f"{args.max_anciennete_jours} jour(s).\n"
    )

    rows = []

    for index, offer in enumerate(recent, start=1):
        pdf_texts = []

        for link in offer["links"]:
            if not is_sfds_pdf(link):
                continue

            try:
                pdf_texts.append(pdf_text(client, link))
            except Exception as error:
                print(f"  PDF illisible ({error}) : {link}")

        row = build_csv_row(offer, pdf_texts)
        rows.append(row)

        pdf_info = f"PDF {sum(len(t) for t in pdf_texts)} car." if pdf_texts else "sans PDF"

        print(
            f"  [{index}/{len(recent)}] {row['intitule'][:60]} - "
            f"{row['entreprise'][:30]} ({pdf_info})"
        )

    path = save_offers(rows)

    print(f"\n{len(rows)} offre(s) enregistrée(s).")
    print(f"Fichier : {path}")


if __name__ == "__main__":
    main()
