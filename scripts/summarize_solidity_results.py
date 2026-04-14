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
                "max_gas_value": None,
                "degradation_guard": None,
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
            "max_gas_value": metrics.get("max_gas_value"),
            "degradation_guard": result_record.get("degradation_guard"),
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
        "max_gas_value",
        "degradation_guard",
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
        "status_transition",
        "final_status",
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
        f"- Final status: {final_status_text}",
        "",
        "| idx | dataset_id | contract | partition | compile | ABI | test | vulns | gas | status | guard | failure |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {sample_idx} | {dataset_id} | {contract_name} | {partition} | {compile_success} | "
            "{abi_success} | {test_success} | {vulnerability_count} | {max_gas_value} | {final_status} | {degradation_guard} | {failure_reason_short} |".format(
                sample_idx=row.get("sample_idx", ""),
                dataset_id=row.get("dataset_id", ""),
                contract_name=row.get("contract_name", ""),
                partition=row.get("partition", ""),
                compile_success=row.get("compile_success", ""),
                abi_success=row.get("abi_success", ""),
                test_success=row.get("test_success", ""),
                vulnerability_count=row.get("vulnerability_count", ""),
                max_gas_value=row.get("max_gas_value", ""),
                final_status=row.get("final_status", ""),
                degradation_guard=row.get("degradation_guard", "") or "",
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
                "| idx | contract | compile | ABI | test | slither | gas | final status | final failure |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in round_comparison["rows"]:
            lines.append(
                "| {sample_idx} | {contract_name} | {compile_transition} | {abi_transition} | {test_transition} | "
                "{slither_transition} | {gas_transition} | {final_status} | {final_failure} |".format(
                    sample_idx=row.get("sample_idx", ""),
                    contract_name=row.get("contract_name", ""),
                    compile_transition=row.get("compile_transition", ""),
                    abi_transition=row.get("abi_transition", ""),
                    test_transition=row.get("test_transition", ""),
                    slither_transition=row.get("slither_transition", ""),
                    gas_transition=row.get("gas_transition", ""),
                    final_status=row.get("final_status", ""),
                    final_failure=(row.get("final_failure", "") or "").replace("|", "/"),
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

    payload = {
        "dataset": str(dataset_path),
        "results_dir": str(results_dir),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "aggregate": aggregate,
        "rows": rows,
    }
    if round_comparison is not None:
        payload["round_comparison"] = round_comparison

    write_json(output_prefix.with_suffix(".json"), payload)
    write_csv(output_prefix.with_suffix(".csv"), rows)
    write_markdown(output_prefix.with_suffix(".md"), rows, aggregate, round_comparison)
    comparison_csv_path = output_prefix.with_name(output_prefix.name + "_round_comparison").with_suffix(".csv")
    if round_comparison is not None:
        write_comparison_csv(comparison_csv_path, round_comparison["rows"])

    print(f"Wrote {output_prefix.with_suffix('.json')}")
    print(f"Wrote {output_prefix.with_suffix('.csv')}")
    print(f"Wrote {output_prefix.with_suffix('.md')}")
    if round_comparison is not None:
        print(f"Wrote {comparison_csv_path}")
    print(json.dumps(aggregate, ensure_ascii=False))


if __name__ == "__main__":
    main()
