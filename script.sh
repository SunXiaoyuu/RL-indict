#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./script.sh <task> [rounds]

Environment overrides:
  MODEL=qwen2.5-14b-instruct
  STRATEGY=indict_llama
  DATA_PATH=data/solidity_fsm_testable_main_5.json
  DEBUG=1
  OVERRIDE=1
  SUFFIX_PREFIX=_fsm_main5
  PYTHON_BIN=python

Required:
  DASHSCOPE_API_KEY or QWEN_API_KEY
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

task="${1:-}"
rounds="${2:-${ROUNDS:-3}}"
model="${MODEL:-qwen2.5-14b-instruct}"
strategy="${STRATEGY:-indict_llama}"
python_bin="${PYTHON_BIN:-python}"
suffix_prefix="${SUFFIX_PREFIX:-}"

if [[ -z "$task" ]]; then
  usage
  exit 2
fi

if ! [[ "$rounds" =~ ^[0-9]+$ ]] || [[ "$rounds" -lt 1 ]]; then
  echo "ERROR: rounds must be a positive integer." >&2
  exit 2
fi

if [[ -z "${DASHSCOPE_API_KEY:-}" && -z "${QWEN_API_KEY:-}" ]]; then
  echo "ERROR: set DASHSCOPE_API_KEY or QWEN_API_KEY before running generation." >&2
  exit 2
fi

output_dir="${task}_${model}"

common_args=(
  run.py
  --model "$model"
  --task "$task"
  --strategy "$strategy"
)

if [[ -n "${DATA_PATH:-}" ]]; then
  common_args+=(--data_path "$DATA_PATH")
fi

if [[ "${DEBUG:-0}" =~ ^(1|true|yes|on)$ ]]; then
  common_args+=(--debug)
fi

if [[ "${OVERRIDE:-0}" =~ ^(1|true|yes|on)$ ]]; then
  common_args+=(--override)
fi

echo "Experiment config:"
echo "  task:      $task"
echo "  model:     $model"
echo "  strategy:  $strategy"
echo "  rounds:    $rounds"
echo "  output:    $output_dir"
if [[ -n "${DATA_PATH:-}" ]]; then
  echo "  data_path: $DATA_PATH"
fi

for ((round = 1; round <= rounds; round++)); do
  suffix="${suffix_prefix}_round${round}"
  round_args=("${common_args[@]}" --suffix "$suffix")

  echo
  echo "=== Generation round $round/$rounds ==="

  if [[ "$round" -gt 1 ]]; then
    prev_trial_path="${output_dir}/${strategy}${suffix_prefix}_round$((round - 1))"
    round_args+=(--prev_trial "$prev_trial_path")
    echo "Previous trial: $prev_trial_path"
  fi

  "$python_bin" "${round_args[@]}"
  echo "[ok] Round $round completed"
done

echo
echo "All rounds completed."
echo "Final results are under: $output_dir"
