from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backends import create_execution_backend
from configs import model_mapping
from util import extract_code, get_code_before, get_model, load_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a direct-generation Solidity baseline: prompt -> one Solidity answer -> "
            "compile/ABI/test/Slither/gas evaluation. No critics, no revision rounds."
        )
    )
    parser.add_argument("--data_path", default="data/solidity_fsm_testable_10.json")
    parser.add_argument("--model", default="qwen2.5-14b-instruct")
    parser.add_argument("--provider", default="auto", choices={"auto", "qwen", "openai", "deepseek"})
    parser.add_argument("--suffix", default="_direct_baseline")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument(
        "--solidity-prompt-mode",
        default="raw",
        choices={"raw", "light", "normalized"},
        help=(
            "Prompt strictness for direct generation. raw is the pure baseline; "
            "light adds broad internal constraints; normalized adds benchmark ABI/spec constraints."
        ),
    )
    parser.add_argument("--override", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--include-hard-constraints",
        action="store_true",
        help=(
            "Append machine-readable ABI/contract constraints to the raw task prompt. "
            "Leave disabled for the pure direct-generation baseline."
        ),
    )
    return parser.parse_args()


def normalize_signatures(signatures: Any) -> list[str]:
    if signatures is None:
        return []
    if isinstance(signatures, str):
        signatures = [signatures]
    if not isinstance(signatures, list):
        return []
    normalized: list[str] = []
    for signature in signatures:
        if not isinstance(signature, str):
            continue
        rendered = "".join(signature.strip().split())
        if rendered:
            normalized.append(rendered)
    return normalized


def build_hard_constraints(sample: dict[str, Any]) -> str:
    required = normalize_signatures(sample.get("required_abi_signatures", []))
    forbidden = normalize_signatures(sample.get("forbidden_abi_signatures", []))
    lines = ["Solidity hard constraints:"]
    contract_name = sample.get("contract_name")
    if contract_name:
        lines.append(f"- The primary contract name must remain exactly `{contract_name}`.")
    lines.extend(
        [
            "- Preserve every required ABI signature exactly.",
            "- Required getters must be implemented either by a public variable/mapping or by an explicit function, never both.",
            "- Do not add external imports, inherited contracts, upgradeable patterns, or third-party dependencies unless explicitly required.",
            "- Do not add unrequested public/external APIs; extra ABI entries count as interface drift.",
        ]
    )
    if required:
        lines.append("- Required ABI signatures: " + ", ".join(required))
    if forbidden:
        lines.append("- Forbidden ABI signatures: " + ", ".join(forbidden))
    return "\n".join(lines)


def build_light_constraints(sample: dict[str, Any]) -> str:
    lines = ["Solidity internal task constraints:"]
    contract_name = sample.get("contract_name")
    if contract_name:
        lines.append(f"- Use `{contract_name}` as the primary contract name if the requirement does not clearly demand another name.")
    lines.extend(
        [
            "- Infer a minimal public interface from the natural-language requirement.",
            "- Avoid broad unrequested admin/helper APIs, external imports, inherited contracts, upgradeable patterns, or third-party dependencies.",
            "- Do not declare a public state variable and an explicit getter with the same name.",
            "- Prefer simple Solidity 0.8.x code that preserves access-control, payment, and state-transition requirements.",
        ]
    )
    return "\n".join(lines)


def build_direct_prompt(
    question: str,
    sample: dict[str, Any],
    include_hard_constraints: bool,
    solidity_prompt_mode: str,
) -> str:
    parts = [
        "You are a Solidity code generator.",
        "Generate exactly one complete Solidity contract for the task below.",
        "Return only the Solidity code in a single ```solidity``` block.",
        "",
        question.strip(),
    ]
    if solidity_prompt_mode == "light":
        parts.extend(["", build_light_constraints(sample)])
    elif include_hard_constraints or solidity_prompt_mode == "normalized":
        parts.extend(["", build_hard_constraints(sample)])
    return "\n".join(parts).strip() + "\n"


def short_command_failure(command_result: dict[str, Any] | None, limit: int = 1500) -> str | None:
    if not isinstance(command_result, dict):
        return None
    if command_result.get("success") is not False:
        return None
    text = command_result.get("stderr") or command_result.get("stdout") or command_result.get("error") or ""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    shortened = "\n".join(lines[:12])
    if len(shortened) > limit:
        return shortened[: limit - 3].rstrip() + "..."
    return shortened or None


