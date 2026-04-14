#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from deepseek_client import DEFAULT_DEEPSEEK_MODEL, DeepSeekClient, DeepSeekClientError, get_deepseek_api_key
from openai_client import DEFAULT_OPENAI_MODEL, OpenAIClient, OpenAIClientError, get_openai_api_key
from qwen_client import DEFAULT_QWEN_MODEL, QwenClient, QwenClientError, get_qwen_api_key, mask_secret


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check configured LLM API connectivity.")
    parser.add_argument("--provider", choices={"qwen", "openai", "deepseek"}, default="qwen", help="Provider to test.")
    parser.add_argument("--model", help="Model name to test. Defaults depend on --provider.")
    parser.add_argument("--prompt", default="Reply with exactly: ok", help="Short prompt used for the check.")
    parser.add_argument("--max-tokens", type=int, default=16, help="Maximum tokens for the test response.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.provider == "openai":
        model = args.model or DEFAULT_OPENAI_MODEL
        api_key = get_openai_api_key()
        print(f"Provider: OpenAI")
        print(f"Model: {model}")
        print(f"API key: {mask_secret(api_key)}")
        try:
            client = OpenAIClient(model_name=model, api_key=api_key)
            response = client.query(args.prompt, max_tokens=args.max_tokens)
        except OpenAIClientError as exc:
            print(f"OpenAI check failed: {exc}")
            return 1

        print("OpenAI check succeeded.")
        print(f"Response: {response}")
        return 0

    if args.provider == "deepseek":
        model = args.model or DEFAULT_DEEPSEEK_MODEL
        api_key = get_deepseek_api_key()
        print(f"Provider: DeepSeek")
        print(f"Model: {model}")
        print(f"API key: {mask_secret(api_key)}")
        try:
            client = DeepSeekClient(model_name=model, api_key=api_key)
            response = client.query(args.prompt, max_tokens=args.max_tokens)
        except DeepSeekClientError as exc:
            print(f"DeepSeek check failed: {exc}")
            return 1

        print("DeepSeek check succeeded.")
        print(f"Response: {response}")
        return 0

    model = args.model or DEFAULT_QWEN_MODEL
    api_key = get_qwen_api_key()
    print(f"Provider: Qwen/DashScope")
    print(f"Model: {model}")
    print(f"API key: {mask_secret(api_key)}")

    try:
        client = QwenClient(model_name=model, api_key=api_key)
        response = client.query(args.prompt, max_tokens=args.max_tokens)
    except QwenClientError as exc:
        print(f"Qwen check failed: {exc}")
        return 1

    print("Qwen check succeeded.")
    print(f"Response: {response}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
