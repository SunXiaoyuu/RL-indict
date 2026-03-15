from typing import Union, Literal
import pdb 
import logging
import time
from abc import ABC, abstractmethod
from typing import Callable
import os

import dashscope
from dashscope import Generation

NUM_LLM_RETRIES = 10
LOG: logging.Logger = logging.getLogger(__name__)

class LLM(ABC):
    def __init__(self, model: str, api_key: str) -> None:
        self.model: str = model
        self.api_key: str | None = api_key

    @abstractmethod
    def query(self, prompt: str) -> str:
        pass

    def query_with_system_prompt(self, system_prompt: str, prompt: str) -> str:
        return self.query(system_prompt + "\n" + prompt)

    def _query_with_retries(
        self,
        func: Callable[..., str],
        *args: str,
        retries: int = NUM_LLM_RETRIES,
        backoff_factor: float = 0.5,
    ) -> str:
        last_exception = None
        for retry in range(retries):
            try:
                return func(*args)
            except Exception as exception:
                last_exception = exception
                sleep_time = backoff_factor * (2**retry)
                time.sleep(sleep_time)
                LOG.debug(
                    f"LLM Query failed with error: {exception}. Sleeping for {sleep_time} seconds..."
                )
                print(f"LLM Query failed with error: {exception}. Sleeping for {sleep_time} seconds...")
        raise RuntimeError(
            f"Unable to query LLM after {retries} retries: {last_exception}"
        )

    def query_with_retries(self, prompt: str, stop_seqs=[], max_tokens=1024, num_outputs=1) -> str:
        return self._query_with_retries(self.query, prompt, stop_seqs, max_tokens, num_outputs)

    def query_with_system_prompt_with_retries(
        self, system_prompt: str, prompt: str, stop_seqs=[], max_tokens=1024, num_outputs=1) -> str:
        return self._query_with_retries(
            self.query_with_system_prompt, system_prompt, prompt, stop_seqs, max_tokens, num_outputs)

class QWEN(LLM):
    """使用Qwen模型"""

    def __init__(self, model_name: str = "qwen2.5-14b-instruct", api_key: str = None, base_url=None) -> None:
        # 使用你已验证有效的API密钥
        api_key = api_key or "sk-e0684cacf12246528358ae32ee4fc135"
        super().__init__(model_name, api_key)
        
        # 设置API密钥
        dashscope.api_key = self.api_key
        self.name = model_name
        print(f"✅ 初始化Qwen模型: {model_name}")

    def query(self, prompt: str, stop_seqs=None, max_tokens=1024, num_outputs=1) -> str:
        """使用Qwen进行查询"""
        for attempt in range(NUM_LLM_RETRIES):
            try:
                messages = [{"role": "user", "content": prompt}]
                response = Generation.call(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    result_format='message'
                )
                
                if response.status_code == 200:
                    # 修复：确保response.output.choices存在
                    if hasattr(response, 'output') and response.output and response.output.choices:
                        return response.output.choices[0].message.content
                    else:
                        return "API响应格式异常"
                else:
                    print(f"Qwen API错误 (尝试 {attempt + 1}/{NUM_LLM_RETRIES}): {response.message}")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"Qwen查询异常 (尝试 {attempt + 1}/{NUM_LLM_RETRIES}): {e}")
                time.sleep(2)
        
        return "抱歉，暂时无法获取回答。"

    def query_with_system_prompt(self, system_prompt: str, prompt: str, stop_seqs=None, max_tokens=1024, num_outputs=1) -> str:
        """带系统提示的查询"""
        for attempt in range(NUM_LLM_RETRIES):
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
                response = Generation.call(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    result_format='message'
                )
                
                if response.status_code == 200:
                    # 修复：确保response.output.choices存在
                    if hasattr(response, 'output') and response.output and response.output.choices:
                        return response.output.choices[0].message.content
                    else:
                        return "API响应格式异常"
                else:
                    print(f"Qwen系统提示查询错误 (尝试 {attempt + 1}/{NUM_LLM_RETRIES}): {response.message}")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"Qwen系统提示查询异常 (尝试 {attempt + 1}/{NUM_LLM_RETRIES}): {e}")
                time.sleep(2)
        
        return "抱歉，暂时无法获取回答。"

# 为了向后兼容，保留OPENAI别名
OPENAI = QWEN