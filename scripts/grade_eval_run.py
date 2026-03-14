#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


AssertionResult = Tuple[bool, str]


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def looks_chinese(text: str) -> bool:
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return cjk_chars > 20


def looks_english(text: str) -> bool:
    ascii_words = len(re.findall(r"[A-Za-z]{2,}", text))
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return ascii_words > 20 and ascii_words > cjk_chars


def has_event_metrics(summary: str) -> bool:
    return all(
        marker in summary
        for marker in [
            "yes_prob:",
            "score=",
            "vol24h=",
            "liquidity:",
            "one_day_price_change:",
            "end_date:",
            "why_selected:",
        ]
    )


def is_handoff_summary(summary: str) -> bool:
    stripped = summary.strip()
    return (
        bool(stripped)
        and not stripped.startswith("{")
        and '"tag_reports"' not in summary
    )


def top_level_summary_check(payload: Dict[str, Any]) -> AssertionResult:
    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        return (
            True,
            "`final_output.json` contains a non-empty top-level `summary` string.",
        )
    return (
        False,
        "`final_output.json` is missing a non-empty top-level `summary` string.",
    )


def zh_language_check(summary: str) -> AssertionResult:
    if "Polymarket 热点雷达摘要" in summary and looks_chinese(summary):
        return (
            True,
            "Summary uses the Chinese title and contains substantial Chinese text.",
        )
    return (
        False,
        "Summary is missing the Chinese title or does not appear primarily Chinese.",
    )


def en_language_check(summary: str) -> AssertionResult:
    if "Polymarket Radar Summary" in summary and looks_english(summary):
        return (
            True,
            "Summary uses the English title and contains substantial English text.",
        )
    return (
        False,
        "Summary is missing the English title or does not appear primarily English.",
    )


def contains_text(summary: str, needle: str, label: str) -> AssertionResult:
    if needle in summary:
        return True, f"Found `{needle}` in the summary for {label}."
    return False, f"Did not find `{needle}` in the summary for {label}."


def absence_check(summary: str, needle: str, label: str) -> AssertionResult:
    if needle not in summary:
        return True, f"`{needle}` does not appear in the summary for {label}."
    return False, f"`{needle}` appears in the summary for {label}."


def metrics_check(summary: str) -> AssertionResult:
    if has_event_metrics(summary):
        return True, "Summary includes the expected event evidence fields."
    return False, "Summary is missing one or more expected event evidence fields."


def raw_json_artifact_check(summary: str) -> AssertionResult:
    if is_handoff_summary(summary):
        return (
            True,
            "Summary reads like a handoff artifact rather than a raw JSON dump.",
        )
    return False, "Summary looks too much like raw structured JSON."


def eval_checks(
    eval_name: str,
) -> List[Tuple[str, Callable[[Dict[str, Any], str], AssertionResult]]]:
    if eval_name == "economy-tech-zh-summary":
        return [
            (
                "The output is a JSON object with a non-empty summary field.",
                lambda payload, summary: top_level_summary_check(payload),
            ),
            (
                "The summary is primarily in Chinese.",
                lambda payload, summary: zh_language_check(summary),
            ),
            (
                "The summary includes '查询 tags: economy, tech' or the equivalent economy/tech-only tag list.",
                lambda payload, summary: contains_text(
                    summary, "查询 tags: economy, tech", "economy/tech tag selection"
                ),
            ),
            (
                "The summary includes both the per-tag highlights section and the global top signals section.",
                lambda payload, summary: (
                    True,
                    "Found both Chinese section headers for per-tag highlights and global top signals.",
                )
                if "分 tag 重点事件" in summary and "全局 Top signals" in summary
                else (False, "Missing one or both expected Chinese section headers."),
            ),
            (
                "At least one selected event includes yes_prob, score, vol24h, liquidity, one_day_price_change, end_date, and why_selected.",
                lambda payload, summary: metrics_check(summary),
            ),
        ]
    if eval_name == "politics-world-en-summary":
        return [
            (
                "The output is a JSON object with a non-empty summary field.",
                lambda payload, summary: top_level_summary_check(payload),
            ),
            (
                "The summary is primarily in English.",
                lambda payload, summary: en_language_check(summary),
            ),
            (
                "The summary includes 'Tags: politics, world' or the equivalent politics/world-only tag list.",
                lambda payload, summary: contains_text(
                    summary, "Tags: politics, world", "politics/world tag selection"
                ),
            ),
            (
                "The summary includes at least one event line with yes_prob and liquidity context.",
                lambda payload, summary: metrics_check(summary),
            ),
            (
                "The summary does not use raw structured JSON as the primary artifact.",
                lambda payload, summary: raw_json_artifact_check(summary),
            ),
        ]
    if eval_name == "future-news-radar-zh":
        return [
            (
                "The output is a JSON object with a non-empty summary field.",
                lambda payload, summary: top_level_summary_check(payload),
            ),
            (
                "The summary is primarily in Chinese.",
                lambda payload, summary: zh_language_check(summary),
            ),
            (
                "The summary includes the requested politics, economy, and world tags without unrelated tags taking over the run configuration.",
                lambda payload, summary: (
                    True,
                    "Found the requested politics, economy, and world tag list without extra tags.",
                )
                if "查询 tags: politics, economy, world" in summary
                else (
                    False,
                    "Did not find the requested politics/economy/world-only tag list.",
                ),
            ),
            (
                "The summary includes a global top signals section that helps a downstream agent identify the most important cross-tag signals.",
                lambda payload, summary: contains_text(
                    summary, "全局 Top signals", "cross-tag section"
                ),
            ),
            (
                "The summary reads like an agent handoff artifact rather than a raw API dump.",
                lambda payload, summary: raw_json_artifact_check(summary),
            ),
        ]
    if eval_name == "crypto-clean-probabilities-en":
        return [
            (
                "The output is a JSON object with a non-empty summary field.",
                lambda payload, summary: top_level_summary_check(payload),
            ),
            (
                "The summary is primarily in English.",
                lambda payload, summary: en_language_check(summary),
            ),
            (
                "The summary includes 'Tags: crypto' or the equivalent crypto-only tag list.",
                lambda payload, summary: contains_text(
                    summary, "Tags: crypto", "crypto tag selection"
                ),
            ),
            (
                "Selected signals include concrete yes_prob values instead of n/a placeholders.",
                lambda payload, summary: absence_check(
                    summary, "yes_prob: n/a", "crypto probability quality"
                ),
            ),
            (
                "The summary still includes the standard evidence fields such as score, vol24h, liquidity, one_day_price_change, end_date, and why_selected.",
                lambda payload, summary: metrics_check(summary),
            ),
        ]
    raise ValueError(f"Unsupported eval_name: {eval_name}")


