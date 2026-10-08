# job_automation/src/offers/fingerprint.py

"""
Empreinte d'une offre pour repérer la même offre publiée sur plusieurs
sources (France Travail, La Bonne Alternance, PASS...), avec des
identifiants différents que le registre ne peut pas rapprocher.

Deux offres sont considérées identiques si elles ont la même entreprise
et le même intitulé, une fois retirés :
- les formes juridiques (SAS, SE, SARL...) ;
- les mentions de contrat ou de genre (Alternance, Stage, H/F...) ;
- le contenu entre parenthèses et les morceaux annexes séparés par
  « - » ou « | » (souvent la ville).

Le lieu départage les postes au même intitulé dans plusieurs villes
(« Développeur IA » d'Atos à Strasbourg et à Villeurbanne) : deux offres
ne sont des doublons que si leurs villes se recoupent, ou si l'une
d'elles n'a pas de lieu.

Une offre sans entreprise connue n'a pas d'empreinte : deux offres
« Data Analyst » d'entreprises inconnues ne sont jamais fusionnées.

Les candidatures déjà préparées sont lues dans data/candidatures_index.csv,
complété automatiquement à partir des dossiers de candidature : les dossiers
peuvent être supprimés sans perdre la détection des doublons.
"""

import csv
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from paths import all_application_dirs


COMPANY_NOISE = {
    "sas", "sasu", "sa", "sarl", "se", "eurl", "snc", "sca",
    "groupe", "group", "france", "the",
}

UNKNOWN_COMPANIES = {
    "", "non precise", "non precisee", "non communique",
    "non communiquee", "inconnu", "inconnue", "na",
}

TITLE_NOISE = {
    "h", "f", "hf", "fh", "x", "m", "w", "e", "se", "ne",
    "homme", "femme",
    "alternance", "alternant", "alternante", "alternants",
    "apprenti", "apprentie", "apprentis", "apprentissage",
    "stage", "stagiaire", "stagiaires", "contrat", "offre", "poste",
    "en", "de", "d", "du", "des", "la", "le", "les", "l", "et",
    "a", "au", "aux", "pour", "un", "une",
}


def _normalize(text: object) -> str:
    value = unicodedata.normalize(
        "NFKD",
        str(text or "").lower(),
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _company_key(company: object) -> str:
    normalized = _normalize(company)

    if normalized in UNKNOWN_COMPANIES:
        return ""

    return " ".join(
        word
        for word in normalized.split()
        if word not in COMPANY_NOISE
    )


def _title_key(title: object) -> str:
    text = re.sub(r"\([^)]*\)", " ", str(title or ""))

    # Le morceau le plus riche est l'intitulé ; les autres sont
    # souvent la ville ou le type de contrat.
    best_words: list[str] = []

    for part in re.split(r"\s[-–|]\s|\|", text):
        words = [
            word
            for word in _normalize(part).split()
            if word not in TITLE_NOISE
        ]

        if len(words) > len(best_words):
            best_words = words

    return " ".join(sorted(set(best_words)))


LOCATION_NOISE = {
    "cedex", "arrondissement", "er", "e", "eme", "le", "la", "les",
    "sur", "sous", "en", "de", "du", "des", "et", "france",
}


def location_words(location: object) -> set[str]:
    """
    Mots du lieu sans codes postaux ni numéros de département :
    « 75 - Paris 12e Arrondissement » -> {"paris"}.
    """

    return {
        word
        for word in _normalize(location).split()
        if not word[0].isdigit()
        and word not in LOCATION_NOISE
        and len(word) > 1
    }


def same_place(first: object, second: object) -> bool:
    first_words = location_words(first)
    second_words = location_words(second)

    if not first_words or not second_words:
        return True

    return bool(first_words & second_words)


def offer_fingerprint(
    company: object,
    title: object,
) -> str | None:
    company_key = _company_key(company)
    title_key = _title_key(title)

    if not company_key or not title_key:
        return None

    return f"{company_key}|{title_key}"


# ---------------------------------------------------------------------------
# Index des candidatures préparées
#
# data/candidatures_index.csv garde une ligne par candidature préparée,
# toutes sources confondues. Il permet de repérer les doublons même après
# la suppression des dossiers de candidature pour gagner de la place.
# ---------------------------------------------------------------------------

INDEX_RELATIVE_PATH = Path("data") / "candidatures_index.csv"

INDEX_FIELDS = [
    "date",
    "source",
    "type_candidature",
    "id",
    "entreprise",
    "intitule",
    "lieu",
    "dossier",
]


def _index_path(project_root: Path) -> Path:
    return project_root / INDEX_RELATIVE_PATH


def _read_index(project_root: Path) -> list[dict]:
    path = _index_path(project_root)

    if not path.exists():
        return []

    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def _append_index_rows(
    project_root: Path,
    rows: list[dict],
) -> None:
    if not rows:
        return

    path = _index_path(project_root)
    is_new = not path.exists()

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8-sig" if is_new else "utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=INDEX_FIELDS, extrasaction="ignore")

        if is_new:
            writer.writeheader()

        writer.writerows(rows)


