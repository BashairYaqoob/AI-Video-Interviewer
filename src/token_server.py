"""
token_server.py

Small local backend for the browser test client.

Responsibilities:
1. Generate short-lived LiveKit access tokens using LIVEKIT_API_KEY /
   LIVEKIT_API_SECRET (these NEVER leave this server / go to the browser).
2. Attach explicit agent dispatch (agent_name="ai-interviewer") to the
   token, so the agent automatically joins the room the browser connects to.
3. Serve the static browser client from web/index.html.

Run with:
    uvicorn src.token_server:app --reload --port 8000
"""

import os
import random
import string

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from livekit import api

load_dotenv()

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# Must exactly match agent_name="ai-interviewer" in src/realtime/agent.py
AGENT_NAME = "ai-interviewer"

app = FastAPI(title="AI Video Interviewer - Token Server")

# Permissive CORS for local hackathon development only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _random_suffix(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


@app.get("/token")
def create_token(identity: str | None = Query(default=None)):
    """
    Issues a LiveKit token for a brand-new room, with the ai-interviewer
    agent explicitly dispatched into it. A fresh room name is generated on
    every call, since LiveKit only honors token-embedded dispatch the first
    time a room is created.
    """
    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        return {"error": "Missing LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET in .env"}

    room_name = f"interview-{_random_suffix()}"
    participant_identity = identity or f"candidate-{_random_suffix(4)}"

    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(participant_identity)
        .with_name(participant_identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)]
            )
        )
        .to_jwt()
    )

    return {
        "token": token,
        "url": LIVEKIT_URL,
        "room": room_name,
        "identity": participant_identity,
    }


# Serves web/index.html at http://localhost:8000/
app.mount("/", StaticFiles(directory="web", html=True), name="web")