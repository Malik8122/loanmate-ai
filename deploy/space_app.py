"""
Entry point for the free Hugging Face Space (Gradio SDK).

A Gradio Space installs requirements.txt and runs `python app.py`; it only
needs something listening on port 7860. This starts the Gemini Live voice
worker as a child process and serves the FastAPI backend on that port — no
Gradio UI involved. prepare_space.ps1 copies this file into the Space as
app.py.
"""

import os
import subprocess
import sys

import uvicorn

from backend.main import app


def main() -> None:
    worker = subprocess.Popen([sys.executable, "-m", "backend.voice_agent.realtime_agent", "start"])
    try:
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
    finally:
        worker.terminate()


if __name__ == "__main__":
    main()