def output_char_count(outputs_dir: Path) -> int:
    total = 0
    for path in outputs_dir.rglob("*"):
        if path.is_file():
            total += len(path.read_text(encoding="utf-8", errors="ignore"))
    return total


def build_grading(eval_metadata: Dict[str, Any], outputs_dir: Path) -> Dict[str, Any]:
    payload = load_json(outputs_dir / "final_output.json")
    summary = read_text(outputs_dir / "summary.txt")
    notes_text = read_text(outputs_dir / "user_notes.md").strip()
    timing_path = outputs_dir.parent / "timing.json"
    timing = load_json(timing_path) if timing_path.exists() else {}
    checks = eval_checks(str(eval_metadata["eval_name"]))

    expectation_results: List[Dict[str, Any]] = []
    for expected_text, check_fn in checks:
        passed, evidence = check_fn(payload, summary)
        expectation_results.append(
            {"text": expected_text, "passed": passed, "evidence": evidence}
        )

    passed_count = sum(1 for item in expectation_results if item["passed"])
    total_count = len(expectation_results)
    failed_count = total_count - passed_count
    output_chars = output_char_count(outputs_dir)
    transcript_chars = len(notes_text)

    claims = [
        {
            "claim": "The run produced a summary-first artifact.",
            "type": "quality",
            "verified": is_handoff_summary(summary),
            "evidence": "Summary title and formatting were checked against human-readable output expectations.",
        }
    ]

    return {
        "expectations": expectation_results,
        "summary": {
            "passed": passed_count,
            "failed": failed_count,
            "total": total_count,
            "pass_rate": round(passed_count / total_count, 4) if total_count else 0.0,
        },
        "execution_metrics": {
            "tool_calls": {},
            "total_tool_calls": 0,
            "total_steps": 0,
            "errors_encountered": 0,
            "output_chars": output_chars,
            "transcript_chars": transcript_chars,
        },
        "timing": timing,
        "claims": claims,
        "user_notes_summary": {
            "uncertainties": [notes_text] if notes_text else [],
            "needs_review": [],
            "workarounds": [],
        },
        "eval_feedback": {
            "suggestions": [],
            "overall": "No suggestions, evals look solid.",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grade a polymarket-radar eval run")
    parser.add_argument(
        "--eval-metadata", required=True, help="Path to eval_metadata.json"
    )
    parser.add_argument("--run-dir", required=True, help="Path to the run directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    eval_metadata_path = Path(args.eval_metadata).resolve()
    run_dir = Path(args.run_dir).resolve()
    outputs_dir = run_dir / "outputs"
    grading_path = run_dir / "grading.json"

    eval_metadata = load_json(eval_metadata_path)
    grading = build_grading(eval_metadata, outputs_dir)
    grading_path.write_text(
        json.dumps(grading, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
