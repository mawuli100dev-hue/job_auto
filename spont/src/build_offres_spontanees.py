"""
build_offres_spontanees.py
Prend le CSV propre produit par normalize_entreprises.py (une entreprise par
ligne) et génère un CSV au FORMAT EXACT des offres collectées par
collect_offers.py (mêmes colonnes : id, intitule, entreprise, lieu,
type_contrat, nature_contrat, duree_contrat, date_creation, salaire,
experience_exigee, competences, description, url).

Objectif : pouvoir lancer tailor_cv.py --csv <ce_fichier> --offer-id SPONT-xxx
exactement comme pour une vraie offre, pour construire une candidature
spontanée ciblée sur une entreprise précise de la liste.

COMMENT ÇA MARCHE (l'agent) :
1. Pour chaque entreprise, si un site web est renseigné, le script tente de
   récupérer le texte de la page d'accueil (requests + nettoyage HTML basique)
   pour donner un contexte réel au LLM plutôt que de deviner.
2. Le LLM rédige ensuite un intitulé de candidature spontanée et une COURTE
   description de l'entreprise, EXCLUSIVEMENT à partir des informations
   fournies (nom, adresse, service, extrait du site web si disponible).

RÈGLE D'HONNÊTETÉ (même principe que generate_letter.py) :
INTERDICTION ABSOLUE d'inventer des faits précis sur l'entreprise (chiffres,
technologies utilisées, projets) qui ne sont pas dans les informations
fournies. Si aucune information fiable n'est disponible au-delà du nom et de
la ville, la description reste volontairement générique ("Structure basée à
Ville, activité non détaillée dans les informations disponibles") plutôt que
d'inventer. C'est essentiel : ce texte sera repris tel quel par
generate_letter.py pour rédiger une vraie lettre de motivation.

Prérequis :
    pip install requests python-dotenv openai
    OPENROUTER_API_KEY dans .env (déjà utilisé par tailor_cv.py/generate_letter.py)

Usage :
    python src/build_offres_spontanees.py --csv data/entreprises/entreprises_uniques.csv --limit 20
    python src/build_offres_spontanees.py --csv data/entreprises/entreprises_uniques.csv --ville-filtre carcassonne,toulouse,montpellier
"""

import os
import re
import csv
import json
import time
import argparse
import unicodedata
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".." / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DEFAULT_MODEL = "openai/gpt-4o-mini"

FIELDNAMES = [
    "id", "intitule", "entreprise", "lieu", "type_contrat", "nature_contrat",
    "duree_contrat", "date_creation", "salaire", "experience_exigee",
    "competences", "description", "url",
]

DELAI_ENTRE_APPELS_SEC = 1.0


def normalize_txt(s) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def slugify_id(nom: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_txt(nom)).strip("-")
    return f"SPONT-{slug[:40]}"


def fetch_website_text(url: str, max_chars: int = 1500) -> str:
    """Récupère un aperçu texte brut de la page d'accueil (best effort).
    Retourne une chaîne vide en cas d'échec (timeout, site down, etc.) plutôt
    que de faire planter le script."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text
        html = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        texte = re.sub(r"<[^>]+>", " ", html)
        texte = re.sub(r"\s+", " ", texte).strip()
        return texte[:max_chars]
    except Exception as e:
        print(f"    (site web inaccessible : {e})")
        return ""


def generate_offre_spontanee(client: OpenAI, model: str, entreprise: dict, extrait_site: str) -> dict:
    prompt = f"""Tu prépares les données d'une CANDIDATURE SPONTANÉE (pas une offre réelle) pour une
alternance en science des données / IA, à destination de l'entreprise suivante.

INFORMATIONS DISPONIBLES SUR L'ENTREPRISE (n'invente RIEN au-delà de ceci) :
- Nom : {entreprise.get('nom', '')}
- Adresse : {entreprise.get('adresse', '')}
- Ville : {entreprise.get('ville', '')}
- Service concerné historiquement : {entreprise.get('service', '') or "non précisé"}
- Site web : {entreprise.get('siteweb', '') or "non précisé"}

EXTRAIT DE LA PAGE D'ACCUEIL DU SITE WEB (peut être vide si le site n'a pas pu être lu) :
{extrait_site or "(aucun extrait disponible)"}

