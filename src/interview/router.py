"""
router.py

Conditional-edge routing for the interview graph (Milestone 4C, extended
in Milestone 6 for HITL skip).

Two routers exist:

- route_after_analysis: the ORIGINAL router. Inspects the most recent
  Gemini-based evidence analysis and decides follow_up / advance_next /
  closing. Used when build_interview_graph() runs in its default
  (non-realtime) mode, which is what the existing test suite exercises.

- route_immediate: A cheap, local (no-LLM) heuristic used on the live
  realtime path (build_interview_graph(realtime_mode=True)). It must
  never wait on Gemini — answer analysis runs independently in the
  background (see src/realtime/agent.py) purely for the final evidence
  report, and is never on the turn-by-turn critical path.

  NOTE (unchanged from Milestone 5, not touched by Milestone 6):
  MIN_ANSWER_WORDS_BEFORE_FOLLOWUP below is currently unused —
  route_immediate does not yet do its own "very short answer" local
  follow-up heuristic, it only ever advances or closes. That's a known
  gap in the realtime heuristic itself, tracked separately from the
  persistence/HITL work in this milestone.

Milestone 6 addition: BOTH routers now check whether the most recent
answer was a HITL skip (AnswerRecord.skipped) and, if so, unconditionally
advance/close — a skipped question must never trigger a follow-up.
"""

MAX_FOLLOW_UPS = 2

# See NOTE above — currently unused by route_immediate.
MIN_ANSWER_WORDS_BEFORE_FOLLOWUP = 3


def _advance_or_close(state) -> str:
    if state.current_question_index + 1 < len(state.interview_plan):
        return "advance_next"
    return "closing"


def route_after_analysis(state) -> str:
    last_answer = state.candidate_answers[-1]
    if last_answer.skipped:
        return _advance_or_close(state)

    last_evidence = state.evidence_collected[-1]

    if last_evidence.follow_up_warranted and state.follow_up_count < MAX_FOLLOW_UPS:
        return "follow_up"

    return _advance_or_close(state)


def route_immediate(state) -> str:
    # A skipped answer is still routed the same way a normal one would be
    # here (route_immediate never triggers follow-up on its own today —
    # see NOTE above), but the check is kept explicit rather than
    # incidental, so this stays correct if/when the local heuristic grows
    # a real follow-up path later.
    last_answer = state.candidate_answers[-1] if state.candidate_answers else None
    if last_answer is not None and last_answer.skipped:
        return _advance_or_close(state)

    return _advance_or_close(state)