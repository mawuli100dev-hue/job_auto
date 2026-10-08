"""
collect_alerts_gmail.py

Lit les alertes emploi LinkedIn reçues dans Gmail et prépare la liste des
nouvelles offres à compléter :

data/linkedin/0_a_completer/<date>/offres_linkedin_a_completer_<date>_<heure>.csv

Les e-mails d'alerte donnent l'intitulé, l'entreprise, le lieu et le lien,
mais pas la description. Elle est ajoutée ensuite avec completer_offres.py,
en ouvrant chaque offre dans le navigateur.

Connexion
---------
Le script se connecte à Gmail en IMAP, en LECTURE SEULE : aucun e-mail n'est
modifié, supprimé ni marqué comme lu. Il lit dans .env :

    GMAIL_ADDRESS=adresse@gmail.com
    GMAIL_APP_PASSWORD=mot de passe d'application Google (16 lettres)

Offres retenues
---------------
Une offre n'est pas reprise si elle figure déjà :
- dans une liste à compléter ou un CSV LinkedIn précédent (même identifiant) ;
- dans le registre des offres traitées ;
- dans l'index des candidatures (même entreprise, intitulé et ville).

Exemples
--------

python src\\collect_alerts_gmail.py
python src\\collect_alerts_gmail.py --jours 3
"""

import argparse
import csv
import email
import email.message
import email.utils
import imaplib
import os
import re
import sys
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

from dotenv import load_dotenv

from offers.fingerprint import (
    existing_applications,
    find_duplicate_application,
)
from paths import (
    SOURCE_LINKEDIN,
    STAGE_RAW,
    STAGE_TO_COMPLETE,
    source_stage_dir,
)
from registre_offres import (
    DEFAULT_REGISTRY_PATH,
    is_already_processed,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

IMAP_HOST = "imap.gmail.com"

# Expéditeurs des alertes emploi.
LINKEDIN_ALERT_SENDER = "jobalerts-noreply@linkedin.com"

JOURS_DEFAUT = 7

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
    "alerte",
]

STAGE_WORDS = ("stage", "stagiaire", "intern", "internship", "stagiaires")
ALTERNANCE_WORDS = (
    "alternance", "alternant", "alternante", "apprenti", "apprentie",
    "apprentissage", "apprenticeship", "work study", "work-study",
)

OFFER_LINK_PATTERN = re.compile(
    r"https://www\.linkedin\.com/comm/jobs/view/(\d+)"
)


# ---------------------------------------------------------------------------
# Lecture des e-mails
# ---------------------------------------------------------------------------

def decoded_header(value: object) -> str:
    return str(make_header(decode_header(str(value or ""))))


def plain_text(message: email.message.Message) -> str:
    for part in message.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            text = payload.decode(part.get_content_charset() or "utf-8", "replace")

            # Les e-mails utilisent des fins de ligne Windows (\r\n).
            return text.replace("\r\n", "\n").replace("\r", "\n")

    return ""


def fetch_alert_messages(days: int) -> list[email.message.Message]:
    address = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")

    if not address or not password:
        sys.exit(
            "GMAIL_ADDRESS et GMAIL_APP_PASSWORD doivent être définis "
            "dans le fichier .env."
        )

    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")

    imap = imaplib.IMAP4_SSL(IMAP_HOST, 993)

    try:
        imap.login(address, password.replace(" ", ""))
    except imaplib.IMAP4.error as error:
        sys.exit(
            f"Connexion à Gmail refusée ({error}). Vérifie GMAIL_ADDRESS "
            "et le mot de passe d'application dans .env."
        )

    try:
        # Lecture seule : les e-mails ne sont ni modifiés ni marqués lus.
        imap.select("INBOX", readonly=True)

        _, data = imap.search(
            None,
            f'(FROM "{LINKEDIN_ALERT_SENDER}" SINCE {since})',
        )

        messages = []

        for message_id in data[0].split():
            _, message_data = imap.fetch(message_id, "(BODY.PEEK[])")
            messages.append(email.message_from_bytes(message_data[0][1]))

        return messages
    finally:
        imap.logout()


# ---------------------------------------------------------------------------
# Lecture d'une alerte LinkedIn
# ---------------------------------------------------------------------------

def alert_name(subject: str) -> str:
    """
    « Hénoc : votre alerte Emploi pour Data Science (France) a été créée »
    -> « Data Science (France) ».
    """

    match = re.search(r"alerte (?:Emploi )?pour (.+?)(?: a été créée)?$", subject)

    return match.group(1).strip() if match else subject


def contract_type_from_title(title: str) -> str:
    text = f" {re.sub(r'[^a-z]+', ' ', title.lower())} "

    if any(f" {word} " in text for word in ALTERNANCE_WORDS):
        return "alternance"

    if any(f" {word} " in text for word in STAGE_WORDS):
        return "stage"

    return ""


