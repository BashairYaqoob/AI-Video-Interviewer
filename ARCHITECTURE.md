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
```
Current limitation

The standalone test observes Gemini's interruption events, but candidate
barge-in has not yet been formally validated as a separate acceptance test.

## Realtime Investigation — Checkpoint 1C

### Finding

Gemini Live API itself was verified independently using a text-input
test. Two consecutive sessions successfully streamed complete audio
responses and reached `TURN COMPLETE`.

Therefore, the earlier interruption behavior is not currently attributed
to API connectivity or model availability.

### Current issue

The microphone-based realtime client incorrectly receives an
`INTERRUPTED` event while Gemini is speaking and does not successfully
continue the conversation afterward.

The current implementation sends microphone chunks directly from the
`sounddevice` callback into the async Gemini session using
`run_coroutine_threadsafe()`.

This implementation is being replaced with a queue-based audio pipeline
to separate the audio-device thread from the Gemini async event loop.

### Status

- Gemini Live connection: ✅
- Text → Gemini Live → audio: ✅
- Microphone → Gemini Live: ⚠️
- Continuous conversational turn-taking: ❌ not yet verified
- Candidate barge-in: ❌ not yet verified

src/
├── test_gemini.py              ← basic Gemini API test
├── test_gemini_live.py         ← realtime mic test (currently broken)
└── test_gemini_live_text.py    ← known-good Live API test

## Realtime Investigation — Gemini Live

### Gemini Live connectivity

Gemini Live was tested independently with both text input and microphone
input.

The text-based Live test successfully connected, streamed Gemini audio,
and reached TURN COMPLETE.

The microphone test also successfully captured candidate speech and
received a complete Gemini response.

### Initial interruption issue

The first microphone implementation continuously streamed microphone
audio while Gemini was speaking. Gemini reported interruptions before the
candidate intentionally interrupted.

A diagnostic version temporarily stopped sending microphone audio while
Gemini was speaking.

With this change, the first Gemini response completed successfully
without a false interruption.

This confirmed that continuous microphone streaming combined with
automatic activity detection was contributing to the false interruption
behavior.

### Remaining issue

After the first turn completed, the raw Gemini Live WebSocket client
experienced:

`1011 internal error — keepalive ping timeout`

The microphone sender was still attempting to send realtime audio when
the connection closed.

Therefore, the raw microphone test client is treated as a diagnostic
prototype rather than the final realtime transport.

### Architectural decision

Gemini Live remains the realtime AI model.

LiveKit Agents will be used as the production realtime transport and
conversation layer.

This provides a more appropriate foundation for:

- microphone input
- audio output
- turn-taking
- interruption handling
- connection lifecycle
- candidate session management