# job_automation/src/registre_offres.py

"""
Registre des candidatures déjà traitées par le pipeline.

Une candidature est considérée comme traitée lorsque l'ensemble de son
dossier a été produit avec succès :

- CV PDF et Word ;
- lettre de motivation PDF et Word ;
- dossiers PDF fusionnés.

Le registre utilise un fichier texte contenant une clé par ligne,
sans en-tête.

Nouvelle clé générale :

    source_type|contract_type|application_id

Exemples :

    published|alternance|214CZVT
    published|stage|1234567
    spontaneous|alternance|carvolix_data_analyst
    spontaneous|stage|entreprise_data_scientist

Compatibilité
-------------

Les anciennes lignes contenant seulement un identifiant restent reconnues
pour les offres publiées en alternance.

Exemple d'ancien registre :

    214CZVT
    214JLFK

Exemple du nouveau registre :

    published|alternance|214CZVT
    published|stage|1234567

Le nom historique data/offres_traitees.csv est conservé pour éviter de
casser le pipeline. Son contenu reste un fichier texte simple.

Commandes
---------

Vérification avec les valeurs historiques par défaut :

    python src\\registre_offres.py --check 214CZVT

Vérification explicite d'une alternance publiée :

    python src\\registre_offres.py ^
        --check 214CZVT ^
        --source-type published ^
        --type-candidature alternance

Vérification d'un stage publié :

    python src\\registre_offres.py ^
        --check 1234567 ^
        --source-type published ^
        --type-candidature stage

Candidature spontanée :

    python src\\registre_offres.py ^
        --check carvolix_data_analyst ^
        --source-type spontaneous ^
        --type-candidature alternance

Ajout :

    python src\\registre_offres.py ^
        --add 214CZVT ^
        --source-type published ^
        --type-candidature alternance

Ajout de plusieurs candidatures :

    python src\\registre_offres.py ^
        --add-list "214CZVT,214JLFK,1234567" ^
        --source-type published ^
        --type-candidature alternance

Lister :

    python src\\registre_offres.py --list

Afficher les détails des clés :

    python src\\registre_offres.py --list --details

Nettoyer :

    python src\\registre_offres.py --nettoyer
"""

import argparse
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REGISTRY_PATH = (
    PROJECT_ROOT
    / "data"
    / "offres_traitees.csv"
)


# ---------------------------------------------------------------------------
# Types autorisés
# ---------------------------------------------------------------------------

SOURCE_PUBLISHED = "published"
SOURCE_SPONTANEOUS = "spontaneous"

SOURCE_TYPES = (
    SOURCE_PUBLISHED,
    SOURCE_SPONTANEOUS,
)

CONTRACT_ALTERNANCE = "alternance"
CONTRACT_STAGE = "stage"

CONTRACT_TYPES = (
    CONTRACT_ALTERNANCE,
    CONTRACT_STAGE,
)

KEY_SEPARATOR = "|"


# ---------------------------------------------------------------------------
# Gestion des chemins
# ---------------------------------------------------------------------------

def resolve_path(
    value: str | Path,
) -> Path:
    """
    Convertit un chemin en chemin absolu.

    Les chemins relatifs sont interprétés depuis la racine
    du projet 
    """

    path = Path(value).expanduser()

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def normalize_identifier(
    application_id: object,
) -> str:
    """
    Nettoie et valide un identifiant de candidature.

    La casse est volontairement conservée pour garder les identifiants
    originaux de France Travail ou des autres sources.
    """

    if application_id is None:
        return ""

    identifier = str(application_id).strip()

    if not identifier:
        return ""

    if "\n" in identifier or "\r" in identifier:
        raise ValueError(
            "L'identifiant ne peut pas contenir "
            "de saut de ligne."
        )

    if KEY_SEPARATOR in identifier:
        raise ValueError(
            f"L'identifiant ne peut pas contenir "
            f"le caractère « {KEY_SEPARATOR} »."
        )

    return identifier


def validate_source_type(
    source_type: str,
) -> str:
    """
    Vérifie et normalise le type de source.
    """

    normalized = str(source_type).strip().lower()

    if normalized not in SOURCE_TYPES:
        raise ValueError(
            "Le type de source doit être "
            "'published' ou 'spontaneous'."
        )

    return normalized


