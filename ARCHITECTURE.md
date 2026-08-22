# Architecture — AI Video Interviewer

## Goal

A realtime, evidence-grounded AI interviewing system: an AI interviewer
joins a live video call, asks candidate-specific questions grounded in
the candidate's resume, the job description, and their GitHub code, and
produces a defensible hiring scorecard.

```
Recruiter uploads JD + Resume
        ↓
Structured extraction (JD, Resume, GitHub, Gap Analysis)
        ↓
Question Plan generated
        ↓
Recruiter Approval Gate  (approve / edit / reject)
        ↓
Live Interview (LiveKit + Gemini Realtime + LangGraph)
        ↓
Transcript + Evidence + HITL audit log
        ↓
Scoring / Scorecard / PDF report   [not yet built]
        ↓
MCP recruiter interface            [not yet built]
```

Built incrementally — each layer was verified working before the next
was added.

---

## Current status at a glance

| Layer | Status |
|---|---|
| Gemini API / Gemini Live (standalone) | ✅ |
| LiveKit Cloud + Agents + Google plugin | ✅ |
| Browser client (token server + `web/index.html`) | ✅ |
| Document ingestion (JD/resume parsing) | ✅ |
| GitHub grounding (evidence collection) | ✅ |
| Gap analysis | ✅ |
| Question planner | ✅ |
| LangGraph interview engine (typed state, conditional edges) | ✅ |
| Live LiveKit + Gemini Realtime interview loop | ✅ |
| SQLite persistence (`AsyncSqliteSaver`) | ✅ |
| Reconnect / resume | ✅ (basic path verified; edge cases pending) |
| Runtime HITL controller (pause/resume/skip/override/terminate) | ✅ |
| Pre-interview plan approval gate | ✅ |
| External HITL control surface (separate API process) | ✅ |
| Visible AI video face/avatar | ⏳ not started |
| GitHub-grounded question proof (≥3 questions) | ⏳ not verified live |
| Guardrails (banned questions, evidence-required scoring) | ⏳ not started |
| Final scoring / scorecard / PDF | ⏳ not started |
| MCP server | ⏳ not started |
| 5-persona evaluation | ⏳ not started |
| Prompt v1→v2 iteration docs | ⏳ not started |

---

## How we got here (condensed history)

**Realtime foundation.** Started with a standalone Gemini Live
WebSocket client to validate the model itself (mic capture, 16kHz PCM
in / 24kHz PCM out, transcription, turn completion). Hit reliability
issues with continuous mic streaming and spurious interruption events
(`1011 internal error`, keepalive timeouts) — decided not to spend
hackathon time building a production-grade realtime transport by hand,
and adopted **LiveKit** as the transport/session layer, keeping Gemini
as the model. This is Decision 2 below.

**LiveKit Agent.** Registered a LiveKit Cloud project and got a
`livekit-agents` worker (`ai-interviewer`) talking to Gemini Realtime
through the LiveKit Google plugin, with manual turn control so every
agent utterance is graph-driven rather than Gemini free-responding off
static instructions. Verified multi-turn conversation through the
LiveKit Console before adding a browser client.

**Browser client.** `src/token_server.py` mints short-lived,
room-scoped JWTs server-side (embedding `RoomAgentDispatch` so LiveKit
auto-dispatches the agent into the room); `web/index.html` connects
with `livekit-client` and publishes the candidate's mic. Secrets
(`LIVEKIT_API_SECRET`, `GEMINI_API_KEY`) never reach the browser.

**Prep pipeline.** `scripts/run_prep_pipeline.py` runs document
ingestion → structured extraction (Gemini, prompts in `prompts/`) →
GitHub evidence collection → gap analysis → question planning,
producing `output/{jd,resume,github,gap_analysis,interview_plan}.json`.
Each stage is an independent, testable artifact.

**Interview engine.** `src/interview/graph.py` (LangGraph): typed
`InterviewState`, and a flow of `intro → ask_question → receive_answer
[interrupt, pauses for the candidate] → analyze_answer → route` with
conditional edges for follow-up (capped) vs. advance vs. close.
Originally ran on an in-memory `MemorySaver`.

