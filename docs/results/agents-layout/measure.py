"""Run the paired, read-only AGENTS layout experiment and preserve its evidence."""

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path


BASE = "0f03aeca843d3350f172f91fbd19c073f462e752"
MODEL = "gpt-6.1-sol"
EFFORT = "ultra"
COMMON_PROMPT = (
    "읽기 전용으로 작업하고 관련 AGENTS 지침을 확인하라. 파일 수정과 보조 에이전트 사용 없이 "
    "요청한 파일의 근거를 확인하라. 최종 답변은 요청한 키만 가진 JSON 객체로 반환하라.\n"
)
TASKS = {
    "code": {
        "prompt": "src/extractor.py에서 한글 단위 금액을 정규화하는 함수의 이름과 정의 행 번호를 찾고, tests/test_extractor.py에서 '1억 2천만원'을 검사하는 test_at_least_three_variants_per_pattern의 기대 금액을 확인하라. 키는 function, line, expected_amount다.",
        "expected": {"function": "_normalize_korean_amount", "line": 118, "expected_amount": 120000000},
    },
    "docs": {
        "prompt": "docs/devops.md의 환경 계약에서 프로젝트 Python 버전, uv 버전, 평가 OS, 테스트 러너를 확인하라. 키는 python, uv, evaluation_os, test_runner다.",
        "expected": {"python": "3.11", "uv": "0.13.7", "evaluation_os": "macOS", "test_runner": "unittest"},
    },
    "mixed": {
        "prompt": "main.py와 docs/extraction.md를 대조해 --mask 사용 시 원문 정보 추출과 분석 문장 마스킹의 순서를 확인하라. 키는 first_call, second_call, documented_order다. documented_order에는 문서와 코드가 일치하면 extract_then_mask를 넣어라.",
        "expected": {"first_call": "extract_information", "second_call": "mask_personal_info", "documented_order": "extract_then_mask"},
    },
}
PAIRS = [
    ("code", 1, "AB"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repository.as_posix()}", "-C", str(repository), *arguments],
        check=True, capture_output=True, encoding="utf-8",
    )
    return result.stdout.strip()


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def session_evidence(thread_id: str, root_instructions: str) -> dict:
    matches = list((Path.home() / ".codex" / "sessions").rglob(f"*{thread_id}.jsonl"))
    evidence = {"path": None, "contexts": [], "root_instructions_present": False, "model_response_count": None}
    if not matches:
        return evidence
    path = matches[0]
    evidence["path"] = str(path)
    cumulative_usages = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        payload = event.get("payload", {})
        if event.get("type") == "turn_context":
            evidence["contexts"].append({
                key: payload.get(key) for key in ("model", "effort", "reasoning_effort", "cwd")
            })
        if event.get("type") == "response_item":
            for part in payload.get("content", []):
                text = part.get("text", "").replace("\r\n", "\n")
                if root_instructions.strip() in text:
                    evidence["root_instructions_present"] = True
        if payload.get("type") == "token_count":
            usage = (payload.get("info") or {}).get("total_token_usage")
            if usage:
                cumulative_usages.add(json.dumps(usage, sort_keys=True))
    if cumulative_usages:
        evidence["model_response_count"] = len(cumulative_usages)
    return evidence


