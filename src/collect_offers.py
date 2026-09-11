"""
collect_offers.py
Collecte les offres d'emploi/alternance via l'API France Travail (ex Pôle Emploi)
et les enregistre dans data/offres/<date_du_jour>/offres_<date>_<heure>.csv

Prérequis :
1. Créer un compte développeur sur https://francetravail.io
2. Créer une application pour obtenir un client_id et un client_secret
3. Souscrire à l'API "Offres d'emploi v2" (scope api_offresdemploiv2 o2dsoffre)
4. Placer les identifiants dans un fichier .env à la racine du projet :
     FT_CLIENT_ID=xxxxx
     FT_CLIENT_SECRET=xxxxx

Installation :
    pip install requests python-dotenv

Codes utiles :
    typeContrat : CDI, CDD, MIS (interim), SAI (saisonnier), CCE, FRA, LIB, REP, TTI, DDI
    natureContrat (alternance) : E1 = contrat d'apprentissage, E2 = contrat de professionnalisation

COMPORTEMENT PAR DÉFAUT : TOUT RÉCUPÉRER AUTOMATIQUEMENT
Sans --max, le script récupère TOUT ce qui correspond à la recherche (pagination
automatique), sans jamais te demander de deviner un chiffre.

FILTRE D'ANCIENNETÉ
Par défaut, seules les offres publiées il y a 3 SEMAINES ou moins sont conservées
(minCreationDate + maxCreationDate envoyés ensemble à l'API, comme elle l'exige,
+ un filet de sécurité qui revérifie chaque date côté script). Réglable via
--max-anciennete-jours (0 pour désactiver).

COUVERTURE DU DOMAINE "DATA" (important)
L'API France Travail fait une recherche PAR PERTINENCE sur les mots-clés fournis,
pas une recherche large automatique : demander "data analyst" privilégie fortement
ce métier précis et laisse de côté une bonne partie des offres "data scientist",
"data engineer", "business intelligence", "machine learning", etc.

Pour couvrir tout le domaine data, utilise --keywords-list avec plusieurs requêtes
séparées par des virgules : le script fait UNE recherche complète (avec pagination
et filtre d'ancienneté) PAR mot-clé, puis FUSIONNE et DÉDOUBLONNE automatiquement
les résultats (une même offre trouvée par deux recherches différentes n'apparaît
qu'une fois dans le CSV final, identifiée par son id).

Usage :
    python src\\collect_offers.py
        # utilise --keywords par défaut ("data"), tout récupérer, offres <= 3 semaines

    python src\\collect_offers.py --keywords-list "data scientist,data engineer,data analyst,business intelligence,machine learning"
        # 5 recherches distinctes, fusionnées et dédoublonnées en un seul CSV

    python src\\collect_offers.py --max-anciennete-jours 14
    python src\\collect_offers.py --max 150

    python src\collect_offers.py --keywords-list "data,data analyst,data scientist,data engineer,business intelligence,machine learning,intelligence artificielle" --max-anciennete-jours 21
"""

import os
import csv
import time
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # remonte de src/ vers job_automation/
load_dotenv(BASE_DIR / ".env")

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
API_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

CLIENT_ID = os.getenv("FT_CLIENT_ID")
CLIENT_SECRET = os.getenv("FT_CLIENT_SECRET")

FIELDNAMES = [
    "id", "intitule", "entreprise", "lieu", "type_contrat", "nature_contrat",
    "duree_contrat", "date_creation", "salaire", "experience_exigee",
    "competences", "description", "url",
]

TAILLE_PAGE_MAX = 150
LIMITE_GLOBALE_API = 3000
DELAI_ENTRE_APPELS_SEC = 0.3
DELAI_ENTRE_MOTS_CLES_SEC = 0.5

ANCIENNETE_MAX_JOURS_DEFAUT = 21

# Mots-clés couvrant largement le domaine "data" (utilisés en exemple/suggestion,
# pas imposés par défaut pour ne pas changer le comportement existant sans le vouloir).
SUGGESTION_KEYWORDS_LIST = (
    "data,data analyst,data scientist,data engineer,"
    "business intelligence,machine learning,intelligence artificielle"
)


