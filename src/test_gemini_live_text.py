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

    print("Connecting to Gemini Live...")

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
    )

    async with client.aio.live.connect(
        model=MODEL,
        config=config,
    ) as session:

        print("CONNECTED!")

        await session.send_client_content(
            turns=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=(
                                "Please give me a detailed 20 second "
                                "introduction to yourself as an AI "
                                "job interviewer."
                            )
                        )
                    ],
                )
            ],
            turn_complete=True,
        )

        print("Waiting for response...\n")

        async for response in session.receive():

            if response.server_content is None:
                continue

            content = response.server_content

            if content.output_transcription:
                print(
                    "[OUTPUT]",
                    content.output_transcription.text,
                    end="",
                    flush=True,
                )

            if content.interrupted:
                print("\n[INTERRUPTED]")

            if content.turn_complete:
                print("\n\n[TURN COMPLETE]")
                break


if __name__ == "__main__":
    asyncio.run(main())