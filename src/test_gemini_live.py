import asyncio
import os
import queue
import threading

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

    # Microphone audio is placed here by the sounddevice thread.
    audio_queue = queue.Queue(maxsize=50)

    # Thread-safe flag.
    # When Gemini is speaking, we temporarily stop feeding
    # microphone audio into Gemini.
    gemini_is_speaking = threading.Event()

    print("Connecting to Gemini Live...")

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
    )

    async with client.aio.live.connect(
        model=MODEL,
        config=config,
    ) as session:

        print("CONNECTED!")
        print("Microphone is active.")
        print("Speak normally.")
        print("Press Ctrl+C to stop.\n")

        # =========================================================
        # MICROPHONE
        # =========================================================

        def microphone_callback(indata, frames, time, status):

            if status:
                print("Microphone:", status)

            # Diagnostic test:
            # Do NOT send microphone audio while Gemini is speaking.
            if gemini_is_speaking.is_set():
                return

            audio_bytes = indata.copy().tobytes()

            try:
                audio_queue.put_nowait(audio_bytes)

            except queue.Full:

                # Drop the oldest chunk instead of blocking
                # the real-time microphone callback.
                try:
                    audio_queue.get_nowait()
                    audio_queue.put_nowait(audio_bytes)

                except queue.Empty:
                    pass

        microphone = sd.InputStream(
            samplerate=INPUT_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=microphone_callback,
        )

        # =========================================================
        # MICROPHONE → GEMINI
        # =========================================================

        async def send_microphone_audio():

            while True:

                try:
                    audio_bytes = audio_queue.get_nowait()

                except queue.Empty:
                    await asyncio.sleep(0.005)
                    continue

                try:

                    await session.send_realtime_input(
                        audio=types.Blob(
                            data=audio_bytes,
                            mime_type="audio/pcm;rate=16000",
                        )
                    )

                except Exception as error:

                    print("\n[Microphone sender error]")
                    print(error)
                    break

        # =========================================================
        # GEMINI → SPEAKER
        # =========================================================

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

                    content = response.server_content

                    # -------------------------------------------------
                    # Candidate transcription
                    # -------------------------------------------------

                    if content.input_transcription:

                        print(
                            "\n[YOU]",
                            content.input_transcription.text,
                            end="",
                            flush=True,
                        )

                    # -------------------------------------------------
                    # Gemini transcription
                    # -------------------------------------------------

                    if content.output_transcription:

                        print(
                            "\n[GEMINI]",
                            content.output_transcription.text,
                            end="",
                            flush=True,
                        )

                    # -------------------------------------------------
                    # Interruption
                    # -------------------------------------------------

                    if content.interrupted:

                        gemini_is_speaking.clear()

                        print(
                            "\n\n========== INTERRUPTED =========="
                        )
                        print(
                            "Gemini reported an interruption."
                        )
                        print(
                            "=================================\n"
                        )

                    # -------------------------------------------------
                    # Gemini turn complete
                    # -------------------------------------------------

                    if content.turn_complete:

                        gemini_is_speaking.clear()

                        print(
                            "\n\n========== TURN COMPLETE =========="
                        )
                        print(
                            "Gemini finished this turn."
                        )
                        print(
                            "===================================\n"
                        )

                    # -------------------------------------------------
                    # Gemini audio
                    # -------------------------------------------------

                    model_turn = content.model_turn

                    if model_turn:

                        # Gemini has started producing audio.
                        gemini_is_speaking.set()

                        for part in model_turn.parts:

                            if part.inline_data:

                                audio_data = part.inline_data.data

                                speaker.write(audio_data)

        # =========================================================
        # START
        # =========================================================

        microphone.start()

        try:

            await asyncio.gather(
                send_microphone_audio(),
                receive_audio(),
            )

        finally:

            microphone.stop()
            microphone.close()


if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print("\nStopped.")