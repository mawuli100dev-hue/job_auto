"""
tailor_cv.py
1. Note les expériences via un LLM (temperature=0) + bonus mots-clés, épingle
   celles marquées "toujours_inclure", trie l'affichage final par date.
2. Adapte les COMPÉTENCES par catégorie via matching mots-clés (+ fallback LLM).
3. Génère un SOUS-TITRE DYNAMIQUE via le LLM (pas de concaténation mécanique) :
   le modèle reçoit l'intitulé brut de l'offre + la date de disponibilité
   détectée (ou par défaut), et rédige une phrase courte et naturelle en bon
   français, du type "Candidature pour l'alternance d'Ingénieur IA". Pour un
   intitulé long et technique ("Offre d'alternance - Ingénieur IA Optimisation
   des algorithmes d'IA appliqués à l'identification des polymères par imagerie
   hyperspectrale"), c'est au LLM de choisir intelligemment ce qu'il condense ou
   omet, plutôt qu'un script qui empile bêtement des bouts de phrase.
4. Génère le CV (PDF 1 page + HTML + Word).
5. Sauvegarde les données EXACTES du CV généré (cv_data.json) dans le dossier
   de candidature, pour que generate_letter.py puisse les relire directement
   au lieu de refaire une sélection indépendante (garantit la cohérence CV <-> lettre).

CORRECTIF (bug de matching par sous-chaîne, historique) :
Le matching de mots-clés se fait par MOT ENTIER (regex \\b...\\b) et non plus
par simple sous-chaîne. Audité : aucun tag de la banque ne génère plus de faux
positif, y compris les tags courts légitimes.

Usage :
    python tailor_cv.py --csv "data/offres_filtrees/2026-09-10/....csv" --offer-id 213QBYH
"""

import os
import csv
import json
import argparse
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from cv_builder import fit_on_one_page, build_docx

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DEFAULT_MODEL = "openai/gpt-4o-mini"

# Disponibilité par défaut si l'offre ne mentionne aucune date de démarrage.
DISPONIBILITE_DEFAUT = "Immédiatement"

MOIS_NORMALISES = [
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
]
MOIS_AFFICHAGE = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

KEYWORD_SYNONYMS = {
    "dashboard": ["dashboard", "tableau de bord", "tableaux de bord"],
    "streamlit": ["streamlit"],
    "power bi": ["power bi", "powerbi"],
    "sql": ["sql"],
    "etl": ["etl"],
    "nlp": ["nlp", "traitement du langage", "traitement de texte"],
    "machine learning": [
        "machine learning", "apprentissage automatique",
        "intelligence artificielle", "ia",
    ],
    "geospatial": ["geospatial", "cartographie", "sig", "qgis", "arcgis"],
    "automatisation": ["automatisation", "automatisee", "automatisees", "automatise"],
}


