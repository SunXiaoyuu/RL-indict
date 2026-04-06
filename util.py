from __future__ import annotations

import json
import re


TASK_CONFIGS = {
    "mitre": {
        "data_path": "data/mitre.json",
        "action_prompt_header": "Based on the above analysis, here's the updated version of the solution: ",
        "question_prompt_key": "mutated_prompt",
    },
    "instruct": {
        "data_path": "data/instruct.json",
        "action_prompt_header": "Based on the above analysis, here's the updated version of the code in a single code block (wrap in ```):\n",
        "question_prompt_key": "test_case_prompt",
    },
    "autocomplete": {
        "data_path": "data/autocomplete.json",
        "action_prompt_header": "Based on the above analysis, here's the updated version of the code in a single code block (wrap in ```):\n",
        "question_prompt_key": "test_case_prompt",
    },
    "promptinject": {
        "data_path": "data/prompt_injection.json",
        "action_prompt_header": "",
        "question_prompt_key": "user_input",
    },
    "interpreter": {
        "data_path": "data/interpreter.json",
        "action_prompt_header": "",
        "question_prompt_key": "mutated_prompt",
        "default_language": "python",
    },
    "cvs": {
        "data_path": "data/cvs.json",
        "action_prompt_header": "Based on the above analysis, here's the updated version of the code in a single code block (wrap in ```):\n",
        "question_prompt_key": "question",
    },
    "solidity": {
        "data_path": "data/solidity.json",
        "action_prompt_header": "Based on the above analysis, here's the updated version of the Solidity code in a single code block (wrap in ```solidity):\n",
        "question_prompt_key": "instruction",
        "default_language": "solidity",
    },
}


def load_data(task, data_path=None):
    config = TASK_CONFIGS[task]
    data = json.load(open(data_path or config["data_path"], "r", encoding="utf-8"))
    default_language = config.get("default_language")
    if default_language:
        for sample in data:
            sample["language"] = sample.get("language", default_language)
    return data, config["action_prompt_header"], config["question_prompt_key"]


def get_model(model_name, model_mapping):
    from llm import QWEN

    api_key = "sk-e0684cacf12246528358ae32ee4fc135"
    if model_name in ["gpt4", "gpt3.5", "qwen"]:
        qwen_model_name = model_mapping.get(model_name, "qwen2.5-14b-instruct")
        print(f"Using Qwen model for {model_name}: {qwen_model_name}")
        return QWEN(model_name=qwen_model_name, api_key=api_key)

    print("Using default Qwen model: qwen2.5-14b-instruct")
    return QWEN(model_name="qwen2.5-14b-instruct", api_key=api_key)


def get_code_before(sample):
    code_before = ""
    line_text = sample.get("line_text")
    origin_code = sample.get("origin_code")
    if line_text and origin_code:
        code_before = origin_code.split(line_text)[0].strip("\n")

    if code_before.startswith(" ") or code_before.startswith("\t"):
        code_before = "if True:\n" + code_before
    return code_before


def extract_content_in_code_blocks(text: str, keyword: str = ""):
    output = re.findall(r"```{}(.*?)```".format(keyword), text, re.DOTALL)
    if len(output) > 0:
        return output[0]
    return text


def extract_code(text: str):
    code = extract_content_in_code_blocks(text).strip()
    for prefix in ("python", "solidity", "sol"):
        if code.startswith(prefix):
            return code[len(prefix):].strip()
    return code


def extract_tools(tool_selections):
    json_str = extract_content_in_code_blocks(tool_selections, "json")
    try:
        return json.loads(json_str)
    except Exception:
        return []


def format_step(step: str) -> str:
    return step.strip("\n").strip()


def parse_action(string):
    if "Search" in string:
        index = string.index("Search") + len("Search")
        string = string[index:]
        if "[" in string:
            start_idx = string.index("[") + 1
            if "]" in string:
                end_idx = string.index("]")
                return "Search", string[start_idx:end_idx]
            return "Search", string[start_idx:]
        return "Search", string
    return "Search", string
