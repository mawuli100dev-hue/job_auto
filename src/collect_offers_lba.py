"""
collect_offers_lba.py
Collecte les offres d'alternance via l'API "La Bonne Alternance" (Mission
Apprentissage / beta.gouv.fr) et les enregistre dans
data/offres_lba/<date_du_jour>/offres_lba_<date>_<heure>.csv

Prérequis :
1. Créer un compte sur https://api.apprentissage.beta.gouv.fr
2. Dans "Mon compte" -> "Jetons d'accès API", générer un jeton (sandbox pour
   tester).
3. Placer le jeton dans le fichier .env à la racine du projet :
     LBA_API_TOKEN=xxxxx

RAPPEL : cette API cherche par CODE(S) ROME, pas par mots-clés libres. Il n'y
a pas de code ROME dédié "intelligence artificielle" : ces offres sont
réparties entre M1403 (IA appliquée à la donnée) et M1805 (IA appliquée au
développement/ingénierie).

CORRECTIF v2 (2026-09-11 - codes ROME orientés data/BI/ML/IA) :
Les 5 codes ROME par défaut couvrent maintenant explicitement "data, data
analyst, data scientist, data engineer, business intelligence, machine
learning, intelligence artificielle" :
- M1419 : Data Analyst (nouveau code dédié introduit par le ROME 4.0)
- M1403 : Études et prospectives socio-économiques (Data Scientist/Analyst,
  ancien classement ROME 3.0 encore très utilisé par de nombreuses offres)
- M1805 : Études et développement informatique (Data Engineer, Machine
  Learning Engineer, développement lié à l'IA)
- M1802 : Expertise et support en systèmes d'information (inclut souvent la
  Business Intelligence)
- M1810 : Production et exploitation de systèmes d'information

CORRECTIF MAJEUR ANTÉRIEUR (à partir du schéma OpenAPI officiel) :
- Chemin exact de la recherche : GET /job/v1/search (base .../api)
- PAS de paramètre "insee" : uniquement latitude/longitude. Ce script géocode
  une ville via l'API Adresse gratuite du gouvernement si --ville est fourni.
- AUCUNE PAGINATION : l'API plafonne à 150 offres par source, une seule
  requête par combinaison de critères.
- Réponse de recherche : {"jobs": [...], "recruiters": [...], "warnings": [...]}.
- Limite de débit recherche : 60 appels/minute par jeton.
- GET /job/v1/offer/{id} renvoie le détail complet d'UNE offre précise (schéma
  identique à celui de la recherche, confirmé par la doc officielle). Limite
  de débit : 120 appels/minute.

  python src\collect_offers_lba.py --romes M1419,M1403,M1805,M1802,M1810
"""

import os
import csv
import json
import time
import argparse
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

LBA_API_TOKEN = os.getenv("LBA_API_TOKEN")

BASE_URL = "https://api.apprentissage.beta.gouv.fr/api"
SEARCH_ENDPOINT = f"{BASE_URL}/job/v1/search"
OFFER_DETAIL_ENDPOINT = f"{BASE_URL}/job/v1/offer/{{id}}"

# API Adresse du gouvernement (gratuite, sans clé) pour convertir une ville
# en coordonnées GPS, puisque l'API La Bonne Alternance ne prend pas de code INSEE.
GEOCODE_ENDPOINT = "https://api-adresse.data.gouv.fr/search/"

FIELDNAMES = [
    "id", "intitule", "entreprise", "lieu", "type_contrat", "teletravail",
    "date_debut", "duree_contrat_mois", "niveau_diplome", "nb_postes",
    "competences_attendues", "competences_a_acquerir", "description",
    "url_candidature", "telephone_candidature", "recipient_id",
    "is_delegated", "partner_label", "codes_rome",
]

DELAI_ENTRE_ROMES_SEC = 1.1  # 60 appels/minute max (recherche) -> marge de sécurité

