# src/cv/experience_selector.py

import re
from typing import Any

from cv.keyword_matcher import keyword_bonus
from domain.models import ApplicationTarget
from llm.json_client import JsonLlmClient


# keyword_bonus renvoie au plus 6 : avec ce poids, le bonus
# vaut au plus 3 points, face à un score LLM sur 10.
KEYWORD_BONUS_WEIGHT = 0.5


class ExperienceSelector:
    def __init__(
        self,
        llm_client: JsonLlmClient,
    ) -> None:
        self.llm_client = llm_client

    def select(
        self,
        target: ApplicationTarget,
        experiences: list[dict[str, Any]],
        top_n: int,
    ) -> tuple[list[dict[str, Any]], list[dict]]:
        if top_n <= 0:
            raise ValueError(
                "top_n doit être supérieur à zéro."
            )

        if not experiences:
            raise ValueError(
                "La banque d'expériences est vide."
            )

        llm_scores = self._score_with_llm(
            target=target,
            experiences=experiences,
        )

        experiences_by_id = {
            experience["id"]: experience
            for experience in experiences
            if experience.get("id")
        }

        target_text = target.searchable_text()

        diagnostics = []

        for experience in experiences:
            experience_id = experience.get("id")

            if not experience_id:
                continue

            llm_entry = llm_scores.get(
                experience_id,
                {},
            )

            llm_score = self._safe_score(
                llm_entry.get("score", 0)
            )

            # Le bonus mots-clés départage les ex aequo sans écraser
            # le jugement du LLM : les tags génériques (python, r...)
            # correspondent à presque toutes les offres data.
            bonus = KEYWORD_BONUS_WEIGHT * keyword_bonus(
                tags=experience.get("tags", []),
                target_text=target_text,
            )

            diagnostics.append(
                {
                    "id": experience_id,
                    "llm_score": llm_score,
                    "bonus": bonus,
                    "final_score": llm_score + bonus,
                    "raison": llm_entry.get(
                        "raison",
                        "",
                    ),
                }
            )

        diagnostics.sort(
            key=lambda item: item["final_score"],
            reverse=True,
        )

        pinned_ids = [
            experience["id"]
            for experience in experiences
            if (
                experience.get("id")
                and experience.get("toujours_inclure")
            )
        ]

        ordered_non_pinned_ids = [
            item["id"]
            for item in diagnostics
            if item["id"] not in pinned_ids
        ]

        remaining_slots = max(
            0,
            top_n - len(pinned_ids),
        )

        selected_ids = (
            pinned_ids
            + ordered_non_pinned_ids[:remaining_slots]
        )

        selected_experiences = [
            experiences_by_id[experience_id]
            for experience_id in selected_ids
            if experience_id in experiences_by_id
        ]

        if not selected_experiences:
            raise RuntimeError(
                "Aucune expérience n'a été sélectionnée."
            )

        selected_experiences.sort(
            key=lambda experience: experience.get(
                "start_date",
                "0000-00",
            ),
            reverse=True,
        )

        return (
            selected_experiences,
            diagnostics,
        )

    def _score_with_llm(
        self,
        target: ApplicationTarget,
        experiences: list[dict],
    ) -> dict[str, dict]:
        experience_blocks = [
            self._describe_experience(experience)
            for experience in experiences
            if experience.get("id")
        ]

        experience_summary = "\n\n".join(
            experience_blocks
        )

        contract_label = {
            "alternance": "une alternance",
            "stage": "un stage",
        }[target.contract_type]

        prompt = f"""
Un étudiant en troisième année de BUT Science des Données (BAC+3) postule à {contract_label}. Son CV ne peut afficher que quelques expériences : tu dois évaluer chacune d'elles par rapport à l'offre ci-dessous.

<offre>
{target.build_summary()}
</offre>

<experiences>
{experience_summary}
</experiences>

MÉTHODE
1. Identifie d'abord les 3 à 5 besoins concrets de l'offre : missions principales, outils exigés, domaine métier (finance, santé, environnement, industrie...).
2. Pour chaque expérience, regarde ce qui a réellement été fait (missions et résultats), pas seulement le titre ou les mots-clés.
3. Attribue un score selon cette grille :
   - 9-10 : mêmes missions ET mêmes outils ou même domaine métier que l'offre ; un recruteur y verrait une preuve directe.
   - 6-8 : outils ou méthodes clairement transférables vers une mission centrale de l'offre.
   - 3-5 : lien indirect (compétence générale de données, rigueur, programmation) sans rapport avec les missions principales.
   - 0-2 : hors sujet pour cette offre.

RÈGLES
- Un titre impressionnant ou une technologie à la mode ne justifie pas un bon score si les missions de l'offre sont différentes (exemple : un projet de deep learning pour une offre de reporting Power BI).
- Un projet académique ou personnel vaut autant qu'une expérience en entreprise s'il démontre la même compétence.
- Base-toi uniquement sur les informations fournies.
- Évalue TOUTES les expériences, avec leur identifiant exact.

Réponds uniquement en JSON, en écrivant la raison AVANT le score :

{{
  "besoins_offre": ["besoin 1", "besoin 2", "besoin 3"],
  "selections": [
    {{
      "id": "identifiant_exact",
      "raison": "Lien concret (ou absence de lien) avec un besoin de l'offre, en une phrase",
      "score": 7
    }}
  ]
}}
""".strip()

        try:
            response = self.llm_client.request(
                prompt=prompt,
                temperature=0,
                max_tokens=2500,
                system=(
                    "Tu es un recruteur expérimenté dans les "
                    "métiers de la donnée. Tu évalues des "
                    "candidatures avec exigence et sans complaisance."
                ),
            )

            needs = response.get(
                "besoins_offre",
                [],
            )

            if isinstance(needs, list) and needs:
                print(
                    "  Besoins identifiés : "
                    + " ; ".join(
                        str(need) for need in needs
                    )
                )

            selections = response.get(
                "selections",
                [],
            )

            if not isinstance(selections, list):
                return {}

            result = {}

            for selection in selections:
                if not isinstance(selection, dict):
                    continue

                experience_id = str(
                    selection.get("id", "")
                ).strip()

                if experience_id:
                    result[experience_id] = selection

            return result

        except Exception as error:
            print(
                "ATTENTION : notation LLM des expériences "
                f"impossible ({error}). "
                "Sélection par mots-clés uniquement."
            )

            return {}

    @staticmethod
    def _describe_experience(
        experience: dict[str, Any],
    ) -> str:
        """
        Décrit une expérience en entier (toutes les puces), sans
        le Markdown ni les URL qui n'aident pas le modèle à juger.
        """

        lines = [
            f"[id={experience.get('id', '')}] "
            f"{experience.get('titre', '')}",
        ]

        context = " | ".join(
            str(value)
            for value in (
                experience.get("sous_titre"),
                experience.get("structure"),
                experience.get("periode"),
            )
            if value
        )

        if context:
            lines.append(f"Contexte : {context}")

        for bullet in experience.get("bullets", []):
            text = str(bullet).replace("**", "")
            text = re.sub(r"\s*:?\s*https?://\S+", "", text)
            lines.append(f"- {text.strip()}")

        return "\n".join(lines)

    @staticmethod
    def _safe_score(value: object) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0

        return max(
            0.0,
            min(score, 10.0),
        )