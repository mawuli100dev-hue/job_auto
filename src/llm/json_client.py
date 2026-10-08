# src/llm/json_client.py

import json
import re
from typing import Any

from openai import OpenAI


class JsonLlmClient:
    def __init__(
        self,
        api_key: str,
        model: str,
    ) -> None:
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY doit être "
                "défini dans le fichier .env."
            )

        self.model = model

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

    def _system_content(
        self,
        system: str,
    ) -> str | list[dict[str, Any]]:
        """
        Pour Claude, le message système (fixe d'une candidature à
        l'autre) est mis en cache via OpenRouter : les appels
        suivants le paient environ 10 fois moins cher pendant
        quelques minutes. OpenAI met en cache automatiquement.
        """

        if not self.model.startswith("anthropic/"):
            return system

        return [
            {
                "type": "text",
                "text": system,
                "cache_control": {
                    "type": "ephemeral",
                },
            }
        ]

    def request(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        system: str | None = None,
    ) -> dict[str, Any]:
        messages = []

        if system:
            messages.append(
                {
                    "role": "system",
                    "content": self._system_content(system),
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={
                "type": "json_object",
            },
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = (
            response.choices[0].message.content
            or ""
        ).strip()

        # Sécurité supplémentaire si un fournisseur ajoute
        # malgré tout des balises Markdown.
        content = re.sub(
            r"^```(?:json)?\s*",
            "",
            content,
            flags=re.IGNORECASE,
        )

        content = re.sub(
            r"\s*```$",
            "",
            content,
        )

        try:
            result = json.loads(content)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "Le modèle n'a pas retourné un JSON valide.\n"
                f"Réponse reçue : {content[:1000]}"
            ) from error

        if not isinstance(result, dict):
            raise RuntimeError(
                "La réponse JSON du modèle doit être "
                "un objet."
            )

        return result