def summarize(records: list[dict]) -> dict:
    metrics = ("cached_input_tokens", "uncached_input_tokens", "output_tokens", "total_tokens", "elapsed_seconds")
    variants = sorted({row["variant"] for row in records})
    if "ORGINAL" in variants:
        variants.remove("ORGINAL")
        variants.insert(0, "ORGINAL")
    summary = {"run_count": len(records), "passed": sum(row["passed"] for row in records), "tasks": {}}
    for task in TASKS:
        rows = [row for row in records if row["task"] == task]
        if not rows:
            continue
        task_summary = {"A": {}, "B": {}, "median_reduction_percent": {}, "pairs": []}
        for variant in variants:
            variant_rows = [row for row in rows if row["variant"] == variant]
            task_summary.setdefault(variant, {})
            task_summary[variant]["passed"] = sum(row["passed"] for row in variant_rows)
            task_summary[variant]["runs"] = len(variant_rows)
            for metric in metrics:
                values = [row[metric] for row in variant_rows if row.get(metric) is not None]
                task_summary[variant][metric] = {"values": values, "median": statistics.median(values) if values else None}
        for metric in metrics:
            a = task_summary["A"][metric]["median"]
            b = task_summary["B"][metric]["median"]
            task_summary["median_reduction_percent"][metric] = 100 * (a - b) / a if a and b is not None else None
        for repetition in range(1, 4):
            pair = {row["variant"]: row for row in rows if row["repetition"] == repetition}
            if not {"A", "B"}.issubset(pair):
                continue
            both_passed = pair["A"]["passed"] and pair["B"]["passed"]
            differences = {metric: pair["B"][metric] - pair["A"][metric] for metric in metrics if pair["A"].get(metric) is not None and pair["B"].get(metric) is not None}
            reductions = {metric: 100 * (pair["A"][metric] - pair["B"][metric]) / pair["A"][metric] if pair["A"][metric] else None for metric in differences}
            task_summary["pairs"].append({"repetition": repetition, "both_passed": both_passed, "B_minus_A": differences, "reduction_percent": reductions})
        summary["tasks"][task] = task_summary
    summary["totals"] = {}
    for variant in variants:
        rows = [row for row in records if row["variant"] == variant]
        summary["totals"][variant] = {metric: sum(row[metric] for row in rows if row.get(metric) is not None) for metric in metrics}
    summary["aggregate_reduction_percent"] = {
        metric: 100 * (summary["totals"]["A"][metric] - summary["totals"]["B"][metric]) / summary["totals"]["A"][metric]
        if summary["totals"]["A"][metric] else None for metric in metrics
    }
    summary["comparison_reduction_percent"] = {}
    for baseline_variant, candidate_variant in combinations(variants, 2):
        baseline = summary["totals"][baseline_variant]
        candidate = summary["totals"][candidate_variant]
        summary["comparison_reduction_percent"][f"{baseline_variant}_to_{candidate_variant}"] = {
            metric: 100 * (baseline[metric] - candidate[metric]) / baseline[metric]
            if baseline[metric] else None for metric in metrics
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--fixture-b", required=True)
    parser.add_argument("--fixture-c")
    parser.add_argument("--fixture-original")
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    repository = args.repository.resolve()
    output = Path(__file__).resolve().parent
    (output / "raw").mkdir(exist_ok=True)
    commits = {"A": BASE, "B": args.fixture_b}
    pairs = list(PAIRS)
    if args.fixture_c:
        commits["C"] = args.fixture_c
        pairs.append(("code", 1, "C"))
    if args.fixture_original:
        commits["ORGINAL"] = args.fixture_original
        pairs.append(("code", 1, ["ORGINAL"]))
    assert not git(repository, "status", "--porcelain"), "Comparison worktree has existing changes"
    tracked = git(repository, "ls-tree", "-r", "--name-only", BASE).splitlines()
    fixed_paths = [path for path in tracked if Path(path).name != "AGENTS.md"]
    fixed_hashes = {path: sha256(repository / path) for path in fixed_paths}
    manifest_path = output / "manifest.json"
    if not manifest_path.exists():
        manifest = {
            "created_utc": utc_now(), "code_base": BASE, "unified_source": "894e9aec5e40a81bd0b69368a8ec96f16cb6eac1",
            "fixture_commits": commits, "repository": str(repository), "model": MODEL, "effort": EFFORT,
            "cli": str(args.codex), "cli_sha256": sha256(args.codex),
            "cli_version": subprocess.run([str(args.codex), "--version"], check=True, capture_output=True, text=True).stdout.strip(),
            "python": platform.python_version(), "platform": platform.platform(),
            "global_guidance_sha256": sha256(Path.home() / ".codex" / "AGENTS.md"),
            "config_sha256": sha256(Path.home() / ".codex" / "config.toml"),
            "fixed_file_sha256": fixed_hashes, "tasks": TASKS, "common_prompt": COMMON_PROMPT,
            "pairs": pairs, "max_attempts": args.max_attempts, "variants": {},
        }
        for variant, commit in commits.items():
            git(repository, "switch", "--detach", commit)
            paths = [path for path in git(repository, "ls-files").splitlines() if Path(path).name == "AGENTS.md"]
            manifest["variants"][variant] = {path: {"sha256": sha256(repository / path), "bytes": (repository / path).stat().st_size} for path in paths}
        save_json(manifest_path, manifest)
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert all(commits[variant] == commit for variant, commit in manifest["fixture_commits"].items())
        assert manifest["fixed_file_sha256"] == fixed_hashes
        assert manifest["config_sha256"] == sha256(Path.home() / ".codex" / "config.toml")
        assert manifest["global_guidance_sha256"] == sha256(Path.home() / ".codex" / "AGENTS.md")
        if args.fixture_c:
            git(repository, "switch", "--detach", args.fixture_c)
            manifest["fixture_commits"]["C"] = args.fixture_c
            manifest["variants"]["C"] = {"AGENTS.md": {
                "sha256": sha256(repository / "AGENTS.md"),
                "bytes": (repository / "AGENTS.md").stat().st_size,
            }}
            manifest["optimized_source"] = "11c494e893f3a430a7e8f942eb98577c26ce20ee"
            manifest["pairs"] = pairs
            manifest["initial_max_attempts"] = 3
            manifest["max_attempts"] = args.max_attempts
            manifest["followup_scope"] = "One additional optimized C run requested for the three-configuration comparison."
            save_json(manifest_path, manifest)
        if args.fixture_original:
            git(repository, "switch", "--detach", args.fixture_original)
            manifest["fixture_commits"]["ORGINAL"] = args.fixture_original
            manifest["variants"]["ORGINAL"] = {"AGENTS.md": {
                "sha256": sha256(repository / "AGENTS.md"),
                "bytes": (repository / "AGENTS.md").stat().st_size,
            }}
            manifest["original_source"] = "ORGINAL.md"
            manifest["original_substitutions"] = {
                "project_path": repository.as_posix(),
                "mission": "규칙 기반 정보 추출·감성 분석 / docs/A4_2_mission.md",
                "repository": "https://github.com/ntt65/A4_2",
                "environment": "Python 3.11 + uv 0.13.7",
            }
            manifest["pairs"] = pairs
            manifest["max_attempts"] = args.max_attempts
            manifest["followup_scope"] = "One additional user-provided ORGINAL instruction run requested for the four-configuration comparison."
            save_json(manifest_path, manifest)
    records_path = output / "runs.jsonl"
    attempts_path = output / "attempts.jsonl"
    records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()] if records_path.exists() else []
    attempts = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines()] if attempts_path.exists() else []
    completed = {row["run_id"] for row in records}
    run_number = 0
    for pair_number, (task, repetition, order) in enumerate(pairs, 1):
        for variant in order:
            run_number += 1
            run_id = f"{run_number:02d}_{task}_{repetition}_{variant}"
            if len(attempts) >= args.max_attempts or run_id in completed:
                continue
            assert not git(repository, "status", "--porcelain"), "Unexpected worktree changes"
            git(repository, "switch", "--detach", commits[variant])
            assert {path: sha256(repository / path) for path in fixed_paths} == fixed_hashes
            root_text = (repository / "AGENTS.md").read_text(encoding="utf-8")
            prompt = COMMON_PROMPT + TASKS[task]["prompt"]
            command = [str(args.codex), "exec", "--sandbox", "read-only", "--json", "--model", MODEL,
                       "-c", f'model_reasoning_effort="{EFFORT}"', "-c", 'approval_policy="never"', "-C", str(repository), "-"]
            print(f"START {run_id} {utc_now()}", flush=True)
            started = utc_now()
            attempt = {"attempt_number": len(attempts) + 1, "run_id": run_id, "started_utc": started}
            with attempts_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(attempt) + "\n")
            attempts.append(attempt)
            clock = time.perf_counter()
            result = subprocess.run(command, input=prompt, capture_output=True, encoding="utf-8", cwd=repository)
            elapsed = time.perf_counter() - clock
            finished = utc_now()
            (output / "raw" / f"{run_id}.jsonl").write_text(result.stdout, encoding="utf-8")
            (output / "raw" / f"{run_id}.stderr.txt").write_text(result.stderr, encoding="utf-8")
            events = [json.loads(line) for line in result.stdout.splitlines() if line.strip().startswith("{")]
            messages = [event["item"]["text"] for event in events if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message"]
            final_text = messages[-1] if messages else ""
            try:
                answer = json.loads(final_text)
            except json.JSONDecodeError:
                answer = None
            usages = [event["usage"] for event in events if event.get("type") == "turn.completed"]
            usage = usages[-1] if usages else {}
            thread_ids = [event["thread_id"] for event in events if event.get("type") == "thread.started"]
            thread_id = thread_ids[-1] if thread_ids else ""
            evidence = session_evidence(thread_id, root_text) if thread_id else {}
            save_json(output / "raw" / f"{run_id}.session.json", evidence)
            input_tokens = usage.get("input_tokens")
            cached_tokens = usage.get("cached_input_tokens")
            output_tokens = usage.get("output_tokens")
            unchanged = {path: sha256(repository / path) for path in fixed_paths} == fixed_hashes and not git(repository, "status", "--porcelain")
            record = {
                "attempt_number": attempt["attempt_number"],
                "run_id": run_id, "pair": pair_number, "task": task, "repetition": repetition, "variant": variant,
                "commit": commits[variant], "started_utc": started, "finished_utc": finished,
                "elapsed_seconds": elapsed, "exit_code": result.returncode, "command": command,
                "thread_id": thread_id, "final_text": final_text, "answer": answer,
                "passed": result.returncode == 0 and answer == TASKS[task]["expected"] and unchanged,
                "fixed_files_unchanged": unchanged, "usage": usage, "input_tokens": input_tokens,
                "cached_input_tokens": cached_tokens, "uncached_input_tokens": input_tokens - cached_tokens if input_tokens is not None and cached_tokens is not None else None,
                "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None,
                "tool_calls": sum(event.get("type") == "item.completed" and event.get("item", {}).get("type") in ("command_execution", "mcp_tool_call", "web_search", "file_change") for event in events),
                "session_evidence": evidence,
            }
            with records_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            records.append(record)
            summary = summarize(records)
            summary["attempt_count"] = len(attempts)
            summary["incomplete_attempts"] = len(attempts) - len(records)
            save_json(output / "summary.json", summary)
            print(f"DONE {run_id} passed={record['passed']} tokens={record['total_tokens']} elapsed={elapsed:.3f}s", flush=True)
            assert unchanged, "Measured session changed comparison files"


if __name__ == "__main__":
    main()
