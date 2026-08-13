import os

from dotenv import load_dotenv

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession
from livekit.plugins import google


load_dotenv()


class Interviewer(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are an AI job interviewer. "
                "For this test, introduce yourself briefly and explain "
                "that you will conduct a professional job interview. "
                "Do not claim to know anything about the candidate yet. "
                "Wait for the candidate to respond."
            )
        )


server = AgentServer()


@server.rtc_session(agent_name="ai-interviewer")
async def ai_interviewer(ctx: agents.JobContext):

    session = AgentSession(
        llm=google.realtime.RealtimeModel(
            voice="Puck",
            temperature=0.7,
        )
    )

    await session.start(
        room=ctx.room,
        agent=Interviewer(),
    )

    await session.generate_reply(
        instructions=(
            "Greet the candidate and introduce yourself as an AI interviewer. "
            "Keep the greeting under 20 seconds."
        )
    )


if __name__ == "__main__":
    agents.cli.run_app(server)