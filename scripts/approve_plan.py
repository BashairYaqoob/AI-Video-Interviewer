"""
approve_plan.py

Recruiter-facing pre-interview approval gate (Phase 2 / Gap 1).
Run AFTER run_prep_pipeline.py and BEFORE src/realtime/agent.py.

Usage:
    python scripts/approve_plan.py                # interactive review
    python scripts/approve_plan.py --approve       # non-interactive approve as-is
    python scripts/approve_plan.py --reject "note" # non-interactive reject
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interview.schemas import InterviewPlan
from src.interview.plan_approval import approve_plan, reject_plan, OUTPUT_DIR

PLAN_PATH = OUTPUT_DIR / "interview_plan.json"


def main():
    if not PLAN_PATH.exists():
        raise FileNotFoundError(f"{PLAN_PATH} not found. Run scripts/run_prep_pipeline.py first.")

    plan = InterviewPlan.model_validate_json(PLAN_PATH.read_text(encoding="utf-8"))

    print(f"\nIntroduction: {plan.introduction}\n")
    for i, q in enumerate(plan.questions, 1):
        print(f"{i}. [{q.question_type}/{q.difficulty}] {q.text}")
        print(f"   competency={q.competency}  evidence_sought={q.evidence_sought}")
    print(f"\nClosing: {plan.closing}\n")

    if "--approve" in sys.argv:
        approve_plan(note="approved non-interactively")
        print("Plan approved as-is.")
        return
    if "--reject" in sys.argv:
        note = sys.argv[sys.argv.index("--reject") + 1] if len(sys.argv) > sys.argv.index("--reject") + 1 else ""
        reject_plan(note=note)
        print("Plan rejected.")
        return

    choice = input("Approve this plan? [y/n] ").strip().lower()
    if choice == "y":
        approve_plan(note="approved interactively")
        print("Plan approved. You may now start the live agent.")
    else:
        note = input("Reason for rejection (optional): ").strip()
        reject_plan(note=note)
        print("Plan rejected. Interview will not start until re-approved.")


if __name__ == "__main__":
    main()