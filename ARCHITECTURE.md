
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