def build_structured_feedback(metrics: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    compile_result = metrics.get("compile") if isinstance(metrics, dict) else None
    abi_result = metrics.get("abi") if isinstance(metrics, dict) else None
    test_result = metrics.get("tests") if isinstance(metrics, dict) else None
    slither_result = metrics.get("slither") if isinstance(metrics, dict) else None
    gas_result = metrics.get("gas") if isinstance(metrics, dict) else None

    required = normalize_signatures(
        (abi_result or {}).get("required") if isinstance(abi_result, dict) else sample.get("required_abi_signatures", [])
    )
    forbidden = normalize_signatures(
        (abi_result or {}).get("forbidden") if isinstance(abi_result, dict) else sample.get("forbidden_abi_signatures", [])
    )
    available = normalize_signatures((abi_result or {}).get("available") if isinstance(abi_result, dict) else [])
    required_set = set(required)
    forbidden_set = set(forbidden)
    has_required_constructor = any(signature.startswith("constructor(") for signature in required)
    abi_extra = [
        signature
        for signature in available
        if signature not in required_set
        and signature not in forbidden_set
        and not (signature.startswith("constructor(") and not has_required_constructor)
    ]

    severity_counts = metrics.get("vulnerability_severity_counts") or {}
    slither_findings = metrics.get("slither_findings") or []
    feedback = {
        "compile_success": compile_result.get("success") if isinstance(compile_result, dict) else None,
        "compile_error": short_command_failure(compile_result),
        "abi_checked": abi_result.get("checked") if isinstance(abi_result, dict) else None,
        "abi_success": abi_result.get("success") if isinstance(abi_result, dict) else None,
        "abi_required": required,
        "abi_missing": (abi_result or {}).get("missing", []) if isinstance(abi_result, dict) else [],
        "abi_extra": abi_extra,
        "abi_forbidden_present": (abi_result or {}).get("forbidden_present", []) if isinstance(abi_result, dict) else [],
        "test_success": test_result.get("success") if isinstance(test_result, dict) else None,
        "test_failure": short_command_failure(test_result),
        "test_diagnostics": metrics.get("test_diagnostics") or {},
        "slither_findings": {
            "count": metrics.get("vulnerability_count"),
            "severity_counts": severity_counts,
            "classification_counts": metrics.get("slither_classification_counts") or {},
            "items": slither_findings,
        },
        "gas_used": metrics.get("max_gas_value"),
        "gas_command_success": gas_result.get("success") if isinstance(gas_result, dict) else None,
    }
    if isinstance(slither_result, dict):
        feedback["slither_findings"]["command_success"] = slither_result.get("success")
        if slither_result.get("success") is False:
            feedback["slither_findings"]["error"] = short_command_failure(slither_result)
    feedback["target_defect"] = infer_target_defect(feedback)
    return feedback


def infer_target_defect(feedback: dict[str, Any]) -> str:
    if feedback.get("compile_success") is False:
        return "compile_error"
    if feedback.get("abi_missing"):
        return "abi_missing"
    if feedback.get("abi_forbidden_present"):
        return "abi_forbidden_present"
    if feedback.get("abi_extra"):
        return "abi_extra"
    if feedback.get("test_success") is False:
        diagnostics = feedback.get("test_diagnostics") or {}
        failure_types = diagnostics.get("failure_types") or []
        return "test_failure:" + ",".join(str(item) for item in failure_types) if failure_types else "test_failure"
    slither = feedback.get("slither_findings") or {}
    classification_counts = slither.get("classification_counts") or {}
    if classification_counts.get("security_blocking"):
        return "security_blocking_slither"
    if classification_counts.get("security_review"):
        return "security_review_slither"
    if feedback.get("gas_used") is None:
        return "gas_unavailable"
    return "none"


def main() -> None:
    args = parse_args()
    data, _action_prompt_header, question_prompt_key = load_data("solidity", data_path=args.data_path)
    model = get_model(args.model, model_mapping, provider=args.provider)

    output_dir = Path(args.output_dir) if args.output_dir else Path(f"solidity_{args.model}") / f"direct_generation{args.suffix}"
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "strategy": "direct_generation",
        "provider": args.provider,
        "model": args.model,
        "data_path": args.data_path,
        "include_hard_constraints": args.include_hard_constraints,
        "solidity_prompt_mode": args.solidity_prompt_mode,
        "max_tokens": args.max_tokens,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
    }
    (output_dir / "run_config.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Direct-generation baseline config:")
    print(f"  provider: {args.provider}")
    print(f"  model:    {args.model}")
    print(f"  dataset:  {args.data_path}")
    print(f"  output:   {output_dir}")
    print(f"  prompt mode: {args.solidity_prompt_mode}")
    print(f"  hard constraints appended: {args.include_hard_constraints}")

    for sample_idx, item in tqdm(list(enumerate(data)), total=len(data)):
        output_path = output_dir / f"{sample_idx}.json"
        if output_path.exists() and not args.override:
            continue

        question = item[question_prompt_key]
        prompt = build_direct_prompt(question, item, args.include_hard_constraints, args.solidity_prompt_mode)
        action = model.query_with_retries(prompt, max_tokens=args.max_tokens)
        llm_call_stats = {
            "total_calls": 1,
            "actor_calls": 1,
            "critic_calls": 0,
            "tool_planning_calls": 0,
            "prompt_chars": len(prompt),
            "completion_chars": len(action or ""),
            "max_tokens_requested": args.max_tokens,
        }

        backend = create_execution_backend(
            task="solidity",
            programming_language=item.get("language", "solidity"),
            sample_metadata=item,
        )
        observation = backend.evaluate(extract_code(action), code_before=get_code_before(item))
        metrics = observation.as_dict()

        result = {
            "sample_idx": sample_idx,
            "strategy": "direct_generation",
            "provider": args.provider,
            "model": args.model,
            "direct_prompt": prompt,
            "action": action,
            "scratchpad": "",
            "critic": "",
            "initial_action": action,
            "critic_scratchpad": "",
            "runtime_config": {
                "cost_profile": "direct",
                "critic_mode": "none",
                "feedback_mode": "none",
                "posthoc_policy": "never",
                "critic_tools_enabled": False,
                "early_stop": True,
                "solidity_prompt_mode": args.solidity_prompt_mode,
            },
            "llm_call_stats": llm_call_stats,
            "execution_observation": observation.to_text(),
            "execution_metrics": metrics,
            "structured_feedback": build_structured_feedback(metrics, item),
        }
        output_path.write_text(json.dumps(result, indent=4, ensure_ascii=False), encoding="utf-8")

        if args.debug:
            break


if __name__ == "__main__":
    main()