def validate_contract_type(
    contract_type: str,
) -> str:
    """
    Vérifie et normalise le type de contrat.
    """

    normalized = str(contract_type).strip().lower()

    if normalized not in CONTRACT_TYPES:
        raise ValueError(
            "Le type de candidature doit être "
            "'alternance' ou 'stage'."
        )

    return normalized


# ---------------------------------------------------------------------------
# Construction des clés
# ---------------------------------------------------------------------------

def build_registry_key(
    application_id: str,
    source_type: str = SOURCE_PUBLISHED,
    contract_type: str = CONTRACT_ALTERNANCE,
) -> str:
    """
    Construit une clé unique de candidature.

    Format :

        source_type|contract_type|application_id
    """

    identifier = normalize_identifier(
        application_id
    )

    if not identifier:
        raise ValueError(
            "L'identifiant de candidature est vide."
        )

    normalized_source = validate_source_type(
        source_type
    )

    normalized_contract = validate_contract_type(
        contract_type
    )

    return KEY_SEPARATOR.join(
        [
            normalized_source,
            normalized_contract,
            identifier,
        ]
    )


def parse_registry_key(
    entry: str,
) -> dict:
    """
    Analyse une ligne du registre.

    Retourne un dictionnaire décrivant soit :
    - une nouvelle clé structurée ;
    - un ancien identifiant simple.
    """

    entry = str(entry).strip()

    parts = entry.split(
        KEY_SEPARATOR,
        maxsplit=2,
    )

    if (
        len(parts) == 3
        and parts[0] in SOURCE_TYPES
        and parts[1] in CONTRACT_TYPES
        and parts[2].strip()
    ):
        return {
            "format": "structured",
            "source_type": parts[0],
            "contract_type": parts[1],
            "application_id": parts[2].strip(),
            "key": entry,
        }

    return {
        "format": "legacy",
        "source_type": SOURCE_PUBLISHED,
        "contract_type": CONTRACT_ALTERNANCE,
        "application_id": entry,
        "key": entry,
    }


# ---------------------------------------------------------------------------
# Lecture du registre
# ---------------------------------------------------------------------------

def load_registry_entries(
    path: Path = DEFAULT_REGISTRY_PATH,
) -> list[str]:
    """
    Charge les lignes du registre en conservant leur ordre.

    Sont ignorés :
    - les lignes vides ;
    - un ancien en-tête CSV exactement égal à « id » ;
    - les lignes commençant par #.
    """

    if not path.exists():
        return []

    entries: list[str] = []

    with path.open(
        mode="r",
        encoding="utf-8-sig",
    ) as registry_file:
        for raw_line in registry_file:
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if line.lower() == "id":
                continue

            entries.append(line)

    return entries


def load_registre(
    path: Path = DEFAULT_REGISTRY_PATH,
) -> set[str]:
    """
    Fonction conservée pour la compatibilité avec l'ancien code.

    Retourne l'ensemble des entrées enregistrées.
    """

    return set(
        load_registry_entries(path)
    )


# ---------------------------------------------------------------------------
# Vérification d'une candidature
# ---------------------------------------------------------------------------

