#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


FAIL_PATTERN = re.compile(r"\[FAIL: ([^\]]+)\]")
WHITESPACE_PATTERN = re.compile(r"\s+")
ROUND_DIR_PATTERN = re.compile(r"^(?P<prefix>.*?round)(?P<num>\d+)(?P<suffix>.*)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Join a Solidity dataset JSON with an INDICT result directory and "
            "write aligned summary tables."
        )
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="Path to the dataset JSON file used for the run.",
    )
    parser.add_argument(
        "--results-dir",
        required=True,
        help="Directory containing result files like 0.json, 1.json, ...",
    )
    parser.add_argument(
        "--output-prefix",
        help=(
            "Output file prefix. Defaults to <results-dir>/summary, which will "
            "create summary.json, summary.csv, and summary.md."
        ),
    )
    parser.add_argument(
        "--instruction-chars",
        type=int,
        default=160,
        help="Maximum length of the instruction summary column.",
    )
    parser.add_argument(
        "--compare-results-dir",
        action="append",
        default=[],
        help=(
            "Additional result directory to include in a round comparison. "
            "May be repeated. If omitted and --results-dir contains roundN, "
            "sibling round directories are detected automatically."
        ),
    )
    parser.add_argument(
        "--baseline-results-dir",
        action="append",
        default=[],
        help=(
            "Direct-generation or other baseline result directory to compare against "
            "--results-dir. May be repeated."
        ),
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(value: str, limit: int | None = None) -> str:
    text = WHITESPACE_PATTERN.sub(" ", (value or "").strip())
    if limit is not None and len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def sort_key_for_result_file(path: Path) -> tuple[int, str]:
    try:
        return (0, str(int(path.stem)))
    except ValueError:
        return (1, path.stem)


def first_nonempty_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def extract_compile_failure_short(metrics: dict[str, Any]) -> str:
    compile_metrics = metrics.get("compile") or {}
    stderr = compile_metrics.get("stderr") or ""
    summary = metrics.get("summary") or ""

    prioritized_errors: list[str] = []
    fallback_lines: list[str] = []
    for line in stderr.splitlines():
        line = line.strip()
        if not line:
            continue
        if line == "Error: Compiler run failed:":
            continue
        if line.startswith("Error"):
            prioritized_errors.append(line)
            continue
        fallback_lines.append(line)

    if prioritized_errors:
        return prioritized_errors[0]
    if fallback_lines:
        return fallback_lines[0]

    return first_nonempty_line(summary)


def extract_test_failure_short(metrics: dict[str, Any]) -> str:
    diagnostics = metrics.get("test_diagnostics") or {}
    failed_tests = diagnostics.get("failed_tests") or []
    if failed_tests:
        first = failed_tests[0]
        if isinstance(first, dict):
            name = first.get("name") or "unknown"
            reason = first.get("reason") or first.get("failure_type") or "test failed"
            return normalize_text(f"{name}: {reason}")

    tests = metrics.get("tests") or {}
    stdout = tests.get("stdout") or ""
    summary = metrics.get("summary") or ""

    fail_match = FAIL_PATTERN.search(stdout)
    if fail_match:
        return normalize_text(fail_match.group(1))

    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("Encountered 1 failing test"):
            return line

    return first_nonempty_line(summary)


def flatten_severity_counts(counts: dict[str, Any] | None) -> tuple[int, int, int, int]:
    counts = counts or {}
    return (
        int(counts.get("critical", 0) or 0),
        int(counts.get("high", 0) or 0),
        int(counts.get("medium", 0) or 0),
        int(counts.get("low", 0) or 0),
    )


def flatten_classification_counts(counts: dict[str, Any] | None) -> tuple[int, int, int, int, int]:
    counts = counts or {}
    return (
        int(counts.get("security_blocking", 0) or 0),
        int(counts.get("security_review", 0) or 0),
        int(counts.get("spec_conflict", 0) or 0),
        int(counts.get("quality_warning", 0) or 0),
        int(counts.get("acceptable_pattern", 0) or 0),
    )


def classify_slither_finding(check: Any, impact: Any, dataset_sample: dict[str, Any]) -> str:
    check_name = str(check or "").lower()
    impact_name = str(impact or "").lower()
    category = str(dataset_sample.get("category") or "").lower()
    contract_name = str(dataset_sample.get("contract_name") or "").lower()
    required = set(str(signature).replace(" ", "") for signature in dataset_sample.get("required_abi_signatures") or [])
    if impact_name in {"critical", "high"}:
        return "security_blocking"
    if check_name == "arbitrary-send-eth":
        return "security_blocking"
    if check_name == "locked-ether":
        if "withdraw()" not in required and not any(signature.startswith("withdraw(") for signature in required):
            return "spec_conflict"
        return "security_blocking"
    if check_name == "timestamp":
        if any(token in category or token in contract_name for token in ("vesting", "timelock", "lock", "presale", "sale")):
            return "acceptable_pattern"
        return "security_review"
    if check_name in {"events-maths", "events-access", "reentrancy-events"}:
        return "quality_warning"
    if impact_name == "medium":
        return "security_review"
    return "quality_warning"


def infer_classification_counts(metrics: dict[str, Any], dataset_sample: dict[str, Any]) -> dict[str, int]:
    counts = dict(metrics.get("slither_classification_counts") or {})
    if counts:
        return counts
    for finding in metrics.get("slither_findings") or []:
        if not isinstance(finding, dict):
            continue
        classification = finding.get("classification") or classify_slither_finding(
            finding.get("check"),
            finding.get("impact"),
            dataset_sample,
        )
        counts[classification] = counts.get(classification, 0) + 1
    return counts


def classify_final_status(row: dict[str, Any]) -> str:
    if row.get("result_present") is not True:
        return "missing_result"
    if row.get("compile_success") is not True:
        return "compile_failed"
    if row.get("abi_success") is False:
        return "abi_failed"
    if row.get("test_success") is False:
        return "test_failed"
    if row.get("test_success") is None:
        return "tests_unavailable"
    if row.get("abi_extra"):
        return "passed_with_extra_abi"
    if int(row.get("slither_security_blocking_count") or 0) > 0:
        return "passed_with_security_blocking_findings"
    if int(row.get("slither_security_review_count") or 0) > 0:
        return "passed_with_security_review_findings"
    vulnerability_count = row.get("vulnerability_count")
    if isinstance(vulnerability_count, int) and vulnerability_count > 0:
        return "passed_with_slither_findings"
    if row.get("max_gas_value") is None:
        return "passed_gas_unavailable"
    return "passed_clean"


def summarize_instruction(instruction: str, limit: int) -> str:
    first_line = instruction.splitlines()[0] if instruction else ""
    return normalize_text(first_line, limit=limit)


def load_dataset_rows(dataset_path: Path) -> list[dict[str, Any]]:
    data = load_json(dataset_path)
    if not isinstance(data, list):
        raise ValueError(f"Dataset must be a JSON list: {dataset_path}")
    rows: list[dict[str, Any]] = []
    for sample_idx, sample in enumerate(data):
        if not isinstance(sample, dict):
            raise ValueError(f"Dataset entry #{sample_idx} must be an object")
        row = dict(sample)
        row["sample_idx"] = sample_idx
        rows.append(row)
    return rows


def load_results(result_dir: Path) -> dict[int, dict[str, Any]]:
    results: dict[int, dict[str, Any]] = {}
    for path in sorted(result_dir.glob("*.json"), key=sort_key_for_result_file):
        record = load_json(path)
        if not isinstance(record, dict):
            continue
        sample_idx = record.get("sample_idx")
        if sample_idx is None:
            try:
                sample_idx = int(path.stem)
            except ValueError:
                continue
        results[int(sample_idx)] = record
    return results


def build_row(
    dataset_sample: dict[str, Any],
    result_record: dict[str, Any] | None,
    instruction_chars: int,
) -> dict[str, Any]:
    sample_idx = int(dataset_sample["sample_idx"])
    instruction = dataset_sample.get("instruction", "")

    row: dict[str, Any] = {
        "sample_idx": sample_idx,
        "dataset_id": dataset_sample.get("id"),
        "source_fsm_id": dataset_sample.get("source_fsm_id"),
        "contract_name": dataset_sample.get("contract_name"),
        "source_contract_name": dataset_sample.get("source_contract_name"),
        "category": dataset_sample.get("category"),
        "difficulty": dataset_sample.get("difficulty"),
        "partition": dataset_sample.get("benchmark_partition"),
        "result_present": result_record is not None,
        "instruction_summary": summarize_instruction(instruction, instruction_chars),
        "instruction": instruction,
    }

    if result_record is None:
        row.update(
            {
                "result_file": None,
                "compile_success": None,
                "abi_checked": None,
                "abi_success": None,
                "abi_missing": "",
                "abi_extra": "",
                "abi_forbidden_present": "",
                "test_success": None,
                "vulnerability_count": None,
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
                "slither_security_blocking_count": 0,
                "slither_security_review_count": 0,
                "slither_spec_conflict_count": 0,
                "slither_quality_warning_count": 0,
                "slither_acceptable_pattern_count": 0,
                "max_gas_value": None,
                "test_failure_types": "",
                "failed_tests": "",
                "repair_hints": "",
                "degradation_guard": None,
                "stop_reason": None,
                "cost_profile": None,
                "critic_mode": None,
                "feedback_mode": None,
                "posthoc_policy": None,
                "total_llm_calls": 0,
                "actor_calls": 0,
                "critic_calls": 0,
                "tool_planning_calls": 0,
                "prompt_chars": 0,
                "completion_chars": 0,
                "max_tokens_requested": 0,
                "compile_command": None,
                "test_command": None,
                "failure_stage": "missing_result",
                "failure_reason_short": "Missing result file",
                "final_status": "missing_result",
                "execution_summary": None,
            }
        )
        return row

    metrics = result_record.get("execution_metrics") or {}
    runtime_config = result_record.get("runtime_config") or {}
    llm_call_stats = result_record.get("llm_call_stats") or {}
    compile_metrics = metrics.get("compile") or {}
    abi_metrics = metrics.get("abi") or {}
    abi_missing = abi_metrics.get("missing") or []
    abi_forbidden_present = abi_metrics.get("forbidden_present") or []
    abi_required = set(abi_metrics.get("required") or dataset_sample.get("required_abi_signatures") or [])
    abi_forbidden = set(abi_metrics.get("forbidden") or dataset_sample.get("forbidden_abi_signatures") or [])
    abi_available = abi_metrics.get("available") or []
    has_required_constructor = any(str(signature).startswith("constructor(") for signature in abi_required)
    abi_extra = [
        signature
        for signature in abi_available
        if signature not in abi_required
        and signature not in abi_forbidden
        and not (str(signature).startswith("constructor(") and not has_required_constructor)
    ]
    tests_metrics = metrics.get("tests")
    vulnerability_counts = metrics.get("vulnerability_severity_counts") or {}
    critical_count, high_count, medium_count, low_count = flatten_severity_counts(vulnerability_counts)
    classification_counts = infer_classification_counts(metrics, dataset_sample)
    (
        slither_security_blocking_count,
        slither_security_review_count,
        slither_spec_conflict_count,
        slither_quality_warning_count,
        slither_acceptable_pattern_count,
    ) = flatten_classification_counts(classification_counts)
    test_diagnostics = metrics.get("test_diagnostics") or result_record.get("structured_feedback", {}).get("test_diagnostics") or {}
    failed_tests = test_diagnostics.get("failed_tests") or []
    failed_test_names = [
        str(item.get("name"))
        for item in failed_tests
        if isinstance(item, dict) and item.get("name")
    ]
    failure_types = test_diagnostics.get("failure_types") or [
        str(item.get("failure_type"))
        for item in failed_tests
        if isinstance(item, dict) and item.get("failure_type")
    ]
    repair_hints = test_diagnostics.get("repair_hints") or [
        str(item.get("repair_hint"))
        for item in failed_tests
        if isinstance(item, dict) and item.get("repair_hint")
    ]

    compile_success = compile_metrics.get("success")
    test_success = tests_metrics.get("success") if tests_metrics is not None else None

    failure_stage = ""
    failure_reason_short = ""
    if compile_success is False:
        failure_stage = "compile"
        failure_reason_short = extract_compile_failure_short(metrics)
    elif test_success is False:
        failure_stage = "test"
        failure_reason_short = extract_test_failure_short(metrics)

    row.update(
        {
            "result_file": f"{sample_idx}.json",
            "compile_success": compile_success,
            "abi_checked": abi_metrics.get("checked") if isinstance(abi_metrics, dict) else None,
            "abi_success": abi_metrics.get("success") if isinstance(abi_metrics, dict) else None,
            "abi_missing": ",".join(abi_missing),
            "abi_extra": ",".join(abi_extra),
            "abi_forbidden_present": ",".join(abi_forbidden_present),
            "test_success": test_success,
            "vulnerability_count": metrics.get("vulnerability_count"),
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
            "slither_security_blocking_count": slither_security_blocking_count,
            "slither_security_review_count": slither_security_review_count,
            "slither_spec_conflict_count": slither_spec_conflict_count,
            "slither_quality_warning_count": slither_quality_warning_count,
            "slither_acceptable_pattern_count": slither_acceptable_pattern_count,
            "max_gas_value": metrics.get("max_gas_value"),
            "test_failure_types": ",".join(sorted(set(str(item) for item in failure_types if item))),
            "failed_tests": ",".join(failed_test_names),
            "repair_hints": " | ".join(sorted(set(str(item) for item in repair_hints if item))),
            "degradation_guard": result_record.get("degradation_guard"),
            "stop_reason": result_record.get("stop_reason"),
            "cost_profile": runtime_config.get("cost_profile"),
            "critic_mode": runtime_config.get("critic_mode"),
            "feedback_mode": runtime_config.get("feedback_mode"),
            "posthoc_policy": runtime_config.get("posthoc_policy"),
            "total_llm_calls": int(llm_call_stats.get("total_calls") or 0),
            "actor_calls": int(llm_call_stats.get("actor_calls") or 0),
            "critic_calls": int(llm_call_stats.get("critic_calls") or 0),
            "tool_planning_calls": int(llm_call_stats.get("tool_planning_calls") or 0),
            "prompt_chars": int(llm_call_stats.get("prompt_chars") or 0),
            "completion_chars": int(llm_call_stats.get("completion_chars") or 0),
            "max_tokens_requested": int(llm_call_stats.get("max_tokens_requested") or 0),
            "compile_command": compile_metrics.get("command"),
            "test_command": (tests_metrics or {}).get("command") if tests_metrics is not None else None,
            "failure_stage": failure_stage,
            "failure_reason_short": normalize_text(failure_reason_short, limit=180),
            "execution_summary": normalize_text(metrics.get("summary") or "", limit=280),
        }
    )
    row["final_status"] = classify_final_status(row)
    return row


def compute_aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    result_present = sum(1 for row in rows if row["result_present"])
    compile_success = sum(1 for row in rows if row["compile_success"] is True)
    compile_failed = sum(1 for row in rows if row["compile_success"] is False)
    tests_available = sum(1 for row in rows if row["test_success"] is not None)
    tests_passed = sum(1 for row in rows if row["test_success"] is True)
    tests_failed = sum(1 for row in rows if row["test_success"] is False)
    abi_checked = sum(1 for row in rows if row["abi_checked"] is True)
    abi_passed = sum(1 for row in rows if row["abi_success"] is True)
    abi_failed = sum(1 for row in rows if row["abi_success"] is False)
    rollback_count = sum(1 for row in rows if row["degradation_guard"])
    abi_extra_samples = sum(1 for row in rows if row.get("abi_extra"))
    vulnerability_total = sum(int(row.get("vulnerability_count") or 0) for row in rows)
    slither_security_blocking_total = sum(int(row.get("slither_security_blocking_count") or 0) for row in rows)
    slither_security_review_total = sum(int(row.get("slither_security_review_count") or 0) for row in rows)
    slither_spec_conflict_total = sum(int(row.get("slither_spec_conflict_count") or 0) for row in rows)
    slither_quality_warning_total = sum(int(row.get("slither_quality_warning_count") or 0) for row in rows)
    slither_acceptable_pattern_total = sum(int(row.get("slither_acceptable_pattern_count") or 0) for row in rows)
    gas_values = [int(row["max_gas_value"]) for row in rows if isinstance(row.get("max_gas_value"), int)]
    total_llm_calls = sum(int(row.get("total_llm_calls") or 0) for row in rows)
    actor_calls = sum(int(row.get("actor_calls") or 0) for row in rows)
    critic_calls = sum(int(row.get("critic_calls") or 0) for row in rows)
    tool_planning_calls = sum(int(row.get("tool_planning_calls") or 0) for row in rows)
    prompt_chars = sum(int(row.get("prompt_chars") or 0) for row in rows)
    completion_chars = sum(int(row.get("completion_chars") or 0) for row in rows)
    max_tokens_requested = sum(int(row.get("max_tokens_requested") or 0) for row in rows)
    final_status_counts: dict[str, int] = {}
    for row in rows:
        status = row.get("final_status") or "unknown"
        final_status_counts[status] = final_status_counts.get(status, 0) + 1

    return {
        "total_samples": total,
        "result_present": result_present,
        "compile_success": compile_success,
        "compile_failed": compile_failed,
        "tests_available": tests_available,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "abi_checked": abi_checked,
        "abi_passed": abi_passed,
        "abi_failed": abi_failed,
        "rollback_count": rollback_count,
        "abi_extra_samples": abi_extra_samples,
        "vulnerability_total": vulnerability_total,
        "slither_security_blocking_total": slither_security_blocking_total,
        "slither_security_review_total": slither_security_review_total,
        "slither_spec_conflict_total": slither_spec_conflict_total,
        "slither_quality_warning_total": slither_quality_warning_total,
        "slither_acceptable_pattern_total": slither_acceptable_pattern_total,
        "gas_available": len(gas_values),
        "gas_average": round(sum(gas_values) / len(gas_values), 1) if gas_values else None,
        "total_llm_calls": total_llm_calls,
        "actor_calls": actor_calls,
        "critic_calls": critic_calls,
        "tool_planning_calls": tool_planning_calls,
        "prompt_chars": prompt_chars,
        "completion_chars": completion_chars,
        "max_tokens_requested": max_tokens_requested,
        "avg_llm_calls_per_sample": round(total_llm_calls / result_present, 2) if result_present else None,
        "final_status_counts": final_status_counts,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sample_idx",
        "dataset_id",
        "source_fsm_id",
        "contract_name",
        "source_contract_name",
        "category",
        "difficulty",
        "partition",
        "result_present",
        "compile_success",
        "abi_checked",
        "abi_success",
        "abi_missing",
        "abi_extra",
        "abi_forbidden_present",
        "test_success",
        "vulnerability_count",
        "critical_count",
        "high_count",
        "medium_count",
        "low_count",
        "slither_security_blocking_count",
        "slither_security_review_count",
        "slither_spec_conflict_count",
        "slither_quality_warning_count",
        "slither_acceptable_pattern_count",
        "max_gas_value",
        "test_failure_types",
        "failed_tests",
        "repair_hints",
        "degradation_guard",
        "stop_reason",
        "cost_profile",
        "critic_mode",
        "feedback_mode",
        "posthoc_policy",
        "total_llm_calls",
        "actor_calls",
        "critic_calls",
        "tool_planning_calls",
        "prompt_chars",
        "completion_chars",
        "max_tokens_requested",
        "failure_stage",
        "failure_reason_short",
        "final_status",
        "instruction_summary",
        "result_file",
        "compile_command",
        "test_command",
        "execution_summary",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def bool_token(value: Any) -> str:
    if value is True:
        return "T"
    if value is False:
        return "F"
    return "-"


def metric_token(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


def infer_round_label(path: Path) -> str:
    match = ROUND_DIR_PATTERN.match(path.name)
    if match:
        return f"round{match.group('num')}"
    return path.name


def round_sort_key(path: Path) -> tuple[int, str]:
    match = ROUND_DIR_PATTERN.match(path.name)
    if match:
        return (int(match.group("num")), path.name)
    return (10**9, path.name)


def discover_comparison_dirs(results_dir: Path, explicit_dirs: list[str]) -> list[Path]:
    if explicit_dirs:
        paths = [Path(value).resolve() for value in explicit_dirs]
        paths.append(results_dir)
    else:
        match = ROUND_DIR_PATTERN.match(results_dir.name)
        if not match:
            return []
        paths = []
        for candidate in results_dir.parent.iterdir():
            if not candidate.is_dir():
                continue
            candidate_match = ROUND_DIR_PATTERN.match(candidate.name)
            if not candidate_match:
                continue
            if (
                candidate_match.group("prefix") == match.group("prefix")
                and candidate_match.group("suffix") == match.group("suffix")
            ):
                paths.append(candidate.resolve())

    unique: dict[Path, Path] = {}
    for path in paths:
        if path.exists() and path.is_dir():
            unique[path.resolve()] = path.resolve()
    return sorted(unique.values(), key=round_sort_key)


def build_round_comparison(
    dataset_rows: list[dict[str, Any]],
    result_dirs: list[Path],
    instruction_chars: int,
) -> dict[str, Any]:
    round_entries = []
    rows_by_round: dict[str, list[dict[str, Any]]] = {}
    for result_dir in result_dirs:
        label = infer_round_label(result_dir)
        result_records = load_results(result_dir)
        rows = [
            build_row(sample, result_records.get(int(sample["sample_idx"])), instruction_chars)
            for sample in dataset_rows
        ]
        round_entries.append({"label": label, "results_dir": str(result_dir)})
        rows_by_round[label] = rows

    comparison_rows: list[dict[str, Any]] = []
    labels = [entry["label"] for entry in round_entries]
    for sample in dataset_rows:
        sample_idx = int(sample["sample_idx"])
        per_round = [rows_by_round[label][sample_idx] for label in labels]
        final_row = per_round[-1]
        comparison_rows.append(
            {
                "sample_idx": sample_idx,
                "dataset_id": sample.get("id"),
                "contract_name": sample.get("contract_name"),
                "partition": sample.get("benchmark_partition"),
                "compile_transition": " -> ".join(bool_token(row.get("compile_success")) for row in per_round),
                "abi_transition": " -> ".join(bool_token(row.get("abi_success")) for row in per_round),
                "test_transition": " -> ".join(bool_token(row.get("test_success")) for row in per_round),
                "slither_transition": " -> ".join(metric_token(row.get("vulnerability_count")) for row in per_round),
                "gas_transition": " -> ".join(metric_token(row.get("max_gas_value")) for row in per_round),
                "llm_calls_transition": " -> ".join(metric_token(row.get("total_llm_calls")) for row in per_round),
                "status_transition": " -> ".join(row.get("final_status", "unknown") for row in per_round),
                "final_status": final_row.get("final_status", "unknown"),
                "final_failure": final_row.get("failure_reason_short", ""),
            }
        )

    return {
        "rounds": round_entries,
        "rows": comparison_rows,
    }


def write_comparison_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sample_idx",
        "dataset_id",
        "contract_name",
        "partition",
        "compile_transition",
        "abi_transition",
        "test_transition",
        "slither_transition",
        "gas_transition",
        "llm_calls_transition",
        "status_transition",
        "final_status",
        "final_failure",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def row_quality_score(row: dict[str, Any]) -> int:
    score = 0
    if row.get("compile_success") is True:
        score += 1000
    else:
        return score
    if row.get("abi_success") is True:
        score += 300
    if row.get("test_success") is True:
        score += 500
    if row.get("test_success") is False:
        score -= 150
    score -= 60 * len([item for item in str(row.get("abi_extra") or "").split(",") if item])
    score -= 300 * int(row.get("slither_security_blocking_count") or 0)
    score -= 80 * int(row.get("slither_security_review_count") or 0)
    score -= 20 * int(row.get("slither_spec_conflict_count") or 0)
    score -= 10 * int(row.get("slither_quality_warning_count") or 0)
    score -= 2 * int(row.get("slither_acceptable_pattern_count") or 0)
    return score


def numeric_delta(final_value: Any, baseline_value: Any) -> str:
    if final_value is None or baseline_value is None:
        return "-"
    try:
        delta = int(final_value) - int(baseline_value)
    except Exception:
        return "-"
    if delta > 0:
        return f"+{delta}"
    return str(delta)


def bool_change(final_value: Any, baseline_value: Any) -> str:
    return f"{bool_token(baseline_value)} -> {bool_token(final_value)}"


def build_baseline_comparison(
    dataset_rows: list[dict[str, Any]],
    baseline_dir: Path,
    final_dir: Path,
    instruction_chars: int,
) -> dict[str, Any]:
    baseline_records = load_results(baseline_dir)
    final_records = load_results(final_dir)
    rows = []
    for sample in dataset_rows:
        sample_idx = int(sample["sample_idx"])
        baseline_row = build_row(sample, baseline_records.get(sample_idx), instruction_chars)
        final_row = build_row(sample, final_records.get(sample_idx), instruction_chars)
        baseline_score = row_quality_score(baseline_row)
        final_score = row_quality_score(final_row)
        if final_score > baseline_score:
            improvement_label = "improved"
        elif final_score < baseline_score:
            improvement_label = "regressed"
        else:
            improvement_label = "unchanged"
        rows.append(
            {
                "sample_idx": sample_idx,
                "dataset_id": sample.get("id"),
                "contract_name": sample.get("contract_name"),
                "partition": sample.get("benchmark_partition"),
                "baseline_status": baseline_row.get("final_status"),
                "final_status": final_row.get("final_status"),
                "compile_change": bool_change(final_row.get("compile_success"), baseline_row.get("compile_success")),
                "abi_change": bool_change(final_row.get("abi_success"), baseline_row.get("abi_success")),
                "test_change": bool_change(final_row.get("test_success"), baseline_row.get("test_success")),
                "abi_extra_change": f"{baseline_row.get('abi_extra') or '-'} -> {final_row.get('abi_extra') or '-'}",
                "slither_change": numeric_delta(final_row.get("vulnerability_count"), baseline_row.get("vulnerability_count")),
                "security_blocking_change": numeric_delta(
                    final_row.get("slither_security_blocking_count"),
                    baseline_row.get("slither_security_blocking_count"),
                ),
                "gas_change": numeric_delta(final_row.get("max_gas_value"), baseline_row.get("max_gas_value")),
                "llm_calls_change": numeric_delta(final_row.get("total_llm_calls"), baseline_row.get("total_llm_calls")),
                "prompt_chars_change": numeric_delta(final_row.get("prompt_chars"), baseline_row.get("prompt_chars")),
                "baseline_score": baseline_score,
                "final_score": final_score,
                "improvement_label": improvement_label,
                "baseline_failure": baseline_row.get("failure_reason_short", ""),
                "final_failure": final_row.get("failure_reason_short", ""),
            }
        )

    counts: dict[str, int] = {}
    for row in rows:
        label = row["improvement_label"]
        counts[label] = counts.get(label, 0) + 1
    return {
        "baseline_dir": str(baseline_dir),
        "final_dir": str(final_dir),
        "counts": counts,
        "rows": rows,
    }


def write_baseline_comparison_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sample_idx",
        "dataset_id",
        "contract_name",
        "partition",
        "baseline_status",
        "final_status",
        "compile_change",
        "abi_change",
        "test_change",
        "abi_extra_change",
        "slither_change",
        "security_blocking_change",
        "gas_change",
        "llm_calls_change",
        "prompt_chars_change",
        "baseline_score",
        "final_score",
        "improvement_label",
        "baseline_failure",
        "final_failure",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def write_markdown(
    path: Path,
    rows: list[dict[str, Any]],
    aggregate: dict[str, Any],
    round_comparison: dict[str, Any] | None = None,
    baseline_comparisons: list[dict[str, Any]] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    final_status_counts = aggregate.get("final_status_counts", {})
    final_status_text = ", ".join(f"{key}={value}" for key, value in sorted(final_status_counts.items()))
    lines = [
        "# Solidity Result Summary",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Total samples: {aggregate['total_samples']}",
        f"- Results present: {aggregate['result_present']}",
        f"- Compile success: {aggregate['compile_success']}",
        f"- Compile failed: {aggregate['compile_failed']}",
        f"- ABI checked: {aggregate['abi_checked']}",
        f"- ABI passed: {aggregate['abi_passed']}",
        f"- ABI failed: {aggregate['abi_failed']}",
        f"- Tests passed: {aggregate['tests_passed']}",
        f"- Tests failed: {aggregate['tests_failed']}",
        f"- Rollback triggered: {aggregate['rollback_count']}",
        f"- ABI extra samples: {aggregate.get('abi_extra_samples', 0)}",
        f"- Slither findings total: {aggregate.get('vulnerability_total', 0)}",
        f"- Slither blocking/review/spec-conflict/quality/acceptable: "
        f"{aggregate.get('slither_security_blocking_total', 0)}/"
        f"{aggregate.get('slither_security_review_total', 0)}/"
        f"{aggregate.get('slither_spec_conflict_total', 0)}/"
        f"{aggregate.get('slither_quality_warning_total', 0)}/"
        f"{aggregate.get('slither_acceptable_pattern_total', 0)}",
        f"- Gas available / average: {aggregate.get('gas_available', 0)} / {aggregate.get('gas_average')}",
        f"- LLM calls total / avg per sample: {aggregate.get('total_llm_calls', 0)} / {aggregate.get('avg_llm_calls_per_sample')}",
        f"- LLM call split actor/critic/tool-planning: "
        f"{aggregate.get('actor_calls', 0)}/{aggregate.get('critic_calls', 0)}/{aggregate.get('tool_planning_calls', 0)}",
        f"- Prompt/completion chars: {aggregate.get('prompt_chars', 0)} / {aggregate.get('completion_chars', 0)}",
        f"- Final status: {final_status_text}",
        "",
        "| idx | dataset_id | contract | partition | compile | ABI | test | abi_extra | slither classes | gas | llm calls | status | guard/stop | failure |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        slither_classes = (
            f"B{row.get('slither_security_blocking_count', 0)}/"
            f"R{row.get('slither_security_review_count', 0)}/"
            f"S{row.get('slither_spec_conflict_count', 0)}/"
            f"Q{row.get('slither_quality_warning_count', 0)}/"
            f"A{row.get('slither_acceptable_pattern_count', 0)}"
        )
        lines.append(
            "| {sample_idx} | {dataset_id} | {contract_name} | {partition} | {compile_success} | "
            "{abi_success} | {test_success} | {abi_extra} | {slither_classes} | {max_gas_value} | "
            "{total_llm_calls} | {final_status} | {guard_or_stop} | {failure_reason_short} |".format(
                sample_idx=row.get("sample_idx", ""),
                dataset_id=row.get("dataset_id", ""),
                contract_name=row.get("contract_name", ""),
                partition=row.get("partition", ""),
                compile_success=row.get("compile_success", ""),
                abi_success=row.get("abi_success", ""),
                test_success=row.get("test_success", ""),
                abi_extra=(row.get("abi_extra", "") or "").replace("|", "/"),
                slither_classes=slither_classes,
                max_gas_value=row.get("max_gas_value", ""),
                total_llm_calls=row.get("total_llm_calls", ""),
                final_status=row.get("final_status", ""),
                guard_or_stop=(row.get("degradation_guard") or row.get("stop_reason") or "").replace("|", "/"),
                failure_reason_short=(row.get("failure_reason_short", "") or "").replace("|", "/"),
            )
        )

    if round_comparison and round_comparison.get("rows"):
        round_labels = " -> ".join(entry["label"] for entry in round_comparison.get("rounds", []))
        lines.extend(
            [
                "",
                "## Round Comparison",
                "",
                f"Rounds: {round_labels}",
                "",
                "| idx | contract | compile | ABI | test | slither | gas | llm calls | final status | final failure |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in round_comparison["rows"]:
            lines.append(
                "| {sample_idx} | {contract_name} | {compile_transition} | {abi_transition} | {test_transition} | "
                "{slither_transition} | {gas_transition} | {llm_calls_transition} | {final_status} | {final_failure} |".format(
                    sample_idx=row.get("sample_idx", ""),
                    contract_name=row.get("contract_name", ""),
                    compile_transition=row.get("compile_transition", ""),
                    abi_transition=row.get("abi_transition", ""),
                    test_transition=row.get("test_transition", ""),
                    slither_transition=row.get("slither_transition", ""),
                    gas_transition=row.get("gas_transition", ""),
                    llm_calls_transition=row.get("llm_calls_transition", ""),
                    final_status=row.get("final_status", ""),
                    final_failure=(row.get("final_failure", "") or "").replace("|", "/"),
                )
            )

    for comparison in baseline_comparisons or []:
        lines.extend(
            [
                "",
                "## Baseline Comparison",
                "",
                f"Baseline: {comparison.get('baseline_dir')}",
                f"Final: {comparison.get('final_dir')}",
                f"Counts: {comparison.get('counts')}",
                "",
                "| idx | contract | baseline status | final status | compile | ABI | test | abi extra | slither | gas | llm calls | label |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in comparison.get("rows", []):
            lines.append(
                "| {sample_idx} | {contract_name} | {baseline_status} | {final_status} | "
                "{compile_change} | {abi_change} | {test_change} | {abi_extra_change} | "
                "{slither_change} | {gas_change} | {llm_calls_change} | {improvement_label} |".format(
                    sample_idx=row.get("sample_idx", ""),
                    contract_name=row.get("contract_name", ""),
                    baseline_status=row.get("baseline_status", ""),
                    final_status=row.get("final_status", ""),
                    compile_change=row.get("compile_change", ""),
                    abi_change=row.get("abi_change", ""),
                    test_change=row.get("test_change", ""),
                    abi_extra_change=(row.get("abi_extra_change", "") or "").replace("|", "/"),
                    slither_change=row.get("slither_change", ""),
                    gas_change=row.get("gas_change", ""),
                    llm_calls_change=row.get("llm_calls_change", ""),
                    improvement_label=row.get("improvement_label", ""),
                )
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).resolve()
    results_dir = Path(args.results_dir).resolve()
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")
    if not results_dir.exists():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    output_prefix = (
        Path(args.output_prefix).resolve()
        if args.output_prefix
        else results_dir / "summary"
    )

    dataset_rows = load_dataset_rows(dataset_path)
    result_records = load_results(results_dir)
    rows = [
        build_row(sample, result_records.get(int(sample["sample_idx"])), args.instruction_chars)
        for sample in dataset_rows
    ]
    aggregate = compute_aggregate(rows)
    comparison_dirs = discover_comparison_dirs(results_dir, args.compare_results_dir)
    round_comparison = None
    if len(comparison_dirs) > 1:
        round_comparison = build_round_comparison(dataset_rows, comparison_dirs, args.instruction_chars)
    baseline_comparisons = []
    for baseline_value in args.baseline_results_dir:
        baseline_dir = Path(baseline_value).resolve()
        if not baseline_dir.exists() or not baseline_dir.is_dir():
            raise FileNotFoundError(f"Baseline results directory not found: {baseline_dir}")
        baseline_comparisons.append(
            build_baseline_comparison(dataset_rows, baseline_dir, results_dir, args.instruction_chars)
        )

    payload = {
        "dataset": str(dataset_path),
        "results_dir": str(results_dir),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "aggregate": aggregate,
        "rows": rows,
    }
    if round_comparison is not None:
        payload["round_comparison"] = round_comparison
    if baseline_comparisons:
        payload["baseline_comparisons"] = baseline_comparisons

    write_json(output_prefix.with_suffix(".json"), payload)
    write_csv(output_prefix.with_suffix(".csv"), rows)
    write_markdown(output_prefix.with_suffix(".md"), rows, aggregate, round_comparison, baseline_comparisons)
    comparison_csv_path = output_prefix.with_name(output_prefix.name + "_round_comparison").with_suffix(".csv")
    if round_comparison is not None:
        write_comparison_csv(comparison_csv_path, round_comparison["rows"])
    baseline_csv_paths = []
    for index, comparison in enumerate(baseline_comparisons, start=1):
        suffix = "_baseline_comparison" if len(baseline_comparisons) == 1 else f"_baseline_comparison_{index}"
        baseline_csv_path = output_prefix.with_name(output_prefix.name + suffix).with_suffix(".csv")
        write_baseline_comparison_csv(baseline_csv_path, comparison["rows"])
        baseline_csv_paths.append(baseline_csv_path)

    print(f"Wrote {output_prefix.with_suffix('.json')}")
    print(f"Wrote {output_prefix.with_suffix('.csv')}")
    print(f"Wrote {output_prefix.with_suffix('.md')}")
    if round_comparison is not None:
        print(f"Wrote {comparison_csv_path}")
    for baseline_csv_path in baseline_csv_paths:
        print(f"Wrote {baseline_csv_path}")
    print(json.dumps(aggregate, ensure_ascii=False))


if __name__ == "__main__":
    main()
