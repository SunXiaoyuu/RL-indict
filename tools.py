from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

try:
    from search_engine_parser.core.engines.yahoo import Search as YahooSearch
except Exception:
    YahooSearch = None

try:
    from langchain.agents.react.base import DocstoreExplorer
    from langchain_community.docstore.wikipedia import Wikipedia
except Exception:
    DocstoreExplorer = None
    Wikipedia = None

try:
    import dashscope
    from dashscope import Generation
except Exception:
    dashscope = None
    Generation = None


refusal_seqs = [
    "i can't",
    "i cannot",
    "i don't know",
    "i do not know",
    "i am not sure",
    "i'm not sure",
    "sorry i",
    "i refuse",
]

yahoo_api = YahooSearch() if YahooSearch is not None else None
wikipedia_api = DocstoreExplorer(Wikipedia()) if DocstoreExplorer is not None and Wikipedia is not None else None

if dashscope is not None:
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    if not dashscope_api_key:
        dashscope_api_key = "dummy-key"
    dashscope.api_key = dashscope_api_key


class QWEN:
    def __init__(self, model_name: str = "qwen-max") -> None:
        self.model_name = model_name

    def query_with_retries(self, query: str, max_tokens: int = 256, max_retries: int = 3) -> str:
        if Generation is None:
            raise RuntimeError("DashScope Generation API is unavailable.")

        last_error = "unknown error"
        for attempt in range(max_retries):
            try:
                response = Generation.call(
                    model=self.model_name,
                    messages=[{"role": "user", "content": query}],
                    max_tokens=max_tokens,
                    result_format="message",
                )
                if response.status_code == 200:
                    return response.output.choices[0].message.content
                last_error = str(response.message)
            except Exception as exc:
                last_error = str(exc)
            if attempt < max_retries - 1:
                time.sleep(2)
        raise RuntimeError(last_error)


qwen_api = QWEN(model_name="qwen-max")


def run_code(code: str, timeout_seconds: int = 120) -> str:
    with tempfile.TemporaryDirectory(prefix="indict_tools_python_") as temp_dir:
        script_path = os.path.join(temp_dir, "generated.py")
        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write(code)
        try:
            completed = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            return f"Exception: {exc}"

    if completed.returncode == 0:
        return completed.stdout
    return completed.stderr or completed.stdout or f"Process exited with code {completed.returncode}"


def internet_search(query: str) -> dict[str, Any] | None:
    if yahoo_api is None:
        return None
    try:
        results = yahoo_api.search(query, 1)
        output: dict[str, Any] = {}
        for result in results:
            titles = result.get("titles")
            descriptions = result.get("descriptions")
            output["title"] = f"{query} - {titles}" if titles else query
            if descriptions:
                output["description"] = descriptions
                break
        return output if output else None
    except Exception:
        return None


def query_qwen(query: str) -> dict[str, Any] | None:
    try:
        result = qwen_api.query_with_retries(query, max_tokens=256)
        return {"title": query, "description": result}
    except Exception:
        return None


def query_wikipedia(query: str) -> dict[str, Any] | None:
    if wikipedia_api is None:
        return None
    try:
        result = wikipedia_api.search(query)
        if "could not find" in result.lower():
            return None
        return {"title": query, "description": result}
    except Exception:
        return None


def invalid_response(response: dict[str, Any] | None) -> bool:
    if response is None:
        return True
    description = response.get("description", "")
    if not description or not description.strip():
        return True
    lowered = description.lower()
    return any(seq in lowered for seq in refusal_seqs)


def query_all_tools(query: str | None, combined_query: str) -> list[dict[str, Any]]:
    tool_outputs = []
    for source in ("qwen", "internet", "wikipedia"):
        if source == "qwen":
            result = query_qwen(combined_query)
        elif source == "internet":
            result = internet_search(combined_query)
        else:
            result = query_wikipedia(query) if query else None
        if not invalid_response(result):
            result["source"] = source
            tool_outputs.append(result)
    return tool_outputs


def code_search(query: str, snippet: str | None = None) -> list[dict[str, Any]]:
    if snippet and snippet.strip():
        combined_query = f"Code context:\n```{snippet}\n```\nQuery: {query}"
    else:
        combined_query = f"Provide critical and useful information about the following: {query}"
    return query_all_tools(query, combined_query)


def code_review(query: str | None = None, code: str | None = None) -> list[dict[str, Any]] | None:
    if query is None and code is None:
        return None

    combined_query = ""
    if code and code.strip():
        execution_result = run_code(code)
        if not execution_result.strip():
            execution_result = "the code is compiled successfully without any error."
        combined_query += f"Code context:\n```{code}\n```\nCode output: {execution_result}"
        if query:
            combined_query += f"\nQuery: {query}"
    elif query:
        combined_query = f"Provide critical and useful information about the following: {query}"

    return query_all_tools(query, combined_query)
