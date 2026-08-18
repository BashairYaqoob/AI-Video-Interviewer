"""
test_persistence_and_hitl.py

Milestone 6 acceptance tests — SQLite persistence, reconnect/resume,
HITL actions (pause/resume/skip/override/terminate), and concurrent
state-update safety.

Uses AsyncSqliteSaver against temporary on-disk SQLite files and a fake
analyzer (no Gemini calls), consistent with test_interview_graph.py's
style (plain check()-based assertions, no pytest dependency).

Run directly:  python tests/test_persistence_and_hitl.py
"""

import asyncio
from logging import config
import sys
import tempfile
from pathlib import Path

# from asyncio import graph

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from src.interview.graph import build_interview_graph
from src.interview.state import InterviewState
from src.interview.schemas import (
    QuestionRecord,
    EvidenceRecord,
    HITLStatus,
    HITL_SKIP_SENTINEL_KEY,
)
from src.interview.hitl import HITLController
from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence, GapAnalysis


def check(condition: bool, description: str):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def _field(record, name):
    """record may be a dict or a pydantic model depending on whether it
    round-tripped through the real SQLite serializer yet — helper mirrors
    the _as_question_record/_as_answer_record pattern already used in
    src/realtime/agent.py."""
    return record[name] if isinstance(record, dict) else getattr(record, name)


def make_initial_state(num_questions: int = 3) -> InterviewState:
    plan = [
        QuestionRecord(
            question_id=f"q{i+1}",
            text=f"Question {i+1} text",
            competency="Python",
            evidence_sought="specific example",
            difficulty="medium",
            question_type="core_competency",
            follow_up_strategy="ask for a specific example",
        )
        for i in range(num_questions)
    ]
    return InterviewState(
        candidate_name="Jane Candidate",
        target_role="Junior AI Engineer",
        jd=JobDescription(title="Junior AI Engineer", seniority="0-2 years"),
        resume=Resume(candidate_name="Jane Candidate"),
        github_evidence=GitHubEvidence(username="jane", profile_url="https://github.com/jane"),
        gap_analysis=GapAnalysis(),
        interview_plan=plan,
    )


def make_fake_analyzer(responses):
    responses = list(responses)

    def _analyzer(question, answer, jd, resume, github_evidence):
        return responses.pop(0)

    return _analyzer


