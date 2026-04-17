#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backends import create_execution_backend
from scripts.run_solidity_direct_baseline import build_structured_feedback
from util import extract_code, get_code_before, load_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-evaluate existing Solidity result JSON files without calling an LLM. "
            "Useful after fixing forge/slither/solc environment issues."
        )
    )
    parser.add_argument("--dataset", required=True, help="Dataset JSON used for the original run.")
    parser.add_argument("--results-dir", required=True, help="Existing result directory containing 0.json, 1.json, ...")
    parser.add_argument(
        "--output-dir",
        help="Directory for re-evaluated records. Defaults to <results-dir>_reeval.",
    )
    parser.add_argument(
        "--action-key",
        default="action",
        help="Result JSON field containing the Solidity candidate to evaluate.",
    )
    parser.add_argument("--override", action="store_true", help="Overwrite files in --output-dir.")
    parser.add_argument("--debug", action="store_true", help="Only re-evaluate the first available sample.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir) if args.output_dir else Path(str(results_dir) + "_reeval")
    output_dir.mkdir(parents=True, exist_ok=True)

    data, _, _ = load_data("solidity", data_path=args.dataset)
    metadata = {
        "source_results_dir": str(results_dir),
        "dataset": args.dataset,
        "action_key": args.action_key,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "note": "Re-evaluation only; no LLM calls were made.",
    }
    (output_dir / "run_config.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    count = 0
    for sample_idx, sample in tqdm(list(enumerate(data)), total=len(data)):
        input_path = results_dir / f"{sample_idx}.json"
        output_path = output_dir / f"{sample_idx}.json"
        if not input_path.exists():
            continue
        if output_path.exists() and not args.override:
            continue

        record = json.loads(input_path.read_text(encoding="utf-8"))
        action = record.get(args.action_key)
        if not isinstance(action, str) or not action.strip():
            raise ValueError(f"{input_path} does not contain a non-empty {args.action_key!r} field")

        backend = create_execution_backend(
            task="solidity",
            programming_language=sample.get("language", "solidity"),
            sample_metadata=sample,
        )
        observation = backend.evaluate(extract_code(action), code_before=get_code_before(sample))
        metrics = observation.as_dict()

        updated = dict(record)
        updated["reevaluated_from"] = str(input_path)
        updated["reevaluated_at"] = datetime.now().isoformat(timespec="seconds")
        updated["execution_observation"] = observation.to_text()
        updated["execution_metrics"] = metrics
        updated["structured_feedback"] = build_structured_feedback(metrics, sample)
        updated["llm_call_stats"] = {
            "total_calls": 0,
            "actor_calls": 0,
            "critic_calls": 0,
            "tool_planning_calls": 0,
            "prompt_chars": 0,
            "completion_chars": 0,
            "max_tokens_requested": 0,
        }
        output_path.write_text(json.dumps(updated, indent=4, ensure_ascii=False), encoding="utf-8")

        count += 1
        if args.debug:
            break

    print(f"Re-evaluated {count} sample(s) into {output_dir}")


if __name__ == "__main__":
    main()
