from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BackendObservation:
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_text(self) -> str:
        return self.summary.strip()

    def as_dict(self) -> dict[str, Any]:
        payload = dict(self.details)
        payload["summary"] = self.to_text()
        return payload


class BaseExecutionBackend:
    def supports_posthoc(self) -> bool:
        return False

    def evaluate(self, generated_code: str, code_before: str = "") -> BackendObservation:
        raise NotImplementedError


class NullExecutionBackend(BaseExecutionBackend):
    pass


class PythonExecutionBackend(BaseExecutionBackend):
    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def supports_posthoc(self) -> bool:
        return True

    def evaluate(self, generated_code: str, code_before: str = "") -> BackendObservation:
        combined_code = f"{code_before}{generated_code}"
        try:
            with tempfile.TemporaryDirectory(prefix="indict_python_") as temp_dir:
                code_path = Path(temp_dir) / "generated.py"
                code_path.write_text(combined_code, encoding="utf-8")
                completed = subprocess.run(
                    [sys.executable, str(code_path)],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )

            stdout = completed.stdout.strip()
            stderr = completed.stderr.strip()
            if completed.returncode == 0:
                summary = stdout or "Solution executed successfully without any runtime error."
            else:
                error_text = stderr or stdout or f"Process exited with code {completed.returncode}."
                summary = f"Execution failed: {error_text}"

            return BackendObservation(
                summary=summary,
                details={
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "success": completed.returncode == 0,
                },
            )
        except Exception as exc:
            return BackendObservation(
                summary=f"Execution failed: {exc}",
                details={"success": False, "error": str(exc)},
            )