async def test_state_survives_new_graph_instance_same_db():
    """Simulates a process restart: build a graph against a sqlite file,
    run it to the first interrupt, throw the graph/checkpointer away,
    build a BRAND NEW graph against the same file + thread_id, and
    confirm state is recovered. This is the core guarantee dropped-call
    resume depends on."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "checkpoints.sqlite")
        config = {"configurable": {"thread_id": "resume-thread-1"}}
        initial_state = make_initial_state(num_questions=1)

        async with AsyncSqliteSaver.from_conn_string(db_path) as cp1:
            graph1 = build_interview_graph(
                analyzer=make_fake_analyzer([EvidenceRecord(relevance="high", follow_up_warranted=False)]),
                checkpointer=cp1,
                realtime_mode=False,
            )
            await graph1.ainvoke(initial_state.model_dump(), config=config)
            snapshot = await graph1.aget_state(config)
            check(
                len(snapshot.values["questions_asked"]) == 1,
                "persistence: first question recorded before 'restart'",
            )

        # New checkpointer + new compiled graph against the SAME file —
        # nothing shared in-process with graph1/cp1 above.
        async with AsyncSqliteSaver.from_conn_string(db_path) as cp2:
            graph2 = build_interview_graph(
                analyzer=make_fake_analyzer([EvidenceRecord(relevance="high", follow_up_warranted=False)]),
                checkpointer=cp2,
                realtime_mode=False,
            )
            recovered = await graph2.aget_state(config)
            check(
                len(recovered.values["questions_asked"]) == 1,
                "persistence: state recovered from disk after 'restart'",
            )
            check(
                recovered.values["candidate_name"] == "Jane Candidate",
                "persistence: full state payload recovered, not just a subset",
            )

            final_state = await graph2.ainvoke(Command(resume="answer to question 1"), config=config)
            check(
                final_state["is_complete"] is True,
                "persistence: recovered interview can be driven to completion",
            )


async def test_hitl_pause_resume_status_and_log():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "checkpoints.sqlite")
        config = {"configurable": {"thread_id": "hitl-thread-1"}}
        initial_state = make_initial_state(num_questions=2)

        async with AsyncSqliteSaver.from_conn_string(db_path) as cp:
            graph = build_interview_graph(
                analyzer=make_fake_analyzer([EvidenceRecord(relevance="high", follow_up_warranted=False)]),
                checkpointer=cp,
                realtime_mode=False,
            )
            await graph.ainvoke(initial_state.model_dump(), config=config)

            hitl = HITLController(graph, config, asyncio.Lock())

            check(await hitl.status() == HITLStatus.RUNNING, "hitl: starts RUNNING")

            await hitl.pause(actor="recruiter", note="checking something")
            check(await hitl.status() == HITLStatus.PAUSED, "hitl: pause updates status")

            await hitl.resume(actor="recruiter")
            check(await hitl.status() == HITLStatus.RUNNING, "hitl: resume restores status")

            log = (await graph.aget_state(config)).values["hitl_actions_log"]
            actions = [_field(entry, "action") for entry in log]
            check(actions == ["pause", "resume"], "hitl: actions logged in order")


async def test_hitl_skip_advances_without_follow_up():
    """Even though the fake analyzer WOULD trigger a follow-up, a
    skipped answer must bypass follow-up logic and advance/close."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "checkpoints.sqlite")
        config = {"configurable": {"thread_id": "hitl-thread-skip"}}
        initial_state = make_initial_state(num_questions=1)

        async with AsyncSqliteSaver.from_conn_string(db_path) as cp:
            graph = build_interview_graph(
                analyzer=make_fake_analyzer(
                    [
                        EvidenceRecord(
                            relevance="low",
                            follow_up_warranted=True,
                            suggested_follow_up_direction="probe more",
                        )
                    ]
                ),
                checkpointer=cp,
                realtime_mode=False,
            )
            await graph.ainvoke(initial_state.model_dump(), config=config)

            hitl = HITLController(graph, config, asyncio.Lock())
            sentinel = await hitl.skip_current_question()
            check(
                sentinel == {HITL_SKIP_SENTINEL_KEY: True},
                "hitl: skip returns the expected resume sentinel",
            )

            final_state = await graph.ainvoke(Command(resume=sentinel), config=config)
            check(
                final_state["is_complete"] is True,
                "hitl: skip closes the interview instead of following up",
            )
            check(
                _field(final_state["candidate_answers"][-1], "skipped") is True,
                "hitl: skipped answer recorded with skipped=True",
            )

            log = (await graph.aget_state(config)).values["hitl_actions_log"]
            check(
                len(log) == 1 and _field(log[0], "action") == "skip",
                "hitl: skip action logged",
            )


