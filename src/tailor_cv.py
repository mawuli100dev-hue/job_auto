# src/tailor_cv.py

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from common.json_utils  import load_json
from cv.artifact_writer import (
    CvArtifactWriter,
)
from cv.experience_selector import (
    ExperienceSelector,
)
from cv.skill_selector import (
    SkillSelector,
)
from cv.subtitle_generator import (
    SubtitleGenerator,
)
from documents.docx_cv_renderer import (
    DocxCvRenderer,
)
from documents.html_cv_renderer import (
    HtmlCvRenderer,
)
from documents.pdf_cv_renderer import (
    PdfCvRenderer,
)
from llm.json_client import JsonLlmClient
from offers.csv_repository import (
    CsvOfferRepository,
)
from offers.normalizer import (
    normalize_published_offer,
    normalize_spontaneous_target,
)
from paths import (
    build_application_paths,
    resolve_source_folder,
)
from services.cv_service import (
    CvService,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(
    PROJECT_ROOT / ".env"
)

DEFAULT_MODEL = "openai/gpt-4o-mini"


def resolve_path(
    value: str,
) -> Path:
    path = Path(value).expanduser()

    if not path.is_absolute():
        path = Path.cwd() / path

    return path.resolve()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Génère un CV adapté au format PDF "
            "et Word."
        )
    )

    parser.add_argument(
        "--csv",
        required=True,
        help="CSV contenant l'offre ciblée.",
    )

    parser.add_argument(
        "--offer-id",
        required=True,
        help="Identifiant de l'offre à traiter.",
    )

    parser.add_argument(
        "--source-type",
        choices=[
            "published",
            "spontaneous",
        ],
        default="published",
        help=(
            "Source de la candidature : "
            "published ou spontaneous. "
            "Défaut : published."
        ),
    )

    parser.add_argument(
        "--type-candidature",
        choices=[
            "alternance",
            "stage",
        ],
        default=None,
        help=(
            "Type de candidature. Si absent, le script "
            "utilise la colonne type_candidature du CSV. "
            "Pour les anciens CSV, alternance est utilisée."
        ),
    )

    parser.add_argument(
        "--experiences",
        default=str(
            PROJECT_ROOT / "experiences.json"
        ),
        help=(
            "Chemin du fichier JSON contenant "
            "les expériences."
        ),
    )

    parser.add_argument(
        "--competences-pool",
        default=str(
            PROJECT_ROOT
            / "competences_pool.json"
        ),
        help=(
            "Chemin du fichier JSON contenant "
            "la banque de compétences."
        ),
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=4,
        help=(
            "Nombre d'expériences affichées, "
            "épinglées comprises. Défaut : 4 "
            "(le tutorat épinglé + les 3 plus pertinentes)."
        ),
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "Modèle OpenRouter utilisé pour "
            "l'adaptation du CV."
        ),
    )

    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.top_n <= 0:
        parser.error(
            "--top-n doit être supérieur à zéro."
        )

    api_key = os.getenv(
        "OPENROUTER_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY doit être "
            "défini dans le fichier .env."
        )

    csv_path = resolve_path(
        args.csv
    )

    experiences_path = resolve_path(
        args.experiences
    )

    skills_pool_path = resolve_path(
        args.competences_pool
    )

    offer_repository = CsvOfferRepository()

    offer_row = offer_repository.find_by_id(
        csv_path=csv_path,
        offer_id=args.offer_id,
    )

    # Même normalisation que generate_letter.py : le dossier de
    # candidature (et donc cv_data.json) en dépend.
    if args.source_type == "published":
        target = normalize_published_offer(
            row=offer_row,
            requested_contract_type=(
                args.type_candidature
            ),
        )
    else:
        target = normalize_spontaneous_target(
            row=offer_row,
            requested_contract_type=(
                args.type_candidature
            ),
        )

    experiences = load_json(
        experiences_path
    )

    skills_pool = load_json(
        skills_pool_path
    )

    if not isinstance(experiences, list):
        raise ValueError(
            "experiences.json doit contenir "
            "une liste."
        )

    if not isinstance(skills_pool, dict):
        raise ValueError(
            "competences_pool.json doit contenir "
            "un objet JSON."
        )

    llm_client = JsonLlmClient(
        api_key=api_key,
        model=args.model,
    )

    html_renderer = HtmlCvRenderer()

    service = CvService(
        subtitle_generator=SubtitleGenerator(
            llm_client=llm_client,
        ),
        experience_selector=ExperienceSelector(
            llm_client=llm_client,
        ),
        skill_selector=SkillSelector(
            llm_client=llm_client,
        ),
        pdf_renderer=PdfCvRenderer(
            html_renderer=html_renderer,
        ),
        docx_renderer=DocxCvRenderer(),
        artifact_writer=CvArtifactWriter(),
    )

    paths = build_application_paths(
        project_root=PROJECT_ROOT,
        target=target,
        source_folder=resolve_source_folder(
            project_root=PROJECT_ROOT,
            csv_path=csv_path,
            target=target,
        ),
    )

    result = service.prepare(
        target=target,
        experiences=experiences,
        skills_pool=skills_pool,
        paths=paths,
        top_n=args.top_n,
    )

    print("\n==============================================")
    print("CV généré avec succès")
    print("==============================================")
    print(
        f"PDF : {result.pdf_path}"
    )
    print(
        f"Word : {result.docx_path}"
    )
    print(
        f"Données : {result.cv_data_path}"
    )
    print(
        f"Échelle PDF : {result.scale_used:.2f}"
    )


if __name__ == "__main__":
    main()