def is_already_processed(
    application_id: str,
    path: Path = DEFAULT_REGISTRY_PATH,
    source_type: str = SOURCE_PUBLISHED,
    contract_type: str = CONTRACT_ALTERNANCE,
) -> bool:
    """
    Vérifie si une candidature est déjà enregistrée.

    Compatibilité avec l'ancien registre :
    un identifiant brut est reconnu seulement pour une offre publiée
    en alternance, car c'était le seul cas pris en charge auparavant.
    """

    identifier = normalize_identifier(
        application_id
    )

    if not identifier:
        return False

    normalized_source = validate_source_type(
        source_type
    )

    normalized_contract = validate_contract_type(
        contract_type
    )

    key = build_registry_key(
        application_id=identifier,
        source_type=normalized_source,
        contract_type=normalized_contract,
    )

    entries = load_registre(path)

    if key in entries:
        return True

    # Compatibilité avec les anciens identifiants simples.
    if (
        normalized_source == SOURCE_PUBLISHED
        and normalized_contract == CONTRACT_ALTERNANCE
        and identifier in entries
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# Ajout dans le registre
# ---------------------------------------------------------------------------

def add_to_registry(
    application_id: str,
    path: Path = DEFAULT_REGISTRY_PATH,
    source_type: str = SOURCE_PUBLISHED,
    contract_type: str = CONTRACT_ALTERNANCE,
) -> bool:
    """
    Ajoute une candidature au registre.

    Retourne :
    - True si une nouvelle clé a été ajoutée ;
    - False si la candidature était déjà enregistrée.
    """

    identifier = normalize_identifier(
        application_id
    )

    if not identifier:
        return False

    if is_already_processed(
        application_id=identifier,
        path=path,
        source_type=source_type,
        contract_type=contract_type,
    ):
        return False

    key = build_registry_key(
        application_id=identifier,
        source_type=source_type,
        contract_type=contract_type,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        mode="a",
        encoding="utf-8",
        newline="\n",
    ) as registry_file:
        registry_file.write(
            key + "\n"
        )

        registry_file.flush()

        try:
            os.fsync(
                registry_file.fileno()
            )
        except OSError:
            # Certains systèmes de fichiers peuvent ne pas
            # prendre en charge fsync.
            pass

    return True


def add_to_registre(
    offer_id: str,
    path: Path = DEFAULT_REGISTRY_PATH,
    source_type: str = SOURCE_PUBLISHED,
    contract_type: str = CONTRACT_ALTERNANCE,
) -> bool:
    """
    Alias conservé pour les anciens imports Python.
    """

    return add_to_registry(
        application_id=offer_id,
        path=path,
        source_type=source_type,
        contract_type=contract_type,
    )


def add_list_to_registry(
    application_ids: list[str],
    path: Path = DEFAULT_REGISTRY_PATH,
    source_type: str = SOURCE_PUBLISHED,
    contract_type: str = CONTRACT_ALTERNANCE,
) -> tuple[int, int, int]:
    """
    Ajoute plusieurs candidatures.

    Retourne :
    - nombre ajouté ;
    - nombre déjà présent ;
    - nombre ignoré car vide.
    """

    added_count = 0
    existing_count = 0
    ignored_count = 0

    for application_id in application_ids:
        identifier = normalize_identifier(
            application_id
        )

        if not identifier:
            ignored_count += 1
            continue

        was_added = add_to_registry(
            application_id=identifier,
            path=path,
            source_type=source_type,
            contract_type=contract_type,
        )

        if was_added:
            added_count += 1
        else:
            existing_count += 1

    return (
        added_count,
        existing_count,
        ignored_count,
    )


def add_list_to_registre(
    offer_ids: list[str],
    path: Path = DEFAULT_REGISTRY_PATH,
    source_type: str = SOURCE_PUBLISHED,
    contract_type: str = CONTRACT_ALTERNANCE,
) -> tuple[int, int]:
    """
    Alias compatible avec l'ancienne fonction.

    L'ancien appel attendait seulement :
    (nombre ajouté, nombre déjà présent).
    """

    (
        added_count,
        existing_count,
        _,
    ) = add_list_to_registry(
        application_ids=offer_ids,
        path=path,
        source_type=source_type,
        contract_type=contract_type,
    )

    return (
        added_count,
        existing_count,
    )


# ---------------------------------------------------------------------------
# Nettoyage du registre
# ---------------------------------------------------------------------------

def clean_registry(
    path: Path = DEFAULT_REGISTRY_PATH,
) -> tuple[int, int, int]:
    """
    Nettoie le registre :

    - supprime les lignes vides ;
    - supprime les doublons ;
    - supprime l'ancien en-tête « id » ;
    - conserve l'ordre de première apparition ;
    - réécrit le fichier de manière atomique.

    Retourne :
    - nombre de lignes utiles avant nettoyage ;
    - nombre de lignes après nettoyage ;
    - nombre de doublons supprimés.
    """

    if not path.exists():
        return (
            0,
            0,
            0,
        )

    raw_entries = load_registry_entries(
        path
    )

    before_count = len(
        raw_entries
    )

    seen: set[str] = set()
    clean_entries: list[str] = []

    for entry in raw_entries:
        if entry in seen:
            continue

        seen.add(entry)
        clean_entries.append(entry)

    after_count = len(
        clean_entries
    )

    removed_duplicates = (
        before_count - after_count
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_name(
        f".{path.name}.tmp"
    )

    with temporary_path.open(
        mode="w",
        encoding="utf-8",
        newline="\n",
    ) as registry_file:
        for entry in clean_entries:
            registry_file.write(
                entry + "\n"
            )

        registry_file.flush()

        try:
            os.fsync(
                registry_file.fileno()
            )
        except OSError:
            pass

    os.replace(
        temporary_path,
        path,
    )

    return (
        before_count,
        after_count,
        removed_duplicates,
    )


def nettoyer_registre(
    path: Path = DEFAULT_REGISTRY_PATH,
) -> tuple[int, int]:
    """
    Alias compatible avec l'ancienne fonction.
    """

    (
        before_count,
        after_count,
        _,
    ) = clean_registry(path)

    return (
        before_count,
        after_count,
    )


# ---------------------------------------------------------------------------
# Migration facultative
# ---------------------------------------------------------------------------

def migrate_legacy_entries(
    path: Path = DEFAULT_REGISTRY_PATH,
) -> tuple[int, int]:
    """
    Convertit les anciens identifiants simples en clés structurées :

        214CZVT

    devient :

        published|alternance|214CZVT

    Les nouvelles clés déjà présentes ne sont pas modifiées.

    Retourne :
    - nombre d'anciennes lignes converties ;
    - nombre total de lignes après migration.
    """

    entries = load_registry_entries(
        path
    )

    if not entries:
        return (
            0,
            0,
        )

    migrated_entries: list[str] = []
    migrated_count = 0
    seen: set[str] = set()

    for entry in entries:
        parsed = parse_registry_key(
            entry
        )

        if parsed["format"] == "legacy":
            new_entry = build_registry_key(
                application_id=parsed[
                    "application_id"
                ],
                source_type=SOURCE_PUBLISHED,
                contract_type=CONTRACT_ALTERNANCE,
            )

            migrated_count += 1

        else:
            new_entry = parsed["key"]

        if new_entry in seen:
            continue

        seen.add(new_entry)
        migrated_entries.append(
            new_entry
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_name(
        f".{path.name}.migration.tmp"
    )

    with temporary_path.open(
        mode="w",
        encoding="utf-8",
        newline="\n",
    ) as registry_file:
        for entry in migrated_entries:
            registry_file.write(
                entry + "\n"
            )

        registry_file.flush()

        try:
            os.fsync(
                registry_file.fileno()
            )
        except OSError:
            pass

    os.replace(
        temporary_path,
        path,
    )

    return (
        migrated_count,
        len(migrated_entries),
    )


# ---------------------------------------------------------------------------
# Affichage
# ---------------------------------------------------------------------------

def print_registry(
    path: Path,
    details: bool = False,
) -> None:
    """
    Affiche les entrées du registre.
    """

    entries = load_registry_entries(
        path
    )

    print(
        f"{len(entries)} candidature(s) "
        f"enregistrée(s) dans :"
    )

    print(
        path
    )

    if not entries:
        return

    print()

    for entry in entries:
        if not details:
            print(f"- {entry}")
            continue

        parsed = parse_registry_key(
            entry
        )

        if parsed["format"] == "legacy":
            print(
                f"- {parsed['application_id']} "
                f"[ancien format : "
                f"published / alternance]"
            )

        else:
            print(
                f"- {parsed['application_id']} "
                f"[{parsed['source_type']} / "
                f"{parsed['contract_type']}]"
            )


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    """
    Construit le parseur des arguments.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Registre des candidatures déjà traitées "
            "par le pipeline."
        )
    )

    parser.add_argument(
        "--registre",
        default=str(
            DEFAULT_REGISTRY_PATH
        ),
        help=(
            "Chemin du registre. "
            "Défaut : data/offres_traitees.csv"
        ),
    )

    parser.add_argument(
        "--source-type",
        choices=SOURCE_TYPES,
        default=SOURCE_PUBLISHED,
        help=(
            "Origine de la candidature : "
            "published ou spontaneous. "
            "Défaut : published."
        ),
    )

    parser.add_argument(
        "--type-candidature",
        choices=CONTRACT_TYPES,
        default=CONTRACT_ALTERNANCE,
        help=(
            "Type de contrat : alternance ou stage. "
            "Défaut : alternance."
        ),
    )

    parser.add_argument(
        "--details",
        action="store_true",
        help=(
            "Avec --list, affiche la source et "
            "le type de contrat."
        ),
    )

    action_group = parser.add_mutually_exclusive_group(
        required=True
    )

    action_group.add_argument(
        "--check",
        "--check-application",
        metavar="ID",
        dest="check_id",
        help=(
            "Vérifie si cette candidature a déjà "
            "été traitée."
        ),
    )

    action_group.add_argument(
        "--add",
        "--add-application",
        metavar="ID",
        dest="add_id",
        help=(
            "Ajoute une candidature au registre."
        ),
    )

    action_group.add_argument(
        "--add-list",
        metavar="ID1,ID2,...",
        help=(
            "Ajoute plusieurs identifiants séparés "
            "par des virgules."
        ),
    )

    action_group.add_argument(
        "--list",
        action="store_true",
        help=(
            "Affiche toutes les candidatures "
            "enregistrées."
        ),
    )

    action_group.add_argument(
        "--nettoyer",
        "--clean",
        dest="clean",
        action="store_true",
        help=(
            "Supprime les doublons, les lignes vides "
            "et l'ancien en-tête."
        ),
    )

    action_group.add_argument(
        "--migrer",
        "--migrate",
        dest="migrate",
        action="store_true",
        help=(
            "Convertit les anciens identifiants simples "
            "vers le nouveau format structuré."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    registry_path = resolve_path(
        args.registre
    )

    if args.list:
        print_registry(
            path=registry_path,
            details=args.details,
        )

        return

    if args.check_id:
        already_processed = (
            is_already_processed(
                application_id=args.check_id,
                path=registry_path,
                source_type=args.source_type,
                contract_type=(
                    args.type_candidature
                ),
            )
        )

        if already_processed:
            print(
                "DEJA_TRAITEE: "
                f"{args.check_id} "
                f"[{args.source_type} / "
                f"{args.type_candidature}]"
            )

            # Comportement historique conservé :
            # 1 signifie déjà traitée.
            raise SystemExit(1)

        print(
            "NON_TRAITEE: "
            f"{args.check_id} "
            f"[{args.source_type} / "
            f"{args.type_candidature}]"
        )

        # Comportement historique conservé :
        # 0 signifie non traitée.
        raise SystemExit(0)

    if args.add_id:
        was_added = add_to_registry(
            application_id=args.add_id,
            path=registry_path,
            source_type=args.source_type,
            contract_type=args.type_candidature,
        )

        key = build_registry_key(
            application_id=args.add_id,
            source_type=args.source_type,
            contract_type=args.type_candidature,
        )

        if was_added:
            print(
                f"Ajoutée au registre : {key}"
            )

        else:
            print(
                "Déjà présente dans le registre, "
                f"aucun doublon ajouté : {key}"
            )

        return

    if args.add_list:
        application_ids = [
            identifier.strip()
            for identifier in args.add_list.split(",")
            if identifier.strip()
        ]

        (
            added_count,
            existing_count,
            ignored_count,
        ) = add_list_to_registry(
            application_ids=application_ids,
            path=registry_path,
            source_type=args.source_type,
            contract_type=args.type_candidature,
        )

        print(
            f"{added_count} candidature(s) ajoutée(s)."
        )

        print(
            f"{existing_count} candidature(s) "
            "déjà présente(s)."
        )

        if ignored_count:
            print(
                f"{ignored_count} identifiant(s) "
                "vide(s) ignoré(s)."
            )

        print(
            f"Registre à jour : {registry_path}"
        )

        return

    if args.clean:
        (
            before_count,
            after_count,
            removed_duplicates,
        ) = clean_registry(
            path=registry_path
        )

        print(
            "Nettoyage terminé."
        )

        print(
            f"Lignes avant : {before_count}"
        )

        print(
            f"Lignes après : {after_count}"
        )

        print(
            f"Doublons supprimés : "
            f"{removed_duplicates}"
        )

        return

    if args.migrate:
        (
            migrated_count,
            final_count,
        ) = migrate_legacy_entries(
            path=registry_path
        )

        print(
            "Migration terminée."
        )

        print(
            f"Anciennes entrées converties : "
            f"{migrated_count}"
        )

        print(
            f"Entrées finales : {final_count}"
        )

        print(
            f"Registre : {registry_path}"
        )


if __name__ == "__main__":
    main()