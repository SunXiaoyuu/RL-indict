#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_PREDICTION_FIELDS = [
    "action",
    "output",
    "response",
    "completion",
    "generated_code",
    "final_output",
    "code",
    "text",
]

CODE_BLOCK_PATTERN = re.compile(r"```(?:solidity|sol|[a-zA-Z0-9_+-]+)?\s*(.*?)```", re.DOTALL)
GAS_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9])(\d[\d,]*)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate generated Solidity code with compile, test, Slither, and gas metrics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Manifest example:
[
  {
    "id": 0,
    "source_relpath": "src/Generated.sol",
    "test_relpath": "test/Generated.t.sol",
    "project_template_dir": "benchmarks/foundry_erc20",
    "test_code": "pragma solidity ^0.8.20; ...",
    "compile_command": "forge build",
    "test_command": "forge test --match-path {test_relpath} -vv",
    "gas_command": "forge test --match-path {test_relpath} --gas-report",
    "slither_target": "{source_relpath}"
  }
]

Prediction inputs supported:
- INDICT output directory with files like 0.json, 1.json, ... and the generated code in `action`
- A JSON/JSONL file with one record per sample
- A directory of raw `.sol` files

Typical usage:
python scripts/evaluate_solidity.py ^
  --manifest data/solidity_eval_manifest.json ^
  --predictions instruct_qwen2.5-14b-instruct/indict_llama_round3 ^
  --output reports/solidity_eval.json
