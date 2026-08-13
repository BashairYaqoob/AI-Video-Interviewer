import asyncio
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set")


MODEL = "gemini-3.1-flash-live-preview"


async def main():
    client = genai.Client(api_key=API_KEY)

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[
                types.Part(
                    text=(
                        "You are a friendly AI job interviewer. "
                        "You are an AI and must disclose that clearly. "
                        "For this test, respond briefly and naturally."
                    )
                )
            ]
        ),
    )

    print("Connecting to Gemini Live...")

    async with client.aio.live.connect(
        model=MODEL,
        config=config,
    ) as session:

        print("CONNECTED!")
        print("Sending test message...")

        await session.send_client_content(
            turns=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text="Hello! Please say hello to me and tell me you are ready for the interview."
                        )
                    ],
                )
            ],
            turn_complete=True,
        )

        print("Waiting for Gemini's response...\n")

        async for response in session.receive():

            if response.server_content is None:
                continue

            model_turn = response.server_content.model_turn

            if model_turn:
                for part in model_turn.parts:

                    if part.text:
                        print("TEXT:", part.text)

                    if part.inline_data:
                        print(
                            "AUDIO RECEIVED:",
                            len(part.inline_data.data),
                            "bytes"
                        )

            if response.server_content.turn_complete:
                print("\nTURN COMPLETE")
                break


if __name__ == "__main__":
    asyncio.run(main())