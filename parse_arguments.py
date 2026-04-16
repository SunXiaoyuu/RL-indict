import argparse

parser = argparse.ArgumentParser(description="Run INDICT generation process")

# Data configuration 
parser.add_argument(
    "--task", type=str, default='mitre', 
    choices={'mitre', 'instruct', 'autocomplete', 'promptinject', 'frr', 'interpreter', 'cvs', 'solidity'}, 
    help="Type of generation tasks to be run",
)
parser.add_argument(
    "--prev_trial", type=str, default=None, 
    help="Path to the last generation iteration",
)
parser.add_argument(
    "--data_path", type=str, default=None,
    help="Optional dataset JSON path. If omitted, the task default in util.py is used.",
)

# Agent configuration
parser.add_argument(
    "--strategy", type=str, default='indict_llama', 
    choices={'indict_llama', 'indict_commandr'}, 
    help="Generation strategy",
)
parser.add_argument(
    "--model", type=str, default='llama3-8b-instruct', 
    help='Base model to initialize llm agents',
)
parser.add_argument(
    "--provider",
    type=str,
    default="auto",
    choices={"auto", "qwen", "openai", "deepseek"},
    help=(
        "LLM API provider. Use auto to infer from --model; qwen uses DashScope/Qwen "
        "openai uses OPENAI_API_KEY, and deepseek uses DEEPSEEK_API_KEY."
    ),
)
parser.add_argument(
    "--cost_profile",
    type=str,
    default="full",
    choices={"full", "gated", "cheap"},
    help=(
        "Runtime cost profile. full preserves the original all-critic flow; gated "
        "routes critics by structured defects; cheap uses compact feedback, early "
        "stop, failure-only posthoc, and disables LLM tool calls."
    ),
)
parser.add_argument(
    "--solidity_prompt_mode",
    type=str,
    default="normalized",
    choices={"normalized", "light", "raw"},
    help=(
        "How strictly Solidity prompts are normalized. normalized uses the full "
        "benchmark ABI/spec constraints; light keeps only broad internal constraints; "
        "raw sends the user requirement without added Solidity hard constraints."
    ),
)

# Generation configuration 
parser.add_argument(
    "--debug", action='store_true', 
    help="Enable this to debug with a single sample",
)
parser.add_argument(
    "--override", action='store_true', 
    help="Enable this to override past generation output",
)
parser.add_argument(
    "--suffix", type=str, default='', 
    help='Suffix to output path',
)