# Codes ROME couvrant le domaine data / BI / machine learning / IA.
ROME_SUGGERES = {
    "M1419": "Data Analyst (code ROME 4.0 dédié)",
    "M1403": "Études et prospectives socio-économiques (Data Scientist/Analyst, ancien classement)",
    "M1805": "Études et développement informatique (Data Engineer, Machine Learning Engineer)",
    "M1802": "Expertise et support en systèmes d'information (inclut souvent la BI)",
    "M1810": "Production et exploitation de systèmes d'information",
}


def _get_headers() -> dict:
    if not LBA_API_TOKEN:
        raise RuntimeError("LBA_API_TOKEN doit être défini dans .env (jeton depuis 'Mon compte').")
    return {"Authorization": f"Bearer {LBA_API_TOKEN}", "Accept": "application/json"}


def geocode_ville(ville: str) -> tuple[float, float] | None:
    """Convertit un nom de ville en (latitude, longitude) via l'API Adresse
    gratuite du gouvernement. Retourne None si aucun résultat."""
    resp = requests.get(GEOCODE_ENDPOINT, params={"q": ville, "limit": 1}, timeout=10)
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        return None
    lon, lat = features[0]["geometry"]["coordinates"]
    label = features[0]["properties"].get("label", ville)
    print(f"  Géocodage '{ville}' -> {label} (lat={lat}, lon={lon})")
    return lat, lon


def _request_json(url: str, headers: dict, params: dict | None = None) -> dict:
    resp = requests.get(url, headers=headers, params=params or {}, timeout=20)

    print(f"    -> GET {resp.url}")
    print(f"    -> Statut HTTP : {resp.status_code} | Content-Type : {resp.headers.get('Content-Type', '?')}")

    if resp.status_code == 401:
        raise RuntimeError("401 Unauthorized : vérifie LBA_API_TOKEN dans .env.")
    if resp.status_code == 403:
        raise RuntimeError("403 Forbidden : jeton invalide ou habilitation insuffisante.")
    if resp.status_code == 404:
        raise RuntimeError(f"404 Not Found sur {resp.url} : ressource introuvable (id incorrect ?).")
    if resp.status_code == 419:
        raise RuntimeError("419 Too Many Requests : limite d'appels/minute atteinte, attends avant de relancer.")

    try:
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.JSONDecodeError:
        apercu = resp.text[:1000] if resp.text else "(corps de réponse totalement vide)"
        raise RuntimeError(
            f"Impossible de parser la réponse en JSON.\n"
            f"  URL appelée : {resp.url}\n"
            f"  Code de statut : {resp.status_code}\n"
            f"  Corps de la réponse (aperçu) :\n{apercu}"
        )


def _normalize_offer(o: dict) -> dict:
    """Aplati la structure identifier/contract/offer/workplace/apply (schéma
    JobOfferRead officiel, confirmé identique entre /job/v1/search et
    /job/v1/offer/{id}) en une ligne de CSV."""
    identifier = o.get("identifier", {}) or {}
    contract = o.get("contract", {}) or {}
    offer = o.get("offer", {}) or {}
    workplace = o.get("workplace", {}) or {}
    apply_block = o.get("apply", {}) or {}
    location = workplace.get("location", {}) or {}
    target_diploma = offer.get("target_diploma", {}) or {}

    type_contrat = contract.get("type", []) or []
    if isinstance(type_contrat, list):
        type_contrat = ", ".join(type_contrat)

    desired_skills = ", ".join(offer.get("desired_skills", []) or [])
    acquired_skills = ", ".join(offer.get("to_be_acquired_skills", []) or [])
    rome_codes = ", ".join(offer.get("rome_codes", []) or [])

    return {
        "id": identifier.get("id", "") or identifier.get("partner_job_id", ""),
        "intitule": offer.get("title", ""),
        "entreprise": workplace.get("name", "Non précisé"),
        "lieu": location.get("address", ""),
        "type_contrat": type_contrat,
        "teletravail": contract.get("remote", ""),
        "date_debut": contract.get("start", ""),
        "duree_contrat_mois": contract.get("duration", ""),
        "niveau_diplome": target_diploma.get("label", "") if target_diploma else "",
        "nb_postes": offer.get("opening_count", ""),
        "competences_attendues": desired_skills,
        "competences_a_acquerir": acquired_skills,
        "description": (offer.get("description", "") or "").replace("\n", " ").strip(),
        "url_candidature": apply_block.get("url", ""),
        "telephone_candidature": apply_block.get("phone", ""),
        "recipient_id": apply_block.get("recipient_id", ""),
        "is_delegated": o.get("is_delegated", ""),
        "partner_label": identifier.get("partner_label", ""),
        "codes_rome": rome_codes,
    }


