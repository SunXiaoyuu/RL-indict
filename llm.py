from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Callable

from deepseek_client import DeepSeekClient
from openai_client import OpenAIClient
from qwen_client import QwenClient


NUM_LLM_RETRIES = 3
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
        super().__init__(model_name, api_key)
        self.client = QwenClient(model_name=model_name, api_key=api_key, base_url=base_url)
        self.name = model_name

    def query(self, prompt: str, stop_seqs=None, max_tokens: int = 1024, num_outputs: int = 1) -> str:
        del stop_seqs, num_outputs
        return self.client.query(prompt, max_tokens=max_tokens)

    def query_with_system_prompt(
        self,
        system_prompt: str,
        prompt: str,
        stop_seqs=None,
        max_tokens: int = 1024,
        num_outputs: int = 1,
    ) -> str:
        del stop_seqs, num_outputs
        return self.client.query_with_system_prompt(system_prompt, prompt, max_tokens=max_tokens)


class OPENAI(LLM):
    def __init__(self, model_name: str = "gpt-5.4", api_key: str | None = None, base_url=None, api_mode=None) -> None:
        super().__init__(model_name, api_key)
        self.client = OpenAIClient(model_name=model_name, api_key=api_key, base_url=base_url, api_mode=api_mode)
        self.name = model_name

    def query(self, prompt: str, stop_seqs=None, max_tokens: int = 1024, num_outputs: int = 1) -> str:
        del num_outputs
        return self.client.query(prompt, max_tokens=max_tokens, stop=stop_seqs)

    def query_with_system_prompt(
        self,
        system_prompt: str,
        prompt: str,
        stop_seqs=None,
        max_tokens: int = 1024,
        num_outputs: int = 1,
    ) -> str:
        del num_outputs
        return self.client.query_with_system_prompt(system_prompt, prompt, max_tokens=max_tokens, stop=stop_seqs)


class DEEPSEEK(LLM):
    def __init__(self, model_name: str = "deepseek-chat", api_key: str | None = None, base_url=None) -> None:
        super().__init__(model_name, api_key)
        self.client = DeepSeekClient(model_name=model_name, api_key=api_key, base_url=base_url)
        self.name = model_name

    def query(self, prompt: str, stop_seqs=None, max_tokens: int = 1024, num_outputs: int = 1) -> str:
        del num_outputs
        return self.client.query(prompt, max_tokens=max_tokens, stop=stop_seqs)

    def query_with_system_prompt(
        self,
        system_prompt: str,
        prompt: str,
        stop_seqs=None,
        max_tokens: int = 1024,
        num_outputs: int = 1,
    ) -> str:
        del num_outputs
        return self.client.query_with_system_prompt(system_prompt, prompt, max_tokens=max_tokens, stop=stop_seqs)
