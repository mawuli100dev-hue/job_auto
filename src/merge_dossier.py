# job_automation/src/merge_dossier.py

"""
Fusionne les documents PDF d'une candidature.

Deux dossiers PDF sont produits :

1. CV_LM_AMAVIGAN.pdf
   CV + lettre de motivation + documents annexes

2. LM_x_AMAVIGAN.pdf
   Lettre de motivation + documents annexes, sans le CV

Les documents annexes sont triés selon le préfixe numérique
de leur nom :

3_bulletin_sem3.pdf
4_bulletin_sem4.pdf
5_lettre_recommandation.pdf

Les fichiers sans préfixe numérique sont placés à la fin,
dans l'ordre alphabétique.

Ce script :
- ne contient aucun appel LLM ;
- fonctionne pour les alternances et les stages ;
- fonctionne pour les offres publiées et les candidatures spontanées ;
- reste compatible avec l'ancien argument --offer-id ;
- peut recevoir directement le dossier avec --dossier.

Exemples
--------

Recherche automatique avec l'identifiant :

python src\\merge_dossier.py --offer-id 213QBYH

Nouvelle appellation plus générale :

python src\\merge_dossier.py --application-id 213QBYH

Dossier explicite :

python src\\merge_dossier.py ^
    --dossier "data\\candidatures\\2026-10-01\\entreprise_213QBYH"

Dossier d'annexes personnalisé :

python src\\merge_dossier.py ^
    --offer-id 213QBYH ^
    --extra-dir "data\\extra"

Sans document annexe :

python src\\merge_dossier.py ^
    --offer-id 213QBYH ^
    --sans-annexes
"""

import argparse
import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from paths import all_application_dirs


# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_EXTRA_DIR = (
    PROJECT_ROOT
    / "data"
    / "extra"
)

