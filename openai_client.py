from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_OPENAI_API_BASE = "https://api.openai.com/v1"
DEFAULT_OPENAI_RESPONSES_URL = "https://gmn.chuangzuoli.com/v1/responses"
DEFAULT_OPENAI_API_MODE = "responses"
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 0.5


class OpenAIClientError(RuntimeError):
    pass


def get_openai_api_key(api_key: str | None = None) -> str | None:
    return api_key or os.getenv("OPENAI_API_KEY")


class OpenAIClient:
    """Minimal OpenAI text-generation client.

    The default path uses the Responses API, which is the recommended OpenAI
    text-generation API for GPT-5 class models. Set OPENAI_API_MODE=chat to use
    Chat Completions for OpenAI-compatible providers that do not expose
    /v1/responses.
    """

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        api_mode: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        self.model_name = model_name or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        self.api_key = get_openai_api_key(api_key)
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or DEFAULT_OPENAI_API_BASE).rstrip("/")
        self.responses_url = (os.getenv("OPENAI_RESPONSES_URL") or "").rstrip("/")
        self.api_mode = (api_mode or os.getenv("OPENAI_API_MODE") or DEFAULT_OPENAI_API_MODE).lower()
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def _ensure_ready(self) -> None:
        if not self.api_key:
            raise OpenAIClientError("Missing OpenAI API key. Set OPENAI_API_KEY.")
        if self.api_mode not in {"responses", "chat"}:
            raise OpenAIClientError("OPENAI_API_MODE must be either 'responses' or 'chat'.")

    def query(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        if self.api_mode == "chat":
            return self.query_messages(
                [{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
                **kwargs,
            )

        del stop
        return self.query_responses(
            [{"role": "user", "text": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def query_with_system_prompt(
        self,
        system_prompt: str,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        if self.api_mode == "chat":
            return self.query_messages(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
                **kwargs,
            )

        del stop
        return self.query_responses(
            [
                {"role": "developer", "text": system_prompt},
                {"role": "user", "text": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def query_responses(
        self,
        input_messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> str:
        self._ensure_ready()
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": self._format_responses_input(input_messages),
            "max_output_tokens": max_tokens,
        }
        reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT")
        if reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}
        text_verbosity = os.getenv("OPENAI_TEXT_VERBOSITY")
        if text_verbosity:
            payload["text"] = {"verbosity": text_verbosity}
        if temperature is not None:
            payload["temperature"] = temperature
        payload.update(kwargs)

        response = self._post_json(self._responses_path_or_url(), payload)
        return self._extract_responses_text(response)

    def _format_responses_input(self, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        formatted = []
        for message in messages:
            role = message.get("role", "user")
            text = message.get("text")
            if text is None:
                text = message.get("content", "")
            formatted.append(
                {
                    "type": "message",
                    "role": role,
                    "content": [
                        {
                            "type": "input_text",
                            "text": str(text),
                        }
                    ],
                }
            )
        return formatted

    def _responses_path_or_url(self) -> str:
        if self.responses_url:
            return self.responses_url
        if self.base_url.endswith("/responses"):
            return self.base_url
        return "/responses"

    def query_messages(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        self._ensure_ready()
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if stop:
            payload["stop"] = stop
        payload.update(kwargs)

        response = self._post_json("/chat/completions", payload)
        return self._extract_chat_text(response)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path.startswith(("http://", "https://")):
            url = path
        else:
            url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = "unknown error"
        for attempt in range(self.max_retries):
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {exc.code}: {error_body}"
            except Exception as exc:
                last_error = str(exc)

            if attempt < self.max_retries - 1:
                time.sleep(self.backoff_seconds * (2**attempt))

        raise OpenAIClientError(f"Unable to query OpenAI model {self.model_name}: {last_error}")

    def _extract_responses_text(self, response: dict[str, Any]) -> str:
        output_text = response.get("output_text")
        if isinstance(output_text, str) and output_text:
            return output_text

        chunks: list[str] = []
        for item in response.get("output", []) or []:
            for content in item.get("content", []) or []:
                if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                    chunks.append(content["text"])
        if chunks:
            return "\n".join(chunks)

        raise OpenAIClientError("OpenAI response did not contain text output.")

    def _extract_chat_text(self, response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            raise OpenAIClientError("OpenAI chat response did not contain choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks = [part.get("text", "") for part in content if isinstance(part, dict)]
            rendered = "\n".join(chunk for chunk in chunks if chunk)
            if rendered:
                return rendered
        raise OpenAIClientError("OpenAI chat response did not contain text content.")

    def query_with_retries(self, query: str, max_tokens: int = 256, max_retries: int | None = None) -> str:
        previous_retries = self.max_retries
        if max_retries is not None:
            self.max_retries = max_retries
        try:
            return self.query(query, max_tokens=max_tokens)
        finally:
            self.max_retries = previous_retries
