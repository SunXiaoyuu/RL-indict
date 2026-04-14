from __future__ import annotations

import json
import os
from enum import Enum
from typing import Any

from backends import BaseExecutionBackend, create_execution_backend
from util import extract_code, extract_tools, format_step, parse_action
import tools as tool_functions


class AgentStrategy(Enum):
    INDICT_LLAMA = "indict_llama"
    INDICT_COMMANDR = "indict_commandr"


class Agents:
    def __init__(
        self,
        sample_idx: int,
        question: str,
        system_prompt=None,
        actor_prompt=None,
        safety_critic_prompt=None,
        helpful_critic_prompt=None,
        gas_critic_prompt=None,
        summary_critic_prompt=None,
        summary_critic_prompt_posthoc=None,
        tool_prompt=None,
        tool_prompt_posthoc=None,
        tool_prompt_code=None,
        action_llm=None,
        critic_llm=None,
        action_prompt_header: str = "",
        critic_tool=None,
        critic_tool_posthoc=None,
        prev_trial=None,
        task=None,
        tokenizer=None,
        programming_language=None,
        code_before="",
        sample_metadata=None,
        execution_backend: BaseExecutionBackend | None = None,
    ) -> None:
        self.sample_idx = sample_idx
        self.question = question
        self.system_prompt = system_prompt
        self.actor_prompt = actor_prompt
        self.safety_critic_prompt = safety_critic_prompt
        self.helpful_critic_prompt = helpful_critic_prompt
        self.gas_critic_prompt = gas_critic_prompt
        self.summary_critic_prompt = summary_critic_prompt
        self.summary_critic_prompt_posthoc = summary_critic_prompt_posthoc
        self.tool_prompt = tool_prompt
        self.tool_prompt_posthoc = tool_prompt_posthoc
        self.tool_prompt_code = tool_prompt_code
        self.action_llm = action_llm
        self.critic_llm = critic_llm
        self.action_prompt_header = action_prompt_header
        self.critic_tool = critic_tool
        self.critic_tool_posthoc = critic_tool_posthoc
        self.task = task
        self.tokenizer = tokenizer
        self.programming_language = programming_language
        self.code_before = code_before
        self.sample_metadata = sample_metadata or {}

        if task == "promptinject":
            self.question_only = self.question
            self.question = "System rule: " + self.system_prompt + "\n" + self.question
        else:
            self.question_only = None

        self.prev_trial = None
        if prev_trial is not None and os.path.exists(prev_trial):
            self.prev_trial = json.load(open(prev_trial, "r", encoding="utf-8"))
            assert self.prev_trial["sample_idx"] == self.sample_idx

        self.num_actions = 1
        self.critic_rounds = 1
        self.num_tool_queries = 1
        self.execution_backend = execution_backend or create_execution_backend(
            task=task,
            programming_language=programming_language,
            sample_metadata=self.sample_metadata,
        )
        self.critic_specs = self._build_critic_specs()
        self.previous_structured_feedback = self._structured_feedback_from_record(self.prev_trial)
        self.reset()

    def _build_critic_specs(self) -> list[dict[str, Any]]:
        specs = []
        if self.task == "solidity":
            if self.safety_critic_prompt is not None:
                specs.append(
                    {
                        "key": "safety",
                        "label": "Security",
                        "analysis_focus": "solution security",
                        "support_label": "Supporting Fact(s) for Security",
                        "prompt": self.safety_critic_prompt,
                        "max_tokens": 256,
                    }
                )
            if self.helpful_critic_prompt is not None:
                specs.append(
                    {
                        "key": "helpful",
                        "label": "Functionality",
                        "analysis_focus": "solution functionality and correctness",
                        "support_label": "Supporting Fact(s) for Functionality",
                        "prompt": self.helpful_critic_prompt,
                        "max_tokens": 384,
                    }
                )
            if self.gas_critic_prompt is not None:
                specs.append(
                    {
                        "key": "gas",
                        "label": "Gas",
                        "analysis_focus": "solution gas usage and on-chain efficiency",
                        "support_label": "Supporting Fact(s) for Gas",
                        "prompt": self.gas_critic_prompt,
                        "max_tokens": 256,
                    }
                )
            return specs

        if self.safety_critic_prompt is not None:
            specs.append(
                {
                    "key": "safety",
                    "label": "Safety",
                    "analysis_focus": "solution safety",
                    "support_label": "Supporting Fact(s) for Safety",
                    "prompt": self.safety_critic_prompt,
                }
            )
        if self.helpful_critic_prompt is not None:
            specs.append(
                {
                    "key": "helpful",
                    "label": "Correctness",
                    "analysis_focus": "solution correctness",
                    "support_label": "Supporting Fact(s) for Correctness",
                    "prompt": self.helpful_critic_prompt,
                }
            )
        return specs

    def _has_posthoc(self) -> bool:
        return self.execution_backend.supports_posthoc()

    def run(self, strategy: AgentStrategy):
        self.strategy = strategy
        self.reset()
        self.step()

        output = {
            "sample_idx": self.sample_idx,
            "action": self.action,
            "scratchpad": self.scratchpad,
            "critic": self._append_prev_trial_field("critic", self.critic),
            "initial_action": self.initial_action,
            "critic_scratchpad": self.critic_scratchpad,
        }
        if self.previous_structured_feedback:
            output["previous_structured_feedback"] = self.previous_structured_feedback

        for spec in self.critic_specs:
            key = spec["key"]
            output[f"{key}_critics"] = getattr(self, f"{key}_critics")
            output[f"{key}_tool_output"] = getattr(self, f"{key}_tool_output")

        if self._has_posthoc():
            output["initial_action_execution_observation"] = getattr(self, "initial_action_execution", "")
            output["initial_action_execution_metrics"] = getattr(self, "initial_action_execution_metrics", {})
            output["initial_structured_feedback"] = getattr(self, "initial_structured_feedback", {})
            output["execution_observation"] = getattr(self, "action_execution", "")
            output["execution_metrics"] = getattr(self, "action_execution_metrics", {})
            output["structured_feedback"] = getattr(self, "action_structured_feedback", {})
            output["mid_action_execution_observation"] = getattr(self, "mid_action_execution", "")
            output["mid_action_execution_metrics"] = getattr(self, "mid_action_execution_metrics", {})
            output["mid_structured_feedback"] = getattr(self, "mid_structured_feedback", {})
            output["final_action_execution_observation"] = getattr(self, "final_action_execution", "")
            output["final_action_execution_metrics"] = getattr(self, "final_action_execution_metrics", {})
            output["final_structured_feedback"] = getattr(self, "final_structured_feedback", {})
            if hasattr(self, "degradation_guard"):
                output["degradation_guard"] = self.degradation_guard
            if hasattr(self, "rejected_action"):
                output["rejected_action"] = self.rejected_action
            output["critic_posthoc"] = self._append_prev_trial_field("critic_posthoc", self.critic_posthoc)
            output["mid_action"] = self.mid_action
            output["critic_scratchpad_posthoc"] = self.critic_scratchpad_posthoc
            for spec in self.critic_specs:
                key = spec["key"]
                output[f"{key}_critics_posthoc"] = getattr(self, f"{key}_critics_posthoc")
                output[f"{key}_tool_output_posthoc"] = getattr(self, f"{key}_tool_output_posthoc")

        return output

    def _append_prev_trial_field(self, field_name: str, current_value: Any):
        if self.prev_trial is None or field_name not in self.prev_trial:
            return current_value
        previous_value = self.prev_trial[field_name]
        if isinstance(previous_value, list):
            return previous_value + [current_value]
        return [previous_value, current_value]

    def _build_solidity_hard_constraints(self) -> str:
        if self.task != "solidity":
            return ""

        contract_name = self.sample_metadata.get("contract_name")
        required = self._normalize_signature_list(self.sample_metadata.get("required_abi_signatures", []))
        forbidden = self._normalize_signature_list(self.sample_metadata.get("forbidden_abi_signatures", []))
        replacement_mode = (
            self.sample_metadata.get("replace_start_line") is not None
            and self.sample_metadata.get("replace_end_line") is not None
        )

        lines = ["Solidity hard constraints:"]
        if replacement_mode:
            lines.extend(
                [
                    "- This is a replacement snippet for an existing Solidity file. Do not emit surrounding contracts, libraries, imports, or unrelated code.",
                    "- Preserve the target signature, visibility, mutability, return types, and surrounding repository assumptions unless the task explicitly requires a correction.",
                ]
            )
        elif contract_name:
            lines.append(f"- The primary contract name must remain exactly `{contract_name}`.")

        lines.extend(
            [
                "- Preserve every required ABI signature exactly. Do not rename, remove, or change argument types for required public/external functions, constructors, mappings, or getters.",
                "- Required getter signatures must be implemented either by a public state variable/mapping or by an explicit function, never both.",
                "- If you use a public state variable or public mapping, do not write an explicit function with the same name; Solidity already creates the getter.",
                "- If you write an explicit getter function, the backing storage variable must use a different private/internal name such as `_name`; never declare storage and function identifiers with the same name.",
                "- Do not add external imports, inherited contracts, upgradeable patterns, or third-party dependencies unless the task explicitly provides and requires them.",
                "- Do not add broad unrequested APIs such as ownership-transfer functions, extra mint/admin functions, helper endpoints, or unrelated events.",
                "- Extra public/external ABI entries count as interface drift unless explicitly required by the task.",
                "- Prefer minimal edits that fix concrete compiler, ABI, test, Slither, or gas feedback while preserving the specified behavior.",
            ]
        )
        if required:
            lines.append("- Required ABI signatures: " + ", ".join(required))
        if forbidden:
            lines.append("- Forbidden ABI signatures: " + ", ".join(forbidden))
        return "\n".join(lines)

    def _question_with_hard_constraints(self) -> str:
        constraints = self._build_solidity_hard_constraints()
        if not constraints:
            return self.question
        return f"{self.question}\n\n{constraints}"

    def _format_feedback_block(self, title: str, feedback: dict[str, Any] | None) -> str:
        if not feedback:
            return ""
        return "\n" + title + ":\n```json\n" + json.dumps(feedback, ensure_ascii=False, indent=2) + "\n```"

    def _structured_feedback_from_record(self, record: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(record, dict):
            return {}
        if isinstance(record.get("structured_feedback"), dict):
            return record["structured_feedback"]
        metrics = record.get("execution_metrics")
        return self._build_structured_feedback(metrics)

    def _build_structured_feedback(self, metrics: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(metrics, dict):
            return {}

        compile_result = metrics.get("compile") or {}
        abi_result = metrics.get("abi") or {}
        tests_result = metrics.get("tests") or {}
        slither_result = metrics.get("slither") or {}
        gas_result = metrics.get("gas") or {}

        required = self._normalize_signature_list(abi_result.get("required") or self.sample_metadata.get("required_abi_signatures", []))
        forbidden = self._normalize_signature_list(
            abi_result.get("forbidden") or self.sample_metadata.get("forbidden_abi_signatures", [])
        )
        available = self._normalize_signature_list(abi_result.get("available", []))
        required_set = set(required)
        forbidden_set = set(forbidden)
        has_required_constructor = any(signature.startswith("constructor(") for signature in required)
        abi_extra = [
            signature
            for signature in available
            if signature not in required_set
            and signature not in forbidden_set
            and not (signature.startswith("constructor(") and not has_required_constructor)
        ]

        feedback: dict[str, Any] = {
            "compile_success": compile_result.get("success") if isinstance(compile_result, dict) else None,
            "compile_error": None,
            "abi_checked": abi_result.get("checked") if isinstance(abi_result, dict) else None,
            "abi_success": abi_result.get("success") if isinstance(abi_result, dict) else None,
            "abi_required": required,
            "abi_missing": abi_result.get("missing", []) if isinstance(abi_result, dict) else [],
            "abi_extra": abi_extra,
            "abi_forbidden_present": abi_result.get("forbidden_present", []) if isinstance(abi_result, dict) else [],
            "test_success": tests_result.get("success") if isinstance(tests_result, dict) and tests_result else None,
            "test_failure": None,
            "slither_findings": {
                "count": metrics.get("vulnerability_count"),
                "severity_counts": metrics.get("vulnerability_severity_counts") or {},
                "items": metrics.get("slither_findings") or [],
            },
            "gas_used": metrics.get("max_gas_value"),
        }

        if feedback["compile_success"] is False:
            feedback["compile_error"] = self._short_command_failure(compile_result)
        if feedback["test_success"] is False:
            feedback["test_failure"] = self._short_command_failure(tests_result)
        if isinstance(slither_result, dict) and slither_result:
            feedback["slither_findings"]["command_success"] = slither_result.get("success")
            if slither_result.get("success") is False:
                feedback["slither_findings"]["error"] = self._short_command_failure(slither_result)
        if isinstance(gas_result, dict) and gas_result:
            feedback["gas_command_success"] = gas_result.get("success")

        return feedback

    @classmethod
    def _short_command_failure(cls, command_result: dict[str, Any] | None, limit: int = 900) -> str:
        if not isinstance(command_result, dict):
            return ""
        text = command_result.get("stderr") or command_result.get("stdout") or command_result.get("error") or ""
        lines = []
        for line in str(text).splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
        shortened = "\n".join(lines[:12])
        if len(shortened) > limit:
            return shortened[: limit - 3].rstrip() + "..."
        return shortened

    def _normalize_signature_list(self, signatures: Any) -> list[str]:
        if signatures is None:
            return []
        if isinstance(signatures, str):
            signatures = [signatures]
        if not isinstance(signatures, list):
            return []
        normalized = []
        for signature in signatures:
            if not isinstance(signature, str):
                continue
            rendered = "".join(signature.strip().split())
            if rendered:
                normalized.append(rendered)
        return normalized

    def step(self) -> None:
        self.scratchpad += self.action_prompt_header

        if self.prev_trial is None:
            self.action = self.prompt_agent(self.action_llm, self.actor_prompt)
        else:
            self.action = self.prev_trial["action"]

        self.scratchpad = "\nSolution: " + self.action_prompt_header
        self.scratchpad += self.action
        self.critic = self.perform_critic_debate(answer=self.action, max_steps=self.critic_rounds)

        self.scratchpad = ""
        self.scratchpad += "\nInitial Solution: " + self.action
        self.scratchpad += self._format_feedback_block(
            "Previous Round Structured Execution Feedback",
            self.previous_structured_feedback,
        )
        self.scratchpad += "\nCritic: " + self.critic + "\nImproved Solution: " + self.action_prompt_header
        self.initial_action = self.action
        self.action = self.prompt_agent(self.action_llm, self.actor_prompt, stop_seqs=["\nCritic:"])
        self.scratchpad += self.action

        if not self._has_posthoc():
            return

        initial_observation = self.execution_backend.evaluate(extract_code(self.initial_action), code_before=self.code_before)
        self.initial_action_execution = initial_observation.to_text()
        self.initial_action_execution_metrics = initial_observation.as_dict()
        self.initial_structured_feedback = self._build_structured_feedback(self.initial_action_execution_metrics)

        observation = self.execution_backend.evaluate(extract_code(self.action), code_before=self.code_before)
        self.action_execution = observation.to_text()
        self.action_execution_metrics = observation.as_dict()
        self.mid_action_execution = self.action_execution
        self.mid_action_execution_metrics = self.action_execution_metrics
        self.mid_structured_feedback = self._build_structured_feedback(self.mid_action_execution_metrics)
        self.scratchpad += "\nObservation: " + self.action_execution
        self.scratchpad += self._format_feedback_block(
            "Current Structured Execution Feedback",
            self.mid_structured_feedback,
        )

        self.critic_posthoc = self.perform_critic_debate(
            answer=self.action,
            max_steps=self.critic_rounds,
            posthoc=True,
        )

        self.scratchpad = ""
        self.scratchpad += "\nInitial Solution: " + self.initial_action
        self.scratchpad += self._format_feedback_block(
            "Initial Structured Execution Feedback",
            self.initial_structured_feedback,
        )
        self.scratchpad += "\nCritic: " + self.critic
        self.scratchpad += "\nFirst Improved Solution: " + self.action
        self.scratchpad += self._format_feedback_block(
            "First Improved Structured Execution Feedback",
            self.mid_structured_feedback,
        )
        self.scratchpad += "\nCritic: " + self.critic_posthoc
        self.scratchpad += "\nSecond Improved Solution: " + self.action_prompt_header
        self.mid_action = self.action
        self.action = self.prompt_agent(self.action_llm, self.actor_prompt, stop_seqs=["\nCritic:"])
        self.scratchpad += self.action
        final_observation = self.execution_backend.evaluate(extract_code(self.action), code_before=self.code_before)
        self.final_action_execution = final_observation.to_text()
        self.final_action_execution_metrics = final_observation.as_dict()
        self.final_structured_feedback = self._build_structured_feedback(self.final_action_execution_metrics)

        if self._is_better_outcome(self.mid_action_execution_metrics, self.final_action_execution_metrics):
            self.rejected_action = self.action
            self.action = self.mid_action
            self.action_execution = self.mid_action_execution
            self.action_execution_metrics = self.mid_action_execution_metrics
            self.action_structured_feedback = self.mid_structured_feedback
            self.degradation_guard = "reverted_to_mid_action_after_final_regression"
            self.scratchpad += (
                "\nDegradation Guard: final rewrite regressed on compile, test, ABI, security, or gas outcome; "
                "reverted to the first improved solution."
            )
        else:
            self.action_execution = self.final_action_execution
            self.action_execution_metrics = self.final_action_execution_metrics
            self.action_structured_feedback = self.final_structured_feedback

        if self._is_better_outcome(self.initial_action_execution_metrics, self.action_execution_metrics):
            self.rejected_action = self.action
            self.action = self.initial_action
            self.action_execution = self.initial_action_execution
            self.action_execution_metrics = self.initial_action_execution_metrics
            self.action_structured_feedback = self.initial_structured_feedback
            initial_guard = "reverted_to_initial_action_after_better_compile_test_abi_security_or_gas_outcome"
            if hasattr(self, "degradation_guard"):
                self.degradation_guard = self.degradation_guard + ";" + initial_guard
            else:
                self.degradation_guard = initial_guard
            self.scratchpad += (
                "\nDegradation Guard: improved rewrites underperformed the initial solution; "
                "reverted to the initial solution."
            )

    def perform_critic_debate(self, max_steps=1, prefix="", answer=None, posthoc=False):
        posthoc_suffix = "_posthoc" if posthoc else ""

        for spec in self.critic_specs:
            setattr(self, f"{prefix}{spec['key']}_critics{posthoc_suffix}", [])
            setattr(self, f"{prefix}{spec['key']}_tool_output{posthoc_suffix}", [])

        self.scratchpad = ""
        if self.prev_trial is not None:
            self.scratchpad += (
                "\nThe following critic(s) provide some analysis of previous solution(s). "
                "Use them as reference only to improve and update your critic based on the latest solution."
            )
            self.scratchpad += self._format_feedback_block(
                "Previous Round Structured Execution Feedback",
                self.previous_structured_feedback,
            )
            prev_critics = self.prev_trial.get(f"{prefix}critic")
            if isinstance(prev_critics, list):
                for value in prev_critics:
                    self.scratchpad += "\nPast Critic: " + value
            elif isinstance(prev_critics, str):
                self.scratchpad += "\nPast Critic: " + prev_critics

        if posthoc:
            self.scratchpad += (
                "\nThe following critic(s) provide some analysis of the current solution. "
                "Use them as reference only to improve and update your critic based on the latest observation."
            )
            self.scratchpad += "\nPast Critic: " + self.critic
            self.scratchpad += (
                "\nThe following provides some observation(s) when executing the current solution. "
                "If these observations are relevant, use them to improve and update your critic:"
            )
            self.scratchpad += "\nCurrent Solution Observation: " + self.action_execution
            self.scratchpad += self._format_feedback_block(
                "Current Structured Execution Feedback",
                self._build_structured_feedback(getattr(self, "action_execution_metrics", {})),
            )

        for step in range(max_steps):
            for index, spec in enumerate(self.critic_specs):
                self.scratchpad += f"\n{spec['label']} Critic: "
                if step > 0 or self.prev_trial is not None:
                    self.scratchpad += f"based on the above discussion, here is my updated analysis of {spec['analysis_focus']}: "
                else:
                    self.scratchpad += f"here is my analysis of {spec['analysis_focus']}: "

                critic_text = self.prompt_critic_agent(
                    self.critic_llm,
                    spec["prompt"],
                    max_tokens=spec.get("max_tokens", 128),
                    answer=answer,
                )

                current_scratchpad = self.scratchpad
                query_tool_output_str, tool_selection, tool_output = self.query_tools(
                    critic_text,
                    answer=answer,
                    tool_prompt=self.tool_prompt_posthoc if posthoc else self.tool_prompt,
                    critic_tool=self.critic_tool_posthoc if posthoc else self.critic_tool,
                )
                if query_tool_output_str.strip():
                    critic_text += "\n" + spec["support_label"] + ": " + query_tool_output_str
                self.scratchpad = current_scratchpad

                getattr(self, f"{prefix}{spec['key']}_tool_output{posthoc_suffix}").append(
                    {"tool": tool_selection, "output": tool_output}
                )
                getattr(self, f"{prefix}{spec['key']}_critics{posthoc_suffix}").append(critic_text)
                self.scratchpad += critic_text

                if index < len(self.critic_specs) - 1:
                    next_label = self.critic_specs[index + 1]["label"]
                    self.scratchpad += f"\n{next_label} Critic: "

        critic_summary = self.prompt_agent(
            self.critic_llm,
            self.summary_critic_prompt_posthoc if posthoc else self.summary_critic_prompt,
            max_tokens=1024,
            main_action=False,
        )
        setattr(self, f"{prefix}critic_scratchpad{posthoc_suffix}", self.scratchpad)
        return critic_summary

    def query_tools(self, critic, answer, tool_prompt, critic_tool):
        if tool_prompt is None or critic_tool is None or len(critic_tool) == 0:
            return "", [], []

        self.scratchpad = "Analysis:" + critic
        if self.strategy == AgentStrategy.INDICT_LLAMA:
            tool = self.prompt_critic_agent(self.critic_llm, tool_prompt, max_tokens=64, answer=answer)
            parsed_tool = None
            for line in tool.split("\n"):
                parsed_tool = parse_action(line)
                if parsed_tool is not None:
                    break

            query = ""
            if parsed_tool is not None:
                _, query = parsed_tool

            query_code = ""
            if self.tool_prompt_code is not None:
                generated_query_code = self.prompt_critic_agent(
                    self.critic_llm,
                    self.tool_prompt_code,
                    max_tokens=128,
                    answer=answer,
                    query=query,
                )
                query_code = extract_code(generated_query_code)

            selected_tool = critic_tool[0]
            if selected_tool["name"] == "code_search":
                tool_selections = [
                    {
                        "tool_name": selected_tool["name"],
                        "parameters": {"query": query, "snippet": query_code},
                    }
                ]
            else:
                tool_selections = [
                    {
                        "tool_name": selected_tool["name"],
                        "parameters": {"query": query, "code": query_code},
                    }
                ]
        else:
            context = self._build_critic_agent_prompt(tool_prompt, "", answer)
            tool_selections = self.critic_llm.query_with_retries(context, max_tokens=512)
            tool_selections = extract_tools(tool_selections)

        tool_outputs = []
        tool_output_str = ""
        num_queries = 0
        for tool_selection in tool_selections:
            try:
                outputs = getattr(tool_functions, tool_selection["tool_name"])(**tool_selection["parameters"])
                num_queries += 1
                if outputs is None:
                    continue
                for output in outputs:
                    if output is None or len(output) == 0:
                        continue
                    current_output_str = ""
                    if output.get("title"):
                        current_output_str += output["title"]
                    if output.get("description"):
                        current_output_str += " - " + output["description"]
                    if current_output_str:
                        tool_output_str += "\nSupporting Fact: " + current_output_str
                        tool_outputs.append(output)
                if num_queries == self.num_tool_queries:
                    break
            except Exception:
                continue
        return tool_output_str, tool_selections, tool_outputs

    def reset(self) -> None:
        self.scratchpad = ""

    @staticmethod
    def _compile_success(metrics: dict[str, Any] | None) -> bool:
        if not isinstance(metrics, dict):
            return False
        compile_result = metrics.get("compile")
        return isinstance(compile_result, dict) and compile_result.get("success") is True

    @staticmethod
    def _tests_success(metrics: dict[str, Any] | None) -> bool:
        if not isinstance(metrics, dict):
            return False
        tests_result = metrics.get("tests")
        return isinstance(tests_result, dict) and tests_result.get("success") is True

    @staticmethod
    def _abi_success(metrics: dict[str, Any] | None) -> bool:
        if not isinstance(metrics, dict):
            return False
        abi_result = metrics.get("abi")
        return (
            not isinstance(abi_result, dict)
            or abi_result.get("checked") is not True
            or abi_result.get("success") is True
        )

    def _abi_extra_count(self, metrics: dict[str, Any] | None) -> int | None:
        if not isinstance(metrics, dict):
            return None
        feedback = self._build_structured_feedback(metrics)
        abi_extra = feedback.get("abi_extra")
        if not isinstance(abi_extra, list):
            return None
        return len(abi_extra)

    @classmethod
    def _vulnerability_score(cls, metrics: dict[str, Any] | None) -> int | None:
        if not isinstance(metrics, dict):
            return None
        count = metrics.get("vulnerability_count")
        if count is None:
            return None
        severity_counts = metrics.get("vulnerability_severity_counts") or {}
        weights = {
            "critical": 1_000_000,
            "high": 10_000,
            "medium": 100,
            "low": 10,
            "informational": 1,
            "optimization": 1,
        }
        score = 0
        if isinstance(severity_counts, dict) and severity_counts:
            for severity, severity_count in severity_counts.items():
                score += weights.get(str(severity).lower(), 10) * int(severity_count or 0)
            return score
        return int(count) * 10

    @staticmethod
    def _gas_value(metrics: dict[str, Any] | None) -> int | None:
        if not isinstance(metrics, dict):
            return None
        value = metrics.get("max_gas_value")
        if value is None:
            return None
        return int(value)

    @classmethod
    def _lower_metric_is_better(cls, candidate_value: int | None, baseline_value: int | None) -> bool | None:
        if candidate_value is None and baseline_value is None:
            return None
        if candidate_value is None:
            return False
        if baseline_value is None:
            return True
        if candidate_value == baseline_value:
            return None
        return candidate_value < baseline_value

    def _is_better_outcome(self, candidate_metrics: dict[str, Any] | None, baseline_metrics: dict[str, Any] | None) -> bool:
        candidate_compile = self._compile_success(candidate_metrics)
        baseline_compile = self._compile_success(baseline_metrics)
        if candidate_compile != baseline_compile:
            return candidate_compile and not baseline_compile

        if not candidate_compile:
            return False

        candidate_tests = self._tests_success(candidate_metrics)
        baseline_tests = self._tests_success(baseline_metrics)
        if candidate_tests != baseline_tests:
            return candidate_tests and not baseline_tests

        candidate_abi = self._abi_success(candidate_metrics)
        baseline_abi = self._abi_success(baseline_metrics)
        if candidate_abi != baseline_abi:
            return candidate_abi and not baseline_abi

        abi_extra_decision = self._lower_metric_is_better(
            self._abi_extra_count(candidate_metrics),
            self._abi_extra_count(baseline_metrics),
        )
        if abi_extra_decision is not None:
            return abi_extra_decision

        vulnerability_decision = self._lower_metric_is_better(
            self._vulnerability_score(candidate_metrics),
            self._vulnerability_score(baseline_metrics),
        )
        if vulnerability_decision is not None:
            return vulnerability_decision

        gas_decision = self._lower_metric_is_better(
            self._gas_value(candidate_metrics),
            self._gas_value(baseline_metrics),
        )
        if gas_decision is not None:
            return gas_decision

        return False

    def prompt_agent(self, llm_module, prompt_template, max_tokens=1024, stop_seqs=None, num_outputs=1, main_action=True) -> str:
        stop_seqs = stop_seqs or []
        prompt = self._build_agent_prompt(prompt_template, main_action)
        if main_action and self.task == "promptinject":
            output = llm_module.query_with_system_prompt_with_retries(
                self.system_prompt,
                prompt,
                max_tokens=max_tokens,
                stop_seqs=stop_seqs,
                num_outputs=num_outputs,
            )
        else:
            output = llm_module.query_with_retries(
                prompt,
                max_tokens=max_tokens,
                stop_seqs=stop_seqs,
                num_outputs=num_outputs,
            )
        return format_step(output)

    def _build_agent_prompt(self, prompt_template, main_action) -> str:
        if main_action and self.task == "promptinject":
            question = self.question_only
        else:
            question = self.question
        if self.task == "solidity":
            question = self._question_with_hard_constraints()
        if "question" in prompt_template.input_variables:
            return prompt_template.format(question=question, scratchpad=self.scratchpad)
        return prompt_template.format(scratchpad=self.scratchpad)

    def prompt_critic_agent(
        self,
        llm_module,
        prompt_template,
        fewshots="",
        max_tokens=1024,
        stop_seqs=None,
        answer=None,
        query=None,
    ) -> str:
        del fewshots
        stop_seqs = stop_seqs or []
        prompt = self._build_critic_agent_prompt(prompt_template, "", answer, query=query)
        return format_step(llm_module.query_with_retries(prompt, max_tokens=max_tokens, stop_seqs=stop_seqs))

    def _build_critic_agent_prompt(self, prompt_template, fewshots="", answer=None, query=None) -> str:
        del fewshots
        if "query" in prompt_template.input_variables:
            return prompt_template.format(
                query=query,
                question=self._question_with_hard_constraints() if self.task == "solidity" else self.question,
                answer=answer,
                scratchpad=self.scratchpad,
            )
        return prompt_template.format(
            question=self._question_with_hard_constraints() if self.task == "solidity" else self.question,
            answer=answer,
            scratchpad=self.scratchpad,
        )
