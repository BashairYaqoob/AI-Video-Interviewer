"""
hitl_api.py

Phase 3 — external recruiter-facing control surface for HITLController.
Runs as a SEPARATE FastAPI process from the live agent worker
(src/realtime/agent.py). Talks to the same on-disk SQLite checkpoint
file, keyed by thread_id, rather than sharing any in-process state with
the running agent — the agent process and this API process do not
import from each other.

LIMITATION (documented, not fixed here): agent.py keeps an in-process
`hitl_mirror` cache of pause state for fast synchronous checks in its
LiveKit event handler. Actions issued through this API update the
durable SQLite state immediately, but agent.py's mirror only
re-synchronizes the next time ITS OWN handle_pause/handle_resume runs.
A transcript that arrives in the small window between an external
pause and agent.py's next state touch may still be processed. See
ARCHITECTURE.md.

Run:
    uvicorn src.interview.hitl_api:app --port 8001 --reload
"""

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.interview.checkpointer import open_sqlite_checkpointer
from src.interview.graph import build_interview_graph
from src.interview.hitl import HITLController
from src.interview.schemas import QuestionRecord, HITLStatus

app = FastAPI(title="AI Video Interviewer — Recruiter HITL Control")


class ActorNote(BaseModel):
    actor: str = "recruiter"
    note: str = ""


class OverrideQuestionRequest(BaseModel):
    question: QuestionRecord
    actor: str = "recruiter"
    note: str = ""


async def _with_controller(thread_id: str):
    """
    Builds a short-lived graph + HITLController against the SAME on-disk
    checkpoint file agent.py uses, scoped to one request. A fresh
    asyncio.Lock() here is fine — this process never runs the interview
    loop itself, only issues discrete control actions, so there is no
    concurrent writer within THIS process to serialize against. The
    real cross-process safety comes from SQLite's own file-level
    locking (see checkpointer.py / agent.py's state_lock comment for
    the in-process case this does NOT need to replicate here).
    """
    config = {"configurable": {"thread_id": thread_id}}
    async with open_sqlite_checkpointer() as checkpointer:
        graph = build_interview_graph(realtime_mode=True, checkpointer=checkpointer)
        existing = await graph.aget_state(config)
        if not existing.values:
            raise HTTPException(status_code=404, detail=f"No interview found for thread_id={thread_id!r}")
        hitl = HITLController(graph, config, asyncio.Lock())
        yield hitl, graph, config


@app.get("/interviews/{thread_id}/status")
async def get_status(thread_id: str):
    async for hitl, graph, config in _with_controller(thread_id):
        values = (await graph.aget_state(config)).values
        return {
            "thread_id": thread_id,
            "hitl_status": values.get("hitl_status"),
            "current_question_index": values.get("current_question_index"),
            "is_complete": values.get("is_complete"),
            "hitl_actions_log": values.get("hitl_actions_log", []),
        }


@app.post("/interviews/{thread_id}/pause")
async def pause_interview(thread_id: str, body: ActorNote):
    async for hitl, _, _ in _with_controller(thread_id):
        await hitl.pause(actor=body.actor, note=body.note)
        return {"status": "paused"}


@app.post("/interviews/{thread_id}/resume")
async def resume_interview(thread_id: str, body: ActorNote):
    async for hitl, _, _ in _with_controller(thread_id):
        await hitl.resume(actor=body.actor, note=body.note)
        return {"status": "resumed"}


@app.post("/interviews/{thread_id}/skip")
async def skip_question(thread_id: str, body: ActorNote):
    """
    NOTE: unlike agent.py's in-process handle_skip, this endpoint alone
    cannot make the graph advance to the next question — that requires
    calling graph.ainvoke(Command(resume=sentinel), ...), which is the
    realtime turn-taking step agent.py's _advance_and_ask performs.
    Doing that from this separate process would race with agent.py
    potentially doing the same thing from a live candidate turn at the
    same moment. So this endpoint only records the skip intent/sentinel
    the same way hitl.skip_current_question() does today; agent.py's
    own turn-handling picks it up on the interview's next natural step.
    Confirm this against hitl.py's actual skip_current_question()
    implementation — if it already only writes state and does not
    itself invoke the graph, this is already correct as-is.
    """
    async for hitl, _, _ in _with_controller(thread_id):
        sentinel = await hitl.skip_current_question(actor=body.actor, note=body.note)
        return {"status": "skip_recorded", "sentinel": sentinel}


@app.post("/interviews/{thread_id}/override-question")
async def override_question(thread_id: str, body: OverrideQuestionRequest):
    async for hitl, _, _ in _with_controller(thread_id):
        await hitl.override_next_question(body.question, actor=body.actor, note=body.note)
        return {"status": "override_set"}


@app.post("/interviews/{thread_id}/terminate")
async def terminate_interview(thread_id: str, body: ActorNote):
    async for hitl, _, _ in _with_controller(thread_id):
        await hitl.terminate(actor=body.actor, note=body.note)
        return {"status": "terminated"}