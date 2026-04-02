from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Any
# The DashScope Generation API is used to query Qwen for information about the code. If the API is not available, the code will still run but will not be able to query Qwen.
try:
    import dashscope
    from dashscope import Generation
except Exception:
    dashscope = None
    Generation = None

# These are sequences that may appear in Qwen's response when it is refusing to answer the question.
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


def _extract_fenced_code_blocks(text: str) -> list[str]:
    pattern = re.compile(r"`{3,}[^\n]*\n(.*?)\n`{3,}", re.DOTALL)
    return [match.group(1).strip() for match in pattern.finditer(text)]


def looks_like_solidity(code: str) -> bool:
    snippet = code.strip()
    lowered = snippet.lower()

    if "```solidity" in lowered or "pragma solidity" in lowered:
        return True

    fenced_blocks = _extract_fenced_code_blocks(snippet)
    if fenced_blocks:
        snippet = fenced_blocks[0]
        lowered = snippet.lower()

    indicators = [
        "pragma solidity",
        "contract ",
        "library ",
        "interface ",
        "abstract contract ",
        "import \"@openzeppelin/",
        "import '@openzeppelin/",
        "import \"./",
        "import '../",
        "function ",
        "constructor(",
        "constructor ",
        "modifier ",
        "event ",
        "error ",
        "struct ",
        "enum ",
    ]

    if lowered.startswith(tuple(indicators)):
        return True

    # Truncated snippets may begin mid-contract; scan the first part of the body too.
    head = lowered[:500]
    return any(indicator in head for indicator in indicators)


def query_qwen(query: str) -> dict[str, Any] | None:
    try:
        result = qwen_api.query_with_retries(query, max_tokens=256)
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
    del query
    tool_outputs = []
    result = query_qwen(combined_query)
    if not invalid_response(result):
        result["source"] = "qwen"
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
        if looks_like_solidity(code):
            execution_result = (
                "Skipped local execution because the provided snippet appears to be Solidity. "
                "Rely on compile, test, static-analysis, and gas observations instead."
            )
        else:
            execution_result = run_code(code)
        if not execution_result.strip():
            execution_result = "the code is compiled successfully without any error."
        combined_query += f"Code context:\n```{code}\n```\nCode output: {execution_result}"
        if query:
            combined_query += f"\nQuery: {query}"
    elif query:
        combined_query = f"Provide critical and useful information about the following: {query}"

    return query_all_tools(query, combined_query)
