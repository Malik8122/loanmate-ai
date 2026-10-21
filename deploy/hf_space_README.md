---
title: LoanMate AI Backend
emoji: 🏦
colorFrom: purple
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
---

# LoanMate AI — backend

FastAPI API and Gemini Live voice worker for the LoanMate AI academic project
(fictional bank, mock customer data). The web frontend is deployed separately
on Vercel. Health check: `/health`. API docs: `/docs`.

Required secrets (Settings → Variables and secrets): `GOOGLE_API_KEY`,
`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.
