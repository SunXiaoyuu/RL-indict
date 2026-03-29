#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


CONTRACT_PATTERN = re.compile(r"\b(contract|library|interface|abstract\s+contract)\s+([A-Za-z_][A-Za-z0-9_]*)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert FSM-SCG whole-contract JSONL samples into the project's Solidity dataset format."
    )
    parser.add_argument(
        "--input",
        default="FSM-Fine-Tuning-Dataset/requirement_fsm_code.jsonl",
        help="Path to the FSM-SCG JSONL dataset.",
    )
    parser.add_argument(
        "--output",
        default="data/solidity_fsm_all.json",
        help="Path to the converted JSON output.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of samples to keep. 0 means no limit.",
    )
    parser.add_argument(
        "--version-prefix",
        default="",
        help="Keep only records whose Solidity version starts with this prefix, e.g. 0.8.",
    )
    parser.add_argument(
        "--with-fsm",
        action="store_true",
        help="Append the FSM text to the generation instruction.",
    )
    return parser.parse_args()


def infer_contract_name(code: str) -> str:
    match = CONTRACT_PATTERN.search(code)
    if match:
        return match.group(2)
    return "GeneratedContract"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def difficulty_from_code(code: str) -> str:
    line_count = len(code.splitlines())
    if line_count <= 80:
        return "easy"
    if line_count <= 180:
        return "medium"
    return "hard"


def build_instruction(user_requirement: str, version: str, fsm_text: str, include_fsm: bool) -> str:
    lines = [
        f"Write a complete Solidity smart contract that satisfies the following user requirement. Use Solidity version {version}.",
        "",
        user_requirement.strip(),
        "",
        "Requirements:",
        "1. Return a single complete Solidity contract, library, or interface as appropriate.",
        "2. Return only the Solidity code in a single ```solidity``` block.",
        "3. Do not include explanations outside the code block.",
    ]
    if include_fsm and fsm_text.strip():
        lines.extend(
            [
                "",
                "You may use the following finite state machine specification as additional guidance:",
                "```json",
                fsm_text.strip(),
                "```",
            ]
        )
    return "\n".join(lines)


def convert_record(record: dict[str, Any], sample_id: int, include_fsm: bool) -> dict[str, Any]:
    user_requirement = normalize_text(record.get("user_requirement"))
    code = normalize_text(record.get("code"))
    version = normalize_text(record.get("version")) or "0.8.0"
    fsm_text = normalize_text(record.get("FSM"))
    contract_name = infer_contract_name(code)

    sample = {
        "id": sample_id,
        "contract_name": contract_name,
        "category": "fsm_scg",
        "difficulty": difficulty_from_code(code),
        "instruction": build_instruction(user_requirement, version, fsm_text, include_fsm),
        "language": "solidity",
        "source_relpath": "src/Generated.sol",
        "dataset_source": "FSM-SCG",
        "version": version,
        "reference_code": code,
    }
    if fsm_text:
        sample["reference_fsm"] = fsm_text
    return sample


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Dataset not found: {input_path}")

    version_counter: Counter[str] = Counter()
    sample_count = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as sink:
        sink.write("[\n")
        first_written = False
        for line in source:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            version = normalize_text(record.get("version"))
            if args.version_prefix and not version.startswith(args.version_prefix):
                continue
            sample = convert_record(record, sample_count, args.with_fsm)
            if first_written:
                sink.write(",\n")
            sink.write(json.dumps(sample, ensure_ascii=False, indent=2))
            first_written = True
            version_counter[version] += 1
            sample_count += 1
            if args.limit and sample_count >= args.limit:
                break
        sink.write("\n]\n")

    print(f"Wrote {sample_count} samples to {output_path}")
    print("Top versions:")
    for version, count in version_counter.most_common(10):
        print(f"  {version}: {count}")


if __name__ == "__main__":
    main()
