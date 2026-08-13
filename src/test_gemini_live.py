import asyncio
import os
import queue

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set")


MODEL = "gemini-3.1-flash-live-preview"

INPUT_SAMPLE_RATE = 16_000
OUTPUT_SAMPLE_RATE = 24_000
CHANNELS = 1
CHUNK_SIZE = 1024


async def main():
    client = genai.Client(api_key=API_KEY)

    audio_queue = queue.Queue()

    print("Connecting to Gemini Live...")

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[
                types.Part(
                    text=(
                        "You are a friendly AI job interviewer. "
                        "You are an AI and must clearly disclose that. "
                        "Keep responses concise and conversational."
                    )
                )
            ]
        ),
    )

    async with client.aio.live.connect(
        model=MODEL,
        config=config,
    ) as session:

        print("CONNECTED!")
        print("Microphone is active.")
        print("Speak to Gemini. Press Ctrl+C to stop.\n")

        async def send_microphone_audio():
            loop = asyncio.get_running_loop()

            def callback(indata, frames, time, status):
                if status:
                    print("Microphone:", status)

                audio_bytes = indata.copy().tobytes()

                asyncio.run_coroutine_threadsafe(
                    session.send_realtime_input(
                        audio=types.Blob(
                            data=audio_bytes,
                            mime_type="audio/pcm;rate=16000",
                        )
                    ),
                    loop,
                )

            with sd.InputStream(
                samplerate=INPUT_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                while True:
                    await asyncio.sleep(0.1)

        async def receive_audio():
            with sd.RawOutputStream(
                samplerate=OUTPUT_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
            ) as speaker:

                async for response in session.receive():

                    if response.server_content is None:
                        continue

                    model_turn = response.server_content.model_turn

                    if model_turn:
                        for part in model_turn.parts:

                            if part.inline_data:
                                audio_data = part.inline_data.data

                                audio_queue.put(audio_data)

                                speaker.write(audio_data)

                    if response.server_content.interrupted:
                        print("\n[Gemini interrupted]\n")

        await asyncio.gather(
            send_microphone_audio(),
            receive_audio(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")