# AI Video Interviewer

An AI-powered live video interviewer that conducts evidence-grounded
technical interviews using a candidate's job description, resume, and
GitHub projects.

## Current Status

🚧 Hackathon build in progress.

The realtime foundation is now working:

**LiveKit Agent → Gemini Realtime → conversational interview**

The next milestone is connecting a browser candidate to the LiveKit room.

---

## Completed

- [x] Project structure initialized
- [x] Python virtual environment configured
- [x] Dependencies captured in `requirements.txt`
- [x] `.gitignore` configured to protect secrets
- [x] Gemini API connection verified
- [x] Gemini Live API connection verified
- [x] Gemini Live streamed audio successfully
- [x] Gemini Live input transcription tested
- [x] Gemini Live output transcription tested
- [x] Gemini Live interruption events tested
- [x] LiveKit CLI installed
- [x] LiveKit Cloud project created
- [x] LiveKit CLI authenticated
- [x] LiveKit credentials verified locally
- [x] LiveKit Agents installed
- [x] LiveKit Google plugin installed
- [x] LiveKit Agent successfully registered with LiveKit Cloud
- [x] Gemini Realtime successfully connected through LiveKit Agent
- [x] LiveKit Agent successfully conducted a multi-turn conversational interview
- [x] Agent introduction and interview questioning verified
- [x] Candidate responses successfully received and followed by Gemini responses

---

## Current Milestone

### Milestone 1 — Realtime Interview Foundation

Status: ✅ Working

Current architecture:

```text
LiveKit Cloud
     ↓
LiveKit Agent
     ↓
Gemini Realtime
     ↓
AI interviewer
     ↓
Two-way conversational interview
```
The LiveKit Agent was tested through the LiveKit Console.

The agent successfully:

Joined the LiveKit environment.
Connected to Gemini Realtime.
Introduced itself as an AI interviewer.
Asked interview questions.
Received candidate responses.
Continued asking relevant follow-up questions.
Maintained a multi-turn conversation.

This confirms that the core realtime AI interviewer path is functional.

### Milestone 2 — Browser test client (COMPLETE)

- src/token_server.py: local FastAPI backend, generates short-lived LiveKit
  tokens server-side (secrets never reach the browser), attaches explicit
  agent dispatch for "ai-interviewer" to each token, serves web/index.html
- web/index.html: minimal browser client — Start Interview button, mic
  publish, agent audio playback, live connection/status log
- Verified: browser connects to a fresh LiveKit room, agent auto-joins via
  token-embedded dispatch, two-way voice conversation confirmed through the
  browser (not just the LiveKit Console)

Run:
  Terminal 1: .\.venv\Scripts\python.exe src\realtime\agent.py dev
  Terminal 2: .\.venv\Scripts\python.exe -m uvicorn src.token_server:app --reload --port 8000
  Browser:    http://localhost:8000/

### ### Milestone 3A — JD + Resume ingestion (COMPLETE)

- src/ingestion/document_parser.py: parses .txt, .md, .pdf, .docx into a
  normalized ParsedDocument (doc_type, filename, source_format, text,
  char_count). No LLM calls, no realtime pipeline involved.
- tests/generate_fixtures.py + tests/test_document_parser.py: prove
  input document -> parser -> normalized text for all 4 formats

Run:
  .\.venv\Scripts\python.exe tests\generate_fixtures.py
  .\.venv\Scripts\python.exe tests\test_document_parser.py

### Milestones 3B–3D — Structured extraction, GitHub ingestion, gap analysis (COMPLETE)

- src/ingestion/structured_extractor.py: Gemini structured JSON extraction
  for JD and resume (prompts in prompts/), writes output/jd.json + resume.json
- src/ingestion/github.py: GitHub REST ingestion (repos, languages, README
  excerpts), GITHUB_TOKEN optional, writes output/github.json
- src/ingestion/gap_analysis.py: deterministic matching of JD requirements
  against resume + GitHub evidence, writes output/gap_analysis.json

Run:
  .\.venv\Scripts\python.exe tests\test_structured_extractor.py
  .\.venv\Scripts\python.exe tests\test_github.py
  .\.venv\Scripts\python.exe tests\test_gap_analysis.py

# LiveKit Console Test

The following conversational behavior was successfully observed:

AI:
Hello. I am your AI interviewer. Today, we will conduct a
professional job interview.

Candidate:
Yes can you tell me the first question?

AI:
Certainly. To begin, could you please provide a brief overview
of your professional background and tell me why you are interested
in this position?

Candidate:
Well, I have studied computer science.

AI:
That's a great foundation. Could you elaborate on your specific
skills and any practical experience you have related to frontend
development?

Candidate:
I've recently worked on a website.

