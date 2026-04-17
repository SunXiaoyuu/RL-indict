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
        cost_profile: str = "full",
        critic_mode: str = "full",
        feedback_mode: str = "full",
        posthoc_policy: str = "always",
        critic_tools_enabled: bool = True,
        early_stop: bool = False,
        solidity_prompt_mode: str = "normalized",
        critic_rounds: int = 1,
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
        self.cost_profile = cost_profile
        self.critic_mode = critic_mode
        self.feedback_mode = feedback_mode
        self.posthoc_policy = posthoc_policy
        self.critic_tools_enabled = critic_tools_enabled
        self.early_stop = early_stop
        self.solidity_prompt_mode = solidity_prompt_mode
        self.critic_rounds = max(1, int(critic_rounds or 1))

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
                        "max_tokens": 512,
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
            "runtime_config": self._runtime_config(),
            "llm_call_stats": self.llm_call_stats,
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
            if hasattr(self, "stop_reason"):
                output["stop_reason"] = self.stop_reason
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
        if self.solidity_prompt_mode == "raw":
            return ""

        contract_name = self.sample_metadata.get("contract_name")
        required = self._normalize_signature_list(self.sample_metadata.get("required_abi_signatures", []))
        forbidden = self._normalize_signature_list(self.sample_metadata.get("forbidden_abi_signatures", []))
        replacement_mode = (
            self.sample_metadata.get("replace_start_line") is not None
            and self.sample_metadata.get("replace_end_line") is not None
        )

        if self.solidity_prompt_mode == "light":
            lines = ["Solidity internal task constraints:"]
            if replacement_mode:
                lines.append("- Generate only the requested replacement snippet and preserve surrounding repository assumptions.")
            elif contract_name:
                lines.append(f"- Use `{contract_name}` as the primary contract name if the requirement does not clearly demand another name.")
            lines.extend(
                [
                    "- Infer a minimal public interface from the natural-language requirement.",
                    "- Avoid broad unrequested admin/helper APIs, external imports, inherited contracts, upgradeable patterns, or third-party dependencies.",
                    "- Do not declare a public state variable and an explicit getter with the same name.",
                    "- Prefer simple Solidity 0.8.x code that preserves access-control, payment, and state-transition requirements.",
                ]
            )
            if required:
                lines.append(
                    "- If the benchmark supplies required ABI signatures, keep them unless the task explicitly says otherwise: "
                    + ", ".join(required)
                )
            return "\n".join(lines)

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
        rendered_feedback = self._compact_feedback(feedback) if self.feedback_mode == "compact" else feedback
        return "\n" + title + ":\n```json\n" + json.dumps(rendered_feedback, ensure_ascii=False, indent=2) + "\n```"

    def _compact_feedback(self, feedback: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(feedback, dict):
            return {}
        diagnostics = feedback.get("test_diagnostics") or {}
        failed_tests = []
        for test in diagnostics.get("failed_tests") or []:
            failed_tests.append(
                {
                    "name": test.get("name"),
                    "failure_type": test.get("failure_type"),
                    "reason": self._short_text(test.get("reason"), 180),
                    "expected": test.get("expected"),
                    "actual": test.get("actual"),
                    "repair_hint": test.get("repair_hint"),
                }
            )
            if len(failed_tests) == 2:
                break

        slither = feedback.get("slither_findings") or {}
        top_findings = []
        for item in slither.get("items") or []:
            top_findings.append(
                {
                    "check": item.get("check"),
                    "impact": item.get("impact"),
                    "classification": item.get("classification"),
                    "description": self._short_text(item.get("description"), 180),
                }
            )
            if len(top_findings) == 3:
                break

        compact = {
            "target_defect": feedback.get("target_defect"),
            "compile_success": feedback.get("compile_success"),
            "compile_diagnostics": feedback.get("compile_diagnostics") or {},
            "abi_success": feedback.get("abi_success"),
            "abi_missing": feedback.get("abi_missing") or [],
            "abi_extra": feedback.get("abi_extra") or [],
            "abi_forbidden_present": feedback.get("abi_forbidden_present") or [],
            "test_success": feedback.get("test_success"),
            "test_failure": self._short_text(feedback.get("test_failure"), 240),
            "failed_tests": failed_tests,
            "slither_classification_counts": slither.get("classification_counts") or {},
            "slither_command_success": slither.get("command_success"),
            "slither_skipped_reason": slither.get("skipped_reason"),
            "top_slither_findings": top_findings,
            "gas_used": feedback.get("gas_used"),
        }
        if feedback.get("compile_error"):
            compact["compile_error"] = self._short_text(feedback.get("compile_error"), 240)
        return compact

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
            "compile_diagnostics": metrics.get("compile_diagnostics") or {},
            "abi_checked": abi_result.get("checked") if isinstance(abi_result, dict) else None,
            "abi_success": abi_result.get("success") if isinstance(abi_result, dict) else None,
            "abi_required": required,
            "abi_missing": abi_result.get("missing", []) if isinstance(abi_result, dict) else [],
            "abi_extra": abi_extra,
            "abi_forbidden_present": abi_result.get("forbidden_present", []) if isinstance(abi_result, dict) else [],
            "test_success": tests_result.get("success") if isinstance(tests_result, dict) and tests_result else None,
            "test_failure": None,
            "test_diagnostics": metrics.get("test_diagnostics") or {},
            "slither_findings": {
                "count": metrics.get("vulnerability_count"),
                "severity_counts": metrics.get("vulnerability_severity_counts") or {},
                "classification_counts": metrics.get("slither_classification_counts") or {},
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
        else:
            feedback["slither_findings"]["command_success"] = None
            if metrics.get("slither_skipped_reason"):
                feedback["slither_findings"]["skipped_reason"] = metrics.get("slither_skipped_reason")
        if isinstance(gas_result, dict) and gas_result:
            feedback["gas_command_success"] = gas_result.get("success")

        feedback["target_defect"] = self._infer_target_defect(feedback)
        return feedback

    def _infer_target_defect(self, feedback: dict[str, Any]) -> str:
        if feedback.get("compile_success") is False:
            diagnostics = feedback.get("compile_diagnostics") or {}
            failure_types = diagnostics.get("failure_types") or []
            if failure_types:
                return "compile_error:" + ",".join(str(item) for item in failure_types)
            return "compile_error"
        if feedback.get("abi_missing"):
            return "abi_missing"
        if feedback.get("abi_forbidden_present"):
            return "abi_forbidden_present"
        if feedback.get("abi_extra"):
            return "abi_extra"
        if feedback.get("test_success") is False:
            diagnostics = feedback.get("test_diagnostics") or {}
            failure_types = diagnostics.get("failure_types") or []
            if failure_types:
                return "test_failure:" + ",".join(str(item) for item in failure_types)
            return "test_failure"
        slither = feedback.get("slither_findings") or {}
        classification_counts = slither.get("classification_counts") or {}
        if classification_counts.get("security_blocking"):
            return "security_blocking_slither"
        if classification_counts.get("security_review"):
            return "security_review_slither"
        if slither.get("command_success") is None:
            return "slither_unavailable"
        if slither.get("command_success") is False:
            return "slither_failed"
        if feedback.get("gas_used") is None:
            return "gas_unavailable"
        return "none"

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

    @staticmethod
    def _short_text(value: Any, limit: int = 240) -> str:
        text = " ".join(str(value or "").split())
        if len(text) > limit:
            return text[: limit - 3].rstrip() + "..."
        return text

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
        if self.task == "solidity" and self.cost_profile in {"gated", "cheap"} and self._has_posthoc():
            self._step_cost_aware()
            return
        self._step_full()

    def _step_full(self) -> None:
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

    def _step_cost_aware(self) -> None:
        self.scratchpad += self.action_prompt_header

        if self.prev_trial is None:
            self.action = self.prompt_agent(self.action_llm, self.actor_prompt)
        else:
            self.action = self.prev_trial["action"]

        self.initial_action = self.action
        initial_observation = self.execution_backend.evaluate(extract_code(self.initial_action), code_before=self.code_before)
        self.initial_action_execution = initial_observation.to_text()
        self.initial_action_execution_metrics = initial_observation.as_dict()
        self.initial_structured_feedback = self._build_structured_feedback(self.initial_action_execution_metrics)

        if self.early_stop and self._should_stop_after_feedback(self.initial_structured_feedback):
            self._accept_initial_action("initial_action_passed_clean")
            return
        if self._is_environment_blocked_feedback(self.initial_structured_feedback):
            self._accept_initial_action(self.initial_structured_feedback.get("target_defect") or "environment_blocked")
            return

        self.critic = self.perform_critic_debate(
            answer=self.action,
            max_steps=self.critic_rounds,
            feedback=self.initial_structured_feedback,
        )

        self.scratchpad = ""
        self.scratchpad += "\nInitial Solution: " + self.initial_action
        self.scratchpad += self._format_feedback_block(
            "Initial Structured Execution Feedback",
            self.initial_structured_feedback,
        )
        self.scratchpad += "\nCritic: " + self.critic + "\nImproved Solution: " + self.action_prompt_header
        self.action = self.prompt_agent(self.action_llm, self.actor_prompt, stop_seqs=["\nCritic:"])
        self.scratchpad += self.action

        observation = self.execution_backend.evaluate(extract_code(self.action), code_before=self.code_before)
        self.action_execution = observation.to_text()
        self.action_execution_metrics = observation.as_dict()
        self.mid_action = self.action
        self.mid_action_execution = self.action_execution
        self.mid_action_execution_metrics = self.action_execution_metrics
        self.mid_structured_feedback = self._build_structured_feedback(self.mid_action_execution_metrics)
        self.action_structured_feedback = self.mid_structured_feedback

        if self._is_better_outcome(self.initial_action_execution_metrics, self.action_execution_metrics):
            self.rejected_action = self.action
            self._accept_initial_action("reverted_to_initial_action_after_first_rewrite_regression")
            return

        if self.early_stop and self._should_stop_after_feedback(self.mid_structured_feedback):
            self._accept_mid_action("first_rewrite_passed_clean")
            return
        if self._is_environment_blocked_feedback(self.mid_structured_feedback):
            self._accept_mid_action(self.mid_structured_feedback.get("target_defect") or "environment_blocked")
            return

        if not self._should_run_posthoc(self.mid_structured_feedback):
            self._accept_mid_action("posthoc_skipped_by_policy")
            return

        self.scratchpad += "\nObservation: " + self.action_execution
        self.scratchpad += self._format_feedback_block(
            "Current Structured Execution Feedback",
            self.mid_structured_feedback,
        )
        self.critic_posthoc = self.perform_critic_debate(
            answer=self.action,
            max_steps=self.critic_rounds,
            posthoc=True,
            feedback=self.mid_structured_feedback,
        )

        self.scratchpad = ""
        self.scratchpad += "\nInitial Solution: " + self.initial_action
        self.scratchpad += self._format_feedback_block(
            "Initial Structured Execution Feedback",
            self.initial_structured_feedback,
        )
        self.scratchpad += "\nCritic: " + self.critic
        self.scratchpad += "\nFirst Improved Solution: " + self.mid_action
        self.scratchpad += self._format_feedback_block(
            "First Improved Structured Execution Feedback",
            self.mid_structured_feedback,
        )
        self.scratchpad += "\nCritic: " + self.critic_posthoc
        self.scratchpad += "\nSecond Improved Solution: " + self.action_prompt_header
        self.action = self.prompt_agent(self.action_llm, self.actor_prompt, stop_seqs=["\nCritic:"])
        self.scratchpad += self.action
        final_observation = self.execution_backend.evaluate(extract_code(self.action), code_before=self.code_before)
        self.final_action_execution = final_observation.to_text()
        self.final_action_execution_metrics = final_observation.as_dict()
        self.final_structured_feedback = self._build_structured_feedback(self.final_action_execution_metrics)

        if self._is_better_outcome(self.mid_action_execution_metrics, self.final_action_execution_metrics):
            self.rejected_action = self.action
            self._accept_mid_action("reverted_to_mid_action_after_final_regression")
        else:
            self.action_execution = self.final_action_execution
            self.action_execution_metrics = self.final_action_execution_metrics
            self.action_structured_feedback = self.final_structured_feedback

        if self._is_better_outcome(self.initial_action_execution_metrics, self.action_execution_metrics):
            self.rejected_action = self.action
            self._accept_initial_action("reverted_to_initial_action_after_better_compile_test_abi_security_or_gas_outcome")

    def _accept_initial_action(self, reason: str) -> None:
        self.action = self.initial_action
        self.action_execution = self.initial_action_execution
        self.action_execution_metrics = self.initial_action_execution_metrics
        self.action_structured_feedback = self.initial_structured_feedback
        self.mid_action = getattr(self, "mid_action", "") or self.initial_action
        self.mid_action_execution = getattr(self, "mid_action_execution", "") or self.initial_action_execution
        self.mid_action_execution_metrics = getattr(self, "mid_action_execution_metrics", {}) or self.initial_action_execution_metrics
        self.mid_structured_feedback = getattr(self, "mid_structured_feedback", {}) or self.initial_structured_feedback
        self.final_action_execution = getattr(self, "final_action_execution", "") or self.initial_action_execution
        self.final_action_execution_metrics = getattr(self, "final_action_execution_metrics", {}) or self.initial_action_execution_metrics
        self.final_structured_feedback = getattr(self, "final_structured_feedback", {}) or self.initial_structured_feedback
        if "reverted" in reason:
            self.degradation_guard = reason
        self.stop_reason = reason
        if "Initial Solution:" not in self.scratchpad:
            self.scratchpad = "\nInitial Solution: " + self.initial_action
            self.scratchpad += self._format_feedback_block(
                "Initial Structured Execution Feedback",
                self.initial_structured_feedback,
            )
        self.scratchpad += "\nStop Reason: " + reason

    def _accept_mid_action(self, reason: str) -> None:
        self.action = self.mid_action
        self.action_execution = self.mid_action_execution
        self.action_execution_metrics = self.mid_action_execution_metrics
        self.action_structured_feedback = self.mid_structured_feedback
        self.final_action_execution = getattr(self, "final_action_execution", "") or self.mid_action_execution
        self.final_action_execution_metrics = getattr(self, "final_action_execution_metrics", {}) or self.mid_action_execution_metrics
        self.final_structured_feedback = getattr(self, "final_structured_feedback", {}) or self.mid_structured_feedback
        if "reverted" in reason:
            self.degradation_guard = reason
        self.stop_reason = reason
        if "First Improved Solution:" not in self.scratchpad:
            self.scratchpad += "\nFirst Improved Solution: " + self.mid_action
            self.scratchpad += self._format_feedback_block(
                "First Improved Structured Execution Feedback",
                self.mid_structured_feedback,
            )
        self.scratchpad += "\nStop Reason: " + reason

    def _should_stop_after_feedback(self, feedback: dict[str, Any] | None) -> bool:
        if not isinstance(feedback, dict):
            return False
        return feedback.get("target_defect") == "none"

    @staticmethod
    def _is_environment_blocked_feedback(feedback: dict[str, Any] | None) -> bool:
        if not isinstance(feedback, dict):
            return False
        return feedback.get("target_defect") in {"slither_unavailable", "slither_failed"}

    def _should_run_posthoc(self, feedback: dict[str, Any] | None) -> bool:
        if self.posthoc_policy == "never":
            return False
        if self.posthoc_policy == "always":
            return True
        return not self._should_stop_after_feedback(feedback)

    def _select_critic_specs(self, feedback: dict[str, Any] | None, posthoc: bool = False) -> list[dict[str, Any]]:
        if self.critic_mode == "full" or self.task != "solidity":
            return list(self.critic_specs)

        specs_by_key = {spec["key"]: spec for spec in self.critic_specs}
        selected_keys: list[str] = []

        if not isinstance(feedback, dict) or not feedback:
            selected_keys = ["helpful"] if self.critic_mode == "cheap" else ["safety", "helpful"]
            return [specs_by_key[key] for key in selected_keys if key in specs_by_key]

        slither = feedback.get("slither_findings") or {}
        classification_counts = slither.get("classification_counts") or {}
        needs_functionality = (
            feedback.get("compile_success") is False
            or bool(feedback.get("abi_missing"))
            or bool(feedback.get("abi_extra"))
            or bool(feedback.get("abi_forbidden_present"))
            or feedback.get("test_success") is False
        )
        needs_security = bool(classification_counts.get("security_blocking") or classification_counts.get("security_review"))
        has_clean_functionality = (
            feedback.get("compile_success") is True
            and not feedback.get("abi_missing")
            and not feedback.get("abi_extra")
            and not feedback.get("abi_forbidden_present")
            and feedback.get("test_success") is not False
        )

        if self.critic_mode == "cheap":
            if needs_functionality:
                selected_keys.append("helpful")
            elif needs_security:
                selected_keys.append("safety")
            elif has_clean_functionality and posthoc:
                selected_keys.append("gas")
        else:
            if needs_functionality:
                selected_keys.append("helpful")
            if needs_security:
                selected_keys.append("safety")
            if has_clean_functionality and not needs_security and posthoc:
                selected_keys.append("gas")

        if not selected_keys and not self._should_stop_after_feedback(feedback):
            selected_keys.append("helpful")
        return [specs_by_key[key] for key in selected_keys if key in specs_by_key]

    def perform_critic_debate(self, max_steps=1, prefix="", answer=None, posthoc=False, feedback=None):
        posthoc_suffix = "_posthoc" if posthoc else ""
        active_specs = self._select_critic_specs(feedback=feedback, posthoc=posthoc)

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

        if feedback is not None and not posthoc:
            self.scratchpad += self._format_feedback_block(
                "Current Structured Execution Feedback",
                feedback,
            )

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
                feedback or self._build_structured_feedback(getattr(self, "action_execution_metrics", {})),
            )

        if not active_specs:
            setattr(self, f"{prefix}critic_scratchpad{posthoc_suffix}", self.scratchpad)
            return "No critic was triggered because the structured feedback did not contain a repair target."

        for step in range(max_steps):
            for index, spec in enumerate(active_specs):
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

                if index < len(active_specs) - 1:
                    next_label = active_specs[index + 1]["label"]
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
        if not self.critic_tools_enabled:
            return "", [], []
        if tool_prompt is None or critic_tool is None or len(critic_tool) == 0:
            return "", [], []

        self.scratchpad = "Analysis:" + critic
        if self.strategy == AgentStrategy.INDICT_LLAMA:
            tool = self.prompt_critic_agent(
                self.critic_llm,
                tool_prompt,
                max_tokens=64,
                answer=answer,
                call_kind="tool_planning",
            )
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
                    call_kind="tool_planning",
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
            tool_selection_text = self.critic_llm.query_with_retries(context, max_tokens=512)
            self._record_llm_call("tool_planning", context, tool_selection_text, 512)
            tool_selections = tool_selection_text
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
        self.critic = ""
        self.critic_posthoc = ""
        self.critic_scratchpad = ""
        self.critic_scratchpad_posthoc = ""
        self.initial_action = ""
        self.mid_action = ""
        self.action = ""
        for spec in getattr(self, "critic_specs", []):
            setattr(self, f"{spec['key']}_critics", [])
            setattr(self, f"{spec['key']}_tool_output", [])
            setattr(self, f"{spec['key']}_critics_posthoc", [])
            setattr(self, f"{spec['key']}_tool_output_posthoc", [])
        self.llm_call_stats = {
            "total_calls": 0,
            "actor_calls": 0,
            "critic_calls": 0,
            "tool_planning_calls": 0,
            "prompt_chars": 0,
            "completion_chars": 0,
            "max_tokens_requested": 0,
        }

    def _runtime_config(self) -> dict[str, Any]:
        return {
            "cost_profile": self.cost_profile,
            "critic_mode": self.critic_mode,
            "feedback_mode": self.feedback_mode,
            "posthoc_policy": self.posthoc_policy,
            "critic_tools_enabled": self.critic_tools_enabled,
            "early_stop": self.early_stop,
            "solidity_prompt_mode": self.solidity_prompt_mode,
            "critic_rounds": self.critic_rounds,
        }

    def _record_llm_call(self, kind: str, prompt: str, output: str, max_tokens: int) -> None:
        if not hasattr(self, "llm_call_stats"):
            return
        self.llm_call_stats["total_calls"] += 1
        if kind == "actor":
            self.llm_call_stats["actor_calls"] += 1
        elif kind == "critic":
            self.llm_call_stats["critic_calls"] += 1
        elif kind == "tool_planning":
            self.llm_call_stats["tool_planning_calls"] += 1
        self.llm_call_stats["prompt_chars"] += len(prompt or "")
        self.llm_call_stats["completion_chars"] += len(output or "")
        self.llm_call_stats["max_tokens_requested"] += int(max_tokens or 0)

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
        classification_counts = metrics.get("slither_classification_counts") or {}
        if isinstance(classification_counts, dict) and classification_counts:
            weights_by_classification = {
                "security_blocking": 100_000,
                "security_review": 1_000,
                "spec_conflict": 50,
                "quality_warning": 10,
                "acceptable_pattern": 1,
            }
            score = 0
            for classification, classification_count in classification_counts.items():
                score += weights_by_classification.get(str(classification), 10) * int(classification_count or 0)
            return score
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
        formatted = format_step(output)
        self._record_llm_call("actor" if main_action else "critic", prompt, formatted, max_tokens)
        return formatted

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
        call_kind: str = "critic",
    ) -> str:
        del fewshots
        stop_seqs = stop_seqs or []
        prompt = self._build_critic_agent_prompt(prompt_template, "", answer, query=query)
        formatted = format_step(llm_module.query_with_retries(prompt, max_tokens=max_tokens, stop_seqs=stop_seqs))
        self._record_llm_call(call_kind, prompt, formatted, max_tokens)
        return formatted

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