**Live integration + SQLite persistence + HITL (Milestones 5–6).**
Wired the graph into the live voice pipeline: `AgentSession` +
`turn_detection="vad"` drives `_advance_and_ask()`, which steps the
graph and speaks the next question. Swapped the checkpointer from
`MemorySaver` to `AsyncSqliteSaver` (`src/interview/checkpointer.py`)
on the realtime path only — the synchronous test suite still uses
`MemorySaver`. Added durable `thread_id` derivation (job metadata →
room name → candidate/role hash fallback) so a dropped call can find
its existing checkpoint. Added `src/interview/hitl.py`
(`HITLController`): pause/resume/skip/override/terminate, implemented
as reads/writes against the checkpointed state rather than new graph
nodes — the graph structure itself is unchanged from Milestone 4.

**Checkpointer lifetime bug (found via first real multi-turn live
test).** `ai_interviewer()`'s `async with open_sqlite_checkpointer()`
block was closing the SQLite connection right after the first question
was asked, because nothing kept the coroutine alive — the interview is
actually driven afterward by an independent LiveKit event handler, not
by `ai_interviewer()`'s own control flow. Fixed with an
`interview_done = asyncio.Event()`, set on genuine completion, awaited
at the end of `ai_interviewer()` to keep the checkpointer connection
open for the interview's real lifetime; a `participant_disconnected`
listener sets it as a safety net if the candidate just leaves.

**Pre-interview approval gate (Phase 2).** The brief requires a
recruiter approve/edit/reject the generated plan before an interview
can start — the runtime `HITLController` doesn't cover this, since it
only controls an interview already in progress. Added
`PlanApprovalRecord`/`PlanApprovalStatus` (`src/interview/schemas.py`),
`src/interview/plan_approval.py` (approve / edit-and-approve / reject /
`get_approved_questions()`), and `scripts/approve_plan.py` (interactive
+ non-interactive CLI). `agent.py` now calls `get_approved_questions()`
before starting a session and raises before ever joining a room if the
plan isn't approved — verified both that an approved plan proceeds
normally and that the gate blocks an unapproved one.

**External HITL control surface (Phase 3).** `HITLController`'s
methods only read/write checkpointed state — none of them call
`graph.ainvoke()` — which makes it safe to drive from a **separate**
process. `src/interview/hitl_api.py` is a small FastAPI app that
opens its own short-lived `AsyncSqliteSaver` against the same on-disk
file and `thread_id` the live agent is using, and exposes
pause/resume/skip/override/terminate/status as HTTP endpoints. Because
this process can't push into the running agent, a lightweight polling
loop was added inside `ai_interviewer()`
(`_external_hitl_poll_loop()`, ~3s interval) that watches
`hitl_actions_log` for entries this process didn't originate itself,
and reacts — ending the interview on an external terminate, muting
turn-taking on pause, and (guarded against racing a real candidate
answer) advancing past the current question on an external skip.

---

## Design decisions worth defending in the viva

1. **LiveKit over a hand-rolled realtime transport.** A standalone
   Gemini Live WebSocket client hit reliability issues (spurious
   interruption events, unexplained connection drops) that would have
   consumed disproportionate hackathon time to harden. LiveKit is a
   purpose-built realtime transport/session layer; Gemini remains the
   model.

2. **HITL as control-plane state, not graph nodes.** Pause/resume/
   skip/override/terminate read or write `InterviewState` fields
   directly via `aupdate_state`, rather than being LangGraph nodes.
   The graph already pauses naturally at the `receive_answer`
   `interrupt()`; HITL actions are things that happen *while* the
   graph sits at that pause point. This keeps the graph's structure
   identical to the pre-HITL version and avoids fighting LangGraph's
   interrupt/resume semantics with parallel control edges.

3. **One coarse-grained lock per interview, not per-field locking.**
   `state_lock` in `agent.py` serializes every writer for a given
   thread: graph advancement, background evidence analysis, and
   in-process HITL actions. Conservative, but a live interview is
   fundamentally sequential and HITL actions are rare/human-triggered,
   so real contention is negligible — not worth per-field optimistic
   locking.

4. **Skip is a real (flagged) answer, not a graph bypass.** A skip
   resumes the `receive_answer` interrupt with a sentinel that becomes
   `AnswerRecord(skipped=True)`, so skips are auditable in the
   transcript, and both routers explicitly check `.skipped` before
   applying follow-up logic.