class SolidityExecutionBackend(BaseExecutionBackend):
    def __init__(self, sample_metadata: dict[str, Any] | None = None, timeout_seconds: int = 180) -> None:
        self.sample_metadata = sample_metadata or {}
        self.timeout_seconds = timeout_seconds

    def supports_posthoc(self) -> bool:
        return True

    def evaluate(self, generated_code: str, code_before: str = "") -> BackendObservation:
        del code_before
        try:
            with tempfile.TemporaryDirectory(prefix="indict_solidity_") as temp_dir:
                workdir = Path(temp_dir)
                context = self._prepare_workspace(workdir, generated_code)

                compile_command = self._compile_command(workdir, context)
                compile_result = self._run_command(compile_command, workdir)

                if not compile_result["success"]:
                    summary = self._build_summary(
                        compile_result=compile_result,
                        test_result=None,
                        vulnerability_count=None,
                        severity_counts={},
                        max_gas_value=None,
                    )
                    return BackendObservation(
                        summary=summary,
                        details={
                            "compile": compile_result,
                            "tests": None,
                            "slither": None,
                            "gas": None,
                            "vulnerability_count": None,
                            "vulnerability_severity_counts": {},
                            "max_gas_value": None,
                            "skipped_after_compile_failure": True,
                        },
                    )

                test_result = None
                test_command = self._test_command(workdir, context)
                if test_command is not None:
                    test_result = self._run_command(test_command, workdir)

                gas_result = None
                gas_command = self._gas_command(workdir, context)
                if gas_command is not None:
                    gas_result = self._run_command(gas_command, workdir)

                slither_result = None
                slither_json_path = workdir / "slither-result.json"
                slither_command = self._slither_command(workdir, context, slither_json_path)
                if slither_command is not None:
                    slither_result = self._run_command(slither_command, workdir)

                vulnerability_count, severity_counts = self._parse_slither_count(slither_json_path)
                max_gas_value = None
                if gas_result is not None and gas_result["success"]:
                    max_gas_value = self._parse_gas_output(f"{gas_result['stdout']}\n{gas_result['stderr']}")

                summary = self._build_summary(
                    compile_result=compile_result,
                    test_result=test_result,
                    vulnerability_count=vulnerability_count,
                    severity_counts=severity_counts,
                    max_gas_value=max_gas_value,
                )
                details = {
                    "compile": compile_result,
                    "tests": test_result,
                    "slither": slither_result,
                    "gas": gas_result,
                    "vulnerability_count": vulnerability_count,
                    "vulnerability_severity_counts": severity_counts,
                    "max_gas_value": max_gas_value,
                }
                return BackendObservation(summary=summary, details=details)
        except Exception as exc:
            return BackendObservation(
                summary=f"Solidity evaluation failed: {exc}",
                details={"success": False, "error": str(exc)},
            )

    def _prepare_workspace(self, workdir: Path, generated_code: str) -> dict[str, str]:
        template_dir = self.sample_metadata.get("project_template_dir")
        if template_dir:
            template_path = Path(template_dir).resolve()
            if template_path.exists():
                shutil.copytree(template_path, workdir, dirs_exist_ok=True)

        (workdir / "src").mkdir(exist_ok=True)
        (workdir / "test").mkdir(exist_ok=True)

        for item in self.sample_metadata.get("extra_files", []):
            target_path = workdir / item["path"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if "content" in item:
                target_path.write_text(item["content"], encoding="utf-8")
            elif "source" in item:
                shutil.copy2(Path(item["source"]).resolve(), target_path)

        source_relpath = self.sample_metadata.get("source_relpath", "src/Generated.sol")
        source_path = workdir / source_relpath
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_text = self._build_source_text(source_path, generated_code)
        source_path.write_text(source_text, encoding="utf-8")

        test_relpath = self.sample_metadata.get("test_relpath", "test/Generated.t.sol")
        if "test_code" in self.sample_metadata:
            test_path = workdir / test_relpath
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text(self.sample_metadata["test_code"], encoding="utf-8")
        elif "test_file" in self.sample_metadata:
            test_path = workdir / test_relpath
            test_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(self.sample_metadata["test_file"]).resolve(), test_path)

        return {
            "source_relpath": source_relpath,
            "test_relpath": test_relpath,
            "slither_target": self.sample_metadata.get("slither_target", source_relpath),
        }

    def _build_source_text(self, source_path: Path, generated_code: str) -> str:
        start_line = self.sample_metadata.get("replace_start_line")
        end_line = self.sample_metadata.get("replace_end_line")
        if start_line is not None and end_line is not None and source_path.exists():
            return self._replace_line_range(
                source_path=source_path,
                generated_code=generated_code,
                start_line=int(start_line),
                end_line=int(end_line),
            )
        return f"{self.sample_metadata.get('source_prefix', '')}{generated_code}{self.sample_metadata.get('source_suffix', '')}"

    def _replace_line_range(self, source_path: Path, generated_code: str, start_line: int, end_line: int) -> str:
        original_lines = source_path.read_text(encoding="utf-8").splitlines(keepends=True)
        if start_line < 1 or end_line < start_line or end_line > len(original_lines):
            raise ValueError(
                f"Invalid replacement range {start_line}-{end_line} for {source_path} with {len(original_lines)} lines."
            )

        replacement = self._indent_replacement(original_lines[start_line - 1], generated_code)
        if replacement and not replacement.endswith(("\n", "\r")):
            replacement += "\n"

        prefix = "".join(original_lines[: start_line - 1])
        suffix = "".join(original_lines[end_line:])
        return prefix + replacement + suffix

    def _indent_replacement(self, original_line: str, generated_code: str) -> str:
        normalized = generated_code.strip("\n")
        if not normalized:
            return ""
        indent = original_line[: len(original_line) - len(original_line.lstrip(" \t"))]
        rendered_lines = normalized.splitlines()
        whitespace = " \t"
        rendered_lines[0] = indent + rendered_lines[0].lstrip(whitespace)
        return "\n".join(rendered_lines)

    def _compile_command(self, workdir: Path, context: dict[str, str]) -> str:
        explicit = self.sample_metadata.get("compile_command")
        if explicit:
            return explicit.format(**context)
        if self._tool_exists("forge") and (workdir / "foundry.toml").exists():
            return "forge build"
        return f"solc {self._build_solc_flags(workdir)} --abi \"{context['source_relpath']}\""

    def _test_command(self, workdir: Path, context: dict[str, str]) -> str | None:
        explicit = self.sample_metadata.get("test_command")
        if explicit:
            return explicit.format(**context)
        test_file = workdir / context["test_relpath"]
        if self._tool_exists("forge") and test_file.exists():
            return f"forge test --match-path \"{context['test_relpath']}\" -vv"
        return None

    def _gas_command(self, workdir: Path, context: dict[str, str]) -> str | None:
        explicit = self.sample_metadata.get("gas_command")
        if explicit:
            return explicit.format(**context)
        test_file = workdir / context["test_relpath"]
        if self._tool_exists("forge") and test_file.exists():
            return f"forge test --match-path \"{context['test_relpath']}\" --gas-report"
        return f"solc {self._build_solc_flags(workdir)} --gas \"{context['source_relpath']}\""

    def _slither_command(self, workdir: Path, context: dict[str, str], json_path: Path) -> str | None:
        explicit = self.sample_metadata.get("slither_command")
        if explicit:
            return explicit.format(slither_json=str(json_path.resolve()), **context)
        if not self._tool_exists("slither"):
            return None
        if (workdir / "foundry.toml").exists():
            return (
                f"slither \"{context['slither_target']}\" "
                f"--exclude-dependencies "
                f"--exclude-informational "
                f"--exclude-optimization "
                f"--fail-none "
                f"--json \"{json_path.resolve()}\""
            )
        solc_args = self._build_relative_solc_flags().replace('"', '\\"')
        return (
            f"slither \"{context['slither_target']}\" "
            f"--compile-force-framework solc "
            f"--solc-working-dir . "
            f"--solc-args \"{solc_args}\" "
            f"--exclude-dependencies "
            f"--exclude-informational "
            f"--exclude-optimization "
            f"--fail-none "
            f"--json \"{json_path.resolve()}\""
        )

    def _build_solc_flags(self, workdir: Path) -> str:
        include_paths = [".", "node_modules", *self.sample_metadata.get("include_paths", [])]
        flags = [f'--base-path "{workdir}"']
        for include_path in include_paths:
            candidate = (workdir / include_path).resolve()
            if candidate.exists():
                flags.append(f'--include-path "{candidate}"')
        flags.append(f'--allow-paths "{workdir}"')
        if self.sample_metadata.get("evm_version"):
            flags.append(f'--evm-version {self.sample_metadata["evm_version"]}')
        if self.sample_metadata.get("solc_args"):
            flags.append(self.sample_metadata["solc_args"])
        return " ".join(flags)

    def _build_relative_solc_flags(self) -> str:
        include_paths = [".", *self.sample_metadata.get("include_paths", [])]
        flags = ["--base-path ."]
        for include_path in include_paths:
            flags.append(f"--include-path {include_path}")
        flags.append("--allow-paths .")
        if self.sample_metadata.get("evm_version"):
            flags.append(f'--evm-version {self.sample_metadata["evm_version"]}')
        if self.sample_metadata.get("solc_args"):
            flags.append(self.sample_metadata["solc_args"])
        return " ".join(flags)

    def _run_command(self, command: str, cwd: Path) -> dict[str, Any]:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            shell=True,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "success": completed.returncode == 0,
        }

    def _build_summary(
        self,
        compile_result: dict[str, Any],
        test_result: dict[str, Any] | None,
        vulnerability_count: int | None,
        severity_counts: dict[str, int],
        max_gas_value: int | None,
    ) -> str:
        lines = []

        if compile_result["success"]:
            lines.append("Compilation: success.")
        else:
            error_text = compile_result["stderr"].strip() or compile_result["stdout"].strip() or "Unknown compiler error."
            lines.append(f"Compilation: failed. {error_text}")

        if test_result is None:
            lines.append("Tests: skipped (no Solidity test command available).")
        elif test_result["success"]:
            lines.append("Tests: passed.")
        else:
            error_text = test_result["stderr"].strip() or test_result["stdout"].strip() or "Unknown test failure."
            lines.append(f"Tests: failed. {error_text}")

        if vulnerability_count is None:
            lines.append("Static analysis: skipped.")
        elif vulnerability_count == 0:
            lines.append("Static analysis: no Slither findings.")
        else:
            severity_text = ", ".join(f"{key}={value}" for key, value in sorted(severity_counts.items()))
            if severity_text:
                lines.append(f"Static analysis: {vulnerability_count} finding(s) ({severity_text}).")
            else:
                lines.append(f"Static analysis: {vulnerability_count} finding(s).")

        if max_gas_value is None:
            lines.append("Gas analysis: unavailable.")
        else:
            lines.append(f"Gas analysis: max observed value {max_gas_value}.")

        return " ".join(lines)

    def _parse_slither_count(self, json_path: Path) -> tuple[int | None, dict[str, int]]:
        if not json_path.exists():
            return None, {}
        data = json.loads(json_path.read_text(encoding="utf-8"))
        detectors = data.get("results", {}).get("detectors", [])
        severity_counts: dict[str, int] = {}
        for detector in detectors:
            impact = str(detector.get("impact", "unknown")).lower()
            severity_counts[impact] = severity_counts.get(impact, 0) + 1
        return len(detectors), severity_counts

    def _parse_gas_output(self, text: str) -> int | None:
        forge_report_value = self._parse_forge_gas_report(text)
        if forge_report_value is not None:
            return forge_report_value

        return self._parse_solc_gas_output(text)

    def _parse_forge_gas_report(self, text: str) -> int | None:
        max_value = None
        awaiting_deployment_row = False
        in_function_table = False

        for line in text.splitlines():
            stripped = line.strip()
            if "|" not in stripped:
                continue

            cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
            if not cells:
                continue

            first_cell = cells[0].lower()
            if first_cell == "deployment cost":
                awaiting_deployment_row = True
                in_function_table = False
                continue
            if first_cell == "function name":
                awaiting_deployment_row = False
                in_function_table = True
                continue
            if not any(cells):
                continue

            if awaiting_deployment_row:
                deployment_cost = self._parse_number(cells[0])
                if deployment_cost is not None:
                    max_value = deployment_cost if max_value is None else max(max_value, deployment_cost)
                    awaiting_deployment_row = False
                continue

            if in_function_table and len(cells) >= 5:
                # Forge gas reports use: Function Name | Min | Avg | Median | Max | # Calls.
                function_max = self._parse_number(cells[4])
                if function_max is not None:
                    max_value = function_max if max_value is None else max(max_value, function_max)

        return max_value

    def _parse_solc_gas_output(self, text: str) -> int | None:
        max_value = None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or "infinite" in stripped.lower():
                continue
            if "|" in stripped:
                table_max = self._parse_gas_report_line(stripped)
                if table_max is not None:
                    max_value = table_max if max_value is None else max(max_value, table_max)
                continue
            if "=" in stripped:
                tail = stripped.split("=")[-1].strip()
                candidate = self._parse_number(tail)
                if candidate is not None:
                    max_value = candidate if max_value is None else max(max_value, candidate)
                    continue
            if ":" in stripped:
                tail = stripped.split(":", 1)[-1].strip()
                candidate = self._parse_number(tail)
                if candidate is not None:
                    max_value = candidate if max_value is None else max(max_value, candidate)
        return max_value

    def _parse_gas_report_line(self, line: str) -> int | None:
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if not cells:
            return None
        numeric_candidates = []
        for cell in cells:
            candidate = self._parse_number(cell)
            if candidate is not None:
                numeric_candidates.append(candidate)
        if not numeric_candidates:
            return None
        return max(numeric_candidates)

    def _parse_number(self, text: str) -> int | None:
        digits = "".join(ch for ch in text if ch.isdigit() or ch == ",")
        if not digits:
            return None
        normalized = digits.replace(",", "")
        if not normalized:
            return None
        return int(normalized)

    def _tool_exists(self, name: str) -> bool:
        return shutil.which(name) is not None


def create_execution_backend(
    task: str | None = None,
    programming_language: str | None = None,
    sample_metadata: dict[str, Any] | None = None,
) -> BaseExecutionBackend:
    language = (programming_language or "").lower()
    task_name = (task or "").lower()

    if task_name == "solidity" or language == "solidity":
        return SolidityExecutionBackend(sample_metadata=sample_metadata)
    if language == "python":
        return PythonExecutionBackend()
    return NullExecutionBackend()