""",
    )
    parser.add_argument("--manifest", required=True, help="Path to the Solidity evaluation manifest (JSON or JSONL).")
    parser.add_argument("--predictions", required=True, help="Path to predictions: directory, JSON, or JSONL.")
    parser.add_argument("--output", required=True, help="Where to write the aggregated evaluation report JSON.")
    parser.add_argument(
        "--workspace-root",
        default=".solidity_eval_work",
        help="Directory used for per-sample temporary projects.",
    )
    parser.add_argument(
        "--prediction-fields",
        nargs="+",
        default=DEFAULT_PREDICTION_FIELDS,
        help="Fields to search in prediction records when extracting generated code.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Timeout in seconds applied to compile/test/gas/slither commands.",
    )
    parser.add_argument(
        "--keep-workdirs",
        action="store_true",
        help="Keep per-sample work directories for debugging.",
    )
    parser.add_argument(
        "--fail-on-missing-prediction",
        action="store_true",
        help="Stop immediately if any sample in the manifest has no matching prediction.",
    )
    return parser.parse_args()


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() == ".jsonl":
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
        return records
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "samples" in data and isinstance(data["samples"], list):
        return data["samples"]
    if isinstance(data, dict):
        return [data]
    raise ValueError(f"Unsupported JSON structure in {path}")


def normalize_id(value: Any) -> str:
    if value is None:
        raise ValueError("Sample id cannot be None")
    return str(value)


def sample_id_from_record(record: dict[str, Any], fallback: str | None = None) -> str:
    for key in ("sample_idx", "id", "prediction_id", "idx", "name"):
        if key in record and record[key] is not None:
            return normalize_id(record[key])
    if fallback is not None:
        return normalize_id(fallback)
    raise ValueError(f"Unable to infer sample id from record: {record}")


def load_manifest(path: Path) -> list[dict[str, Any]]:
    records = load_records(path)
    manifest = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Manifest entry #{index} must be a JSON object")
        entry = dict(record)
        entry["_sample_id"] = sample_id_from_record(entry, fallback=str(index))
        manifest.append(entry)
    return manifest


def load_predictions(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Predictions path not found: {path}")

    predictions: dict[str, Any] = {}
    if path.is_dir():
        for child in sorted(path.iterdir()):
            if child.is_dir():
                continue
            if child.suffix.lower() == ".json":
                record = json.loads(child.read_text(encoding="utf-8"))
                prediction_id = sample_id_from_record(record, fallback=child.stem)
                predictions[prediction_id] = record
            elif child.suffix.lower() == ".jsonl":
                for idx, record in enumerate(load_records(child)):
                    prediction_id = sample_id_from_record(record, fallback=f"{child.stem}-{idx}")
                    predictions[prediction_id] = record
            elif child.suffix.lower() == ".sol":
                predictions[child.stem] = {"id": child.stem, "code": child.read_text(encoding="utf-8")}
        return predictions

    records = load_records(path)
    for index, record in enumerate(records):
        if isinstance(record, dict):
            prediction_id = sample_id_from_record(record, fallback=str(index))
            predictions[prediction_id] = record
        elif isinstance(record, str):
            predictions[str(index)] = {"id": index, "code": record}
        else:
            raise ValueError(f"Unsupported prediction record type at index {index}: {type(record)}")
    return predictions


def extract_code_block(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    match = CODE_BLOCK_PATTERN.search(text)
    if not match:
        return text
    return match.group(1).strip()


def extract_prediction_code(record: Any, prediction_fields: list[str]) -> str:
    if isinstance(record, str):
        return extract_code_block(record)
    if not isinstance(record, dict):
        raise ValueError(f"Unsupported prediction record type: {type(record)}")

    for field in prediction_fields:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return extract_code_block(value)

    for value in record.values():
        if isinstance(value, str) and "contract " in value:
            return extract_code_block(value)

    raise ValueError(f"Unable to locate generated code in prediction record with keys: {list(record.keys())}")


def tool_exists(name: str) -> bool:
    return shutil.which(name) is not None


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def maybe_copy_file(source: Path, target: Path) -> None:
    ensure_parent(target)
    shutil.copy2(source, target)


def prepare_workspace(
    sample: dict[str, Any],
    generated_code: str,
    workspace_root: Path,
) -> tuple[Path, dict[str, str]]:
    sample_id = sample["_sample_id"]
    workdir = workspace_root / f"sample_{sample_id}"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    template_dir = sample.get("project_template_dir")
    if template_dir:
        template_path = Path(template_dir).resolve()
        if not template_path.exists():
            raise FileNotFoundError(f"Template directory not found for sample {sample_id}: {template_path}")
        shutil.copytree(template_path, workdir, dirs_exist_ok=True)
    else:
        (workdir / "src").mkdir(exist_ok=True)
        (workdir / "test").mkdir(exist_ok=True)

    for item in sample.get("extra_files", []):
        relpath = item["path"]
        content = item.get("content")
        source_file = item.get("source")
        target = workdir / relpath
        if content is not None:
            write_text(target, content)
        elif source_file is not None:
            maybe_copy_file(Path(source_file).resolve(), target)
        else:
            raise ValueError(f"extra_files entry must include content or source: {item}")

    source_relpath = sample.get("source_relpath", "src/Generated.sol")
    source_path = workdir / source_relpath
    source_text = build_source_text(source_path, sample, generated_code)
    write_text(source_path, source_text)

    test_relpath = sample.get("test_relpath", "test/Generated.t.sol")
    test_path = workdir / test_relpath
    if "test_code" in sample:
        write_text(test_path, sample["test_code"])
    elif "test_file" in sample:
        maybe_copy_file(Path(sample["test_file"]).resolve(), test_path)

    context = {
        "sample_id": sample_id,
        "workdir": str(workdir.resolve()),
        "source_relpath": source_relpath,
        "source_abspath": str(source_path.resolve()),
        "test_relpath": test_relpath,
        "test_abspath": str(test_path.resolve()),
        "slither_target": sample.get("slither_target", source_relpath),
    }
    return workdir, context


def build_source_text(source_path: Path, sample: dict[str, Any], generated_code: str) -> str:
    start_line = sample.get("replace_start_line")
    end_line = sample.get("replace_end_line")
    if start_line is not None and end_line is not None and source_path.exists():
        return replace_line_range(
            source_path=source_path,
            generated_code=generated_code,
            start_line=int(start_line),
            end_line=int(end_line),
        )
    return f"{sample.get('source_prefix', '')}{generated_code}{sample.get('source_suffix', '')}"


def replace_line_range(source_path: Path, generated_code: str, start_line: int, end_line: int) -> str:
    original_lines = source_path.read_text(encoding="utf-8").splitlines(keepends=True)
    if start_line < 1 or end_line < start_line or end_line > len(original_lines):
        raise ValueError(
            f"Invalid replacement range {start_line}-{end_line} for {source_path} with {len(original_lines)} lines."
        )

    replacement = indent_replacement(original_lines[start_line - 1], generated_code)
    if replacement and not replacement.endswith(("\n", "\r")):
        replacement += "\n"

    prefix = "".join(original_lines[: start_line - 1])
    suffix = "".join(original_lines[end_line:])
    return prefix + replacement + suffix


def indent_replacement(original_line: str, generated_code: str) -> str:
    normalized = generated_code.strip("\n")
    if not normalized:
        return ""
    indent = original_line[: len(original_line) - len(original_line.lstrip(" \t"))]
    rendered_lines = normalized.splitlines()
    rendered_lines[0] = f"{indent}{rendered_lines[0].lstrip(' \t')}"
    return "\n".join(rendered_lines)


def shell_quote(path_like: str) -> str:
    return f'"{path_like}"'


def format_command(template: str, context: dict[str, str]) -> str:
    class SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return template.format_map(SafeDict(context))


def run_command(command: str, cwd: Path, timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "success": completed.returncode == 0,
    }


def build_solc_include_flags(cwd: Path, sample: dict[str, Any]) -> str:
    include_paths = [".", "node_modules"]
    include_paths.extend(sample.get("include_paths", []))

    flags = [f"--base-path {shell_quote(str(cwd))}"]
    for include_path in include_paths:
        candidate = (cwd / include_path).resolve() if not Path(include_path).is_absolute() else Path(include_path)
        if candidate.exists():
            flags.append(f"--include-path {shell_quote(str(candidate))}")
    allow_paths = [str(cwd.resolve())]
    flags.append(f"--allow-paths {shell_quote(','.join(allow_paths))}")

    if sample.get("evm_version"):
        flags.append(f"--evm-version {sample['evm_version']}")
    if sample.get("solc_args"):
        flags.append(sample["solc_args"])
    return " ".join(flags)


def build_relative_solc_flags(sample: dict[str, Any]) -> str:
    include_paths = ["."]
    include_paths.extend(sample.get("include_paths", []))

    flags = ["--base-path ."]
    for include_path in include_paths:
        flags.append(f"--include-path {include_path}")
    flags.append("--allow-paths .")

    if sample.get("evm_version"):
        flags.append(f"--evm-version {sample['evm_version']}")
    if sample.get("solc_args"):
        flags.append(sample["solc_args"])
    return " ".join(flags)


def default_compile_command(cwd: Path, sample: dict[str, Any], context: dict[str, str]) -> str:
    if sample.get("compile_command"):
        return format_command(sample["compile_command"], context)
    if tool_exists("forge") and (cwd / "foundry.toml").exists():
        return "forge build"
    include_flags = build_solc_include_flags(cwd, sample)
    return f"solc {include_flags} --abi {shell_quote(context['source_relpath'])}"


def default_test_command(cwd: Path, sample: dict[str, Any], context: dict[str, str]) -> str | None:
    if sample.get("test_command"):
        return format_command(sample["test_command"], context)
    if not tool_exists("forge"):
        return None
    test_path = cwd / context["test_relpath"]
    if test_path.exists():
        return f"forge test --match-path {shell_quote(context['test_relpath'])} -vv"
    return None


def default_gas_command(cwd: Path, sample: dict[str, Any], context: dict[str, str]) -> str | None:
    if sample.get("gas_command"):
        return format_command(sample["gas_command"], context)
    if tool_exists("forge"):
        test_path = cwd / context["test_relpath"]
        if test_path.exists():
            return f"forge test --match-path {shell_quote(context['test_relpath'])} --gas-report"
    include_flags = build_solc_include_flags(cwd, sample)
    return f"solc {include_flags} --gas {shell_quote(context['source_relpath'])}"


def default_slither_command(cwd: Path, sample: dict[str, Any], context: dict[str, str], json_path: Path) -> str | None:
    if sample.get("slither_command"):
        merged = dict(context)
        merged["slither_json"] = str(json_path.resolve())
        return format_command(sample["slither_command"], merged)
    if not tool_exists("slither"):
        return None
    target = context["slither_target"]
    if (cwd / "foundry.toml").exists():
        return (
            f"slither {shell_quote(target)} "
            f"--exclude-dependencies "
            f"--exclude-informational "
            f"--exclude-optimization "
            f"--fail-none "
            f"--json {shell_quote(str(json_path.resolve()))}"
        )
    solc_flags = build_relative_solc_flags(sample).replace('"', '\\"')
    return (
        f"slither {shell_quote(target)} "
        f"--compile-force-framework solc "
        f"--solc-working-dir . "
        f"--solc-args \"{solc_flags}\" "
        f"--exclude-dependencies "
        f"--exclude-informational "
        f"--exclude-optimization "
        f"--fail-none "
        f"--json {shell_quote(str(json_path.resolve()))}"
    )


def parse_solc_gas(output: str) -> int | None:
    max_gas: int | None = None
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "infinite" in stripped.lower():
            continue
        if "=" in stripped:
            tail = stripped.split("=")[-1]
            match = GAS_NUMBER_PATTERN.search(tail)
            if match:
                value = int(match.group(1).replace(",", ""))
                max_gas = value if max_gas is None else max(max_gas, value)
            continue
        if ":" not in stripped:
            continue
        head, tail = stripped.split(":", 1)
        if not head or not tail:
            continue
        match = GAS_NUMBER_PATTERN.search(tail)
        if match:
            value = int(match.group(1).replace(",", ""))
            max_gas = value if max_gas is None else max(max_gas, value)
    return max_gas


def parse_pipe_table(headers: list[str], rows: list[list[str]], key: str) -> list[int]:
    normalized = [header.strip().lower() for header in headers]
    if key not in normalized:
        return []
    target_idx = normalized.index(key)
    values = []
    for row in rows:
        if len(row) <= target_idx:
            continue
        cell = row[target_idx].strip()
        if not cell or not any(ch.isdigit() for ch in cell):
            continue
        match = GAS_NUMBER_PATTERN.search(cell)
        if match:
            values.append(int(match.group(1).replace(",", "")))
    return values


def parse_forge_or_table_gas(output: str) -> int | None:
    rows = []
    for line in output.splitlines():
        if "|" not in line:
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if any(cell for cell in cells):
            rows.append(cells)

    max_gas: int | None = None
    for idx, row in enumerate(rows):
        lowered = [cell.lower() for cell in row]
        if "function name" in lowered:
            headers = row
            data_rows = []
            for next_row in rows[idx + 1 :]:
                if next_row and next_row[0].lower() in {"deployment cost", "function name"}:
                    break
                if all(set(cell) <= {"-"} for cell in next_row if cell):
                    continue
                data_rows.append(next_row)
            for key in ("max", "avg", "median", "min"):
                values = parse_pipe_table(headers, data_rows, key)
                if values:
                    candidate = max(values)
                    max_gas = candidate if max_gas is None else max(max_gas, candidate)
                    break

        if row and row[0].strip().lower() == "deployment cost":
            if idx + 1 < len(rows):
                next_row = rows[idx + 1]
                if next_row and any(ch.isdigit() for ch in next_row[0]):
                    match = GAS_NUMBER_PATTERN.search(next_row[0])
                    if match:
                        value = int(match.group(1).replace(",", ""))
                        max_gas = value if max_gas is None else max(max_gas, value)

    if max_gas is not None:
        return max_gas
    return parse_solc_gas(output)


def parse_slither_count(json_path: Path) -> tuple[int | None, dict[str, int]]:
    if not json_path.exists():
        return None, {}
    data = json.loads(json_path.read_text(encoding="utf-8"))
    detectors = data.get("results", {}).get("detectors", [])
    severity_counts: dict[str, int] = {}
    for detector in detectors:
        impact = str(detector.get("impact", "unknown")).lower()
        severity_counts[impact] = severity_counts.get(impact, 0) + 1
    return len(detectors), severity_counts


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(samples)
    compile_successes = sum(1 for sample in samples if sample.get("compile_success") is True)
    tested_samples = sum(1 for sample in samples if sample.get("test_pass") is not None)
    test_passes = sum(1 for sample in samples if sample.get("test_pass") is True)
    scanned_samples = sum(1 for sample in samples if sample.get("vulnerability_count") is not None)
    vulnerability_total = sum(sample.get("vulnerability_count") or 0 for sample in samples)
    gas_values = [sample["max_gas_value"] for sample in samples if sample.get("max_gas_value") is not None]
    return {
        "num_samples": total,
        "compile_successes": compile_successes,
        "compile_success_rate": (compile_successes / total) if total else None,
        "tested_samples": tested_samples,
        "test_passes": test_passes,
        "test_pass_rate_overall": (test_passes / total) if total and tested_samples else None,
        "test_pass_rate_tested_only": (test_passes / tested_samples) if tested_samples else None,
        "scanned_samples": scanned_samples,
        "total_vulnerabilities": vulnerability_total,
        "avg_vulnerabilities_per_scanned_sample": (vulnerability_total / scanned_samples) if scanned_samples else None,
        "gas_measured_samples": len(gas_values),
        "max_gas_value": max(gas_values) if gas_values else None,
    }


def evaluate_sample(
    sample: dict[str, Any],
    prediction: Any,
    args: argparse.Namespace,
    workspace_root: Path,
) -> dict[str, Any]:
    sample_id = sample["_sample_id"]
    result: dict[str, Any] = {
        "id": sample_id,
        "compile_success": False,
        "test_pass": None,
        "vulnerability_count": None,
        "vulnerability_severity_counts": {},
        "max_gas_value": None,
        "errors": [],
    }

    try:
        generated_code = extract_prediction_code(prediction, args.prediction_fields)
        workdir, context = prepare_workspace(sample, generated_code, workspace_root)
        if args.keep_workdirs:
            result["workspace"] = str(workdir.resolve())

        compile_command = default_compile_command(workdir, sample, context)
        compile_run = run_command(compile_command, workdir, args.timeout)
        result["compile_command"] = compile_command
        result["compile_returncode"] = compile_run["returncode"]
        result["compile_stdout"] = compile_run["stdout"]
        result["compile_stderr"] = compile_run["stderr"]
        result["compile_success"] = compile_run["success"]

        test_command = default_test_command(workdir, sample, context)
        if test_command is not None:
            test_run = run_command(test_command, workdir, args.timeout)
            result["test_command"] = test_command
            result["test_returncode"] = test_run["returncode"]
            result["test_stdout"] = test_run["stdout"]
            result["test_stderr"] = test_run["stderr"]
            result["test_pass"] = test_run["success"]

        gas_command = default_gas_command(workdir, sample, context)
        if gas_command is not None:
            gas_run = run_command(gas_command, workdir, args.timeout)
            result["gas_command"] = gas_command
            result["gas_returncode"] = gas_run["returncode"]
            result["gas_stdout"] = gas_run["stdout"]
            result["gas_stderr"] = gas_run["stderr"]
            if gas_run["success"]:
                result["max_gas_value"] = parse_forge_or_table_gas(gas_run["stdout"] + "\n" + gas_run["stderr"])

        slither_json = workdir / "slither-result.json"
        slither_command = default_slither_command(workdir, sample, context, slither_json)
        if slither_command is not None:
            slither_run = run_command(slither_command, workdir, args.timeout)
            result["slither_command"] = slither_command
            result["slither_returncode"] = slither_run["returncode"]
            result["slither_stdout"] = slither_run["stdout"]
            result["slither_stderr"] = slither_run["stderr"]
            count, severity_counts = parse_slither_count(slither_json)
            result["vulnerability_count"] = count
            result["vulnerability_severity_counts"] = severity_counts

    except subprocess.TimeoutExpired as exc:
        result["errors"].append(f"timeout: {exc}")
    except Exception as exc:
        result["errors"].append(str(exc))
    finally:
        if not args.keep_workdirs:
            workdir = workspace_root / f"sample_{sample_id}"
            if workdir.exists():
                shutil.rmtree(workdir, ignore_errors=True)

    return result


def main() -> None:
    args = parse_args()
    manifest = load_manifest(Path(args.manifest).resolve())
    predictions = load_predictions(Path(args.predictions).resolve())
    workspace_root = Path(args.workspace_root).resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)

    sample_results = []
    for sample in manifest:
        prediction_id = normalize_id(sample.get("prediction_id", sample["_sample_id"]))
        if prediction_id not in predictions:
            message = f"Missing prediction for sample {sample['_sample_id']} (expected prediction id {prediction_id})"
            if args.fail_on_missing_prediction:
                raise KeyError(message)
            sample_results.append(
                {
                    "id": sample["_sample_id"],
                    "compile_success": False,
                    "test_pass": None,
                    "vulnerability_count": None,
                    "vulnerability_severity_counts": {},
                    "max_gas_value": None,
                    "errors": [message],
                }
            )
            continue

        sample_result = evaluate_sample(sample, predictions[prediction_id], args, workspace_root)
        sample_results.append(sample_result)

    report = {
        "manifest": str(Path(args.manifest).resolve()),
        "predictions": str(Path(args.predictions).resolve()),
        "summary": summarize(sample_results),
        "samples": sample_results,
    }

    output_path = Path(args.output).resolve()
    ensure_parent(output_path)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print(f"Saved report to: {output_path}")


if __name__ == "__main__":
    main()
