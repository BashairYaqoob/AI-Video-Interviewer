
---

### `Architecture.md`

```md
# Architecture

## Project Goal

The AI Video Interviewer is designed as a realtime, evidence-grounded
interviewing system.

Target architecture:

```text
Candidate Browser
       ↓
LiveKit Room
       ↓
LiveKit Agent
       ↓
Gemini Realtime
       ↓
Interview Logic
       ↓
Transcript + Evidence
       ↓
Scoring / Report
       ↓
MCP Recruiter Interface

The project is being developed incrementally so that every major layer is
tested before the next layer is added.
```
# Phase 1 — Realtime Foundation
## Checkpoint 1A — Gemini API

Status: ✅ Working

The project successfully establishes a Gemini API connection using the
Google Gemini Python SDK.

An initial test using:

gemini-2.5-flash

returned a 404 NOT_FOUND because the model was no longer available to
new users.

The implementation was updated to use an available Gemini model and the
connection was successfully verified.
 
## Checkpoint 1B — Gemini Live

Status: ✅ Working

Gemini Live was successfully tested independently.

The standalone test verified:

realtime connection
microphone capture
16 kHz, 16-bit, mono PCM input
streamed Gemini audio output
24 kHz PCM playback
input transcription
output transcription
turn completion
interruption events

### Basic flow:

Microphone
    ↓
16 kHz PCM
    ↓
Gemini Live API
    ↓
24 kHz PCM
    ↓
Speakers
## Checkpoint 1C — Gemini Live Investigation

Status: ⚠️ Diagnostic prototype

The standalone microphone implementation revealed problems with
continuous microphone streaming and automatic activity detection.

Gemini could report an interruption while it was speaking even when the
candidate had not intentionally interrupted.

The implementation was investigated and the text-based Gemini Live test
confirmed that Gemini Live itself was capable of producing complete
multi-turn responses.

The standalone microphone implementation eventually encountered:

1011 internal error
keepalive ping timeout; no close frame was received

The error occurred after a completed turn while the microphone sender was
still attempting to communicate with the WebSocket.

### Architectural decision

Rather than spending the hackathon implementing and maintaining a custom
low-level realtime WebSocket transport, LiveKit was selected as the
production realtime transport and session layer.

Gemini remains the AI model.

LiveKit handles the realtime communication layer.

## Checkpoint 1D — LiveKit Cloud

Status: ✅ Working

LiveKit CLI was installed and authenticated.

CLI version:

lk version 2.18.2

LiveKit Cloud project:

ai-video-interviewer

LiveKit URL:

wss://ai-video-interviewer-d8akvoul.livekit.cloud

The project successfully authenticated with:

LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET

The credentials were verified locally without exposing their values.

## Checkpoint 1E — LiveKit Agents

Status: ✅ Working

The following packages are installed:

livekit-agents==1.6.10
livekit-plugins-google==1.6.10

The Google plugin successfully imports.

The LiveKit Agent successfully registered with LiveKit Cloud.

Agent name:

ai-interviewer

The initial worker registration was successfully observed in the terminal:

starting worker
plugin registered: livekit.plugins.google
registered worker

## Checkpoint 1F — Gemini Realtime Through LiveKit

Status: ✅ Working

The first real LiveKit Agent was implemented using the LiveKit Google
Realtime plugin.

Current agent structure:

src/
└── realtime/
    └── agent.py

The agent uses:

google.realtime.RealtimeModel()

with the Gemini realtime model provided through the LiveKit Google plugin.

The initial interviewer instructions tell the agent to:

introduce itself
behave as a professional job interviewer
avoid claiming knowledge about the candidate before receiving it
wait for candidate responses

LiveKit Console Acceptance Test

Status: ✅ Passed

The agent was launched and tested through the LiveKit Console.

The agent successfully produced an initial greeting:

Hello. I am your AI interviewer. Today, we will conduct a
professional job interview. I look forward to our conversation.
Please feel free to start whenever you are ready.

The candidate then interacted with the agent across multiple turns.

Observed conversation:

Candidate:
Yes can you tell me the first question?

Agent:
Certainly. To begin, could you please provide a brief overview
of your professional background and tell me why you are interested
in this position?

Candidate:
Well, I have studied computer science.

Agent:
That's a great foundation. Could you elaborate on your specific
skills and any practical experience you have related to frontend
development, perhaps through projects or internships?

Candidate:
I've recently worked on a website.

Agent:
That sounds like a valuable project. What was your specific role
and responsibilities within the development team for that website?

Candidate:
A mental health website...

Agent:
Could you describe a specific technical challenge you encountered
during your work and how you resolved it?

This is the first successful demonstration of the intended conversational
behavior through the LiveKit Agent architecture.

## Milestone 2 — Browser Client (Verified Working)

Browser (web/index.html, livekit-client via CDN)
   ↓ GET /token
Token server (src/token_server.py) — mints token server-side,
   embeds RoomAgentDispatch(agent_name="ai-interviewer")
   ↓ token + url
Browser connects directly to LiveKit Cloud room, publishes mic
   ↓ (agent auto-dispatched by LiveKit on room creation)
LiveKit Agent (src/realtime/agent.py) joins same room
   ↓
Gemini RealtimeModel → audio → back through room → browser <audio> element

Secrets (LIVEKIT_API_SECRET, GEMINI_API_KEY) remain server-side only;
browser only ever receives a short-lived room-scoped JWT.

## Milestone 3A — Document Ingestion (Verified Working)

Input file (.txt / .md / .pdf / .docx)
   ↓
parse_document() [src/ingestion/document_parser.py]
   ↓
ParsedDocument { doc_type, filename, source_format, text, char_count }

Isolated from the realtime pipeline — no LLM calls yet. This will later
feed into separate jd_parser / resume_parser agents that call an LLM for
structured extraction (competencies, claims, skills, links) — not built yet.

## Milestones 3B–3D — Prep Pipeline (Verified Working)

Normalized text (Milestone 3A)
   ↓
structured_extractor.py (Gemini, prompts/*.txt) --> jd.json, resume.json
   ↓
github.py (GitHub REST API) --> github.json
   ↓
gap_analysis.py (deterministic matching) --> gap_analysis.json

All four output/ files are independent JSON artifacts, not yet wired into
the realtime pipeline or a LangGraph — that's the next milestone.

## Milestone 4 — Interview Intelligence Layer (Verified Working)

jd.json + resume.json + github.json + gap_analysis.json (Milestone 3)
   ↓
question_planner.py (Gemini) --> InterviewPlan
   ↓
InterviewState (Pydantic) seeded with plan + JD/resume/GitHub/gap context
   ↓
LangGraph (graph.py):
  intro -> ask_question -> receive_answer [interrupt: pause for answer]
    -> analyze_answer (answer_analysis.py, Gemini)
    -> route_after_analysis:
         follow_up_warranted & under cap -> ask_follow_up -> receive_answer (loop)
         more questions remain           -> advance_question -> ask_question (loop)
         plan exhausted                  -> closing -> END

Checkpointer: in-memory (MemorySaver) for now. Graph pauses genuinely
between questions/follow-ups via interrupt()/Command(resume=...) — this
is the same mechanism planned for the HITL recruiter-approval gate later.

Scope: interview control + evidence collection only. No final competency
scoring yet. Not yet connected to the live LiveKit/Gemini voice pipeline.

## Milestone 5 — Live Interview Integration (Verified Working)

output/{jd,resume,github,gap_analysis,interview_plan}.json (Milestone 3-4)
   ↓
agent.py: InterviewState seeded, interview graph compiled (in-memory
checkpointer — SQLite swap is Milestone 6)
   ↓
AgentSession(llm=Gemini RealtimeModel, turn_detection="manual")
   ↓
Loop: user_input_transcribed (final) -> commit_user_turn()
   -> graph.invoke(Command(resume=transcript))
   -> graph decides: follow-up | next question | closing
   -> generate_reply(instructions="ask exactly: <question>")

Manual turn control ensures every agent utterance is graph-driven, not
Gemini free-responding off static instructions.

# Milestone 6 addendum — persistence, HITL, resume/recovery

(Merge the relevant parts of this into your existing ARCHITECTURE.md —
this is written as a standalone addendum since I only had the individual
source files, not the full document, to edit in place.)

## What changed

- `MemorySaver` → `AsyncSqliteSaver` (`src/interview/checkpointer.py`) on
  the realtime path only. The synchronous test suite / default
  `build_interview_graph()` behavior is unchanged (still `MemorySaver`,
  still `.invoke()`/`.get_state()`).
- `src/realtime/agent.py` now drives the graph entirely through the
  async API (`ainvoke`/`aget_state`/`aupdate_state`) instead of
  `asyncio.to_thread`-wrapping the synchronous one. Only
  `answer_analysis.analyze_answer()` itself (the actual Gemini call)
  still runs via `asyncio.to_thread` — that part is intentionally
  unchanged from Milestone 5.
- Durable thread IDs (`_derive_thread_id`) replace the previous random
  `uuid.uuid4()` per process start, so a reconnect can compute the same
  `thread_id` and find existing checkpointed state.
- HITL (`src/interview/hitl.py`) is implemented as an external
  control-plane layer over the checkpointed state, not as new graph
  nodes/edges — the graph structure from Milestone 4C is unchanged.
- A single `asyncio.Lock` (`state_lock` in `agent.py`) serializes every
  writer to a given interview's state: the main advance-the-graph flow,
  background evidence analysis, and all HITL actions.
- Fixed the `awaiting_answer`/`processing_answer` closure-shadowing bug
  (see the comment block above their declaration in `agent.py`).

## Design decisions worth defending in the viva

**HITL as control-plane state, not graph nodes.** Pause/resume/skip/
override/terminate all read or write `InterviewState` fields directly
via `aupdate_state`, rather than being represented as LangGraph nodes.
The graph already has a natural pause point (the `receive_answer`
`interrupt()`); HITL actions are things that happen *while* the graph is
sitting at that pause point, not new transitions through it. This keeps
the graph's node/edge count and structure identical to Milestone 4C and
avoids fighting LangGraph's interrupt/resume semantics with parallel
control edges.

**One coarse-grained lock, not per-field locking.** All state writers
for one interview thread share a single `asyncio.Lock`. This is
correct but conservative — it serializes background evidence writes,
HITL actions, and graph advances even when, in principle, some of them
touch disjoint fields. Given that a live interview is fundamentally
sequential (one question in flight at a time) and HITL actions are rare,
human-triggered events, the actual contention this lock introduces is
negligible; the alternative (per-field optimistic locking / CAS against
the checkpointer) was judged not worth the complexity for the amount of
real concurrency here.

**HITL skip is modeled as a real answer, not a graph bypass.** A skip
resumes the `receive_answer` interrupt with a sentinel value
(`{"__hitl_skip__": True}`) that `receive_answer_node` turns into a real
`AnswerRecord(skipped=True)`. This means skips show up in the transcript
and are auditable, and both routers (`route_after_analysis`,
`route_immediate`) explicitly check `answer.skipped` before applying any
follow-up logic.

**Override affects content, not position.** `hitl_override_question`
replaces *what* is asked next; it does not touch `current_question_index`
or the underlying `interview_plan`. The plan still advances normally
afterward. This was a deliberate simplification — inserting an
out-of-plan question without disturbing "how far through the plan are
we" bookkeeping.

## Latency

Not independently re-measured in this milestone — the realtime
voice/turn-taking path (Gemini Realtime, VAD, endpointing) is unchanged
from Milestone 5. The only latency-relevant change is that state I/O
around each turn now hits a real SQLite file (via `aiosqlite`/
`AsyncSqliteSaver`) instead of an in-memory dict. This should be small
(local disk, small rows) but has not been measured — re-run your
existing latency measurement methodology from Milestone 5 and update the
number in ARCHITECTURE.md; don't assume it's unchanged.

## Known limitations / risks (state these honestly rather than hide them)

1. **`langgraph-checkpoint-sqlite` API surface was not verified against
   your installed version.** This was written in an environment with no
   package registry access, so `AsyncSqliteSaver.from_conn_string(...)`
   / the optional `.setup()` call in `checkpointer.py` could not be
   executed against your actual installed version. If it raises an
   `ImportError`/`AttributeError`, check `pip show
   langgraph-checkpoint-sqlite` and adjust.
2. **Pause does not buffer a mid-flight transcript.** If a candidate's
   answer transcript arrives in the brief window between a pause taking
   effect and the recruiter resuming, that transcript is dropped, not
   queued for replay. The candidate would need to repeat their answer
   after resume.
3. **The in-process HITL "paused" mirror (`hitl_mirror`) only stays in
   sync with actions taken through this same process's `handle_pause`/
   `handle_resume`.** If a future external control channel (MCP tool in
   a separate process, admin API, etc.) writes `hitl_status` directly
   against the same SQLite file, this process won't see it until the
   next local HITL call or an explicit re-read. Wiring the actual
   external control channel is out of scope for this milestone —
   `handle_pause`/`handle_resume`/`handle_skip`/
   `handle_override_question`/`handle_terminate` in `agent.py` are the
   intended integration points for whatever transport you choose next.
4. **The realtime local follow-up heuristic (`route_immediate`) is
   still a no-op beyond "advance or close"** — `MIN_ANSWER_WORDS_BEFORE_FOLLOWUP`
   remains unused, same as before this milestone. Not a regression, but
   also not fixed here; it's a pre-existing gap, noted for completeness.
5. **The last-resort thread_id fallback (candidate name + role hash)
   can collide** for two different interviews of the same candidate for
   the same role on the same day, if neither job metadata nor a stable
   room name is available. Pass a real scheduling-system interview ID
   via job metadata in production to avoid relying on this branch.
6. **Tests could not be executed in the environment they were written
   in** (no `langgraph`/`livekit-agents`/`langgraph-checkpoint-sqlite`
   installed, no network access to install them). They were written to
   mirror the exact conventions and assertions of the pre-existing
   `test_interview_graph.py` and reviewed carefully by hand, but you
   should run them yourself before trusting them — see the commands
   below.

# Current Realtime Architecture
                 LIVEKIT CLOUD
                      │
                      ▼
              ┌───────────────┐
              │  LiveKit Room │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ LiveKit Agent │
              │               │
              │ ai-interviewer│
              └───────┬───────┘
                      │
                      ▼
              ┌────────────────┐
              │ Gemini Realtime│
              │                │
              │ Google Plugin  │
              └───────┬────────┘
                      │
                      ▼
              AI Interview Logic

# Next Checkpoint — Browser Integration

Status: ⏳ NEXT

The next milestone is:

Candidate Browser
       ↓
LiveKit Room
       ↓
LiveKit Agent
       ↓
Gemini Realtime
       ↓
Browser audio

The objective is to allow a candidate to join from a browser and have a
real two-way voice conversation with the existing AI interviewer.

# Acceptance criteria:

browser can connect to LiveKit
microphone can be published
agent receives candidate audio
Gemini generates a response
browser receives agent audio
multiple conversational turns work

Only after this acceptance test passes should additional application
layers be introduced.

# Planned Architecture After Realtime Foundation

Once browser realtime communication is stable, the architecture will
expand:

                         Browser
                            │
                            ▼
                     LiveKit Room
                            │
                            ▼
                     LiveKit Agent
                            │
             ┌──────────────┴──────────────┐
             │                             │
             ▼                             ▼
      Gemini Realtime                Interview State
             │                             │
             │                       LangGraph
             │                             │
             ▼                             ▼
       Conversation              Question Planner
                                           │
                    ┌──────────────────────┼───────────────────┐
                    │                      │                   │
                    ▼                      ▼                   ▼
                   JD                   Resume              GitHub
                Grounding             Grounding           Grounding
                    │                      │                   │
                    └──────────────────────┼───────────────────┘
                                           │
                                           ▼
                                  Evidence Collection
                                           │
                                           ▼
                                        Scoring
                                           │
                                           ▼
                                     Scorecard
                                           │
                                           ▼
                                  MCP Recruiter UI

# Planned Components

## Job Description Parser

Extract:

required skills
preferred skills
responsibilities
experience requirements
evaluation criteria

## Resume Parser

Extract candidate evidence:

education
experience
projects
technologies
achievements

## GitHub Grounding

Use public repositories to provide additional evidence about:

technologies used
project complexity
code activity
implementation details

## Question Planner

Generate an interview plan based on:

Job Description
      +
Resume
      +
GitHub evidence
      ↓
Question Plan

## LangGraph Interview Flow

Manage interview state and determine:

current competency
questions already asked
evidence collected
missing evidence
follow-up questions
completion conditions

## HITL

Allow recruiter approval/editing of the generated question plan before
the interview begins.

## Scoring

Scores must be grounded in observed evidence from:

candidate responses
resume
GitHub
job requirements
## MCP

Provide a recruiter-facing interface for accessing:

candidate profile
transcript
evidence
scorecard
interview report

## Current Project Status
Component	Status
Python environment	✅
Requirements	✅
Git repository	✅
Gemini API	✅
Gemini Live	✅
Gemini Live audio	✅
Gemini Live transcription	✅
LiveKit CLI	✅
LiveKit Cloud	✅
LiveKit credentials	✅
LiveKit Agents	✅
Google LiveKit plugin	✅
LiveKit Agent registration	✅
Gemini Realtime through LiveKit	✅
Multi-turn interview	✅
Browser client	⏳
Avatar	⏳
JD parser	⏳
Resume parser	⏳
GitHub grounding	⏳
Question planner	⏳
LangGraph	⏳
HITL	⏳
Scoring	⏳
MCP	⏳
Evaluations	⏳
Reports	⏳

# Important Architectural Decisions
### Decision 1 — Gemini remains the realtime model

Gemini Realtime provides the conversational AI capability.

### Decision 2 — LiveKit handles realtime transport

LiveKit replaces the custom standalone Gemini WebSocket transport for the
production application.

### Decision 3 — Build incrementally

Each major subsystem must pass an acceptance test before the next layer
is added.

### Decision 4 — Keep secrets local

API keys and secrets remain in .env and are excluded from Git.

### Decision 5 — Explainability is a requirement

The final architecture must remain understandable for the hackathon viva.

Current Breakpoint
Working
Python environment             ✅
requirements.txt               ✅
Git repository                 ✅
Gemini API                     ✅
Gemini Live standalone         ✅
LiveKit CLI                    ✅
LiveKit Cloud                  ✅
LiveKit credentials            ✅
LiveKit Agents                 ✅
Google plugin                  ✅
Gemini Realtime via LiveKit    ✅
Multi-turn interview           ✅
Next
Browser → LiveKit Room → LiveKit Agent → Gemini → Browser audio
Not Started
Avatar
JD parser
Resume parser
GitHub agent
Question planner
LangGraph
HITL
Scoring
MCP
Evaluations
Reports


### One more thing: save the conversation as an actual artifact

I'd also create:

```text
output/
└── livekit_console_interview_2026-08-14.md