AI:
That sounds like a valuable project. What was your specific role
and responsibilities within the development team for that website?

Candidate:
A mental health website...

AI:
Could you describe a specific technical challenge you encountered
during your work and how you resolved it?

## Current Architecture
                    ┌──────────────────┐
                    │   LiveKit Cloud   │
                    │                  │
                    │     Room         │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  LiveKit Agent   │
                    │                  │
                    │ ai-interviewer   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Gemini Realtime  │
                    │                  │
                    │ Google Realtime  │
                    └────────┬─────────┘
                             │
                             ▼
                    AI Interviewer

### Next Milestone
Browser → LiveKit → Agent → Gemini

The next objective is to create the browser-side interview experience.

## Target flow:

Candidate Browser
       │
       │ microphone / audio
       ▼
LiveKit Room
       │
       ▼
LiveKit Agent
       │
       ▼
Gemini Realtime
       │
       ▼
AI voice response
       │
       ▼
Candidate Browser

Only after this basic browser conversation works should we move on to:

 AI face/avatar
 JD parsing
 Resume parsing
 GitHub grounding
 Question planning
 LangGraph interview flow
 HITL question-plan approval
 Evidence collection
 Scoring
 MCP recruiter interface
 Evaluations
 Reports
Gemini Live Investigation

Before adopting LiveKit, Gemini Live was tested directly using the
google-genai SDK.

The standalone implementation successfully demonstrated:

microphone capture
realtime audio input
streamed Gemini audio output
input transcription
output transcription
turn completion
interruption events

However, the standalone WebSocket implementation eventually encountered:

1011 internal error
keepalive ping timeout; no close frame was received

Because the hackathon requires a reliable realtime conversational layer,
the production architecture was changed to use LiveKit Agents rather than
maintaining a custom low-level Gemini WebSocket transport.

This was a deliberate architectural decision.

## Environment

The following realtime credentials are configured locally:

GEMINI_API_KEY
GOOGLE_API_KEY
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET

GOOGLE_API_KEY and GEMINI_API_KEY intentionally contain the same
Gemini API credential.

The following are reserved for later stages:

AVATAR_API_KEY
GITHUB_TOKEN

Secrets must never be committed to Git.

## Project Structure
AI_Video_Interviewer/
│
├── .env
├── .env.example
├── .gitignore
├── Readme.md
├── Architecture.md
├── requirements.txt
│
├── src/
│   ├── test_gemini.py
│   ├── test_gemini_live.py
│   ├── test_gemini_live_text.py
│   │
│   └── realtime/
│       └── agent.py
│
├── inputs/
├── output/
├── prompts/
├── evals/
├── mcp_server/
└── tests/

## Progress
| Component                         | Status |
| --------------------------------- | ------ |
| Python environment                | ✅      |
| Requirements                      | ✅      |
| Git repository                    | ✅      |
| Gemini API                        | ✅      |
| Gemini Live standalone            | ✅      |
| LiveKit CLI                       | ✅      |
| LiveKit Cloud                     | ✅      |
| LiveKit credentials               | ✅      |
| LiveKit Agents                    | ✅      |
| Google LiveKit plugin             | ✅      |
| LiveKit Agent registration        | ✅      |
| Gemini Realtime through LiveKit   | ✅      |
| Multi-turn interview conversation | ✅      |
| Browser client                    | ⏳      |
| Avatar                            | ⏳      |
| JD grounding                      | ⏳      |
| Resume grounding                  | ⏳      |
| GitHub grounding                  | ⏳      |
| Interview planner                 | ⏳      |
| LangGraph                         | ⏳      |
| HITL                              | ⏳      |
| Scoring                           | ⏳      |
| MCP                               | ⏳      |
| Evaluations                       | ⏳      |
| Reports                           | ⏳      |

## Known Limitations

The current LiveKit test was performed through the LiveKit Console.

The browser candidate interface has not yet been implemented.

Avatar/video presentation has not yet been implemented.

Candidate-specific grounding using JD, resume, and GitHub data has not
yet been implemented.

Interview scoring and evidence extraction have not yet been implemented.

## Current Breakpoint
Working
Python environment             ✅
requirements.txt               ✅
Git repository                 ✅
Gemini API                     ✅
Gemini Live standalone test    ✅
LiveKit CLI                    ✅
LiveKit Cloud                  ✅
LiveKit credentials            ✅
LiveKit Agents                 ✅
Gemini Realtime via LiveKit    ✅
Multi-turn AI interview       ✅
Next
Browser → LiveKit Room → LiveKit Agent → Gemini → Browser audio

Do not begin avatar, LangGraph, GitHub, scoring, or MCP work until the
browser realtime path is working.