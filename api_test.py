#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from qwen_client import DEFAULT_QWEN_MODEL, QwenClient, QwenClientError, get_qwen_api_key, mask_secret


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Qwen/DashScope connectivity.")
    parser.add_argument("--model", default=DEFAULT_QWEN_MODEL, help="Qwen model name to test.")
    parser.add_argument("--prompt", default="Reply with exactly: ok", help="Short prompt used for the check.")
    parser.add_argument("--max-tokens", type=int, default=16, help="Maximum tokens for the test response.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = get_qwen_api_key()
    print(f"Model: {args.model}")
    print(f"API key: {mask_secret(api_key)}")

    try:
        client = QwenClient(model_name=args.model, api_key=api_key)
        response = client.query(args.prompt, max_tokens=args.max_tokens)
    except QwenClientError as exc:
        print(f"Qwen check failed: {exc}")
        return 1

    print("Qwen check succeeded.")
    print(f"Response: {response}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
