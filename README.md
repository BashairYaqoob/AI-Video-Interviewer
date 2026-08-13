
---

# AI Video Interviewer

An AI-powered live video interviewer that conducts evidence-grounded
technical interviews using a candidate's job description, resume, and
GitHub projects.

## Current Status

🚧 Hackathon build in progress.

### Completed

- [x] Project structure initialized
- [x] Python virtual environment configured
- [x] Gemini API connection verified
- [x] Gemini Live API connection verified
- [x] Gemini Live successfully returned audio response chunks
- [x] Microphone input
- [x] Audio playback
- [x] Realtime Gemini Live audio conversation

### In Progress

- [ ] LiveKit realtime transport
- [ ] AI face/avatar
- [ ] Barge-in / interruption
- [ ] JD parsing
- [ ] Resume parsing
- [ ] GitHub grounding
- [ ] Question planning
- [ ] LangGraph interview flow
- [ ] HITL question-plan approval
- [ ] Scoring and evidence validation
- [ ] MCP server
- [ ] Evaluations

## Running the Gemini Live Test

### Setup

Create a `.env` file:

```env
GEMINI_API_KEY=your_key_here
```
### Install dependencies:
pip install -r requirements.txt
### Run:
python src/test_gemini_live.py

## Project Structure
src/
inputs/
output/
prompts/
evals/
mcp_server/
tests/