def normalize(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def slugify(text: str, max_len: int = 40) -> str:
    text = normalize(text)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text[:max_len]


def remove_forbidden_chars(text: str) -> str:
    """Retire les tirets cadratin/demi-cadratin (— et –) de tout texte destiné
    à apparaître dans un document final (CV inclus), remplacés par une virgule
    ou un tiret simple pour garder une ponctuation naturelle."""
    if not text:
        return text
    text = text.replace("—", ",").replace("–", "-")
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_offer(csv_path: Path, offer_id: str) -> dict:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("id") == offer_id:
                return row
    raise ValueError(f"Offre id={offer_id} introuvable dans {csv_path}")


def build_offer_summary(offer: dict, max_desc: int = 2500) -> str:
    return (
        f"Intitulé: {offer.get('intitule', '')}\n"
        f"Entreprise: {offer.get('entreprise', '')}\n"
        f"Niveau d'expérience demandé: {offer.get('experience_exigee', '')}\n"
        f"Compétences demandées: {offer.get('competences', '')}\n"
        f"Description: {offer.get('description', '')[:max_desc]}"
    )


def extract_start_date(offer_text: str) -> str | None:
    """Cherche une date de démarrage explicitement mentionnée dans l'offre
    (ex: 'à partir de septembre 2026', 'rentrée 2026'). Retourne None si
    aucune date claire n'est trouvée (on utilisera alors la valeur par défaut).
    Sert d'INDICE fourni au LLM pour rédiger le sous-titre, pas de construction
    mécanique finale."""
    texte = normalize(offer_text)
    mois_pattern = "|".join(MOIS_NORMALISES)

    m = re.search(
        rf"(?:a partir de|des|debut|demarrage)\s+(?:le\s+)?(?:\d{{1,2}}\s+)?({mois_pattern})\s+(\d{{4}})",
        texte,
    )
    if m:
        mois_idx = MOIS_NORMALISES.index(m.group(1))
        return f"{MOIS_AFFICHAGE[mois_idx]} {m.group(2)}"

    m2 = re.search(r"rentree\s+(\d{4})", texte)
    if m2:
        return f"septembre {m2.group(1)}"

    return None


def generate_sous_titre(client: OpenAI, model: str, offer: dict) -> str:
    """Demande au LLM de rédiger le sous-titre du CV (accroche sous le nom),
    en bon français naturel, à partir de l'intitulé brut de l'offre (souvent
    long, technique, mal formaté). Le LLM décide lui-même quoi condenser ou
    omettre, plutôt qu'une concaténation mécanique de morceaux de phrase.
    En cas d'échec de l'appel LLM, retombe sur une version simple de secours."""
    intitule_brut = offer.get("intitule", "") or "Data Analyst"
    date_dispo = extract_start_date(offer.get("description", "")) or DISPONIBILITE_DEFAUT

    prompt = f"""Tu rédiges le SOUS-TITRE d'un CV (une seule phrase courte, affichée juste sous le nom
du candidat), pour une candidature à une ALTERNANCE.

INTITULÉ BRUT DE L'OFFRE (peut être long, technique, mal formaté, avec des sigles) :
"{intitule_brut}"

DATE DE DISPONIBILITÉ DU CANDIDAT : {date_dispo}

CONSIGNES :
1. Rédige UNE SEULE phrase, en bon français naturel et fluide, PAS une concaténation mécanique
   de bouts de phrase. Tu dois activement CHOISIR ce que tu gardes ou condenses dans l'intitulé,
   pas tout recopier tel quel si c'est trop long ou trop technique pour une phrase d'accroche.
2. Commence par une formule du type "Candidature pour l'alternance de/d'..." ou "Candidature pour
   le poste de ... en alternance" - choisis celle qui sonne le mieux selon l'intitulé.
3. Si l'intitulé est long et détaillé (ex: contient un sous-titre très technique après un tiret
   ou un "-"), tu peux t'arrêter au titre de poste principal (ex: "Ingénieur IA") sans reprendre
   toute la description technique qui suit, SAUF si un mot-clé precis est vraiment central et se
   dit naturellement en une phrase courte.
4. N'ajoute la date de disponibilité à la fin QUE si la phrase reste fluide et pas trop longue une
   fois cette date ajoutée (ex: ", disponible à partir de {date_dispo}"). Si la phrase devient trop
   lourde ou redondante, tu peux omettre la date.
5. Vise une longueur totale raisonnable pour tenir sur une seule ligne de CV (environ 8 à 14 mots,
   un peu plus si nécessaire pour rester grammaticalement correct, mais jamais une phrase à rallonge).
6. INTERDICTION ABSOLUE d'utiliser "—" (tiret cadratin) ou "–" (tiret demi-cadratin). Utilise des
   virgules ou un tiret simple "-" si besoin.
7. Ne recopie jamais l'intitulé brut mot pour mot s'il est mal formaté (sigles, doubles espaces,
   mentions de type "H/F", "Offre d'alternance -" à retirer) : reformule proprement.

Réponds uniquement en JSON :
{{"sous_titre": "..."}}"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=150,
        )
        result = json.loads(resp.choices[0].message.content)
        sous_titre = result.get("sous_titre", "").strip()
        if sous_titre:
            return remove_forbidden_chars(sous_titre)
    except Exception as e:
        print(f"ATTENTION : échec de la génération du sous-titre via le LLM ({e}), utilisation d'un secours simple.")

    # Secours minimal si l'appel LLM échoue (rare) : reste sobre plutôt que de mal concaténer.
    titre_court = re.sub(r"\(H\s*/\s*F\)|\(F\s*/\s*H\)", "", intitule_brut, flags=re.IGNORECASE)
    titre_court = re.sub(r"\s+", " ", titre_court).strip(" -,")
    if len(titre_court) > 60:
        titre_court = titre_court[:60].rsplit(" ", 1)[0]
    return remove_forbidden_chars(f"Candidature pour l'alternance en {titre_court}")


def _mot_entier_present(mot: str, texte_normalise: str) -> bool:
    """Vrai si `mot` apparaît comme MOT ENTIER (pas une sous-chaîne d'un autre
    mot) dans `texte_normalise`."""
    return re.search(r'\b' + re.escape(mot) + r'\b', texte_normalise) is not None


def keyword_bonus(tags: list[str], offer_text_normalized: str) -> float:
    bonus = 0.0
    for tag in tags:
        tag_norm = normalize(tag)
        synonymes = KEYWORD_SYNONYMS.get(tag_norm, [tag_norm])
        if any(_mot_entier_present(normalize(syn), offer_text_normalized) for syn in synonymes):
            bonus += 2.0
    return min(bonus, 6.0)


def score_competences_pool(pool: dict, offer_text_normalized: str) -> tuple[dict, int]:
    scores_by_category = {}
    total_matches = 0
    for category, config in pool.items():
        scored = []
        for entry in config.get("swappable", []):
            score = keyword_bonus(entry.get("tags", []), offer_text_normalized)
            scored.append({"id": entry.get("id"), "item": entry["item"], "score": score})
            if score > 0:
                total_matches += 1
        scores_by_category[category] = scored
    return scores_by_category, total_matches


def build_competences_from_scores(pool: dict, scores_by_category: dict) -> dict:
    result = {}
    for category, config in pool.items():
        toujours = [e["item"] for e in config.get("toujours", [])]
        slots_total = config.get("slots_total", len(toujours))
        remaining_slots = max(0, slots_total - len(toujours))

        scored = scores_by_category.get(category, [])
        matched = sorted([s for s in scored if s["score"] > 0], key=lambda s: s["score"], reverse=True)
        unmatched = [s for s in scored if s["score"] == 0]
        final_items = [s["item"] for s in (matched + unmatched)][:remaining_slots]
        result[category] = toujours + final_items
    return result


def llm_rerank_competences(client: OpenAI, model: str, pool: dict, offer_summary: str) -> dict:
    categories_desc = ""
    for category, config in pool.items():
        entries = [e for e in config.get("swappable", []) if "id" in e]
        if not entries:
            continue
        items_desc = "\n".join(f"  id={e['id']} : {e['item']}" for e in entries)
        categories_desc += f"\nCatégorie \"{category}\":\n{items_desc}\n"

    prompt = f"""Offre visée :
{offer_summary}

Pour CHAQUE catégorie ci-dessous, classe les compétences par pertinence décroissante pour cette offre (même si le lien n'est pas évident, choisis un ordre plausible) :
{categories_desc}

Réponds uniquement en JSON de cette forme (toutes les catégories, tous les ids listés) :
{{"NomCategorie": ["id_le_plus_pertinent", "id_suivant", ...], ...}}"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=1000,
    )
    return json.loads(resp.choices[0].message.content)


def build_competences_from_llm_order(pool: dict, llm_order: dict) -> dict:
    result = {}
    for category, config in pool.items():
        toujours = [e["item"] for e in config.get("toujours", [])]
        slots_total = config.get("slots_total", len(toujours))
        remaining_slots = max(0, slots_total - len(toujours))

        id_to_item = {e["id"]: e["item"] for e in config.get("swappable", []) if "id" in e}
        ordered_ids = llm_order.get(category, list(id_to_item.keys()))
        ordered_items = [id_to_item[i] for i in ordered_ids if i in id_to_item]
        for i, item in id_to_item.items():
            if item not in ordered_items:
                ordered_items.append(item)
        result[category] = toujours + ordered_items[:remaining_slots]
    return result


def score_experiences(client: OpenAI, model: str, offer_summary: str, experiences: list[dict]) -> list[dict]:
    exp_summary = "\n".join(
        f"- id={e['id']} | titre={e['titre']} | tags={', '.join(e['tags'])} | "
        f"extrait={e['bullets'][0].replace('**', '')[:140] if e.get('bullets') else ''}"
        for e in experiences
    )
    prompt = f"""Tu aides un étudiant en 3e année de BUT Science des Données (niveau BAC+3, candidat à une ALTERNANCE, donc profil junior/débutant en poste) à choisir les meilleures expériences de son CV pour UNE offre précise.

OFFRE CIBLÉE :
{offer_summary}

BANQUE D'EXPÉRIENCES DISPONIBLES :
{exp_summary}

CRITÈRES DE SÉLECTION (dans cet ordre d'importance) :
1. Pertinence des compétences et outils : privilégie fortement les expériences qui utilisent des outils, méthodes ou domaines EXPLICITEMENT cités dans l'offre (y compris des domaines comme l'IA, le machine learning ou l'automatisation si l'offre les mentionne).
2. Calibrage de niveau : le poste est un poste JUNIOR/ALTERNANCE. Évite les expériences en décalage de niveau, tout en restant convaincant pour décrocher un entretien.
3. Diversité utile : préfère un ensemble complémentaire plutôt que plusieurs expériences démontrant exactement la même compétence.

Pour CHAQUE expérience, donne un score de 0 à 10 et une courte raison (1 phrase, en français).

Réponds uniquement en JSON, trié du score le plus haut au plus bas :
{{"selections": [{{"id": "id1", "score": 9, "raison": "..."}}, ...]}}
Inclus TOUS les ids de la banque dans la réponse."""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=1500,
    )
    return json.loads(resp.choices[0].message.content).get("selections", [])