def parse_linkedin_alert(
    text: str,
    alert: str,
    received: str,
) -> list[dict]:
    """
    Chaque offre est un bloc :

        Intitulé
        Entreprise
        Lieu
        (lignes facultatives : relations, « recrute activement »...)
        Voir l’offre d’emploi : https://www.linkedin.com/comm/jobs/view/<numéro>?...
    """

    rows = []

    for block in re.split(r"\n-{10,}\n", text):
        link = OFFER_LINK_PATTERN.search(block)

        if not link:
            continue

        before_link = block[: link.start()]

        lines = [
            line.strip()
            for line in before_link.splitlines()
            if line.strip()
            and not line.strip().startswith("Voir l")
            and not line.strip().startswith("Votre alerte")
            and not line.strip().startswith("Vous recevrez")
        ]

        if len(lines) < 3:
            continue

        title, company, location = lines[0], lines[1], lines[2]
        job_id = link.group(1)

        rows.append(
            {
                "id": f"LI-{job_id}",
                "source": SOURCE_LINKEDIN,
                "type_candidature": contract_type_from_title(title),
                "intitule": title,
                "entreprise": company,
                "lieu": location,
                "date_creation": received,
                "description": "",
                # Lien sans les jetons de connexion de l'e-mail.
                "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
                "alerte": alert,
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Offres déjà connues
# ---------------------------------------------------------------------------

def known_linkedin_ids() -> set[str]:
    """
    Identifiants déjà présents dans les listes à compléter et les CSV
    LinkedIn précédents.
    """

    ids = set()

    for stage in (STAGE_TO_COMPLETE, STAGE_RAW):
        folder = source_stage_dir(PROJECT_ROOT, SOURCE_LINKEDIN, stage)

        if not folder.exists():
            continue

        for path in folder.rglob("*.csv"):
            with path.open(encoding="utf-8-sig", newline="") as csv_file:
                ids.update(
                    str(row.get("id", "")).strip()
                    for row in csv.DictReader(csv_file)
                )

    return ids


def already_processed(row: dict) -> bool:
    contract_types = (
        [row["type_candidature"]]
        if row["type_candidature"]
        else ["alternance", "stage"]
    )

    return any(
        is_already_processed(
            application_id=row["id"],
            path=DEFAULT_REGISTRY_PATH,
            contract_type=contract_type,
        )
        for contract_type in contract_types
    )


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Lit les alertes emploi LinkedIn de Gmail et prépare la "
            "liste des nouvelles offres à compléter."
        )
    )

    parser.add_argument(
        "--jours",
        type=int,
        default=JOURS_DEFAUT,
        help=f"Lit les alertes reçues depuis ce nombre de jours. Défaut : {JOURS_DEFAUT}.",
    )

    args = parser.parse_args()

    print("==============================================")
    print("Alertes LinkedIn (Gmail, lecture seule)")
    print("==============================================")

    messages = fetch_alert_messages(args.jours)

    print(f"{len(messages)} e-mail(s) d'alerte depuis {args.jours} jour(s).")

    offers: dict[str, dict] = {}

    for message in messages:
        subject = decoded_header(message["Subject"])

        try:
            received = email.utils.parsedate_to_datetime(message["Date"]).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            received = ""

        for row in parse_linkedin_alert(plain_text(message), alert_name(subject), received):
            offers.setdefault(row["id"], row)

    known_ids = known_linkedin_ids()
    applications = existing_applications(PROJECT_ROOT)

    new_rows = []
    skipped = {"déjà listée": 0, "déjà traitée": 0, "déjà préparée (autre source)": 0}

    for row in offers.values():
        if row["id"] in known_ids:
            skipped["déjà listée"] += 1
        elif already_processed(row):
            skipped["déjà traitée"] += 1
        elif find_duplicate_application(
            project_root=PROJECT_ROOT,
            company=row["entreprise"],
            title=row["intitule"],
            offer_id=row["id"],
            applications=applications,
            location=row["lieu"],
        ):
            skipped["déjà préparée (autre source)"] += 1
        else:
            new_rows.append(row)

    print(f"{len(offers)} offre(s) dans les alertes.")

    for reason, count in skipped.items():
        if count:
            print(f"  {count} écartée(s) : {reason}")

    if not new_rows:
        print("\nAucune nouvelle offre.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    folder = source_stage_dir(PROJECT_ROOT, SOURCE_LINKEDIN, STAGE_TO_COMPLETE) / today
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / (
        f"offres_linkedin_a_completer_{today}_{datetime.now().strftime('%H%M%S')}.csv"
    )

    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(new_rows)

    print(f"\n{len(new_rows)} nouvelle(s) offre(s) à compléter :")

    for row in new_rows:
        contract = row["type_candidature"] or "type à préciser"
        print(f"  - [{contract}] {row['intitule'][:60]} - {row['entreprise'][:30]} ({row['lieu'][:25]})")

    print(f"\nFichier : {path}")
    print("Étape suivante : python src\\completer_offres.py")


if __name__ == "__main__":
    main()