# Dossiers data/<source>/3_candidatures, plus l'ancien data/candidatures.
CANDIDATURES_DIRS = all_application_dirs(PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Noms des documents
# ---------------------------------------------------------------------------

CV_FILENAME = "CV_Henoc_AMAVIGAN.pdf"
LETTER_FILENAME = "LM_Henoc_AMAVIGAN.pdf"

COMPLETE_PACKAGE_FILENAME = (
    "CV_LM_AMAVIGAN.pdf"
)

LETTER_PACKAGE_FILENAME = (
    "LM_x_AMAVIGAN.pdf"
)


# ---------------------------------------------------------------------------
# Utilitaires de chemins
# ---------------------------------------------------------------------------

def resolve_path(
    value: str | Path,
    base_dir: Path = PROJECT_ROOT,
) -> Path:
    """
    Convertit un chemin en chemin absolu.

    Les chemins relatifs sont interprétés depuis la racine
    du projet 
    """

    path = Path(value).expanduser()

    if not path.is_absolute():
        path = base_dir / path

    return path.resolve()


def normalize_identifier(
    value: object,
) -> str:
    """
    Normalise un identifiant pour comparer les noms de dossiers.

    Cette fonction applique la même logique générale que slugify :
    - suppression des accents ;
    - passage en minuscules ;
    - remplacement des caractères spéciaux par des underscores.
    """

    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    normalized = unicodedata.normalize(
        "NFKD",
        text,
    )

    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    normalized_identifier = re.sub(
        r"[^a-zA-Z0-9]+",
        "_",
        without_accents,
    )

    return normalized_identifier.strip("_").lower()


# ---------------------------------------------------------------------------
# Lecture sécurisée du JSON
# ---------------------------------------------------------------------------

def load_json_safely(
    path: Path,
) -> dict:
    """
    Charge un objet JSON.

    Retourne un dictionnaire vide si le fichier est invalide
    ou inaccessible.
    """

    try:
        with path.open(
            mode="r",
            encoding="utf-8",
        ) as json_file:
            data = json.load(json_file)

    except (
        OSError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def extract_application_identifiers(
    data: dict,
) -> set[str]:
    """
    Extrait les identifiants possibles depuis cv_data.json
    ou letter_data.json.

    Cette fonction reste compatible avec :
    - l'ancien schéma cv_data.json ;
    - le nouveau schéma factorisé ;
    - les candidatures spontanées.
    """

    identifiers: set[str] = set()

    def add_identifier(
        value: object,
    ) -> None:
        if value is None:
            return

        value_text = str(value).strip()

        if value_text:
            identifiers.add(value_text)

    # Ancien schéma.
    add_identifier(
        data.get("offer_id")
    )

    add_identifier(
        data.get("application_id")
    )

    # Nouveau schéma.
    application = data.get(
        "application",
        {},
    )

    if isinstance(application, dict):
        add_identifier(
            application.get(
                "application_id"
            )
        )

        add_identifier(
            application.get(
                "external_id"
            )
        )

        add_identifier(
            application.get(
                "offer_id"
            )
        )

    target = data.get(
        "target",
        {},
    )

    if isinstance(target, dict):
        add_identifier(
            target.get(
                "application_id"
            )
        )

        add_identifier(
            target.get(
                "external_id"
            )
        )

        add_identifier(
            target.get(
                "id"
            )
        )

        add_identifier(
            target.get(
                "offer_id"
            )
        )

    offer = data.get(
        "offer",
        {},
    )

    if isinstance(offer, dict):
        add_identifier(
            offer.get("id")
        )

        add_identifier(
            offer.get("offer_id")
        )

    return identifiers


# ---------------------------------------------------------------------------
# Recherche du dossier de candidature
# ---------------------------------------------------------------------------

def directory_matches_identifier(
    directory: Path,
    application_id: str,
) -> bool:
    """
    Vérifie si le nom d'un dossier correspond à l'identifiant.

    Exemple :

    carvolix_214CZVT
    correspond à :
    214CZVT
    """

    normalized_directory_name = (
        normalize_identifier(
            directory.name
        )
    )

    normalized_application_id = (
        normalize_identifier(
            application_id
        )
    )

    if not normalized_application_id:
        return False

    return (
        normalized_directory_name
        == normalized_application_id
        or normalized_directory_name.endswith(
            f"_{normalized_application_id}"
        )
    )


def find_candidature_dir(
    application_id: str,
    candidatures_dirs: list[Path] = CANDIDATURES_DIRS,
) -> Path:
    """
    Recherche le dossier de candidature correspondant à un identifiant.

    Ordre de recherche :

    1. Lecture de cv_data.json ;
    2. Lecture de letter_data.json ;
    3. Comparaison avec le nom du dossier.

    Si plusieurs dossiers correspondent, le plus récemment modifié
    est utilisé.
    """

    if not candidatures_dirs:
        raise FileNotFoundError(
            "Aucun dossier de candidatures trouvé "
            "(data/<source>/3_candidatures)."
        )

    application_id = str(
        application_id
    ).strip()

    if not application_id:
        raise ValueError(
            "L'identifiant de candidature est vide."
        )

    matches: set[Path] = set()

    # Recherche fiable dans les fichiers de données.
    metadata_filenames = (
        "cv_data.json",
        "letter_data.json",
    )

    for metadata_filename in metadata_filenames:
        for metadata_path in (
            path
            for directory in candidatures_dirs
            for path in directory.rglob(metadata_filename)
        ):
            data = load_json_safely(
                metadata_path
            )

            identifiers = (
                extract_application_identifiers(
                    data
                )
            )

            if application_id in identifiers:
                matches.add(
                    metadata_path.parent.resolve()
                )

                continue

            normalized_requested = (
                normalize_identifier(
                    application_id
                )
            )

            normalized_identifiers = {
                normalize_identifier(
                    identifier
                )
                for identifier in identifiers
            }

            if (
                normalized_requested
                and normalized_requested
                in normalized_identifiers
            ):
                matches.add(
                    metadata_path.parent.resolve()
                )

    # Recherche de secours dans les noms des dossiers.
    for path in (
        path
        for directory in candidatures_dirs
        for path in directory.rglob("*")
    ):
        if not path.is_dir():
            continue

        if directory_matches_identifier(
            directory=path,
            application_id=application_id,
        ):
            matches.add(
                path.resolve()
            )

    if not matches:
        raise FileNotFoundError(
            "Aucun dossier de candidature trouvé pour "
            f"l'identifiant « {application_id} ».\n"
            "Vérifie que tailor_cv.py et generate_letter.py "
            "ont déjà été exécutés pour cette candidature.\n"
            "Dossiers examinés : "
            + ", ".join(str(directory) for directory in candidatures_dirs)
        )

    ordered_matches = sorted(
        matches,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if len(ordered_matches) > 1:
        print(
            "ATTENTION : plusieurs dossiers correspondent "
            f"à l'identifiant « {application_id} »."
        )

        for match in ordered_matches:
            print(f"- {match}")

        print(
            "Le dossier modifié le plus récemment sera utilisé."
        )

    return ordered_matches[0]


def resolve_candidature_dir(
    application_id: str | None,
    explicit_directory: str | None,
) -> Path:
    """
    Détermine le dossier de candidature.

    Un dossier fourni explicitement est prioritaire.
    """

    if explicit_directory:
        directory = resolve_path(
            explicit_directory
        )

        if not directory.exists():
            raise FileNotFoundError(
                "Le dossier de candidature est introuvable : "
                f"{directory}"
            )

        if not directory.is_dir():
            raise NotADirectoryError(
                "Le chemin fourni avec --dossier n'est "
                f"pas un dossier : {directory}"
            )

        return directory

    if not application_id:
        raise ValueError(
            "Il faut fournir soit --offer-id, "
            "--application-id ou --dossier."
        )

    return find_candidature_dir(
        application_id=application_id,
        candidatures_dirs=CANDIDATURES_DIRS,
    )


# ---------------------------------------------------------------------------
# Validation des fichiers PDF
# ---------------------------------------------------------------------------

def validate_pdf(
    pdf_path: Path,
    label: str,
) -> int:
    """
    Vérifie qu'un PDF existe, qu'il peut être lu et qu'il contient
    au moins une page.

    Retourne le nombre de pages.
    """

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"{label} introuvable : {pdf_path}"
        )

    if not pdf_path.is_file():
        raise ValueError(
            f"{label} n'est pas un fichier : {pdf_path}"
        )

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(
            f"{label} n'est pas un PDF : {pdf_path}"
        )

    try:
        reader = PdfReader(
            str(pdf_path)
        )

        if reader.is_encrypted:
            try:
                decrypt_result = reader.decrypt("")
            except Exception as error:
                raise ValueError(
                    f"{label} est protégé par un mot de passe : "
                    f"{pdf_path}"
                ) from error

            if decrypt_result == 0:
                raise ValueError(
                    f"{label} est protégé par un mot de passe : "
                    f"{pdf_path}"
                )

        page_count = len(
            reader.pages
        )

    except ValueError:
        raise

    except Exception as error:
        raise ValueError(
            f"{label} est invalide ou illisible : "
            f"{pdf_path}\n"
            f"Détail : {error}"
        ) from error

    if page_count == 0:
        raise ValueError(
            f"{label} ne contient aucune page : "
            f"{pdf_path}"
        )

    return page_count


# ---------------------------------------------------------------------------
# Documents annexes
# ---------------------------------------------------------------------------

def extraction_prefix(
    path: Path,
) -> tuple[int, str]:
    """
    Extrait le préfixe numérique du nom du fichier.

    Exemples :

    3_bulletin.pdf -> (3, "3_bulletin.pdf")
    recommandation.pdf -> (très grand nombre, "recommandation.pdf")
    """

    match = re.match(
        r"^(\d+)[_\-\s]",
        path.stem,
    )

    if match:
        return (
            int(match.group(1)),
            path.name.casefold(),
        )

    return (
        10**9,
        path.name.casefold(),
    )


def collect_extra_files(
    extra_dir: Path,
) -> list[Path]:
    """
    Collecte et valide les documents annexes PDF.

    Les PDF invalides provoquent une erreur afin d'éviter de produire
    silencieusement un dossier incomplet.
    """

    if not extra_dir.exists():
        print(
            "ATTENTION : le dossier d'annexes "
            f"n'existe pas : {extra_dir}"
        )

        print(
            "Aucun document annexe ne sera ajouté."
        )

        return []

    if not extra_dir.is_dir():
        raise NotADirectoryError(
            "Le chemin des annexes n'est pas un dossier : "
            f"{extra_dir}"
        )

    pdf_files = [
        path.resolve()
        for path in extra_dir.iterdir()
        if (
            path.is_file()
            and path.suffix.lower() == ".pdf"
        )
    ]

    pdf_files.sort(
        key=extraction_prefix
    )

    validated_files: list[Path] = []
    seen_paths: set[Path] = set()

    for pdf_path in pdf_files:
        if pdf_path in seen_paths:
            continue

        page_count = validate_pdf(
            pdf_path=pdf_path,
            label=(
                f"Document annexe "
                f"« {pdf_path.name} »"
            ),
        )

        print(
            f"Annexe trouvée : {pdf_path.name} "
            f"({page_count} page(s))"
        )

        validated_files.append(
            pdf_path
        )

        seen_paths.add(
            pdf_path
        )

    return validated_files


# ---------------------------------------------------------------------------
# Affichage de l'ordre de fusion
# ---------------------------------------------------------------------------

def print_merge_order(
    title: str,
    named_files: list[tuple[Path, str]],
) -> None:
    """
    Affiche l'ordre dans lequel les PDF seront assemblés.
    """

    print(
        f"\nOrdre de fusion pour {title} :"
    )

    for index, (
        file_path,
        label,
    ) in enumerate(
        named_files,
        start=1,
    ):
        page_count = validate_pdf(
            pdf_path=file_path,
            label=label or file_path.name,
        )

        label_suffix = (
            f" - {label}"
            if label
            else ""
        )

        print(
            f"  {index}. {file_path.name}"
            f"{label_suffix} "
            f"({page_count} page(s))"
        )


# ---------------------------------------------------------------------------
# Fusion des PDF
# ---------------------------------------------------------------------------

def unique_files(
    ordered_files: list[Path],
) -> list[Path]:
    """
    Supprime les doublons tout en conservant l'ordre.
    """

    result: list[Path] = []
    seen_paths: set[Path] = set()

    for path in ordered_files:
        resolved_path = path.resolve()

        if resolved_path in seen_paths:
            print(
                "ATTENTION : document présent plusieurs fois, "
                f"doublon ignoré : {resolved_path.name}"
            )

            continue

        result.append(
            resolved_path
        )

        seen_paths.add(
            resolved_path
        )

    return result


def build_unlocked_alternative_path(
    output_path: Path,
) -> Path:
    """
    Construit un nouveau nom si le fichier de destination
    est ouvert dans une autre application.
    """

    timestamp = datetime.now().strftime(
        "%H%M%S"
    )

    return output_path.with_name(
        f"{output_path.stem}_"
        f"{timestamp}"
        f"{output_path.suffix}"
    )


def merge_pdfs(
    ordered_files: list[Path],
    output_path: Path,
) -> Path:
    """
    Fusionne plusieurs PDF dans un ordre déterminé.

    Le résultat est d'abord écrit dans un fichier temporaire,
    puis déplacé vers sa destination. Cela évite de laisser un
    fichier final partiellement écrit en cas d'erreur.
    """

    ordered_files = unique_files(
        ordered_files
    )

    if not ordered_files:
        raise ValueError(
            "Aucun fichier PDF n'a été fourni "
            "pour la fusion."
        )

    output_path = output_path.resolve()

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    for pdf_path in ordered_files:
        if pdf_path == output_path:
            raise ValueError(
                "Le fichier de sortie ne peut pas être "
                "utilisé comme fichier d'entrée : "
                f"{output_path}"
            )

        validate_pdf(
            pdf_path=pdf_path,
            label=f"Document source « {pdf_path.name} »",
        )

    temporary_path = output_path.with_name(
        f".{output_path.stem}_temp"
        f"{output_path.suffix}"
    )

    writer = PdfWriter()

    try:
        for pdf_path in ordered_files:
            writer.append(
                str(pdf_path)
            )

        with temporary_path.open(
            mode="wb",
        ) as output_file:
            writer.write(
                output_file
            )

    except Exception:
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass

        raise

    finally:
        writer.close()

    validate_pdf(
        pdf_path=temporary_path,
        label="PDF fusionné temporaire",
    )

    try:
        os.replace(
            temporary_path,
            output_path,
        )

        final_path = output_path

    except PermissionError:
        alternative_path = (
            build_unlocked_alternative_path(
                output_path
            )
        )

        print(
            "ATTENTION : le fichier "
            f"« {output_path.name} » est verrouillé, "
            "probablement parce qu'il est ouvert."
        )

        print(
            "Le résultat sera enregistré sous : "
            f"« {alternative_path.name} »."
        )

        os.replace(
            temporary_path,
            alternative_path,
        )

        final_path = alternative_path

    return final_path


# ---------------------------------------------------------------------------
# Création des deux dossiers PDF
# ---------------------------------------------------------------------------

def build_application_packages(
    candidature_dir: Path,
    extra_files: list[Path],
) -> tuple[Path, Path]:
    """
    Produit les deux fichiers finaux :

    - CV_LM_AMAVIGAN.pdf ;
    - LM_x_AMAVIGAN.pdf.
    """

    cv_path = (
        candidature_dir
        / CV_FILENAME
    )

    letter_path = (
        candidature_dir
        / LETTER_FILENAME
    )

    validate_pdf(
        pdf_path=cv_path,
        label="CV",
    )

    validate_pdf(
        pdf_path=letter_path,
        label="Lettre de motivation",
    )

    # ---------------------------------------------------------------
    # Dossier complet : CV + lettre + annexes
    # ---------------------------------------------------------------

    complete_order = [
        (cv_path, "CV"),
        (
            letter_path,
            "Lettre de motivation",
        ),
        *[
            (
                extra_file,
                "Document annexe",
            )
            for extra_file in extra_files
        ],
    ]

    print_merge_order(
        title=COMPLETE_PACKAGE_FILENAME,
        named_files=complete_order,
    )

    complete_output = (
        candidature_dir
        / COMPLETE_PACKAGE_FILENAME
    )

    final_complete_output = merge_pdfs(
        ordered_files=[
            file_path
            for file_path, _ in complete_order
        ],
        output_path=complete_output,
    )

    print(
        "PDF complet généré : "
        f"{final_complete_output}"
    )

    # ---------------------------------------------------------------
    # Dossier sans CV : lettre + annexes
    # ---------------------------------------------------------------

    letter_order = [
        (
            letter_path,
            "Lettre de motivation",
        ),
        *[
            (
                extra_file,
                "Document annexe",
            )
            for extra_file in extra_files
        ],
    ]

    print_merge_order(
        title=LETTER_PACKAGE_FILENAME,
        named_files=letter_order,
    )

    letter_output = (
        candidature_dir
        / LETTER_PACKAGE_FILENAME
    )

    final_letter_output = merge_pdfs(
        ordered_files=[
            file_path
            for file_path, _ in letter_order
        ],
        output_path=letter_output,
    )

    print(
        "PDF sans CV généré : "
        f"{final_letter_output}"
    )

    return (
        final_complete_output,
        final_letter_output,
    )


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    """
    Construit le parseur d'arguments.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Fusionne le CV, la lettre de motivation "
            "et les documents annexes d'une candidature."
        )
    )

    identification_group = (
        parser.add_mutually_exclusive_group(
            required=True
        )
    )

    identification_group.add_argument(
        "--offer-id",
        "--application-id",
        dest="application_id",
        help=(
            "Identifiant de l'offre ou de la candidature. "
            "--offer-id est conservé pour la compatibilité."
        ),
    )

    identification_group.add_argument(
        "--dossier",
        "--output-dir",
        dest="candidature_dir",
        help=(
            "Chemin explicite du dossier de candidature. "
            "Cette option évite la recherche automatique."
        ),
    )

    parser.add_argument(
        "--extra-dir",
        default=str(
            DEFAULT_EXTRA_DIR
        ),
        help=(
            "Dossier contenant les documents annexes. "
            "Défaut : data/extra."
        ),
    )

    parser.add_argument(
        "--sans-annexes",
        action="store_true",
        help=(
            "Génère les deux dossiers PDF sans ajouter "
            "les documents de data/extra."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    candidature_dir = (
        resolve_candidature_dir(
            application_id=args.application_id,
            explicit_directory=(
                args.candidature_dir
            ),
        )
    )

    print("==============================================")
    print("Fusion du dossier de candidature")
    print("==============================================")

    print(
        f"Dossier de candidature : "
        f"{candidature_dir}"
    )

    if args.sans_annexes:
        print(
            "Documents annexes : désactivés"
        )

        extra_files: list[Path] = []

    else:
        extra_dir = resolve_path(
            args.extra_dir
        )

        print(
            f"Dossier des annexes : "
            f"{extra_dir}"
        )

        extra_files = collect_extra_files(
            extra_dir=extra_dir
        )

        if not extra_files:
            print(
                "Aucun document annexe ne sera ajouté."
            )

    (
        complete_output,
        letter_output,
    ) = build_application_packages(
        candidature_dir=candidature_dir,
        extra_files=extra_files,
    )

    print("\n==============================================")
    print("Fusion terminée avec succès")
    print("==============================================")

    print(
        f"Dossier complet : {complete_output}"
    )

    print(
        f"Dossier sans CV : {letter_output}"
    )


if __name__ == "__main__":
    main()