def main():
    parser = argparse.ArgumentParser(description="Génère un CV adapté (PDF 1 page + HTML + Word)")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--offer-id", required=True)
    parser.add_argument("--experiences", default=str(BASE_DIR / "experiences.json"))
    parser.add_argument("--competences-pool", default=str(BASE_DIR / "competences_pool.json"))
    parser.add_argument("--top-n", type=int, default=4)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY doit être défini dans .env")

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = Path.cwd() / csv_path

    experiences = load_json(Path(args.experiences))
    pool = load_json(Path(args.competences_pool))
    offer = load_offer(csv_path, args.offer_id)
    exp_by_id = {e["id"]: e for e in experiences}

    offer_summary = build_offer_summary(offer)
    offer_text_normalized = normalize(
        f"{offer.get('intitule', '')} {offer.get('competences', '')} {offer.get('description', '')}"
    )

    print(f"Offre ciblée : {offer.get('intitule')} - {offer.get('entreprise')}")

    print("Rédaction du sous-titre du CV via le LLM...")
    sous_titre = generate_sous_titre(client, args.model, offer)
    print(f"Sous-titre du CV : {sous_titre}")

    print("Notation des expériences via le LLM (temperature=0)...")
    raw_selections = score_experiences(client, args.model, offer_summary, experiences)

    hybrid = []
    for s in raw_selections:
        exp = exp_by_id.get(s["id"])
        if not exp:
            continue
        bonus = keyword_bonus(exp.get("tags", []), offer_text_normalized)
        hybrid.append({"id": s["id"], "llm_score": s.get("score", 0), "bonus": bonus, "final_score": s.get("score", 0) + bonus})
    hybrid.sort(key=lambda s: s["final_score"], reverse=True)

    pinned_ids = [e["id"] for e in experiences if e.get("toujours_inclure")]
    non_pinned_ordered_ids = [s["id"] for s in hybrid if s["id"] not in pinned_ids]
    remaining_slots = max(0, args.top_n - len(pinned_ids))
    final_ids = pinned_ids + non_pinned_ordered_ids[:remaining_slots]
    selected = [exp_by_id[i] for i in final_ids if i in exp_by_id]

    if not selected:
        raise RuntimeError("Aucune expérience sélectionnée.")

    hybrid_by_id = {s["id"]: s for s in hybrid}
    print("\nExpériences retenues :")
    for e in selected:
        if e["id"] in pinned_ids:
            print(f"  - {e['titre']} [épinglée]")
        else:
            h = hybrid_by_id.get(e["id"], {})
            print(f"  - {e['titre']} [LLM={h.get('llm_score')} + bonus={h.get('bonus')} = {h.get('final_score')}]")

    selected.sort(key=lambda e: e.get("start_date", "0000-00"), reverse=True)

    print("\nAdaptation des compétences...")
    scores_by_category, total_matches = score_competences_pool(pool, offer_text_normalized)

    if total_matches > 0:
        print(f"  {total_matches} correspondance(s) trouvée(s) par mots-clés.")
        competences = build_competences_from_scores(pool, scores_by_category)
    else:
        print("  Aucune correspondance par mots-clés — appel du LLM en secours...")
        llm_order = llm_rerank_competences(client, args.model, pool, offer_summary)
        competences = build_competences_from_llm_order(pool, llm_order)

    for cat, items in competences.items():
        print(f"  {cat} : {', '.join(items)}")

    today = datetime.now().strftime("%Y-%m-%d")
    entreprise_slug = slugify(offer.get("entreprise", "entreprise"))
    dossier = BASE_DIR / "data" / "candidatures" / today / f"{entreprise_slug}_{args.offer_id}"
    dossier.mkdir(parents=True, exist_ok=True)

    pdf_path = dossier / "CV_Henoc_AMAVIGAN.pdf"
    html_path = dossier / "CV_Henoc_AMAVIGAN.html"
    docx_path = dossier / "CV_Henoc_AMAVIGAN.docx"

    scale_used = fit_on_one_page(selected, pdf_path, html_path, competences=competences, sous_titre=sous_titre)
    build_docx(selected, docx_path, competences=competences, sous_titre=sous_titre)

    resume_path = dossier / "offre.txt"
    with open(resume_path, "w", encoding="utf-8") as f:
        f.write(f"Intitulé : {offer.get('intitule')}\n")
        f.write(f"Entreprise : {offer.get('entreprise')}\n")
        f.write(f"Lieu : {offer.get('lieu')}\n")
        f.write(f"URL : {offer.get('url')}\n\n")
        f.write("--- Description complète de l'offre ---\n")
        f.write(offer.get("description", ""))

    # --- Sauvegarde des données EXACTES du CV généré, pour generate_letter.py ---
    cv_data_path = dossier / "cv_data.json"
    with open(cv_data_path, "w", encoding="utf-8") as f:
        json.dump({
            "offer_id": args.offer_id,
            "offer": {
                "intitule": offer.get("intitule"),
                "entreprise": offer.get("entreprise"),
                "lieu": offer.get("lieu"),
                "url": offer.get("url"),
            },
            "sous_titre_cv": sous_titre,
            "experiences_sur_cv": selected,
            "competences_sur_cv": competences,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nPDF généré sur 1 page (échelle {scale_used:.2f}) : {pdf_path}")
    print(f"Word (secours) : {docx_path}")
    print(f"Données du CV sauvegardées pour la lettre : {cv_data_path}")
    print("\nLe CV est prêt à être envoyé.")


if __name__ == "__main__":
    main()