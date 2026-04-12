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

        for spec in self.critic_specs:
            key = spec["key"]
            output[f"{key}_critics"] = getattr(self, f"{key}_critics")
            output[f"{key}_tool_output"] = getattr(self, f"{key}_tool_output")

        if self._has_posthoc():
            output["initial_action_execution_observation"] = getattr(self, "initial_action_execution", "")
            output["initial_action_execution_metrics"] = getattr(self, "initial_action_execution_metrics", {})
            output["execution_observation"] = getattr(self, "action_execution", "")
            output["execution_metrics"] = getattr(self, "action_execution_metrics", {})
            output["mid_action_execution_observation"] = getattr(self, "mid_action_execution", "")
            output["mid_action_execution_metrics"] = getattr(self, "mid_action_execution_metrics", {})
            output["final_action_execution_observation"] = getattr(self, "final_action_execution", "")
            output["final_action_execution_metrics"] = getattr(self, "final_action_execution_metrics", {})
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
        self.scratchpad += "\nCritic: " + self.critic + "\nImproved Solution: " + self.action_prompt_header
        self.initial_action = self.action
        self.action = self.prompt_agent(self.action_llm, self.actor_prompt, stop_seqs=["\nCritic:"])
        self.scratchpad += self.action

        if not self._has_posthoc():
            return

        initial_observation = self.execution_backend.evaluate(extract_code(self.initial_action), code_before=self.code_before)
        self.initial_action_execution = initial_observation.to_text()
        self.initial_action_execution_metrics = initial_observation.as_dict()

        observation = self.execution_backend.evaluate(extract_code(self.action), code_before=self.code_before)
        self.action_execution = observation.to_text()
        self.action_execution_metrics = observation.as_dict()
        self.mid_action_execution = self.action_execution
        self.mid_action_execution_metrics = self.action_execution_metrics
        self.scratchpad += "\nObservation: " + self.action_execution

        self.critic_posthoc = self.perform_critic_debate(
            answer=self.action,
            max_steps=self.critic_rounds,
            posthoc=True,
        )

        self.scratchpad = ""
        self.scratchpad += "\nInitial Solution: " + self.initial_action
        self.scratchpad += "\nCritic: " + self.critic
        self.scratchpad += "\nFirst Improved Solution: " + self.action
        self.scratchpad += "\nCritic: " + self.critic_posthoc
        self.scratchpad += "\nSecond Improved Solution: " + self.action_prompt_header
        self.mid_action = self.action
        self.action = self.prompt_agent(self.action_llm, self.actor_prompt, stop_seqs=["\nCritic:"])
        self.scratchpad += self.action
        final_observation = self.execution_backend.evaluate(extract_code(self.action), code_before=self.code_before)
        self.final_action_execution = final_observation.to_text()
        self.final_action_execution_metrics = final_observation.as_dict()

        if self._compile_success(self.mid_action_execution_metrics) and not self._compile_success(self.final_action_execution_metrics):
            self.rejected_action = self.action
            self.action = self.mid_action
            self.action_execution = self.mid_action_execution
            self.action_execution_metrics = self.mid_action_execution_metrics
            self.degradation_guard = "reverted_to_mid_action_after_final_compile_failure"
            self.scratchpad += (
                "\nDegradation Guard: final rewrite failed compilation; "
                "reverted to the first improved solution."
            )
        else:
            self.action_execution = self.final_action_execution
            self.action_execution_metrics = self.final_action_execution_metrics

        if self._is_better_outcome(self.initial_action_execution_metrics, self.action_execution_metrics):
            self.rejected_action = self.action
            self.action = self.initial_action
            self.action_execution = self.initial_action_execution
            self.action_execution_metrics = self.initial_action_execution_metrics
            initial_guard = "reverted_to_initial_action_after_better_compile_or_test_outcome"
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
                    max_tokens=128,
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

    @classmethod
    def _is_better_outcome(cls, candidate_metrics: dict[str, Any] | None, baseline_metrics: dict[str, Any] | None) -> bool:
        candidate_compile = cls._compile_success(candidate_metrics)
        baseline_compile = cls._compile_success(baseline_metrics)
        if candidate_compile != baseline_compile:
            return candidate_compile and not baseline_compile

        if not candidate_compile:
            return False

        candidate_tests = cls._tests_success(candidate_metrics)
        baseline_tests = cls._tests_success(baseline_metrics)
        if candidate_tests != baseline_tests:
            return candidate_tests and not baseline_tests

        candidate_abi = cls._abi_success(candidate_metrics)
        baseline_abi = cls._abi_success(baseline_metrics)
        return candidate_abi and not baseline_abi

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
                question=self.question,
                answer=answer,
                scratchpad=self.scratchpad,
            )
        return prompt_template.format(
            question=self.question,
            answer=answer,
            scratchpad=self.scratchpad,
        )
