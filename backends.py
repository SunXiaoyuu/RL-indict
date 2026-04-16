from __future__ import annotations

import json
import re
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
                        abi_result=None,
                        test_result=None,
                        vulnerability_count=None,
                        severity_counts={},
                        max_gas_value=None,
                    )
                    return BackendObservation(
                        summary=summary,
                        details={
                            "compile": compile_result,
                            "abi": None,
                            "tests": None,
                            "slither": None,
                            "gas": None,
                            "vulnerability_count": None,
                            "vulnerability_severity_counts": {},
                            "slither_findings": [],
                            "slither_classification_counts": {},
                            "test_diagnostics": self._empty_test_diagnostics(command_success=None),
                            "max_gas_value": None,
                            "skipped_after_compile_failure": True,
                        },
                    )

                abi_result = self._check_abi_conformity(workdir, context)

                test_result = None
                test_command = self._test_command(workdir, context)
                if test_command is not None:
                    test_result = self._run_command(test_command, workdir)
                test_diagnostics = self._parse_test_diagnostics(test_result)

                gas_result = None
                gas_command = self._gas_command(workdir, context)
                if gas_command is not None:
                    gas_result = self._run_command(gas_command, workdir)

                slither_result = None
                slither_json_path = workdir / "slither-result.json"
                slither_command = self._slither_command(workdir, context, slither_json_path)
                if slither_command is not None:
                    slither_result = self._run_command(slither_command, workdir)

                (
                    vulnerability_count,
                    severity_counts,
                    slither_findings,
                    slither_classification_counts,
                ) = self._parse_slither_count(slither_json_path)
                max_gas_value = None
                if gas_result is not None and gas_result["success"]:
                    max_gas_value = self._parse_gas_output(f"{gas_result['stdout']}\n{gas_result['stderr']}")

                summary = self._build_summary(
                    compile_result=compile_result,
                    abi_result=abi_result,
                    test_result=test_result,
                    vulnerability_count=vulnerability_count,
                    severity_counts=severity_counts,
                    max_gas_value=max_gas_value,
                )
                details = {
                    "compile": compile_result,
                    "abi": abi_result,
                    "tests": test_result,
                    "slither": slither_result,
                    "gas": gas_result,
                    "vulnerability_count": vulnerability_count,
                    "vulnerability_severity_counts": severity_counts,
                    "slither_findings": slither_findings,
                    "slither_classification_counts": slither_classification_counts,
                    "test_diagnostics": test_diagnostics,
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

    def _check_abi_conformity(self, workdir: Path, context: dict[str, str]) -> dict[str, Any]:
        required = self._normalize_signature_list(self.sample_metadata.get("required_abi_signatures", []))
        forbidden = self._normalize_signature_list(self.sample_metadata.get("forbidden_abi_signatures", []))
        if not required and not forbidden:
            return {
                "checked": False,
                "success": None,
                "required": [],
                "forbidden": [],
                "available": [],
                "missing": [],
                "forbidden_present": [],
            }

        try:
            artifact_path = self._find_contract_artifact(workdir, context)
            if artifact_path is not None:
                abi = self._load_abi_from_artifact(artifact_path)
                abi_source = str(artifact_path)
            else:
                abi, abi_source = self._load_abi_from_solc(workdir, context)
            available = sorted(self._abi_signatures(abi))
        except Exception as exc:
            return {
                "checked": True,
                "success": False,
                "required": required,
                "forbidden": forbidden,
                "available": [],
                "missing": required,
                "forbidden_present": [],
                "error": str(exc),
            }

        available_set = set(available)
        missing = [signature for signature in required if signature not in available_set]
        forbidden_present = [signature for signature in forbidden if signature in available_set]
        return {
            "checked": True,
            "success": len(missing) == 0 and len(forbidden_present) == 0,
            "required": required,
            "forbidden": forbidden,
            "available": available,
            "missing": missing,
            "forbidden_present": forbidden_present,
            "artifact": abi_source,
        }

    def _load_abi_from_artifact(self, artifact_path: Path) -> list[dict[str, Any]]:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        abi = artifact.get("abi", [])
        if isinstance(abi, str):
            abi = json.loads(abi)
        if not isinstance(abi, list):
            raise ValueError(f"Artifact ABI is not a list: {artifact_path}")
        return abi

    def _load_abi_from_solc(self, workdir: Path, context: dict[str, str]) -> tuple[list[dict[str, Any]], str]:
        if not self._tool_exists("solc"):
            raise FileNotFoundError("Compiled contract artifact not found and solc is unavailable for ABI extraction.")

        command = f"solc {self._build_solc_flags(workdir)} --combined-json abi \"{context['source_relpath']}\""
        result = self._run_command(command, workdir)
        if not result["success"]:
            error_text = result["stderr"].strip() or result["stdout"].strip() or "Unknown solc ABI extraction error."
            raise RuntimeError(error_text)

        data = json.loads(result["stdout"])
        contracts = data.get("contracts", {})
        contract_name = self.sample_metadata.get("contract_name")
        for key, value in contracts.items():
            if key.split(":")[-1] != contract_name:
                continue
            abi = value.get("abi", [])
            if isinstance(abi, str):
                abi = json.loads(abi)
            if not isinstance(abi, list):
                raise ValueError(f"solc ABI is not a list for {key}")
            return abi, f"solc:{key}"

        raise FileNotFoundError(f"ABI for contract {contract_name} not found in solc output.")

    def _find_contract_artifact(self, workdir: Path, context: dict[str, str]) -> Path | None:
        contract_name = self.sample_metadata.get("contract_name")
        if not contract_name:
            return None

        source_name = Path(context["source_relpath"]).name
        direct = workdir / "out" / source_name / f"{contract_name}.json"
        if direct.exists():
            return direct

        candidates = sorted((workdir / "out").glob(f"**/{contract_name}.json"))
        for candidate in candidates:
            if candidate.name == f"{contract_name}.json":
                return candidate
        return None

    def _abi_signatures(self, abi: list[dict[str, Any]]) -> set[str]:
        signatures: set[str] = set()
        for item in abi:
            item_type = item.get("type")
            if item_type == "function":
                name = item.get("name")
                if not name:
                    continue
                signatures.add(f"{name}({self._abi_input_types(item)})")
            elif item_type == "constructor":
                signatures.add(f"constructor({self._abi_input_types(item)})")
            elif item_type == "receive":
                signatures.add("receive()")
            elif item_type == "fallback":
                signatures.add("fallback()")
        return signatures

    def _abi_input_types(self, abi_item: dict[str, Any]) -> str:
        return ",".join(self._canonical_abi_type(input_item) for input_item in abi_item.get("inputs", []))

    def _canonical_abi_type(self, input_item: dict[str, Any]) -> str:
        abi_type = str(input_item.get("type", "")).strip()
        if abi_type == "tuple":
            components = ",".join(self._canonical_abi_type(component) for component in input_item.get("components", []))
            return f"({components})"
        if abi_type.startswith("tuple["):
            suffix = abi_type[len("tuple") :]
            components = ",".join(self._canonical_abi_type(component) for component in input_item.get("components", []))
            return f"({components}){suffix}"
        return self._normalize_signature_type(abi_type)

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
            rendered = self._normalize_signature(signature)
            if rendered:
                normalized.append(rendered)
        return normalized

    def _normalize_signature(self, signature: str) -> str:
        signature = "".join(signature.strip().split())
        if not signature:
            return ""
        if "(" not in signature or not signature.endswith(")"):
            return signature
        name, raw_args = signature.split("(", 1)
        raw_args = raw_args[:-1]
        if not raw_args:
            return f"{name}()"
        args = ",".join(self._normalize_signature_type(arg) for arg in raw_args.split(","))
        return f"{name}({args})"

    def _normalize_signature_type(self, abi_type: str) -> str:
        return abi_type.replace("addresspayable", "address")

    def _build_summary(
        self,
        compile_result: dict[str, Any],
        abi_result: dict[str, Any] | None,
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

        if abi_result is None or not abi_result.get("checked"):
            lines.append("ABI: not checked.")
        elif abi_result.get("success"):
            lines.append("ABI: passed.")
        else:
            issues = []
            if abi_result.get("missing"):
                issues.append("missing=" + ",".join(abi_result["missing"]))
            if abi_result.get("forbidden_present"):
                issues.append("forbidden_present=" + ",".join(abi_result["forbidden_present"]))
            if abi_result.get("error"):
                issues.append(f"error={abi_result['error']}")
            issue_text = "; ".join(issues) if issues else "unknown mismatch"
            lines.append(f"ABI: failed ({issue_text}).")

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

    def _parse_slither_count(self, json_path: Path) -> tuple[int | None, dict[str, int], list[dict[str, Any]], dict[str, int]]:
        if not json_path.exists():
            return None, {}, [], {}
        data = json.loads(json_path.read_text(encoding="utf-8"))
        detectors = data.get("results", {}).get("detectors", [])
        severity_counts: dict[str, int] = {}
        classification_counts: dict[str, int] = {}
        findings: list[dict[str, Any]] = []
        for detector in detectors:
            impact = str(detector.get("impact", "unknown")).lower()
            check = str(detector.get("check") or "unknown")
            classification = self._classify_slither_finding(check, detector.get("description", ""), impact)
            severity_counts[impact] = severity_counts.get(impact, 0) + 1
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
            findings.append(
                {
                    "check": check,
                    "impact": impact,
                    "confidence": detector.get("confidence"),
                    "description": self._short_text(detector.get("description", ""), limit=320),
                    "classification": classification,
                    "blocking": classification == "security_blocking",
                }
            )
        return len(detectors), severity_counts, findings, classification_counts

    def _classify_slither_finding(self, check: str, description: Any, impact: str) -> str:
        check_name = str(check or "").lower()
        description_text = str(description or "").lower()
        category = str(self.sample_metadata.get("category") or "").lower()
        contract_name = str(self.sample_metadata.get("contract_name") or "").lower()
        required = set(self._normalize_signature_list(self.sample_metadata.get("required_abi_signatures", [])))

        if impact in {"critical", "high"}:
            return "security_blocking"
        if check_name == "arbitrary-send-eth":
            return "security_blocking"
        if check_name == "locked-ether":
            if "withdraw()" not in required and not any(signature.startswith("withdraw(") for signature in required):
                return "spec_conflict"
            return "security_blocking"
        if check_name == "timestamp":
            if any(token in category or token in contract_name for token in ("vesting", "timelock", "lock", "presale", "sale")):
                return "acceptable_pattern"
            return "security_review"
        if check_name in {"events-maths", "events-access", "reentrancy-events"}:
            return "quality_warning"
        if "should emit an event" in description_text:
            return "quality_warning"
        if impact == "medium":
            return "security_review"
        return "quality_warning"

    def _empty_test_diagnostics(self, command_success: bool | None) -> dict[str, Any]:
        return {
            "command_success": command_success,
            "passed_count": None,
            "failed_count": None,
            "failed_tests": [],
            "failure_types": [],
            "repair_hints": [],
        }

    def _parse_test_diagnostics(self, test_result: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(test_result, dict):
            return self._empty_test_diagnostics(command_success=None)

        text = f"{test_result.get('stdout') or ''}\n{test_result.get('stderr') or ''}"
        diagnostics = self._empty_test_diagnostics(command_success=test_result.get("success"))
        diagnostics["passed_count"] = len(re.findall(r"^\[PASS\]\s+", text, flags=re.MULTILINE))
        failed_tests: list[dict[str, Any]] = []

        seen_failures: set[tuple[str, str, str | None]] = set()
        for match in re.finditer(
            r"^\[FAIL(?:: (?P<reason>[^\]]+))?\]\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\(\)\s*(?:\(gas:\s*(?P<gas>\d+)\))?",
            text,
            flags=re.MULTILINE,
        ):
            reason = (match.group("reason") or "").strip()
            key = (match.group("name"), reason, match.group("gas"))
            if key in seen_failures:
                continue
            seen_failures.add(key)
            actual, expected = self._parse_assertion_values(reason)
            failed_tests.append(
                {
                    "name": match.group("name"),
                    "reason": reason,
                    "gas": int(match.group("gas")) if match.group("gas") else None,
                    "failure_type": self._classify_test_failure(reason, match.group("name")),
                    "expected": expected,
                    "actual": actual,
                    "repair_hint": self._test_repair_hint(match.group("name"), reason),
                }
            )

        summary_match = re.search(
            r"Suite result:\s+\w+\.\s+(?P<passed>\d+)\s+passed;\s+(?P<failed>\d+)\s+failed",
            text,
        )
        if summary_match:
            diagnostics["passed_count"] = int(summary_match.group("passed"))
            diagnostics["failed_count"] = int(summary_match.group("failed"))
        else:
            diagnostics["failed_count"] = len(failed_tests)

        diagnostics["failed_tests"] = failed_tests
        diagnostics["failure_types"] = sorted({test["failure_type"] for test in failed_tests if test.get("failure_type")})
        diagnostics["repair_hints"] = sorted({test["repair_hint"] for test in failed_tests if test.get("repair_hint")})
        return diagnostics

    def _classify_test_failure(self, reason: str, test_name: str = "") -> str:
        combined = f"{test_name} {reason}".lower()
        lowered = reason.lower()
        if not reason and not test_name:
            return "unknown_failure"
        if "public" in combined or "presale" in combined or "sale" in combined:
            return "sale_phase_transition"
        if "only deployer" in combined or "owner" in combined or "unauthorized" in combined or "not owner" in combined:
            return "access_control_or_initialization"
        if "assertion failed" in lowered or "!=" in reason:
            if "0x" in reason and ("416c696365" in lowered or len(reason) > 80):
                return "return_encoding_mismatch"
            return "assertion_mismatch"
        if "revert" in lowered or "cannot" in lowered or "invalid" in lowered:
            return "unexpected_revert"
        return "test_revert_or_failure"

    def _parse_assertion_values(self, reason: str) -> tuple[str | None, str | None]:
        match = re.search(r"assertion failed:\s*(?P<actual>.+?)\s*!=\s*(?P<expected>.+)$", reason)
        if not match:
            return None, None
        return match.group("actual").strip(), match.group("expected").strip()

    def _test_repair_hint(self, test_name: str, reason: str) -> str:
        combined = f"{test_name} {reason}".lower()
        if "public" in combined or "presale" in combined or "sale" in combined:
            return "Inspect sale state transitions, constructor initial state, and startPresale/startPublicSale guards."
        if "owner" in combined or "deployer" in combined or "unauthorized" in combined:
            return "Inspect owner/deployer initialization and only-owner permission checks."
        if "0x" in combined and ("assertion failed" in combined or "!=" in combined):
            return "Inspect return encoding; tests may expect a plain string or exact stored value rather than a hash/bytes32 surrogate."
        if "assertion failed" in combined or "!=" in combined:
            return "Inspect the state variable or mapping updated by the tested function."
        return "Inspect the failed test's target function and preserve the required ABI."

    def _short_text(self, value: Any, limit: int = 320) -> str:
        text = " ".join(str(value or "").split())
        if len(text) > limit:
            return text[: limit - 3].rstrip() + "..."
        return text

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
