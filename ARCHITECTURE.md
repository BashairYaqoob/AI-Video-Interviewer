# Architecture

## Current Progress

### Checkpoint 1A — Gemini Live API

Status: ✅ Working

The project successfully establishes a Gemini Live API session using the
`google-genai` Python SDK.

Current flow:

```text
Python test client
       ↓
google-genai
       ↓
Gemini Live API
       ↓
gemini-3.1-flash-live-preview
       ↓
Audio response chunks