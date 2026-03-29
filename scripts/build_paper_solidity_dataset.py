#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pickle
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT = Path("data/solidity_paper_50.json")
DEFAULT_LIMIT = 50
DEFAULT_REPO_QUOTAS = {
    "Account2": 2,
    "openzeppelin-contracts": 17,
    "solady": 31,
}
FALLBACK_REPOS = [
    "openzeppelin-community-contracts",
    "openzeppelin-foundry-upgrades",
    "ethernaut",
    "openzeppelin-contracts-upgradeable",
    "uniswap-solidity-hooks-template",
]
VISIBILITY_SCORES = {
    "external": 5,
    "public": 4,
    "internal": 3,
    "private": 2,
    "": 1,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a paper-derived Solidity dataset using SolAgent annotations and SolEval repositories."
    )
    parser.add_argument("--solagent-dir", default="SolAgent", help="Path to the local SolAgent directory.")
    parser.add_argument("--soleval-dir", default="SolEval", help="Path to the local SolEval directory.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Where to write the generated dataset JSON.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Number of samples to produce.")
    return parser.parse_args()


def normalize_repo_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if normalized.startswith("/root/"):
        normalized = f"repository/{normalized[len('/root/'):]}"
    return normalized.lstrip("/")


def parse_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        return None


def normalize_whitespace(value: str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(normalize_whitespace(item) for item in value if item)
    if isinstance(value, dict):
        return " ".join(f"{key}={normalize_whitespace(val)}" for key, val in value.items() if val)
    if not value:
        return ""
    return " ".join(value.split())


def summarize_field(field: Any) -> str:
    if isinstance(field, str):
        return normalize_whitespace(field)
    if not isinstance(field, dict):
        return normalize_whitespace(str(field))
    for key in ("class_method_signature", "full_signature", "signature"):
        if field.get(key):
            return normalize_whitespace(str(field[key]))
    pieces = []
    if field.get("visibility"):
        pieces.append(str(field["visibility"]))
    if field.get("type_name"):
        pieces.append(str(field["type_name"]))
    elif field.get("type"):
        pieces.append(str(field["type"]))
    if field.get("identifier"):
        pieces.append(str(field["identifier"]))
    return normalize_whitespace(" ".join(pieces))


def summarize_methods(methods: list[dict[str, Any]], current_method: dict[str, Any], limit: int = 8) -> list[str]:
    signatures = []
    current_signature = normalize_whitespace(current_method.get("full_signature") or current_method.get("signature"))
    for method in methods:
        if normalize_whitespace(method.get("full_signature") or method.get("signature")) == current_signature:
            continue
        if str(method.get("testcase", "")).strip():
            continue
        signature = normalize_whitespace(method.get("full_signature") or method.get("signature") or method.get("identifier"))
        if signature:
            signatures.append(signature)
    return signatures[:limit]


def summarize_hierarchy(values: list[Any] | Any) -> str:
    if not values:
        return ""
    if not isinstance(values, list):
        values = [values]
    rendered = []
    for value in values:
        if isinstance(value, dict):
            rendered.append(normalize_whitespace(str(value.get("identifier") or value.get("signature") or value)))
        else:
            rendered.append(normalize_whitespace(str(value)))
    rendered = [value for value in rendered if value]
    return ", ".join(rendered)


def method_score(method: dict[str, Any]) -> tuple[int, int, str]:
    body = method.get("body", "") or ""
    start_line = parse_int(method.get("start")) or 0
    end_line = parse_int(method.get("end")) or start_line
    line_count = max(1, end_line - start_line + 1)
    visibility = str(method.get("visibility", "")).strip().lower()
    full_signature = normalize_whitespace(method.get("full_signature") or method.get("signature") or method.get("identifier"))
    comment = normalize_whitespace(method.get("human_labeled_comment") or method.get("comment"))

    score = 0
    score += VISIBILITY_SCORES.get(visibility, 0)
    score += 10 if comment else 0
    score += 5 if full_signature else 0
    score += 3 if method.get("kind") == "function" else 1
    if 3 <= line_count <= 40:
        score += 4
    elif line_count <= 80:
        score += 2
    if "assembly" not in body:
        score += 1
    return score, -line_count, full_signature


def resolve_actual_path(repository_root: Path, dataset_path: str) -> Path | None:
    normalized = normalize_repo_path(dataset_path)
    parts = Path(normalized).parts
    if len(parts) < 3 or parts[0] != "repository":
        return None
    repo_name = parts[1]
    relpath = Path(*parts[2:])
    direct = repository_root / repo_name / relpath
    if direct.exists():
        return direct
    nested = repository_root / repo_name / "lib" / repo_name / relpath
    if nested.exists():
        return nested
    return None


def find_project_root(path: Path) -> Path | None:
    current = path if path.is_dir() else path.parent
    while True:
        if (current / "foundry.toml").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def index_soleval_entries(soleval_dataset: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    index: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for raw_path, entries in soleval_dataset.items():
        normalized_path = normalize_repo_path(raw_path)
        for entry in entries:
            start_line = parse_int(entry.get("start"))
            end_line = parse_int(entry.get("end"))
            identifier = str(entry.get("identifier", "")).strip()
            if start_line is None or end_line is None or not identifier:
                continue
            index[(normalized_path, start_line, end_line, identifier)] = entry
    return index


def choose_method(
    source_path: str,
    items: list[dict[str, Any]],
    soleval_index: dict[tuple[str, int, int, str], dict[str, Any]],
) -> dict[str, Any] | None:
    best_choice = None
    best_rank = None
    for item in items:
        for method in item.get("methods", []):
            if str(method.get("testcase", "")).strip():
                continue
            if method.get("kind") not in {"function", "constructor"}:
                continue
            start_line = parse_int(method.get("start"))
            end_line = parse_int(method.get("end"))
            if start_line is None or end_line is None:
                continue
            body = method.get("body", "") or ""
            if not body.strip():
                continue

            rank = method_score(method)
            if best_rank is not None and rank <= best_rank:
                continue
            best_rank = rank
            soleval_entry = soleval_index.get(
                (normalize_repo_path(source_path), start_line, end_line, str(method.get("identifier", "")).strip())
            )
            best_choice = {
                "item": item,
                "method": method,
                "soleval_entry": soleval_entry,
            }
    return best_choice


def difficulty_from_lines(start_line: int, end_line: int) -> str:
    line_count = max(1, end_line - start_line + 1)
    if line_count <= 8:
        return "easy"
    if line_count <= 20:
        return "medium"
    return "hard"


def render_instruction(
    *,
    repo_name: str,
    source_relpath: str,
    test_relpath: str,
    item: dict[str, Any],
    method: dict[str, Any],
    soleval_entry: dict[str, Any] | None,
) -> str:
    container_kind = str(item.get("kind") or "contract").strip()
    container_name = str(item.get("identifier") or "UnknownContainer").strip()
    signature = normalize_whitespace(method.get("full_signature") or method.get("signature") or method.get("identifier"))
    comment = normalize_whitespace(method.get("human_labeled_comment") or method.get("comment"))
    if not comment and soleval_entry is not None:
        comment = normalize_whitespace(soleval_entry.get("human_labeled_comment") or soleval_entry.get("comment"))

    sibling_signatures = summarize_methods(item.get("methods", []), method)
    field_summaries = [value for value in (summarize_field(field) for field in item.get("fields", [])) if value][:8]
    inheritance = summarize_hierarchy(item.get("superclass"))
    interfaces = summarize_hierarchy(item.get("interfaces"))
    import_directive = normalize_whitespace(
        method.get("import_directive") or (soleval_entry or {}).get("import_directive")
    )
    extra_context = normalize_whitespace((soleval_entry or {}).get("context"))

    lines = [
        "You are completing a Solidity implementation task extracted from the SolAgent/SolEval benchmarks.",
        "",
        "The code will be inserted back into a real Foundry repository and evaluated with the repository's existing Forge tests.",
        "",
        f"Repository: {repo_name}",
        f"Source file: {source_relpath}",
        f"Mapped Forge test file: {test_relpath}",
        f"Enclosing {container_kind}: {container_name}",
        f"Target signature: {signature}",
        "",
        "Requirements:",
        "1. Return only the complete replacement Solidity code for the target function or constructor.",
        "2. Preserve the exact signature, visibility, mutability, and return types unless the benchmark description clearly requires a correction.",
        "3. Do not add new imports, contracts, libraries, state variables, helper functions, or extra surrounding code.",
        "4. The result must remain compatible with the surrounding repository context and should pass the mapped Forge tests.",
        "",
    ]
    if comment:
        lines.extend(["Natural-language specification:", comment, ""])
    if inheritance:
        lines.append(f"Inheritance context: {inheritance}")
    if interfaces:
        lines.append(f"Interface context: {interfaces}")
    if field_summaries:
        lines.append("Relevant fields and members:")
        lines.extend(f"- {field_summary}" for field_summary in field_summaries)
    if sibling_signatures:
        lines.append("Other methods in the same type:")
        lines.extend(f"- {signature_text}" for signature_text in sibling_signatures)
    if import_directive:
        lines.append(f"Existing imports: {import_directive}")
    if extra_context:
        lines.append(f"Additional benchmark context: {extra_context}")
    lines.extend(["", "Return the answer in a single ```solidity``` block."])
    return "\n".join(lines)


def replace_line_range(original_text: str, replacement_text: str, start_line: int, end_line: int) -> str:
    original_lines = original_text.splitlines(keepends=True)
    replacement = indent_replacement(original_lines[start_line - 1], replacement_text)
    if replacement and not replacement.endswith(("\n", "\r")):
        replacement += "\n"
    prefix = "".join(original_lines[: start_line - 1])
    suffix = "".join(original_lines[end_line:])
    return prefix + replacement + suffix


def indent_replacement(original_line: str, replacement_text: str) -> str:
    normalized = replacement_text.strip("\n")
    if not normalized:
        return ""
    indent = original_line[: len(original_line) - len(original_line.lstrip(" \t"))]
    rendered_lines = normalized.splitlines()
    rendered_lines[0] = f"{indent}{rendered_lines[0].lstrip(' \t')}"
    return "\n".join(rendered_lines)


def build_candidates(
    solagent_dataset: dict[str, list[dict[str, Any]]],
    test_mapping: dict[str, str],
    soleval_index: dict[tuple[str, int, int, str], dict[str, Any]],
    repository_root: Path,
    soleval_dir: Path,
) -> list[dict[str, Any]]:
    candidates = []
    for source_key, test_key in sorted(test_mapping.items()):
        if source_key not in solagent_dataset:
            continue
        actual_source = resolve_actual_path(repository_root, source_key)
        actual_test = resolve_actual_path(repository_root, test_key)
        if actual_source is None or actual_test is None:
            continue
        project_root = find_project_root(actual_source)
        test_root = find_project_root(actual_test)
        if project_root is None or test_root is None or project_root != test_root:
            continue

        choice = choose_method(source_key, solagent_dataset[source_key], soleval_index)
        if choice is None:
            continue

        method = choice["method"]
        item = choice["item"]
        source_relpath = actual_source.relative_to(project_root).as_posix()
        test_relpath = actual_test.relative_to(project_root).as_posix()
        start_line = parse_int(method.get("start"))
        end_line = parse_int(method.get("end"))
        if start_line is None or end_line is None:
            continue

        original_text = actual_source.read_text(encoding="utf-8")
        recreated = replace_line_range(original_text, method["body"], start_line, end_line)
        if recreated != original_text:
            continue

        repo_name = Path(normalize_repo_path(source_key)).parts[1]
        instruction = render_instruction(
            repo_name=repo_name,
            source_relpath=source_relpath,
            test_relpath=test_relpath,
            item=item,
            method=method,
            soleval_entry=choice["soleval_entry"],
        )
        project_template_dir = (Path(soleval_dir.name) / project_root.relative_to(soleval_dir)).as_posix()
        candidates.append(
            {
                "repo_name": repo_name,
                "source_key": source_key,
                "test_key": test_key,
                "project_template_dir": project_template_dir,
                "source_relpath": source_relpath,
                "test_relpath": test_relpath,
                "slither_target": source_relpath,
                "instruction": instruction,
                "container_name": item.get("identifier"),
                "container_kind": item.get("kind"),
                "target_identifier": method.get("identifier"),
                "target_signature": method.get("full_signature"),
                "replace_start_line": start_line,
                "replace_end_line": end_line,
                "difficulty": difficulty_from_lines(start_line, end_line),
            }
        )
    return candidates


def select_candidates(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_repo[candidate["repo_name"]].append(candidate)
    for repo_candidates in by_repo.values():
        repo_candidates.sort(key=lambda item: item["source_key"])

    selected: list[dict[str, Any]] = []
    selected_keys: set[tuple[str, str]] = set()
    repo_counts: dict[str, int] = defaultdict(int)

    def try_add(candidate: dict[str, Any]) -> bool:
        key = (candidate["repo_name"], candidate["source_key"])
        if key in selected_keys:
            return False
        selected.append(candidate)
        selected_keys.add(key)
        repo_counts[candidate["repo_name"]] += 1
        return True

    for repo_name, quota in DEFAULT_REPO_QUOTAS.items():
        for candidate in by_repo.get(repo_name, []):
            if repo_counts[repo_name] >= quota:
                break
            try_add(candidate)

    remaining_repos = [
        repo_name for repo_name in DEFAULT_REPO_QUOTAS if repo_name in by_repo
    ] + [repo_name for repo_name in FALLBACK_REPOS if repo_name in by_repo]

    for repo_name in remaining_repos:
        for candidate in by_repo.get(repo_name, []):
            if len(selected) >= limit:
                break
            try_add(candidate)
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for candidate in sorted(candidates, key=lambda item: (item["repo_name"], item["source_key"])):
            if len(selected) >= limit:
                break
            try_add(candidate)

    return selected[:limit]


def finalize_samples(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dataset = []
    for sample_id, candidate in enumerate(selected):
        dataset.append(
            {
                "id": sample_id,
                "instruction": candidate["instruction"],
                "language": "solidity",
                "contract_name": candidate["container_name"],
                "category": candidate["repo_name"],
                "difficulty": candidate["difficulty"],
                "dataset_source": "SolAgent+SolEval",
                "repo_name": candidate["repo_name"],
                "container_kind": candidate["container_kind"],
                "target_identifier": candidate["target_identifier"],
                "target_signature": candidate["target_signature"],
                "source_key": candidate["source_key"],
                "test_key": candidate["test_key"],
                "project_template_dir": candidate["project_template_dir"],
                "source_relpath": candidate["source_relpath"],
                "test_relpath": candidate["test_relpath"],
                "slither_target": candidate["slither_target"],
                "replace_start_line": candidate["replace_start_line"],
                "replace_end_line": candidate["replace_end_line"],
            }
        )
    return dataset


def main() -> None:
    args = parse_args()
    root = Path.cwd()
    solagent_dir = (root / args.solagent_dir).resolve()
    soleval_dir = (root / args.soleval_dir).resolve()
    repository_root = soleval_dir / "repository"
    output_path = (root / args.output).resolve()

    with (solagent_dir / "data" / "dataset.json").open("r", encoding="utf-8") as handle:
        solagent_dataset = json.load(handle)
    with (solagent_dir / "data" / "test_map_cargo.pkl").open("rb") as handle:
        test_mapping = pickle.load(handle)
    with (soleval_dir / "data" / "dataset.json").open("r", encoding="utf-8") as handle:
        soleval_dataset = json.load(handle)

    soleval_index = index_soleval_entries(soleval_dataset)
    candidates = build_candidates(solagent_dataset, test_mapping, soleval_index, repository_root, soleval_dir)
    selected = select_candidates(candidates, args.limit)
    dataset = finalize_samples(selected)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")

    repo_summary: dict[str, int] = defaultdict(int)
    for sample in dataset:
        repo_summary[sample["repo_name"]] += 1

    print(f"Wrote {len(dataset)} samples to {output_path}")
    print("Repository distribution:")
    for repo_name in sorted(repo_summary):
        print(f"  {repo_name}: {repo_summary[repo_name]}")


if __name__ == "__main__":
    main()