RÈGLE ABSOLUE : n'invente AUCUN fait précis (chiffre, technologie, projet, client) qui n'est
pas explicitement présent dans les informations ci-dessus ou l'extrait du site. Si tu ne sais
pas ce que fait vraiment l'entreprise, reste générique et dis-le implicitement (ex: "Structure
basée à {entreprise.get('ville', '')}, active dans le secteur suggéré par son nom/service"), sans
prétendre connaître des détails que tu n'as pas.

Réponds en JSON avec :
- "intitule" : un intitulé court de candidature spontanée, ex "Candidature spontanée - Alternance Data / Science des données"
- "description" : un paragraphe de 3-4 phrases MAXIMUM décrivant l'entreprise de façon honnête et mesurée à partir des seules informations fournies, sans superlatif ni invention.
- "competences" : laisse une chaîne vide "" (pas assez d'information pour deviner des compétences précises attendues).

Réponds uniquement en JSON : {{"intitule": "...", "description": "...", "competences": ""}}"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=500,
    )
    return json.loads(resp.choices[0].message.content)


def main():
    parser = argparse.ArgumentParser(description="Transforme une liste d'entreprises en CSV d'offres spontanées pour tailor_cv.py")
    parser.add_argument("--csv", required=True, help="CSV produit par normalize_entreprises.py")
    parser.add_argument("--limit", type=int, default=None, help="Nombre max d'entreprises à traiter (utile pour tester avant de tout lancer)")
    parser.add_argument("--ville-filtre", default=None,
                         help="Liste de villes séparées par des virgules (insensible à la casse) pour ne traiter qu'un sous-ensemble")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY doit être défini dans .env")

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

    csv_path = Path(args.csv)
    with open(csv_path, encoding="utf-8") as f:
        entreprises = list(csv.DictReader(f))

    villes_filtre = None
    if args.ville_filtre:
        villes_filtre = {normalize_txt(v.strip()) for v in args.ville_filtre.split(",") if v.strip()}
        entreprises = [e for e in entreprises if normalize_txt(e.get("ville", "")) in villes_filtre]
        print(f"Filtre ville appliqué : {len(entreprises)} entreprise(s) restante(s).")

    if args.limit:
        entreprises = entreprises[: args.limit]

    print(f"Traitement de {len(entreprises)} entreprise(s)...")

    offres = []
    today = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")

    for i, entreprise in enumerate(entreprises, start=1):
        nom = entreprise.get("nom", "").strip()
        if not nom:
            continue
        print(f"\n[{i}/{len(entreprises)}] {nom}")

        extrait_site = ""
        if entreprise.get("siteweb"):
            print(f"  Récupération du site web : {entreprise['siteweb']}")
            extrait_site = fetch_website_text(entreprise["siteweb"])

        try:
            resultat = generate_offre_spontanee(client, args.model, entreprise, extrait_site)
        except Exception as e:
            print(f"  ❌ Erreur LLM pour '{nom}' : {e}, entreprise ignorée.")
            continue

        lieu = ", ".join(filter(None, [entreprise.get("code_postal", ""), entreprise.get("ville", "")]))

        offres.append({
            "id": slugify_id(nom),
            "intitule": resultat.get("intitule", "Candidature spontanée - Alternance Data/IA"),
            "entreprise": nom,
            "lieu": lieu,
            "type_contrat": "Candidature spontanée",
            "nature_contrat": "",
            "duree_contrat": "",
            "date_creation": today,
            "salaire": "",
            "experience_exigee": "Débutant accepté",
            "competences": resultat.get("competences", ""),
            "description": resultat.get("description", ""),
            "url": entreprise.get("siteweb", ""),
        })

        if i < len(entreprises):
            time.sleep(DELAI_ENTRE_APPELS_SEC)

    output_path = Path(args.output) if args.output else BASE_DIR / "data" / "offres_spontanees" / f"offres_spontanees_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(offres)

    print(f"\n{len(offres)} offre(s) spontanée(s) générée(s).")
    print(f"Fichier enregistré : {output_path}")
    print("\nPour générer un CV/lettre pour une entreprise précise :")
    if offres:
        print(f'  python src/tailor_cv.py --csv "{output_path}" --offer-id {offres[0]["id"]}')
    print("\nATTENTION : relis chaque description générée avant de l'utiliser dans une vraie "
          "candidature - vérifie qu'aucun fait inventé ne s'est glissé malgré la consigne.")


if __name__ == "__main__":
    main()
