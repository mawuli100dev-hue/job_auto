# job_automation/src/job_automation/paths.py

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from common.slug import slugify
from domain.models import ApplicationTarget


# ---------------------------------------------------------------------------
# Organisation du dossier data/
#
# data/<source>/1_brutes/<type>/<date>/        offres collectées
# data/<source>/2_filtrees/<type>/<date>/      offres filtrées
# data/<source>/3_candidatures/<date>/<dossier>/  CV, lettre, PDF à envoyer
#
# Le registre (data/offres_traitees.csv) et les annexes (data/extra/)
# restent communs à toutes les sources.
# ---------------------------------------------------------------------------

SOURCE_FRANCE_TRAVAIL = "france_travail"
SOURCE_LBA = "la_bonne_alternance"
SOURCE_PASS = "pass"
SOURCE_ENGAGEMENT_JEUNES = "engagement_jeunes"
SOURCE_LETUDIANT = "letudiant"
SOURCE_LINKEDIN = "linkedin"
SOURCE_MANUAL = "manuelles"
SOURCE_SPONTANEOUS = "spontanees"

SOURCE_FOLDERS = (
    SOURCE_FRANCE_TRAVAIL,
    SOURCE_LBA,
    SOURCE_PASS,
    SOURCE_ENGAGEMENT_JEUNES,
    SOURCE_LETUDIANT,
    SOURCE_LINKEDIN,
    SOURCE_MANUAL,
    SOURCE_SPONTANEOUS,
)

# Offres repérées par les alertes e-mail, en attente de leur description.
STAGE_TO_COMPLETE = "0_a_completer"
STAGE_RAW = "1_brutes"
STAGE_FILTERED = "2_filtrees"
STAGE_APPLICATIONS = "3_candidatures"

# Ancien emplacement des candidatures, encore lu par merge_dossier.py.
LEGACY_APPLICATIONS_DIR = Path("data") / "candidatures"


def source_stage_dir(
    project_root: Path,
    source: str,
    stage: str,
) -> Path:
    return project_root / "data" / source / stage


def source_from_value(
    value: object,
    source_type: str = "published",
) -> str:
    """
    Dossier source d'après la colonne « source » d'un CSV.
    Une colonne vide vient de France Travail (le collecteur ne
    l'écrivait pas) ; une valeur inconnue (linkedin...) d'une offre
    ajoutée à la main.
    """

    if source_type == "spontaneous":
        return SOURCE_SPONTANEOUS

    text = str(value or "").strip().lower().replace(" ", "_")

    aliases = {
        "": SOURCE_FRANCE_TRAVAIL,
        "francetravail": SOURCE_FRANCE_TRAVAIL,
        "france_travail": SOURCE_FRANCE_TRAVAIL,
        "la_bonne_alternance": SOURCE_LBA,
        "lba": SOURCE_LBA,
        "pass": SOURCE_PASS,
        "engagement_jeunes": SOURCE_ENGAGEMENT_JEUNES,
        "letudiant": SOURCE_LETUDIANT,
        "linkedin": SOURCE_LINKEDIN,
    }

    return aliases.get(text, SOURCE_MANUAL)


def source_from_path(
    project_root: Path,
    path: Path,
) -> str | None:
    """
    Source d'un fichier rangé dans data/<source>/..., sinon None.
    """

    try:
        relative = path.resolve().relative_to(
            (project_root / "data").resolve()
        )
    except ValueError:
        return None

    if relative.parts and relative.parts[0] in SOURCE_FOLDERS:
        return relative.parts[0]

    return None


def all_application_dirs(
    project_root: Path,
) -> list[Path]:
    """
    Tous les dossiers 3_candidatures existants, plus l'ancien
    data/candidatures.
    """

    directories = [
        source_stage_dir(project_root, source, STAGE_APPLICATIONS)
        for source in SOURCE_FOLDERS
    ]

    directories.append(project_root / LEGACY_APPLICATIONS_DIR)

    return [
        directory
        for directory in directories
        if directory.exists()
    ]


def resolve_source_folder(
    project_root: Path,
    csv_path: Path,
    target: ApplicationTarget,
) -> str:
    """
    Les candidatures sont rangées dans la source du CSV traité
    (data/<source>/2_filtrees/...), pour que tout ce qui vient d'une
    source reste au même endroit. Un CSV rangé ailleurs utilise la
    colonne « source » de l'offre.
    """

    return (
        source_from_path(project_root, csv_path)
        or source_from_value(target.origin, target.source_type)
    )


@dataclass(frozen=True)
class ApplicationPaths:
    directory: Path

    # CV : noms conservés pour la compatibilité
    pdf: Path
    docx: Path
    cv_data: Path

    # Lettre
    letter_pdf: Path
    letter_docx: Path
    letter_data: Path

    # Source de la candidature
    source_snapshot: Path


def build_application_paths(
    project_root: Path,
    target: ApplicationTarget,
    generation_date: str | None = None,
    output_directory: Path | None = None,
    source_folder: str | None = None,
) -> ApplicationPaths:
    """
    Dossier de candidature :
    data/<source>/3_candidatures/<date>/<entreprise>_<id>/

    source_folder vient du CSV (voir resolve_source_folder) ; à défaut,
    il est déduit de la colonne « source » de l'offre.
    """

    source_folder = source_folder or source_from_value(
        target.origin,
        target.source_type,
    )

    date_value = (
        generation_date
        or datetime.now().strftime("%Y-%m-%d")
    )

    if output_directory is not None:
        directory = output_directory.resolve()
    else:
        company_slug = slugify(
            target.company_name
        )

        identifier = slugify(
            target.external_id
            or target.application_id
        )

        directory_name = (
            f"{company_slug}_{identifier}"
        )

        directory = (
            source_stage_dir(
                project_root,
                source_folder,
                STAGE_APPLICATIONS,
            )
            / date_value
            / directory_name
        )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return ApplicationPaths(
        directory=directory,

        pdf=(
            directory
            / "CV_Henoc_AMAVIGAN.pdf"
        ),

        docx=(
            directory
            / "CV_Henoc_AMAVIGAN.docx"
        ),

        cv_data=(
            directory
            / "cv_data.json"
        ),

        letter_pdf=(
            directory
            / "LM_Henoc_AMAVIGAN.pdf"
        ),

        letter_docx=(
            directory
            / "LM_Henoc_AMAVIGAN.docx"
        ),

        letter_data=(
            directory
            / "letter_data.json"
        ),

        source_snapshot=(
            directory
            / "offre.txt"
        ),
    )