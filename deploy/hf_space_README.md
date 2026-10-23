---
title: LoanMate AI Backend
emoji: 🏦
colorFrom: purple
colorTo: pink
sdk: gradio
python_version: "3.12"
app_file: app.py
pinned: false
---

# LoanMate AI — backend

FastAPI API and Gemini Live voice worker for the LoanMate AI academic project
(fictional bank, mock customer data). The web frontend is deployed separately
on Vercel. This Space uses the free Gradio runtime only to run `app.py`, which
serves the API on port 7860 — there is no Gradio interface.

Health check: `/health`. API docs: `/docs`.

Required secrets (Settings → Variables and secrets): `GOOGLE_API_KEY`,
`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.
