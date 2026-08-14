"""
router.py

Conditional-edge routing for the interview graph (Milestone 4C).

Two routers now exist:

- route_after_analysis: the ORIGINAL router. Inspects the most recent
  Gemini-based evidence analysis and decides follow_up / advance_next /
  closing. Unchanged. Used when build_interview_graph() runs in its
  default (non-realtime) mode, which is what the existing test suite
  exercises — nothing about this path changed.

- route_immediate: NEW. A cheap, local (no-LLM) heuristic used on the
  live realtime path (build_interview_graph(realtime_mode=True)). It
  must never wait on Gemini — answer analysis runs independently in the
  background (see src/realtime/agent.py) purely for the final evidence
  report, and is never on the turn-by-turn critical path.
"""

MAX_FOLLOW_UPS = 2

# Local, no-LLM signal for "this answer was too thin, probe a bit more"
# before we fall back to just advancing. This is intentionally simple —
# it is a stopgap for realtime responsiveness, not a replacement for the
# real (backgrounded) evidence-based follow-up logic.
MIN_ANSWER_WORDS_BEFORE_FOLLOWUP = 3


def route_after_analysis(state) -> str:
    last_evidence = state.evidence_collected[-1]

    if last_evidence.follow_up_warranted and state.follow_up_count < MAX_FOLLOW_UPS:
        return "follow_up"

    if state.current_question_index + 1 < len(state.interview_plan):
        return "advance_next"

    return "closing"


def route_immediate(state) -> str:
    if state.current_question_index + 1 < len(state.interview_plan):
        return "advance_next"

    return "closing"