def get_offer_detail(offer_id: str, debug: bool = False) -> dict:
    """GET /job/v1/offer/{id} : récupère le détail complet d'UNE offre.
    Limite de débit : 120 appels/minute (distincte de la recherche)."""
    headers = _get_headers()
    url = OFFER_DETAIL_ENDPOINT.format(id=offer_id)
    raw_offer = _request_json(url, headers)

    if debug:
        print("\n--- DEBUG : JSON brut de l'offre ---")
        print(json.dumps(raw_offer, indent=2, ensure_ascii=False)[:3000])
        print("--- FIN DEBUG ---\n")

    return _normalize_offer(raw_offer)


def search_offers_for_rome(
    rome: str,
    latitude: float | None,
    longitude: float | None,
    distance_km: int,
    diploma_level: str | None,
    rncp: str | None,
    debug: bool = False,
) -> list[dict]:
    """Une seule requête (pas de pagination possible sur cette API)."""
    headers = _get_headers()
    params: dict = {"romes": rome, "radius": distance_km}
    if latitude is not None and longitude is not None:
        params["latitude"] = latitude
        params["longitude"] = longitude
    if diploma_level:
        params["target_diploma_level"] = diploma_level
    if rncp:
        params["rncp"] = rncp

    payload = _request_json(SEARCH_ENDPOINT, headers, params)

    raw_offers = payload.get("jobs", [])
    warnings = payload.get("warnings", [])
    for w in warnings:
        print(f"    ⚠ Avertissement API : {w.get('message', w)}")

    if debug and raw_offers:
        print("\n--- DEBUG : JSON brut de la 1ère offre reçue ---")
        print(json.dumps(raw_offers[0], indent=2, ensure_ascii=False)[:3000])
        print("--- FIN DEBUG ---\n")

    offers = [_normalize_offer(o) for o in raw_offers]
    print(f"    ROME {rome} : {len(offers)} offre(s) reçue(s) "
          f"(plafond de 150/source appliqué par l'API elle-même, pas de pagination possible).")
    return offers


def search_offers_multi_romes(
    romes: list[str],
    latitude: float | None,
    longitude: float | None,
    distance_km: int,
    diploma_level: str | None,
    rncp: str | None,
    debug: bool = False,
) -> tuple[list[dict], dict]:
    offres_par_id: dict[str, dict] = {}
    stats: dict[str, dict] = {}

    for i, rome in enumerate(romes, start=1):
        rome = rome.strip()
        if not rome:
            continue
        libelle = ROME_SUGGERES.get(rome, "")
        print(f"\n[{i}/{len(romes)}] Recherche pour le code ROME : '{rome}'"
              + (f" ({libelle})" if libelle else ""))

        offres = search_offers_for_rome(
            rome=rome, latitude=latitude, longitude=longitude,
            distance_km=distance_km, diploma_level=diploma_level, rncp=rncp, debug=debug,
        )

        nouvelles = 0
        for offre in offres:
            if offre["id"] and offre["id"] not in offres_par_id:
                offres_par_id[offre["id"]] = offre
                nouvelles += 1

        stats[rome] = {"trouvees": len(offres), "nouvelles_apres_dedoublonnage": nouvelles}
        print(f"  -> {len(offres)} offre(s) trouvée(s), dont {nouvelles} nouvelle(s).")

        if i < len(romes):
            time.sleep(DELAI_ENTRE_ROMES_SEC)

    return list(offres_par_id.values()), stats


