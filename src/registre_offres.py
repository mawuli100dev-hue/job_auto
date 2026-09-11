"""
registre_offres.py
Registre simple des offres déjà traitées par le pipeline (CV + lettre déjà
générés), identifiées par leur ID France Travail.

FORMAT (nouveau, simplifié) : un simple fichier TEXTE, UN ID PAR LIGNE, SANS
EN-TÊTE. Le format CSV-avec-en-tête a été abandonné car il causait un bug
silencieux : si le fichier était un jour créé/édité sans la ligne d'en-tête
"id" (par erreur, ou manuellement), csv.DictReader traitait la première offre
comme le nom de la colonne au lieu d'une donnée, et TOUT le registre semblait
vide alors qu'il contenait des ids valides. Un simple fichier ligne par ligne
n'a pas cette ambiguïté : chaque ligne non vide est un id, un point c'est tout.

Le registre est stocké par défaut dans data/offres_traitees.csv (le nom de
fichier ne change pas, seul son contenu interne est maintenant un texte simple
plutôt qu'un CSV avec en-tête - ton fichier existant fonctionne tel quel avec
cette nouvelle version, aucune migration nécessaire).

Usage :
    python src\\registre_offres.py --check 213QBYH
    python src\\registre_offres.py --add 213QBYH
    python src\\registre_offres.py --add-list "213SGGN,213QWNF,213QBYH,6764798,6748181"
    python src\\registre_offres.py --list
    python src\\registre_offres.py --nettoyer   # supprime doublons/lignes vides du fichier
"""

import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REGISTRE_PATH_DEFAUT = BASE_DIR / "data" / "offres_traitees.csv"


def load_registre(path: Path) -> set[str]:
    """Charge l'ensemble des ids déjà présents dans le registre. Une ligne par
    id, lignes vides ignorées. Renvoie un ensemble vide si le fichier n'existe
    pas encore (première utilisation)."""
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {ligne.strip() for ligne in f if ligne.strip()}


def is_already_processed(offer_id: str, path: Path = REGISTRE_PATH_DEFAUT) -> bool:
    return offer_id.strip() in load_registre(path)


def add_to_registre(offer_id: str, path: Path = REGISTRE_PATH_DEFAUT) -> bool:
    """Ajoute l'id au registre s'il n'y est pas déjà.
    Retourne True si réellement ajouté, False si déjà présent (idempotent)."""
    offer_id = offer_id.strip()
    if not offer_id:
        return False

    ids_existants = load_registre(path)
    if offer_id in ids_existants:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(offer_id + "\n")
    return True


def add_list_to_registre(offer_ids: list[str], path: Path = REGISTRE_PATH_DEFAUT) -> tuple[int, int]:
    """Ajoute plusieurs ids d'un coup. Retourne (nb_ajoutes, nb_deja_presents)."""
    nb_ajoutes = 0
    nb_deja_presents = 0
    for offer_id in offer_ids:
        offer_id = offer_id.strip()
        if not offer_id:
            continue
        if add_to_registre(offer_id, path):
            nb_ajoutes += 1
        else:
            nb_deja_presents += 1
    return nb_ajoutes, nb_deja_presents


def nettoyer_registre(path: Path) -> tuple[int, int]:
    """Réécrit le fichier proprement : supprime lignes vides et doublons,
    en conservant l'ordre de première apparition. Retourne (avant, apres)."""
    if not path.exists():
        return (0, 0)

    with open(path, encoding="utf-8") as f:
        lignes_brutes = [ligne.strip() for ligne in f]

    avant = len([l for l in lignes_brutes if l])

    vus = set()
    propres = []
    for ligne in lignes_brutes:
        if ligne and ligne not in vus:
            vus.add(ligne)
            propres.append(ligne)

    with open(path, "w", encoding="utf-8") as f:
        for id_ in propres:
            f.write(id_ + "\n")

    return (avant, len(propres))


def main():
    parser = argparse.ArgumentParser(description="Registre des offres deja traitees par le pipeline (CV + lettre generes)")
    parser.add_argument("--registre", default=str(REGISTRE_PATH_DEFAUT),
                         help="Chemin du fichier registre (defaut: data/offres_traitees.csv)")

    groupe = parser.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--check", metavar="ID", help="Verifie si cet ID a deja ete traite (code retour 0=non, 1=oui)")
    groupe.add_argument("--add", metavar="ID", help="Ajoute cet ID au registre (idempotent)")
    groupe.add_argument("--add-list", metavar="ID1,ID2,...", help="Ajoute plusieurs IDs d'un coup, separes par des virgules")
    groupe.add_argument("--list", action="store_true", help="Affiche tous les IDs deja enregistres")
    groupe.add_argument("--nettoyer", action="store_true", help="Supprime les lignes vides et les doublons du fichier")

    args = parser.parse_args()
    path = Path(args.registre)

    if args.list:
        ids = sorted(load_registre(path))
        print(f"{len(ids)} offre(s) deja traitee(s) dans le registre ({path}) :")
        for i in ids:
            print(f"  - {i}")
        return

    if args.check:
        if is_already_processed(args.check, path):
            print(f"DEJA_TRAITEE: {args.check}")
            raise SystemExit(1)
        else:
            print(f"NON_TRAITEE: {args.check}")
            raise SystemExit(0)

    if args.add:
        ajoute = add_to_registre(args.add, path)
        if ajoute:
            print(f"Ajoute au registre : {args.add}")
        else:
            print(f"Deja present dans le registre, aucun doublon ajoute : {args.add}")
        return

    if args.add_list:
        ids = [i for i in args.add_list.split(",") if i.strip()]
        nb_ajoutes, nb_deja_presents = add_list_to_registre(ids, path)
        print(f"{nb_ajoutes} id(s) ajoute(s), {nb_deja_presents} deja present(s) (ignore(s)).")
        print(f"Registre a jour : {path}")
        return

    if args.nettoyer:
        avant, apres = nettoyer_registre(path)
        print(f"Nettoyage termine : {avant} ligne(s) valide(s) avant, {apres} apres suppression des doublons/lignes vides.")


if __name__ == "__main__":
    main()