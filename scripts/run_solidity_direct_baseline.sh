#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/run_solidity_direct_baseline.sh

Runs one direct-generation baseline round for Qwen and DeepSeek:
  prompt -> Solidity code -> compile/ABI/test/Slither/gas -> summary

Environment overrides:
  DATA_PATH=data/solidity_fsm_testable_10.json
  EXPERIMENT=fsm_testable10_direct_baseline
  QWEN_MODEL=qwen2.5-14b-instruct
  DEEPSEEK_MODEL=deepseek-chat
  PYTHON_BIN=python
  OVERRIDE=1
  DEBUG=1
  INCLUDE_HARD_CONSTRAINTS=1
  RUN_QWEN=0
  RUN_DEEPSEEK=0

Required:
  DASHSCOPE_API_KEY or QWEN_API_KEY for Qwen
  DEEPSEEK_API_KEY for DeepSeek

Outputs:
  solidity_<QWEN_MODEL>/direct_generation_<EXPERIMENT>/summary.*
  solidity_<DEEPSEEK_MODEL>/direct_generation_<EXPERIMENT>/summary.*
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

data_path="${DATA_PATH:-data/solidity_fsm_testable_10.json}"
experiment="${EXPERIMENT:-fsm_testable10_direct_baseline}"
qwen_model="${QWEN_MODEL:-qwen2.5-14b-instruct}"
deepseek_model="${DEEPSEEK_MODEL:-deepseek-chat}"
python_bin="${PYTHON_BIN:-python}"
override="${OVERRIDE:-1}"
debug="${DEBUG:-0}"
include_hard_constraints="${INCLUDE_HARD_CONSTRAINTS:-0}"
run_qwen="${RUN_QWEN:-1}"
run_deepseek="${RUN_DEEPSEEK:-1}"

if [[ -d "$HOME/.foundry/bin" ]]; then
  export PATH="$HOME/.foundry/bin:$PATH"
fi

if [[ ! -f "$data_path" ]]; then
  echo "ERROR: dataset not found: $data_path" >&2
  exit 2
fi

if ! command -v forge >/dev/null 2>&1; then
  echo "ERROR: forge is not available in PATH. Run: export PATH=\"\$HOME/.foundry/bin:\$PATH\"" >&2
  exit 2
fi

run_one() {
  local provider="$1"
  local model="$2"
  local output_dir="solidity_${model}/direct_generation_${experiment}"

  if [[ "$provider" == "qwen" ]]; then
    if [[ -z "${DASHSCOPE_API_KEY:-}" && -z "${QWEN_API_KEY:-}" ]]; then
      echo "ERROR: set DASHSCOPE_API_KEY or QWEN_API_KEY before running Qwen baseline." >&2
      exit 2
    fi
  elif [[ "$provider" == "deepseek" ]]; then
    if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
      echo "ERROR: set DEEPSEEK_API_KEY before running DeepSeek baseline." >&2
      exit 2
    fi
  fi

  local args=(
    scripts/run_solidity_direct_baseline.py
    --provider "$provider"
    --model "$model"
    --data_path "$data_path"
    --suffix "_${experiment}"
  )

  if [[ "$override" =~ ^(1|true|yes|on)$ ]]; then
    args+=(--override)
  fi
  if [[ "$debug" =~ ^(1|true|yes|on)$ ]]; then
    args+=(--debug)
  fi
  if [[ "$include_hard_constraints" =~ ^(1|true|yes|on)$ ]]; then
    args+=(--include-hard-constraints)
  fi

  echo
  echo "=== Direct-generation baseline: ${provider} / ${model} ==="
  echo "output: ${output_dir}"
  "$python_bin" "${args[@]}"

  echo
  echo "=== Summarizing ${provider} / ${model} direct baseline ==="
  "$python_bin" scripts/summarize_solidity_results.py \
    --dataset "$data_path" \
    --results-dir "$output_dir" \
    --output-prefix "$output_dir/summary"

  echo "[ok] Summary written under ${output_dir}/summary.*"
}

echo "Direct baseline config:"
echo "  data_path:                $data_path"
echo "  experiment:               $experiment"
echo "  qwen_model:               $qwen_model"
echo "  deepseek_model:           $deepseek_model"
echo "  override:                 $override"
echo "  debug:                    $debug"
echo "  include_hard_constraints: $include_hard_constraints"

if [[ "$run_qwen" =~ ^(1|true|yes|on)$ ]]; then
  run_one qwen "$qwen_model"
fi

if [[ "$run_deepseek" =~ ^(1|true|yes|on)$ ]]; then
  run_one deepseek "$deepseek_model"
fi

echo
echo "[ok] Direct-generation baseline run completed."