def save_to_csv(offers: list[dict], base_dir: Path | None = None) -> str:
    if base_dir is None:
        base_dir = BASE_DIR / "data" / "offres_lba"

    today = datetime.now().strftime("%Y-%m-%d")
    folder = base_dir / today
    folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"offres_lba_{today}_{timestamp}.csv"
    filepath = folder / filename

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(offers)

    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="Collecte d'offres La Bonne Alternance (data/BI/ML/IA par défaut)")
    parser.add_argument("--romes", default=",".join(ROME_SUGGERES.keys()),
                         help="Codes ROME séparés par des virgules. Défaut : sélection data/BI/ML/IA.")
    parser.add_argument("--ville", default=None,
                         help="Nom de ville à géocoder automatiquement (ex: 'Carcassonne'). "
                              "Alternative à --latitude/--longitude.")
    parser.add_argument("--latitude", type=float, default=None)
    parser.add_argument("--longitude", type=float, default=None)
    parser.add_argument("--distance", type=int, default=30, help="Rayon de recherche en km (0-200)")
    parser.add_argument("--diploma-level", default=None, choices=["3", "4", "5", "6", "7"])
    parser.add_argument("--rncp", default=None)
    parser.add_argument("--offer-id", default=None,
                         help="Si fourni, ignore la recherche et récupère UNIQUEMENT le détail "
                              "de cette offre précise via GET /job/v1/offer/{id}.")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    # --- Mode "détail d'une offre précise" ---
    if args.offer_id:
        print(f"Récupération du détail de l'offre '{args.offer_id}'...")
        try:
            offre = get_offer_detail(args.offer_id, debug=args.debug)
        except RuntimeError as e:
            print(f"\n❌ ERREUR : {e}")
            return
        print(json.dumps(offre, indent=2, ensure_ascii=False))
        filepath = save_to_csv([offre])
        print(f"\nFichier enregistré : {filepath}")
        return

    # --- Mode recherche multi-ROME (comportement par défaut, orienté data/BI/ML/IA) ---
    romes = [r for r in args.romes.split(",") if r.strip()]
    print(f"Recherche La Bonne Alternance sur {len(romes)} code(s) ROME : {', '.join(romes)}")

    latitude, longitude = args.latitude, args.longitude
    if args.ville and (latitude is None or longitude is None):
        result = geocode_ville(args.ville)
        if result is None:
            print(f"ATTENTION : impossible de géocoder '{args.ville}', recherche sans géolocalisation.")
        else:
            latitude, longitude = result

    if latitude is None or longitude is None:
        print("ATTENTION : aucune géolocalisation fournie (--ville ou --latitude/--longitude), "
              "la recherche couvrira toute la France.")

    try:
        offers, stats = search_offers_multi_romes(
            romes=romes, latitude=latitude, longitude=longitude,
            distance_km=args.distance, diploma_level=args.diploma_level,
            rncp=args.rncp, debug=args.debug,
        )
    except RuntimeError as e:
        print(f"\n❌ ERREUR : {e}")
        return

    print("\n=== Résumé par code ROME ===")
    for rome, s in stats.items():
        print(f"  '{rome}' : {s['trouvees']} trouvée(s), {s['nouvelles_apres_dedoublonnage']} nouvelle(s)")

    print(f"\n{len(offers)} offre(s) UNIQUE(S) au total après fusion et dédoublonnage.")
    print("RAPPEL : l'API plafonne à 150 offres par source (La Bonne Alternance / France "
          "Travail / partenaires) et par requête, sans pagination possible.")

    filepath = save_to_csv(offers)
    print(f"\nFichier enregistré : {filepath}")


if __name__ == "__main__":
    main()