async def test_hitl_override_replaces_next_question_once():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "checkpoints.sqlite")
        config = {"configurable": {"thread_id": "hitl-thread-override"}}
        initial_state = make_initial_state(num_questions=2)

        async with AsyncSqliteSaver.from_conn_string(db_path) as cp:
            graph = build_interview_graph(
                analyzer=make_fake_analyzer(
                    [
                        EvidenceRecord(relevance="high", follow_up_warranted=False),
                        EvidenceRecord(relevance="high", follow_up_warranted=False),
                    ]
                ),
                checkpointer=cp,
                realtime_mode=False,
            )
            await graph.ainvoke(initial_state.model_dump(), config=config)

            hitl = HITLController(graph, config, asyncio.Lock())
            override = QuestionRecord(
                question_id="recruiter-override-1",
                text="Actually, tell me about a production incident you handled.",
                competency="Debugging",
                evidence_sought="a specific incident",
                difficulty="hard",
                question_type="core_competency",
                follow_up_strategy="ask for root cause",
            )
            await hitl.override_next_question(override)

            await graph.ainvoke(Command(resume="answer to question 1"), config=config)
            state_after = (await graph.aget_state(config)).values
            asked = state_after["questions_asked"][-1]
            check(
                _field(asked, "question_id") == "recruiter-override-1",
                "hitl: overridden question was asked instead of the plan's next question",
            )
            check(
                state_after["hitl_override_question"] is None,
                "hitl: override is cleared after being consumed once",
            )


async def test_hitl_terminate_ends_interview_immediately():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "checkpoints.sqlite")
        config = {"configurable": {"thread_id": "hitl-thread-terminate"}}
        initial_state = make_initial_state(num_questions=3)

        async with AsyncSqliteSaver.from_conn_string(db_path) as cp:
            graph = build_interview_graph(
                analyzer=make_fake_analyzer([EvidenceRecord(relevance="high", follow_up_warranted=False)]),
                checkpointer=cp,
                realtime_mode=False,
            )
            await graph.ainvoke(initial_state.model_dump(), config=config)

            hitl = HITLController(graph, config, asyncio.Lock())
            await hitl.terminate(note="candidate no-showed")

            values = (await graph.aget_state(config)).values
            check(values["is_complete"] is True, "hitl: terminate marks interview complete")
            check(values["hitl_status"] == HITLStatus.TERMINATED, "hitl: terminate sets TERMINATED status")
            check(
                values["current_question_index"] == 0,
                "hitl: terminate does not fabricate progress through the plan",
            )


async def test_concurrent_writers_do_not_clobber_each_other():
    """Regression test for the exact race the shared state_lock exists to
    prevent: two concurrent read-modify-write updates to the SAME list
    field must both land, not just whichever wrote last."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "checkpoints.sqlite")
        config = {"configurable": {"thread_id": "concurrency-thread-1"}}
        initial_state = make_initial_state(num_questions=1)

        async with AsyncSqliteSaver.from_conn_string(db_path) as cp:
            graph = build_interview_graph(
                analyzer=make_fake_analyzer([EvidenceRecord(relevance="high", follow_up_warranted=False)]),
                checkpointer=cp,
                realtime_mode=False,
            )
            await graph.ainvoke(initial_state.model_dump(), config=config)

            lock = asyncio.Lock()

            async def append_evidence(tag: str):
                async with lock:
                    current = (await graph.aget_state(config)).values.get("evidence_collected", [])
                    ev = EvidenceRecord(relevance="high", follow_up_warranted=False, claims_made=[tag])
                    await graph.aupdate_state(config, {"evidence_collected": current + [ev]})

            await asyncio.gather(append_evidence("A"), append_evidence("B"), append_evidence("C"))

            final = (await graph.aget_state(config)).values["evidence_collected"]
            tags = sorted(_field(e, "claims_made")[0] for e in final)
            check(tags == ["A", "B", "C"], "concurrency: all 3 locked concurrent writers landed, none lost")


async def main():
    print(
        "Running Milestone 6 persistence/HITL/resume/concurrency tests "
        "(fake analyzer + temp SQLite files, no Gemini calls)...\n"
    )
    await test_state_survives_new_graph_instance_same_db()
    await test_hitl_pause_resume_status_and_log()
    await test_hitl_skip_advances_without_follow_up()
    await test_hitl_override_replaces_next_question_once()
    await test_hitl_terminate_ends_interview_immediately()
    await test_concurrent_writers_do_not_clobber_each_other()
    print("\nAll persistence/HITL/resume/concurrency tests passed.")


if __name__ == "__main__":
    asyncio.run(main())