def _index_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("id", "")).strip(),
        _normalize(row.get("entreprise", "")),
        _normalize(row.get("intitule", "")),
    )


def _relative_dossier(project_root: Path, directory: Path) -> str:
    try:
        return str(directory.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(directory)


def record_application(
    project_root: Path,
    source: str,
    contract_type: str,
    offer_id: str,
    company: str,
    title: str,
    location: str,
    directory: Path,
    date: str | None = None,
) -> None:
    """
    Ajoute une candidature préparée à l'index, si elle n'y est pas déjà.
    Appelé par generate_letter.py une fois la lettre générée.
    """

    row = {
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "source": source,
        "type_candidature": contract_type,
        "id": offer_id,
        "entreprise": company,
        "intitule": title,
        "lieu": location,
        "dossier": _relative_dossier(project_root, directory),
    }

    known = {_index_key(existing) for existing in _read_index(project_root)}

    if _index_key(row) not in known:
        _append_index_rows(project_root, [row])


def _rows_from_folders(project_root: Path) -> list[dict]:
    """
    Candidatures trouvées dans les dossiers data/<source>/3_candidatures
    (et l'ancien data/candidatures), au format de l'index.
    """

    rows = []

    for directory in all_application_dirs(project_root):
        for cv_data_path in directory.rglob("cv_data.json"):
            try:
                data = json.loads(cv_data_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue

            target = data.get("target") or {}
            offer = data.get("offer") or {}
            application = data.get("application") or {}
            folder = cv_data_path.parent

            # data/<source>/3_candidatures/<date>/<dossier>
            parts = folder.resolve().relative_to(project_root.resolve()).parts

            rows.append(
                {
                    "date": parts[-2] if len(parts) >= 2 else "",
                    "source": parts[1] if len(parts) >= 5 else "",
                    "type_candidature": (
                        target.get("contract_type")
                        or application.get("contract_type")
                        or ""
                    ),
                    "id": str(
                        target.get("external_id")
                        or data.get("offer_id")
                        or ""
                    ),
                    "entreprise": target.get("company_name") or offer.get("entreprise") or "",
                    "intitule": target.get("job_title") or offer.get("intitule") or "",
                    "lieu": target.get("location") or offer.get("lieu") or "",
                    "dossier": _relative_dossier(project_root, folder),
                }
            )

    return rows


def existing_applications(
    project_root: Path,
) -> list[dict]:
    """
    Candidatures déjà préparées, toutes sources confondues : celles de
    l'index, plus celles des dossiers encore présents. Un dossier absent
    de l'index y est ajouté au passage : l'index se remplit tout seul,
    et reste complet si les dossiers sont supprimés ensuite.
    """

    index_rows = _read_index(project_root)
    known = {_index_key(row) for row in index_rows}

    missing_rows = []

    for row in _rows_from_folders(project_root):
        key = _index_key(row)

        if key not in known:
            known.add(key)
            missing_rows.append(row)

    _append_index_rows(project_root, missing_rows)

    applications = []

    for row in index_rows + missing_rows:
        fingerprint = offer_fingerprint(row.get("entreprise"), row.get("intitule"))

        if fingerprint:
            applications.append(
                {
                    "fingerprint": fingerprint,
                    "location": row.get("lieu", ""),
                    "external_id": str(row.get("id", "")),
                    "directory": project_root / row.get("dossier", ""),
                }
            )

    return applications


def find_duplicate_application(
    project_root: Path,
    company: object,
    title: object,
    offer_id: str,
    applications: list[dict] | None = None,
    location: object = "",
) -> Path | None:
    """
    Dossier d'une candidature déjà préparée pour la même offre venue
    d'une autre source, ou None. Une candidature au même identifiant
    n'est pas un doublon : c'est le registre qui la gère.
    """

    fingerprint = offer_fingerprint(company, title)

    if fingerprint is None:
        return None

    if applications is None:
        applications = existing_applications(project_root)

    for application in applications:
        if (
            application["fingerprint"] == fingerprint
            and application["external_id"] != str(offer_id)
            and same_place(application["location"], location)
        ):
            return application["directory"]

    return None
