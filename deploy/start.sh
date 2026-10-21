#!/bin/sh
# Starts the Gemini Live voice worker in the background and the API in the
# foreground. The container stops if the API stops.
set -e

python -m backend.voice_agent.realtime_agent start &

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-7860}"
