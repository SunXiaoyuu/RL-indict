from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 0.5


class DeepSeekClientError(RuntimeError):
    pass


def get_deepseek_api_key(api_key: str | None = None) -> str | None:
    return api_key or os.getenv("DEEPSEEK_API_KEY")


class DeepSeekClient:
    """DeepSeek Chat Completions client.

    DeepSeek exposes an OpenAI-compatible chat endpoint at
    https://api.deepseek.com/chat/completions. Use DEEPSEEK_API_BASE to point at
    compatible gateways, or DEEPSEEK_CHAT_URL for a full endpoint URL.
    """

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        chat_url: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        self.model_name = model_name or os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL
        self.api_key = get_deepseek_api_key(api_key)
        self.base_url = (base_url or os.getenv("DEEPSEEK_API_BASE") or DEFAULT_DEEPSEEK_API_BASE).rstrip("/")
        self.chat_url = (chat_url or os.getenv("DEEPSEEK_CHAT_URL") or "").rstrip("/")
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def _ensure_ready(self) -> None:
        if not self.api_key:
            raise DeepSeekClientError("Missing DeepSeek API key. Set DEEPSEEK_API_KEY.")

    def query(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        return self.query_messages(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
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
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if stop:
            payload["stop"] = stop
        payload.update(kwargs)

        response = self._post_json(self._chat_path_or_url(), payload)
        return self._extract_chat_text(response)

    def _chat_path_or_url(self) -> str:
        if self.chat_url:
            return self.chat_url
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return "/chat/completions"

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

        raise DeepSeekClientError(f"Unable to query DeepSeek model {self.model_name}: {last_error}")

    def _extract_chat_text(self, response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            raise DeepSeekClientError("DeepSeek response did not contain choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        raise DeepSeekClientError("DeepSeek response did not contain text content.")

    def query_with_retries(self, query: str, max_tokens: int = 256, max_retries: int | None = None) -> str:
        previous_retries = self.max_retries
        if max_retries is not None:
            self.max_retries = max_retries
        try:
            return self.query(query, max_tokens=max_tokens)
        finally:
            self.max_retries = previous_retries
