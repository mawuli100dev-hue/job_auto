# src/cv/skill_selector.py

"""
Sélection des compétences du CV, sur le modèle du CV manuel.

Le fichier competences_pool.json (format v3) contient une liste de
sections :

- sections « domaine » (Télédétection & SIG, Data Science & IA, ...) :
  une seule est retenue, celle qui correspond le mieux à l'offre,
  et elle est affichée EN PREMIER ;
- sections « fixe » (Traitement de données, Développement, Atouts,
  Bases de données, Langues, Loisirs) : toujours affichées, dans
  l'ordre du fichier.

Le résultat est un dictionnaire ordonné :

    {"Titre de section": ["puce 1", "puce 2", ...], ...}

Chaque puce est déjà mise en forme (éléments regroupés avec « | »),
donc les renderers HTML et Word n'ont plus qu'à l'afficher.
"""

from cv.keyword_matcher import keyword_bonus
from domain.models import ApplicationTarget
from llm.json_client import JsonLlmClient


class SkillSelector:
    def __init__(
        self,
        llm_client: JsonLlmClient | None,
        max_domain_sections: int = 1,
    ) -> None:
        self.llm_client = llm_client
        self.max_domain_sections = max_domain_sections

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def select(
        self,
        target: ApplicationTarget,
        pool: dict,
    ) -> dict[str, list[str]]:
        sections = pool.get("sections")

        if not isinstance(sections, list):
            raise ValueError(
                "competences_pool.json doit contenir une clé "
                "'sections' (format v3)."
            )

        target_text = target.searchable_text()

        domain_sections = [
            section
            for section in sections
            if section.get("type") == "domaine"
        ]

        fixed_sections = [
            section
            for section in sections
            if section.get("type", "fixe") == "fixe"
        ]

        result: dict[str, list[str]] = {}

        llm_choice = self._choose_domain_and_items_with_llm(
            target=target,
            domain_sections=domain_sections,
        )

        if llm_choice is not None:
            section, items = llm_choice

            print(
                f"  Section choisie par le LLM : "
                f"« {section['titre']} »"
            )

            result[section["titre"]] = self._format_bullets(
                section=section,
                items=items,
            )
        else:
            for section in self._choose_domain_sections(
                target=target,
                domain_sections=domain_sections,
                target_text=target_text,
            ):
                items = self._pick_items(
                    section=section,
                    target_text=target_text,
                    fill_without_match=True,
                    min_items=2,
                )

                result[section["titre"]] = self._format_bullets(
                    section=section,
                    items=items,
                )

        for section in fixed_sections:
            items = self._pick_items(
                section=section,
                target_text=target_text,
                fill_without_match=section.get(
                    "remplir_sans_correspondance",
                    True,
                ),
            )

            bullets = self._format_bullets(
                section=section,
                items=items,
            )

            if bullets:
                result[section["titre"]] = bullets

        return result

    # ------------------------------------------------------------------
    # Choix de la section spécialisée et de ses éléments par le LLM
    # ------------------------------------------------------------------

    def _choose_domain_and_items_with_llm(
        self,
        target: ApplicationTarget,
        domain_sections: list[dict],
    ) -> tuple[dict, list[dict]] | None:
        """
        Le LLM choisit UNE section spécialisée et, dans celle-ci,
        les éléments qui répondent le plus précisément à l'offre.
        Renvoie None en cas d'échec : la sélection par mots-clés
        prend alors le relais.
        """

        if self.llm_client is None or not domain_sections:
            return None

        catalog_lines = []

        for section in domain_sections:
            catalog_lines.append(
                f"SECTION id={section['id']} : {section['titre']}"
            )

            for entry in section.get("swappable", []):
                catalog_lines.append(
                    f"  - item id={entry['id']} : {entry['item']}"
                )

        catalog = "\n".join(catalog_lines)

        slots = max(
            section.get("slots_total", 3)
            for section in domain_sections
        )

        prompt = f"""
<offre>
{target.build_summary()}
</offre>

<catalogue>
{catalog}
</catalogue>

Le CV d'un étudiant en science des données commence par une section de compétences spécialisée, juste sous son nom. Un recruteur doit y retrouver en quelques secondes ce que l'offre demande.

1. Repère dans l'offre les missions principales et les outils explicitement exigés.
2. Choisis LA section du catalogue qui y correspond le mieux, en te fondant sur les missions réelles du poste plutôt que sur son intitulé (un « Data Engineer » qui fait surtout de l'analyse et du reporting relève de la BI ou de la statistique).
3. Dans cette section uniquement, choisis exactement {slots} éléments, du plus pertinent au moins pertinent : en premier ceux qui citent un outil exigé par l'offre, puis ceux qui correspondent à une mission de l'offre.

Réponds uniquement en JSON :
{{"raison": "une phrase", "section_id": "identifiant", "item_ids": ["id1", "id2", "id3"]}}
""".strip()

        try:
            response = self.llm_client.request(
                prompt=prompt,
                temperature=0,
                max_tokens=300,
            )
        except Exception as error:
            print(
                "ATTENTION : choix LLM des compétences "
                f"impossible ({error}). Sélection par mots-clés."
            )
            return None

        section_id = str(
            response.get("section_id", "")
        ).strip()

        section = next(
            (
                candidate
                for candidate in domain_sections
                if candidate["id"] == section_id
            ),
            None,
        )

        if section is None:
            return None

        entries_by_id = {
            entry["id"]: entry
            for entry in section.get("swappable", [])
        }

        item_ids = response.get("item_ids", [])

        if not isinstance(item_ids, list):
            return None

        items = []

        for item_id in item_ids:
            entry = entries_by_id.get(str(item_id).strip())

            if entry is not None and entry not in items:
                items.append(entry)

        items = items[: section.get("slots_total", slots)]

        if len(items) < 2:
            return None

        if response.get("raison"):
            print(f"  Raison : {response['raison']}")

        return section, items

    # ------------------------------------------------------------------
    # Choix de la section spécialisée (secours par mots-clés)
    # ------------------------------------------------------------------

    def _section_score(
        self,
        section: dict,
        target_text: str,
    ) -> float:
        return sum(
            keyword_bonus(
                tags=entry.get("tags", []),
                target_text=target_text,
            )
            for entry in section.get("swappable", [])
        )

    def _choose_domain_sections(
        self,
        target: ApplicationTarget,
        domain_sections: list[dict],
        target_text: str,
    ) -> list[dict]:
        if not domain_sections or self.max_domain_sections <= 0:
            return []

        scored = sorted(
            (
                (
                    self._section_score(section, target_text),
                    index,
                    section,
                )
                for index, section in enumerate(domain_sections)
            ),
            key=lambda entry: (-entry[0], entry[1]),
        )

        for score, _, section in scored:
            print(
                f"  Section « {section['titre']} » : "
                f"score {score:g} "
                f"(seuil {section.get('seuil_affichage', 4)})"
            )

        chosen = [
            section
            for score, _, section in scored
            if score >= section.get("seuil_affichage", 4)
        ][: self.max_domain_sections]

        if chosen:
            return chosen

        print(
            "  Aucune section spécialisée n'atteint son seuil : "
            "choix par le LLM."
        )

        llm_choice = self._choose_domain_with_llm(
            target=target,
            domain_sections=domain_sections,
        )

        if llm_choice is not None:
            return [llm_choice]

        default = next(
            (
                section
                for section in domain_sections
                if section.get("defaut")
            ),
            domain_sections[0],
        )

        return [default]

    def _choose_domain_with_llm(
        self,
        target: ApplicationTarget,
        domain_sections: list[dict],
    ) -> dict | None:
        if self.llm_client is None:
            return None

        options = "\n".join(
            f"- id={section['id']} : {section['titre']} "
            f"({'; '.join(e['item'] for e in section.get('swappable', []))})"
            for section in domain_sections
        )

        prompt = f"""
OFFRE CIBLÉE :
{target.build_summary()}

Le CV commence par UNE section de compétences spécialisée.
Choisis celle qui est la plus pertinente pour cette offre :

{options}

Réponds uniquement en JSON : {{"id": "identifiant_choisi"}}
""".strip()

        try:
            response = self.llm_client.request(
                prompt=prompt,
                temperature=0,
                max_tokens=60,
            )
        except Exception as error:
            print(
                "ATTENTION : choix LLM de la section spécialisée "
                f"impossible ({error})."
            )
            return None

        chosen_id = str(response.get("id", "")).strip()

        return next(
            (
                section
                for section in domain_sections
                if section["id"] == chosen_id
            ),
            None,
        )

    # ------------------------------------------------------------------
    # Choix des éléments d'une section
    # ------------------------------------------------------------------

    def _pick_items(
        self,
        section: dict,
        target_text: str,
        fill_without_match: bool,
        min_items: int = 0,
    ) -> list[dict]:
        always = [
            entry
            for entry in section.get("toujours", [])
            if entry.get("item")
        ]

        slots_total = section.get(
            "slots_total",
            len(always),
        )

        remaining = max(0, slots_total - len(always))

        scored = []

        for index, entry in enumerate(section.get("swappable", [])):
            if not entry.get("item"):
                continue

            score = keyword_bonus(
                tags=entry.get("tags", []),
                target_text=target_text,
            )

            scored.append((score, index, entry))

        matched = [
            entry
            for score, _, entry in sorted(
                scored,
                key=lambda value: (-value[0], value[1]),
            )
            if score > 0
        ]

        unmatched = [
            entry
            for score, _, entry in scored
            if score == 0
        ]

        chosen = matched[:remaining]

        needed = max(
            remaining - len(chosen) if fill_without_match else 0,
            min_items - len(always) - len(chosen),
        )

        if needed > 0:
            chosen += unmatched[:needed]

        # Les éléments gardent l'ordre du fichier pour un rendu stable.
        file_order = {
            id(entry): index
            for index, entry in enumerate(
                section.get("swappable", [])
            )
        }

        chosen.sort(key=lambda entry: file_order[id(entry)])

        return always + chosen

    # ------------------------------------------------------------------
    # Mise en forme des puces
    # ------------------------------------------------------------------

    @staticmethod
    def _format_bullets(
        section: dict,
        items: list[dict],
    ) -> list[str]:
        if section.get("affichage", "puces") == "puces":
            return [entry["item"] for entry in items]

        separator = section.get("separateur", " | ")
        max_per_bullet = max(1, section.get("max_par_puce", 99))

        bullets: list[str] = []
        current: list[str] = []

        def flush() -> None:
            if current:
                bullets.append(separator.join(current))
                current.clear()

        for entry in items:
            if entry.get("puce_seule"):
                flush()
                bullets.append(entry["item"])
                continue

            current.append(entry["item"])

            if len(current) >= max_per_bullet:
                flush()

        flush()

        return bullets
