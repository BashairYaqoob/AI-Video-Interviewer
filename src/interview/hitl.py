"""
hitl.py

Milestone 6 — human-in-the-loop control layer for the live interview.

Deliberately NOT implemented as extra LangGraph nodes or edges. The graph
already pauses naturally at the receive_answer interrupt between
questions; HITL actions are external control-plane operations that
read/mutate the checkpointed InterviewState directly (via
graph.aupdate_state) rather than participating in graph routing. This
keeps the interview flow graph itself unchanged from Milestone 4C/5 and
keeps HITL logic independently testable (see
tests/test_persistence_and_hitl.py).

Concurrency: every method acquires the SAME asyncio.Lock the caller also
uses for background evidence writes and for advancing the graph (see
state_lock in src/realtime/agent.py), so a HITL action can never race
with — and silently lose against — a concurrent background evidence
write or an in-flight graph step for the same thread_id. Construct one
HITLController per live interview session, sharing that lock.
"""

import time

from src.interview.schemas import HITLActionRecord, HITLStatus, HITL_SKIP_SENTINEL_KEY, QuestionRecord


class HITLController:
    def __init__(self, graph, config: dict, state_lock):
        self._graph = graph
        self._config = config
        self._lock = state_lock

    async def _record_action(self, action: str, actor: str, note: str) -> None:
        async with self._lock:
            current = await self._graph.aget_state(self._config)
            log = list(current.values.get("hitl_actions_log", []))
            log.append(HITLActionRecord(action=action, actor=actor, note=note, timestamp=time.time()))
            await self._graph.aupdate_state(self._config, {"hitl_actions_log": log})

    async def pause(self, actor: str = "recruiter", note: str = "") -> None:
        async with self._lock:
            await self._graph.aupdate_state(self._config, {"hitl_status": HITLStatus.PAUSED})
        await self._record_action("pause", actor, note)

    async def resume(self, actor: str = "recruiter", note: str = "") -> None:
        async with self._lock:
            await self._graph.aupdate_state(self._config, {"hitl_status": HITLStatus.RUNNING})
        await self._record_action("resume", actor, note)

    async def terminate(self, actor: str = "recruiter", note: str = "") -> None:
        """
        Ends the interview immediately. Sets is_complete=True directly
        (rather than routing through closing_node) since the graph may
        currently be paused at an interrupt with no pending resume value
        — this must work regardless of where in the flow the interview
        currently is.
        """
        async with self._lock:
            await self._graph.aupdate_state(
                self._config,
                {"hitl_status": HITLStatus.TERMINATED, "is_complete": True},
            )
        await self._record_action("terminate", actor, note)

    async def override_next_question(
        self, question: QuestionRecord, actor: str = "recruiter", note: str = ""
    ) -> None:
        """
        Replaces the content of the NEXT question the graph will ask
        (the next time ask_question_node runs — see
        src/interview/nodes.py). Only meaningful while the interview is
        paused between questions, at the receive_answer interrupt;
        setting it mid-answer has no effect on the question already in
        flight. It is consumed (cleared) automatically the first time
        ask_question_node runs after being set.
        """
        async with self._lock:
            await self._graph.aupdate_state(self._config, {"hitl_override_question": question})
        await self._record_action("override_question", actor, note or f"-> {question.question_id}")

    async def skip_current_question(self, actor: str = "recruiter", note: str = "") -> dict:
        """
        Returns the sentinel value the caller must resume the graph's
        CURRENT interrupt with, e.g.:

            sentinel = await hitl.skip_current_question()
            await graph.ainvoke(Command(resume=sentinel), config=config)

        The actual resume/advance is intentionally left to the caller
        (src/realtime/agent.py) rather than done here, since it needs to
        happen as part of the same state_lock-guarded advance step as
        every other graph invocation — see _advance_and_ask in agent.py.
        The skip action itself is still logged here so it shows up in
        hitl_actions_log even if the caller's resume happens moments
        later.
        """
        await self._record_action("skip", actor, note)
        return {HITL_SKIP_SENTINEL_KEY: True}

    async def status(self) -> HITLStatus:
        current = await self._graph.aget_state(self._config)
        return current.values.get("hitl_status", HITLStatus.RUNNING)