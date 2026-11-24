"""Run an evaluator over a labelled case file and report agreement.

    # free, deterministic
    python scripts/run_evaluator_cases.py --provider fake
    # real Claude calls: one request per case (33 in v2). Costs money; needs credentials.
    python scripts/run_evaluator_cases.py --provider llm --confirm-cost
    # the original Day 3 set
    python scripts/run_evaluator_cases.py --cases data/evals/evaluator_cases.v1.json

v2 adds intent cases (questions about the topic, "say that again", off topic, a wellbeing
concern) so the run also measures whether the evaluator tells answers from side turns.

Run from the repo root with the backend virtualenv active. This is a Day 3 smoke check
on a small hand-labelled set, not the Day 6 benchmark: report it as such.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from app.config import REPO_ROOT, Settings
from app.domain.scoring import EvidenceStatus
from app.lesson_catalog import load_catalog
from app.main import build_evaluator
from app.providers.llm import EvaluationRequest
from app.services.evaluator import validate_output

CASES = REPO_ROOT / "data" / "evals" / "evaluator_cases.v2.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["fake", "llm"], default="fake")
    parser.add_argument("--confirm-cost", action="store_true", help="required for --provider llm")
    parser.add_argument("--out", type=Path, help="write per-case results as JSON")
    parser.add_argument("--cases", type=Path, default=CASES, help="labelled case file")
    args = parser.parse_args()
    if args.provider == "llm" and not args.confirm_cost:
        print(
            "--provider llm makes one paid API call per case; add --confirm-cost", file=sys.stderr
        )
        return 2

    settings = Settings(evaluator_provider=args.provider)
    evaluator = build_evaluator(settings)
    catalog = load_catalog(settings.lessons_dir)
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]

    results, latencies = [], []
    for case in cases:
        lesson = catalog.latest(case["lesson_id"])
        question = lesson.question(case["question_id"])
        started = time.perf_counter()
        try:
            output = evaluator.evaluate(
                EvaluationRequest(lesson, question, case["transcript"], assisted=False)
            )
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            results.append({"id": case["id"], "error": f"{type(exc).__name__}: {exc}"})
            print(f"{case['id']:28} ERROR {type(exc).__name__}")
            continue
        latencies.append(time.perf_counter() - started)
        assessment = validate_output(lesson, question, case["transcript"], output)

        accepted = [e for e in assessment.evidence if e.status is EvidenceStatus.ACCEPTED]
        level = accepted[0].proposed_level if accepted else None
        expected = case["expected"]
        level_ok = (
            level is None
            if expected["level_range"] is None
            else level is not None
            and expected["level_range"][0] <= level <= expected["level_range"][1]
        )
        row = {
            "id": case["id"],
            "category": case["category"],
            "signal": assessment.signal.value,
            "signal_ok": assessment.signal.value == expected["signal"],
            "tag": assessment.misconception_tag,
            "tag_ok": assessment.misconception_tag == expected["misconception_tag"],
            "level": level,
            "level_ok": level_ok,
            "intent": output.intent.value,
            "intent_ok": output.intent.value == expected.get("intent", output.intent.value),
            "rejected": [
                e.rejection_reason
                for e in assessment.evidence
                if e.status is EvidenceStatus.REJECTED
            ],
            "evaluator_version": output.evaluator_version,
            "model": output.model,
        }
        results.append(row)
        checks = ("signal_ok", "tag_ok", "level_ok", "intent_ok")
        marks = "".join("." if row[k] else "x" for k in checks)
        print(
            f"{case['id']:28} {marks}  signal={row['signal']:15} tag={row['tag']} "
            f"level={level} rejected={len(row['rejected'])}"
        )

    scored = [r for r in results if "error" not in r]
    print(f"\ncases={len(cases)} scored={len(scored)} errors={len(cases) - len(scored)}")
    for key in ("signal_ok", "tag_ok", "level_ok", "intent_ok"):
        print(f"{key:10} {sum(r[key] for r in scored)}/{len(scored)}")
    print(f"rejected evidence items: {sum(len(r['rejected']) for r in scored)}")
    if latencies:
        ordered = sorted(latencies)
        print(f"latency s: median={ordered[len(ordered) // 2]:.2f} max={ordered[-1]:.2f}")
    if args.out:
        args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
