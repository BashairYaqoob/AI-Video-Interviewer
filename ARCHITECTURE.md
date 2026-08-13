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
```

## Checkpoint 1B — Realtime microphone and audio playback

Status: ✅ Working

The standalone Gemini Live test now supports:

- Microphone capture using `sounddevice`
- 16 kHz, 16-bit, mono PCM microphone input
- Realtime audio streaming to Gemini Live
- 24 kHz PCM audio playback through the speakers
- Realtime Gemini audio responses

Current flow:

```text
Microphone
    ↓
16 kHz PCM
    ↓
Gemini Live API
    ↓
24 kHz PCM
    ↓
Speakers

Current limitation

The standalone test observes Gemini's interruption events, but candidate
barge-in has not yet been formally validated as a separate acceptance test.