5. **External HITL via a separate process + polling, not a shared
   in-memory channel.** LiveKit gives no push channel into a running
   agent process from outside. Since `HITLController` only ever
   touches durable SQLite state, a second FastAPI process can safely
   issue control actions against the same checkpoint file without any
   shared in-process state — SQLite is the coordination point. The
   running agent polls for actions it didn't originate itself (every
   ~3s) so an external terminate/pause/skip is still noticed promptly
   even while the interview is silently waiting on a candidate's turn.
   Skip is additionally guarded against racing a real candidate answer
   arriving at the same instant.

6. **Approval gate kept separate from runtime HITL.** The brief's
   "recruiter must approve/edit/reject before the interview starts" is
   a different mechanism from "recruiter can pause/skip/terminate a
   running interview" — modeling them as one system would conflate a
   one-time go/no-go gate with an ongoing control channel. They're
   implemented as independent modules (`plan_approval.py` vs.
   `hitl.py`) that don't share code, only the same underlying
   `InterviewPlan`/`QuestionRecord` schema types.

---

## Known limitations (stated honestly)

1. **In-process HITL mirror can go briefly stale.** `agent.py` keeps
   an in-process `hitl_mirror["paused"]` cache for fast synchronous
   checks in its LiveKit event handler. Actions from `hitl_api.py`
   update durable state immediately, but the mirror only catches up on
   the next poll tick (~3s) or the next local HITL call — not
   instantaneous.
2. **Pause does not buffer a mid-flight transcript.** A candidate
   answer arriving in the window between pause taking effect and
   resume is dropped, not queued for replay.
3. **`route_immediate`'s minimum-answer-length heuristic is defined
   but unused** — a pre-existing gap, not fixed as part of any phase
   so far.
4. **Thread-ID fallback (candidate name + role hash) can collide** for
   two interviews of the same candidate/role on the same day, if
   neither job metadata nor a stable room name is available.
5. **Candidate microphone audio intermittently stops reaching the
   agent** after the first question in some live sessions (no further
   `user_input_transcribed` events). Confirmed the agent's own speech
   and LiveKit/room/process are unaffected, so this is suspected to be
   browser-side (mic permission or track-publish issue in
   `web/index.html`) — not yet root-caused. Deferred; needs a browser
   DevTools console check on a fresh join.
6. **SQLite/recovery has only been validated for the basic reconnect
   path**, not exhaustively for every disconnect timing / concurrent
   writer scenario.
7. **`langgraph-checkpoint-sqlite`'s exact API surface** (the optional
   `.setup()` call in `checkpointer.py`) was written without being
   able to verify it against the installed package version at the
   time; confirmed working in practice via live testing since, but
   worth being aware of if the package is ever upgraded.

---

## Repository layout

```
AI_Video_Interviewer/
├── inputs/                       jd.<ext>, resume.<ext>
├── output/                       jd.json, resume.json, github.json,
│                                  gap_analysis.json, interview_plan.json,
│                                  interview_plan_approval.json,
│                                  interview_checkpoints.sqlite
├── web/index.html                browser client
├── scripts/
│   ├── run_prep_pipeline.py      JD/resume -> ... -> interview_plan.json
│   └── approve_plan.py           recruiter approval gate CLI
├── src/
│   ├── token_server.py           mints LiveKit room-scoped JWTs
│   ├── realtime/agent.py         LiveKit Agent — live interview loop
│   ├── ingestion/                document_parser, structured_extractor,
│   │                             github, gap_analysis
│   └── interview/
│       ├── schemas.py            QuestionRecord, AnswerRecord, InterviewPlan,
│       │                         EvidenceRecord, HITL*, PlanApproval*
│       ├── state.py              InterviewState
│       ├── question_planner.py
│       ├── answer_analysis.py
│       ├── graph.py / nodes.py / router.py
│       ├── checkpointer.py       AsyncSqliteSaver wrapper (realtime path only)
│       ├── hitl.py               HITLController (runtime control-plane)
│       ├── hitl_api.py           external FastAPI control surface (Phase 3)
│       └── plan_approval.py      pre-interview approval gate (Phase 2)
├── prompts/                      *_v1.txt + ITERATION_NOTES.md
└── tests/
```

---

## Next planned work

Visible AI avatar → GitHub-grounding proof → guardrails → scoring/
scorecard/PDF → MCP server → 5-persona evaluation → prompt v1→v2 docs →
final submission package. See the project plan for the full phase
breakdown.