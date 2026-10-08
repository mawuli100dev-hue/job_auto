# job_automation/src/job_automation/common/json_utils.py

import json
from pathlib import Path
from typing import Any


def load_json(
    path: str | Path,
) -> Any:
    """
    Charge et retourne le contenu d'un fichier JSON.

    Le chemin peut être fourni sous forme de chaîne
    ou d'objet Path.
    """

    json_path = Path(path)

    if not json_path.exists():
        raise FileNotFoundError(
            f"Fichier JSON introuvable : {json_path}"
        )

    if not json_path.is_file():
        raise ValueError(
            f"Le chemin JSON n'est pas un fichier : {json_path}"
        )

    try:
        with json_path.open(
            mode="r",
            encoding="utf-8-sig",
        ) as json_file:
            return json.load(json_file)

    except json.JSONDecodeError as error:
        raise ValueError(
            f"Le fichier JSON est invalide : {json_path}\n"
            f"Ligne {error.lineno}, colonne {error.colno} : "
            f"{error.msg}"
        ) from error


def save_json(
    path: str | Path,
    data: Any,
    indent: int = 2,
) -> Path:
    """
    Enregistre des données dans un fichier JSON UTF-8.

    Le dossier parent est créé automatiquement.
    """

    json_path = Path(path)

    json_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with json_path.open(
        mode="w",
        encoding="utf-8",
    ) as json_file:
        json.dump(
            data,
            json_file,
            ensure_ascii=False,
            indent=indent,
        )

        json_file.write("\n")

    return json_path


def load_json_object(
    path: str | Path,
) -> dict:
    """
    Charge un fichier JSON et vérifie que sa racine
    contient un objet JSON.
    """

    data = load_json(path)

    if not isinstance(data, dict):
        raise ValueError(
            f"Le fichier {path} doit contenir "
            "un objet JSON."
        )

    return data


def load_json_list(
    path: str | Path,
) -> list:
    """
    Charge un fichier JSON et vérifie que sa racine
    contient une liste JSON.
    """

    data = load_json(path)

    if not isinstance(data, list):
        raise ValueError(
            f"Le fichier {path} doit contenir "
            "une liste JSON."
        )

    return data