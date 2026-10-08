# job_automation/src/generate_letter.py

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from common.json_utils import load_json
from documents.docx_letter_renderer import (
    DocxLetterRenderer,
)
from documents.html_letter_renderer import (
    HtmlLetterRenderer,
)
from documents.pdf_letter_renderer import (
    PdfLetterRenderer,
)
from letter.company_context import (
    CompanyContextBuilder,
)
from letter.letter_artifact_writer import (
    LetterArtifactWriter,
)
from letter.letter_context import (
    LetterContextBuilder,
)
from letter.letter_generator import (
    LetterGenerator,
)
from letter.letter_prompt_builder import (
    LetterPromptBuilder,
)
from letter.letter_validator import (
    LetterValidator,
)
from letter.recipient_resolver import (
    RecipientResolver,
)
from llm.json_client import JsonLlmClient
from offers.fingerprint import (
    record_application,
)
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
from services.letter_service import (
    LetterService,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parent.parent

load_dotenv(
    PROJECT_ROOT / ".env"
)

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"


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
            "Génère une lettre de motivation "
            "au format PDF et Word."
        )
    )

    parser.add_argument(
        "--csv",
        "--csv-path",
        "--input",
        dest="csv_path",
        required=True,
        help=(
            "CSV contenant l'offre ou "
            "l'entreprise ciblée."
        ),
    )

    parser.add_argument(
        "--offer-id",
        "--id",
        dest="offer_id",
        required=True,
        help=(
            "Identifiant de la ligne à traiter."
        ),
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
            "Contrat recherché. Si absent, "
            "la valeur du CSV est utilisée."
        ),
    )

    parser.add_argument(
        "--cv-data",
        default=None,
        help=(
            "Chemin explicite vers cv_data.json. "
            "Si absent, le fichier est recherché "
            "dans le dossier de candidature."
        ),
    )

    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Dossier de sortie explicite. "
            "Facultatif."
        ),
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Modèle OpenRouter utilisé.",
    )

    parser.add_argument(
        "--correction-attempts",
        type=int,
        default=1,
        help=(
            "Nombre maximal de corrections automatiques, "
            "limitées aux erreurs bloquantes. Défaut : 1."
        ),
    )

    parser.add_argument(
        "--review",
        action="store_true",
        help=(
            "Active la relecture « recruteur » du "
            "premier jet (un appel LLM payant de plus)."
        ),
    )

    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.correction_attempts < 0:
        parser.error(
            "--correction-attempts doit être "
            "positif ou égal à zéro."
        )

    api_key = os.getenv(
        "OPENROUTER_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY doit être défini "
            "dans le fichier .env."
        )

    csv_path = resolve_path(
        args.csv_path
    )

    repository = CsvOfferRepository()

    target_row = repository.find_by_id(
        csv_path=csv_path,
        offer_id=args.offer_id,
    )

    if args.source_type == "published":
        target = normalize_published_offer(
            row=target_row,
            requested_contract_type=(
                args.type_candidature
            ),
        )
    else:
        target = normalize_spontaneous_target(
            row=target_row,
            requested_contract_type=(
                args.type_candidature
            ),
        )

    output_directory = None

    if args.output_dir:
        output_directory = resolve_path(
            args.output_dir
        )

    paths = build_application_paths(
        project_root=PROJECT_ROOT,
        target=target,
        output_directory=output_directory,
        source_folder=resolve_source_folder(
            project_root=PROJECT_ROOT,
            csv_path=csv_path,
            target=target,
        ),
    )

    if args.cv_data:
        cv_data_path = resolve_path(
            args.cv_data
        )
    else:
        cv_data_path = paths.cv_data

    if not cv_data_path.exists():
        raise FileNotFoundError(
            "Le fichier cv_data.json est introuvable : "
            f"{cv_data_path}\n"
            "Exécute d'abord tailor_cv.py pour cette cible."
        )

    cv_data = load_json(
        cv_data_path
    )

    if not isinstance(cv_data, dict):
        raise ValueError(
            "cv_data.json doit contenir "
            "un objet JSON."
        )

    llm_client = JsonLlmClient(
        api_key=api_key,
        model=args.model,
    )

    context_builder = LetterContextBuilder(
        recipient_resolver=RecipientResolver(),
        company_context_builder=(
            CompanyContextBuilder()
        ),
    )

    prompt_builder = LetterPromptBuilder()

    letter_generator = LetterGenerator(
        llm_client=llm_client,
        prompt_builder=prompt_builder,
    )

    html_renderer = HtmlLetterRenderer()

    service = LetterService(
        context_builder=context_builder,
        letter_generator=letter_generator,
        letter_validator=LetterValidator(),

        pdf_renderer=PdfLetterRenderer(
            html_renderer=html_renderer,
        ),

        docx_renderer=DocxLetterRenderer(),

        artifact_writer=(
            LetterArtifactWriter()
        ),

        correction_attempts=(
            args.correction_attempts
        ),

        review=args.review,
    )

    result = service.prepare(
        target=target,
        cv_data=cv_data,
        paths=paths,
    )

    print("\n==============================================")
    print("Lettre générée avec succès")
    print("==============================================")
    print(
        f"PDF : {result.pdf_path}"
    )
    print(
        f"Word : {result.docx_path}"
    )
    print(
        f"Données : {result.letter_data_path}"
    )
    print(
        f"Échelle PDF : {result.scale_used:.2f}"
    )

    # La candidature est prête : elle entre dans l'index qui sert à
    # repérer les doublons, même si son dossier est supprimé plus tard.
    record_application(
        project_root=PROJECT_ROOT,
        source=resolve_source_folder(
            project_root=PROJECT_ROOT,
            csv_path=csv_path,
            target=target,
        ),
        contract_type=target.contract_type,
        offer_id=target.external_id,
        company=target.company_name,
        title=target.job_title,
        location=target.location,
        directory=paths.directory,
    )


if __name__ == "__main__":
    main()