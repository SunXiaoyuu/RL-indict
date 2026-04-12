from __future__ import annotations

import os
import time
from typing import Any

try:
    import dashscope
    from dashscope import Generation
except Exception:
    dashscope = None
    Generation = None


DEFAULT_QWEN_MODEL = "qwen2.5-14b-instruct"
DEFAULT_QWEN_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 0.5


class QwenClientError(RuntimeError):
    pass


def get_qwen_api_key(api_key: str | None = None) -> str | None:
    return api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")


def mask_secret(value: str | None, visible_prefix: int = 6, visible_suffix: int = 4) -> str:
    if not value:
        return "<missing>"
    if len(value) <= visible_prefix + visible_suffix:
        return "*" * len(value)
    return f"{value[:visible_prefix]}...{value[-visible_suffix:]}"


class QwenClient:
    """Small DashScope/Qwen client used by generation and tool calls."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        self.model_name = model_name or os.getenv("INDICT_QWEN_MODEL") or DEFAULT_QWEN_MODEL
        self.api_key = get_qwen_api_key(api_key)
        self.base_url = base_url or os.getenv("QWEN_API_BASE") or DEFAULT_QWEN_API_BASE
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

        if dashscope is not None and self.api_key:
            dashscope.api_key = self.api_key

    def _ensure_ready(self) -> None:
        if Generation is None:
            raise QwenClientError("DashScope Generation API is unavailable. Install `dashscope` first.")
        if not self.api_key:
            raise QwenClientError("Missing Qwen API key. Set DASHSCOPE_API_KEY or QWEN_API_KEY.")
        dashscope.api_key = self.api_key

    def query(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        del stop
        return self.query_messages(
            [{"role": "user", "content": prompt}],
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
        del stop
        return self.query_messages(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def query_messages(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> str:
        self._ensure_ready()

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "result_format": "message",
        }
        if temperature is not None:
            payload["temperature"] = temperature
        payload.update(kwargs)

        last_error = "unknown error"
        for attempt in range(self.max_retries):
            try:
                response = Generation.call(**payload)
                if response.status_code == 200:
                    return response.output.choices[0].message.content
                last_error = str(getattr(response, "message", response))
            except Exception as exc:
                last_error = str(exc)

            if attempt < self.max_retries - 1:
                time.sleep(self.backoff_seconds * (2**attempt))

        raise QwenClientError(f"Unable to query Qwen model {self.model_name}: {last_error}")

    def query_with_retries(self, query: str, max_tokens: int = 256, max_retries: int | None = None) -> str:
        previous_retries = self.max_retries
        if max_retries is not None:
            self.max_retries = max_retries
        try:
            return self.query(query, max_tokens=max_tokens)
        finally:
            self.max_retries = previous_retries
