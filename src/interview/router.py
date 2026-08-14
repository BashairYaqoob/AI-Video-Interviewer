"""
router.py

Conditional-edge routing for the interview graph (Milestone 4C).

route_after_analysis inspects the most recent evidence analysis and
decides whether to: ask a follow-up (evidence insufficient, under the
follow-up cap), advance to the next question in the plan, or close the
interview (plan exhausted). One router function, three real outcomes —
this is exactly why a graph is needed instead of a linear script.
"""

MAX_FOLLOW_UPS = 2


def route_after_analysis(state) -> str:
    last_evidence = state.evidence_collected[-1]

    if last_evidence.follow_up_warranted and state.follow_up_count < MAX_FOLLOW_UPS:
        return "follow_up"

    if state.current_question_index + 1 < len(state.interview_plan):
        return "advance_next"

    return "closing"