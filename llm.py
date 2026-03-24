from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Callable

try:
    import dashscope
    from dashscope import Generation
except Exception:
    dashscope = None
    Generation = None


NUM_LLM_RETRIES = 10
LOG: logging.Logger = logging.getLogger(__name__)


class LLM(ABC):
    def __init__(self, model: str, api_key: str | None) -> None:
        self.model = model
        self.api_key = api_key

    @abstractmethod
    def query(self, prompt: str, stop_seqs=None, max_tokens: int = 1024, num_outputs: int = 1) -> str:
        raise NotImplementedError

    def query_with_system_prompt(
        self,
        system_prompt: str,
        prompt: str,
        stop_seqs=None,
        max_tokens: int = 1024,
        num_outputs: int = 1,
    ) -> str:
        return self.query(system_prompt + "\n" + prompt, stop_seqs=stop_seqs, max_tokens=max_tokens, num_outputs=num_outputs)

    def _query_with_retries(
        self,
        func: Callable[..., str],
        *args,
        retries: int = NUM_LLM_RETRIES,
        backoff_factor: float = 0.5,
        **kwargs,
    ) -> str:
        last_exception = None
        for retry in range(retries):
            try:
                return func(*args, **kwargs)
            except Exception as exception:
                last_exception = exception
                sleep_time = backoff_factor * (2**retry)
                time.sleep(sleep_time)
                LOG.debug(
                    "LLM query failed with error: %s. Sleeping for %s seconds...",
                    exception,
                    sleep_time,
                )
        raise RuntimeError(f"Unable to query LLM after {retries} retries: {last_exception}")

    def query_with_retries(self, prompt: str, stop_seqs=None, max_tokens: int = 1024, num_outputs: int = 1) -> str:
        return self._query_with_retries(
            self.query,
            prompt,
            stop_seqs=stop_seqs,
            max_tokens=max_tokens,
            num_outputs=num_outputs,
        )

    def query_with_system_prompt_with_retries(
        self,
        system_prompt: str,
        prompt: str,
        stop_seqs=None,
        max_tokens: int = 1024,
        num_outputs: int = 1,
    ) -> str:
        return self._query_with_retries(
            self.query_with_system_prompt,
            system_prompt,
            prompt,
            stop_seqs=stop_seqs,
            max_tokens=max_tokens,
            num_outputs=num_outputs,
        )


class QWEN(LLM):
    def __init__(self, model_name: str = "qwen2.5-14b-instruct", api_key: str | None = None, base_url=None) -> None:
        del base_url
        api_key = api_key or "sk-e0684cacf12246528358ae32ee4fc135"
        super().__init__(model_name, api_key)
        if dashscope is not None:
            dashscope.api_key = self.api_key
        self.name = model_name

    def _ensure_generation(self) -> None:
        if Generation is None:
            raise RuntimeError("DashScope Generation API is unavailable. Please install/configure dashscope first.")

    def query(self, prompt: str, stop_seqs=None, max_tokens: int = 1024, num_outputs: int = 1) -> str:
        del stop_seqs, num_outputs
        self._ensure_generation()
        response = Generation.call(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            result_format="message",
        )
        if response.status_code != 200:
            raise RuntimeError(str(response.message))
        return response.output.choices[0].message.content

    def query_with_system_prompt(
        self,
        system_prompt: str,
        prompt: str,
        stop_seqs=None,
        max_tokens: int = 1024,
        num_outputs: int = 1,
    ) -> str:
        del stop_seqs, num_outputs
        self._ensure_generation()
        response = Generation.call(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            result_format="message",
        )
        if response.status_code != 200:
            raise RuntimeError(str(response.message))
        return response.output.choices[0].message.content


OPENAI = QWEN
