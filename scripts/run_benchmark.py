"""Benchmark: 60 scripted synthetic learners, adaptive policy vs fixed-question baseline.

    # free, deterministic
    python scripts/run_benchmark.py --provider fake
    # real Claude calls (about 250 with caching). Costs money; needs credentials.
    python scripts/run_benchmark.py --provider llm --confirm-cost --out docs/benchmark-llm.json

Run from the repo root with the backend virtualenv active. The evaluator model and effort
come from the environment (.env): LLM_MODEL, LLM_EFFORT. See docs/evaluation.md for how to
read the output and what it does not show.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import REPO_ROOT, Settings
from app.domain.policy import Budget
from app.evals.simulation import (
    SEED,
    CachingEvaluator,
    Metrics,
    build_profiles,
    load_bank,
    run_session,
)
from app.lesson_catalog import load_catalog
from app.main import build_evaluator
from app.providers.prompts import PROMPT_VERSION

BANK = REPO_ROOT / "data" / "evals" / "answer_bank.v1.json"
# Claude Haiku 5.5 list price per million tokens (prompts up to 100K tokens), 2026-11.
PRICE_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50)}


def pct(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator}" + (
        f" ({100 * numerator / denominator:.0f}%)" if denominator else ""
    )


def describe(name: str, m: Metrics) -> list[str]:
    rows = [
        ("criteria with a suggested level", m.criteria_with_level, m.criteria),
        ("answer level exact", m.level_exact, m.level_judged),
        ("answer level within one", m.level_within_one, m.level_judged),
        (
            "judgeable answers left unknown",
            m.abstained_on_judgeable,
            m.level_judged + m.abstained_on_judgeable,
        ),
        ("vague answers kept unknown", m.vague_left_unknown, m.vague_answers),
        ("hint/side turns wrongly scored", m.non_answers_scored, m.non_answers),
        ("final level within one", m.final_within_one, m.final_judged),
        ("final unknown kept unknown", m.final_unknown_kept, m.final_unknown_expected),
        (
            "learner misconceptions detected",
            m.learner_misconceptions_detected,
            m.learner_misconceptions,
        ),
        (
            "learner misconceptions followed up",
            m.learner_misconceptions_followed_up,
            m.learner_misconceptions,
        ),
    ]
    return [
        f"## {name}",
        f"sessions {m.sessions} | turns per session {m.turns / max(m.sessions, 1):.2f}"
        f" | finish {m.finish_reasons}",
        *(f"{label:36} {pct(n, d)}" for label, n, d in rows),
        f"misconception tags: TP {m.tag_true_positive} FP {m.tag_false_positive}"
        f" FN {m.tag_false_negative}",
        f"rejected evidence items              {m.rejected_evidence}",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["fake", "llm"], default="fake")
    parser.add_argument("--confirm-cost", action="store_true", help="required for --provider llm")
    parser.add_argument("--out", type=Path, help="write the full result as JSON")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.provider == "llm" and not args.confirm_cost:
        print("--provider llm makes paid API calls; add --confirm-cost", file=sys.stderr)
        return 2

    settings = Settings(evaluator_provider=args.provider)
    inner = build_evaluator(settings)
    evaluator = CachingEvaluator(inner)
    catalog = load_catalog(settings.lessons_dir)
    bank = load_bank(BANK)
    profiles = build_profiles(bank)
    budget = Budget(
        max_turns=settings.max_turns, max_seconds=1e9, max_side_turns=settings.max_side_turns
    )

    jobs = [(p, policy) for p in profiles for policy in ("adaptive", "fixed")]
    started = time.perf_counter()
    failures: list[str] = []

    def run(job):  # noqa: ANN001, ANN202
        profile, policy = job
        try:
            return run_session(
                catalog.latest(profile.lesson_id), profile, bank, evaluator, policy, budget
            )
        except Exception as exc:  # noqa: BLE001 - count and report every failed session
            failures.append(f"{profile.id}/{policy}: {type(exc).__name__}")
            return None

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = [r for r in pool.map(run, jobs) if r is not None]
    elapsed = time.perf_counter() - started

    groups: dict[str, Metrics] = {}
    for result in results:
        for key in (f"{result.policy} / all", f"{result.policy} / {result.profile.split}"):
            groups.setdefault(key, Metrics()).add(result, bank)

    version = getattr(inner, "version", "?")
    lines = [
        "# Kira Verbal benchmark",
        f"evaluator {version} | prompt {PROMPT_VERSION} | effort "
        f"{settings.llm_effort if args.provider == 'llm' else 'n/a'}",
        f"profiles {len(profiles)} (seed {SEED}) | max_turns {settings.max_turns}"
        f" | sessions run {len(results)} | failed {len(failures)}",
        f"evaluator calls {evaluator.calls} (cached repeats excluded) | errors {evaluator.errors}"
        f" | wall time {elapsed:.0f}s | python {platform.python_version()} on {platform.system()}",
    ]
    usage = getattr(inner, "usage", None)
    if evaluator.latencies:
        ordered = sorted(evaluator.latencies)
        p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
        lines.append(
            f"evaluator latency s: median {ordered[len(ordered) // 2]:.2f} | p95 {p95:.2f}"
            f" | max {ordered[-1]:.2f} (nearest-rank, n={len(ordered)})"
        )
    cost = None
    if usage:
        price = PRICE_PER_MTOK.get(settings.llm_model)
        if price:
            cost = (usage["input_tokens"] * price[0] + usage["output_tokens"] * price[1]) / 1e6
        lines.append(
            f"tokens: input {usage['input_tokens']} output {usage['output_tokens']}"
            f" over {usage['requests']} requests"
            + (f" | estimated cost ${cost:.4f} at list price" if cost is not None else "")
        )
    for key in sorted(groups):
        lines += ["", *describe(key, groups[key])]
    if failures:
        lines += ["", "failed sessions: " + ", ".join(failures[:20])]
    print("\n".join(lines))

    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "evaluator_version": version,
                    "prompt_version": PROMPT_VERSION,
                    "seed": SEED,
                    "profiles": len(profiles),
                    "max_turns": settings.max_turns,
                    "evaluator_calls": evaluator.calls,
                    "usage": usage,
                    "estimated_cost_usd": cost,
                    "failures": failures,
                    "metrics": {k: m.as_dict() for k, m in sorted(groups.items())},
                    "sessions": [
                        {
                            "profile": r.profile.id,
                            "split": r.profile.split,
                            "policy": r.policy,
                            "states": r.profile.states,
                            "finish": r.finish_reason,
                            "suggested": r.suggested,
                            "detected_tags": sorted(r.detected_tags),
                            "turns": [
                                {
                                    "question": t.question_id,
                                    "kind": t.answer.kind,
                                    "true_level": t.answer.true_level,
                                    "true_tag": t.answer.true_tag,
                                    "signal": t.signal,
                                    "level": t.accepted_level,
                                    "tag": t.accepted_tag,
                                    "assisted": t.assisted,
                                }
                                for t in r.turns
                            ],
                        }
                        for r in results
                    ],
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
