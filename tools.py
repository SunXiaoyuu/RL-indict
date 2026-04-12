from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from typing import Any

from qwen_client import QwenClient

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


ENABLE_QWEN_TOOL = os.getenv("INDICT_ENABLE_QWEN_TOOL", "0").lower() in {"1", "true", "yes", "on"}
QWEN_TOOL_MODEL = os.getenv("INDICT_QWEN_TOOL_MODEL", "qwen2.5-14b-instruct")


qwen_api = QwenClient(model_name=QWEN_TOOL_MODEL)


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
    if not ENABLE_QWEN_TOOL:
        return None

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
        result["source"] = f"qwen:{qwen_api.model_name}"
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