def get_access_token() -> str:
    """Récupère un token OAuth2 (client_credentials) valable ~30 minutes."""
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "FT_CLIENT_ID et FT_CLIENT_SECRET doivent être définis (fichier .env)."
        )

    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "api_offresdemploiv2 o2dsoffre",
    }
    resp = requests.post(TOKEN_URL, data=data, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _normalize_offer(o: dict) -> dict:
    lieu = o.get("lieuTravail", {}) or {}
    entreprise = o.get("entreprise", {}) or {}
    competences = ", ".join(
        c.get("libelle", "") for c in o.get("competences", []) or []
    )
    return {
        "id": o.get("id", ""),
        "intitule": o.get("intitule", ""),
        "entreprise": entreprise.get("nom", "Non précisé"),
        "lieu": lieu.get("libelle", ""),
        "type_contrat": o.get("typeContratLibelle", ""),
        "nature_contrat": o.get("natureContrat", ""),
        "duree_contrat": o.get("dureeTravailLibelle", ""),
        "date_creation": o.get("dateCreation", ""),
        "salaire": (o.get("salaire", {}) or {}).get("libelle", ""),
        "experience_exigee": o.get("experienceLibelle", ""),
        "competences": competences,
        "description": (o.get("description", "") or "").replace("\n", " ").strip(),
        "url": o.get("origineOffre", {}).get("urlOrigine", ""),
    }


def _parse_total_disponible(headers: dict) -> int | None:
    content_range = headers.get("Content-Range")
    if not content_range or "/" not in content_range:
        return None
    try:
        return int(content_range.rsplit("/", 1)[-1])
    except ValueError:
        return None


def _parse_date_creation(date_str: str) -> datetime | None:
    if not date_str:
        return None
    candidats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in candidats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _fetch_page(token: str, params: dict, start: int, end: int) -> tuple[list[dict], int | None, str]:
    headers = {"Authorization": f"Bearer {token}"}
    page_params = dict(params)
    page_params["range"] = f"{start}-{end}"

    resp = requests.get(API_URL, headers=headers, params=page_params, timeout=20)

    if resp.status_code == 401:
        print("    Token expiré en cours de pagination, renouvellement...")
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(API_URL, headers=headers, params=page_params, timeout=20)

    if resp.status_code == 204:
        return [], _parse_total_disponible(resp.headers), token

    if resp.status_code not in (200, 206):
        print("Réponse de l'API :", resp.text[:1000])
        resp.raise_for_status()

    total_disponible = _parse_total_disponible(resp.headers)
    raw_offers = resp.json().get("resultats", [])
    return raw_offers, total_disponible, token


def discover_total(token: str, params: dict) -> int | None:
    _, total_disponible, _ = _fetch_page(token, params, 0, 0)
    return total_disponible


def _build_base_params(keywords: str, commune: str | None, distance_km: int,
                        contract_type: str | None, contract_nature: str | None,
                        anciennete_max_jours: int) -> tuple[dict, "datetime | None"]:
    params = {
        "motsCles": keywords,
        "sort": 1,
    }
    if commune:
        params["commune"] = commune
        params["distance"] = distance_km
    if contract_type:
        params["typeContrat"] = contract_type
    if contract_nature:
        params["natureContrat"] = contract_nature

    seuil_date = None
    if anciennete_max_jours and anciennete_max_jours > 0:
        maintenant = datetime.now(timezone.utc)
        seuil_date = maintenant - timedelta(days=anciennete_max_jours)
        # minCreationDate et maxCreationDate sont OBLIGATOIREMENT fournis ensemble.
        params["minCreationDate"] = seuil_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        params["maxCreationDate"] = maintenant.strftime("%Y-%m-%dT%H:%M:%SZ")

    return params, seuil_date


def search_offers(
    token: str,
    keywords: str = "",
    commune: str | None = None,
    distance_km: int = 30,
    contract_type: str | None = None,
    contract_nature: str | None = None,
    max_results: int | None = None,
    anciennete_max_jours: int = ANCIENNETE_MAX_JOURS_DEFAUT,
) -> tuple[list[dict], int | None, int]:
    """Recherche pour UN SEUL mot-clé (ou une seule chaîne motsCles). Pagine
    automatiquement et applique le filtre d'ancienneté (serveur + filet de sécurité)."""
    params, seuil_date = _build_base_params(
        keywords, commune, distance_km, contract_type, contract_nature, anciennete_max_jours
    )

    if seuil_date is not None:
        print(f"  Filtre d'ancienneté actif : offres depuis {seuil_date.strftime('%d/%m/%Y %H:%M')} ({anciennete_max_jours}j max).")
    else:
        print("  Filtre d'ancienneté désactivé.")

    total_disponible = discover_total(token, params)

    if max_results is None:
        if total_disponible is None:
            objectif = LIMITE_GLOBALE_API
        else:
            objectif = min(total_disponible, LIMITE_GLOBALE_API)
            if total_disponible > LIMITE_GLOBALE_API:
                print(f"  {total_disponible} offre(s) au total, plafonné à {LIMITE_GLOBALE_API} (limite API).")
    else:
        objectif = max_results

    print(f"  {total_disponible if total_disponible is not None else '?'} offre(s) disponible(s), objectif : {objectif}.")

    if objectif == 0:
        return [], total_disponible, 0

    all_offers: list[dict] = []
    ecartees_anciennete = 0
    start = 0

    while len(all_offers) < objectif:
        end = min(start + TAILLE_PAGE_MAX, objectif) - 1

        raw_offers, page_total, token = _fetch_page(token, params, start, end)
        if page_total is not None:
            total_disponible = page_total

        if not raw_offers:
            break

        for o in raw_offers:
            offer = _normalize_offer(o)
            if seuil_date is not None:
                date_creation = _parse_date_creation(offer["date_creation"])
                if date_creation is not None and date_creation < seuil_date:
                    ecartees_anciennete += 1
                    continue
            all_offers.append(offer)

        print(f"    Page {start}-{end} : {len(raw_offers)} reçue(s), {len(all_offers)} retenue(s)"
              + (f" / {total_disponible} disponibles" if total_disponible is not None else ""))

        start += TAILLE_PAGE_MAX

        if total_disponible is not None and start >= total_disponible:
            break

        if len(all_offers) < objectif:
            time.sleep(DELAI_ENTRE_APPELS_SEC)

    return all_offers[:objectif], total_disponible, ecartees_anciennete


def search_offers_multi_keywords(
    token: str,
    keywords_list: list[str],
    commune: str | None = None,
    distance_km: int = 30,
    contract_type: str | None = None,
    contract_nature: str | None = None,
    max_results_par_mot_cle: int | None = None,
    anciennete_max_jours: int = ANCIENNETE_MAX_JOURS_DEFAUT,
) -> tuple[list[dict], dict]:
    """Lance une recherche complète (pagination + filtre ancienneté) POUR CHAQUE
    mot-clé de la liste, puis fusionne et dédoublonne les résultats par id d'offre.
    Retourne (offres fusionnées et dédoublonnées, statistiques par mot-clé)."""
    offres_par_id: dict[str, dict] = {}
    stats: dict[str, dict] = {}

    for i, mot_cle in enumerate(keywords_list, start=1):
        mot_cle = mot_cle.strip()
        if not mot_cle:
            continue
        print(f"\n[{i}/{len(keywords_list)}] Recherche pour le mot-clé : '{mot_cle}'")
        offres, total_disponible, ecartees = search_offers(
            token,
            keywords=mot_cle,
            commune=commune,
            distance_km=distance_km,
            contract_type=contract_type,
            contract_nature=contract_nature,
            max_results=max_results_par_mot_cle,
            anciennete_max_jours=anciennete_max_jours,
        )

        nouvelles = 0
        for offre in offres:
            if offre["id"] and offre["id"] not in offres_par_id:
                offres_par_id[offre["id"]] = offre
                nouvelles += 1

        stats[mot_cle] = {
            "trouvees": len(offres),
            "nouvelles_apres_dedoublonnage": nouvelles,
            "total_disponible_api": total_disponible,
        }
        print(f"  -> {len(offres)} offre(s) trouvée(s) pour '{mot_cle}', dont {nouvelles} nouvelle(s) "
              f"(pas encore vue(s) avec un autre mot-clé).")

        if i < len(keywords_list):
            time.sleep(DELAI_ENTRE_MOTS_CLES_SEC)

    return list(offres_par_id.values()), stats


def save_to_csv(offers: list[dict], base_dir: Path | None = None) -> str:
    """Crée data/offres/<date_du_jour>/offres_<date>_<heure>.csv et y écrit les offres."""
    if base_dir is None:
        base_dir = BASE_DIR / "data" / "offres"

    today = datetime.now().strftime("%Y-%m-%d")
    folder = base_dir / today
    folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"offres_{today}_{timestamp}.csv"
    filepath = folder / filename

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(offers)

    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="Collecte d'offres France Travail (couverture large du domaine data)")
    parser.add_argument("--keywords", default="data",
                         help="Mot-clé de recherche unique (défaut 'data', volontairement large). "
                              "Ignoré si --keywords-list est fourni.")
    parser.add_argument("--keywords-list", default=None,
                         help="Liste de mots-clés séparés par des virgules, pour couvrir plusieurs métiers "
                              "data en une seule exécution (une recherche complète par mot-clé, fusionnées "
                              "et dédoublonnées). Ex: \"" + SUGGESTION_KEYWORDS_LIST + "\"")
    parser.add_argument("--commune", default=None, help="Code INSEE de la commune (ex: 11069 pour Carcassonne)")
    parser.add_argument("--distance", type=int, default=30, help="Rayon de recherche en km (utilisé seulement avec --commune)")
    parser.add_argument("--contrat", default=None, help="Type de contrat: CDI, CDD, MIS, SAI...")
    parser.add_argument("--nature", default="E1,E2", help="Nature de contrat pour l'alternance: E1 (apprentissage), E2 (professionnalisation)")
    parser.add_argument("--max", type=int, default=None,
                         help="Plafond volontaire du nombre d'offres à récupérer PAR MOT-CLÉ. NON PRÉCISÉ : "
                              "récupère TOUT ce qui correspond, automatiquement.")
    parser.add_argument("--max-anciennete-jours", type=int, default=ANCIENNETE_MAX_JOURS_DEFAUT,
                         help=f"Ancienneté maximale des offres, en jours (défaut {ANCIENNETE_MAX_JOURS_DEFAUT} = 3 semaines). "
                              f"0 pour désactiver.")
    args = parser.parse_args()

    print("Authentification auprès de l'API France Travail...")
    token = get_access_token()

    if args.keywords_list:
        keywords_list = [k for k in args.keywords_list.split(",") if k.strip()]
        print(f"Recherche multi-mots-clés ({len(keywords_list)} terme(s)) : {', '.join(keywords_list)}")
        offers, stats = search_offers_multi_keywords(
            token,
            keywords_list=keywords_list,
            commune=args.commune,
            distance_km=args.distance,
            contract_type=args.contrat,
            contract_nature=args.nature,
            max_results_par_mot_cle=args.max,
            anciennete_max_jours=args.max_anciennete_jours,
        )

        print("\n=== Résumé par mot-clé ===")
        for mot_cle, s in stats.items():
            print(f"  '{mot_cle}' : {s['trouvees']} trouvée(s), {s['nouvelles_apres_dedoublonnage']} nouvelle(s) après dédoublonnage")

        print(f"\n{len(offers)} offre(s) UNIQUE(S) au total après fusion et dédoublonnage de {len(keywords_list)} recherche(s).")

    else:
        print(f"Recherche d'offres : '{args.keywords}' (nature={args.nature})"
              + (f", plafond volontaire : {args.max}" if args.max is not None else ", objectif : TOUT récupérer") + "...")
        offers, total_disponible, ecartees_anciennete = search_offers(
            token,
            keywords=args.keywords,
            commune=args.commune,
            distance_km=args.distance,
            contract_type=args.contrat,
            contract_nature=args.nature,
            max_results=args.max,
            anciennete_max_jours=args.max_anciennete_jours,
        )
        print(f"\n{len(offers)} offre(s) récupérée(s) au total.")
        if ecartees_anciennete > 0:
            print(f"{ecartees_anciennete} offre(s) écartée(s) par le filet de sécurité d'ancienneté.")
        if total_disponible is not None and args.max is not None and total_disponible > len(offers):
            manquantes = total_disponible - len(offers)
            print(f"ATTENTION : {manquantes} offre(s) supplémentaire(s) existent mais n'ont pas été récupérées "
                  f"à cause du plafond volontaire --max {args.max}.")

    filepath = save_to_csv(offers)
    print(f"\nFichier enregistré : {filepath}")


if __name__ == "__main__":
    main()