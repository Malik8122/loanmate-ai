# Deploying LoanMate AI for free

The app is deployed in two pieces on free tiers:

| Piece | Host | URL you get |
| --- | --- | --- |
| Backend API + Gemini Live voice worker | Hugging Face Spaces (Gradio SDK, free CPU) | `https://<hf-user>-<space-name>.hf.space` |
| React web app (`frontend/web`) | Vercel (Hobby plan) | `https://<project>.vercel.app` |

**Simplest option — everything on Streamlit:** skip sections 1 and 2 and follow
[section 2b](#2b-everything-on-streamlit-community-cloud-no-separate-backend). The
Streamlit app (`frontend/app.py`) then runs the backend and voice worker itself, so you
only need a GitHub account and a Streamlit Community Cloud account.

LiveKit Cloud (calls) and the Gemini API (AI) stay on the free plans you already use.

You need: a Hugging Face account, a Vercel account, the project on GitHub, and the four
keys from your local `.env`. Total time: about 20–30 minutes, most of it waiting for the
first backend build.

---

## 1. Backend on Hugging Face Spaces

1. Go to <https://huggingface.co/new-space>.
   - **Space name:** e.g. `loanmate-backend`
   - **SDK:** **Gradio** → **Blank** template (Docker Spaces are now paid; the Gradio runtime
     is free and just runs our `app.py`, which serves the API — there is no Gradio interface)
   - **Hardware:** CPU basic (free)
   - **Visibility:** Public or Private (Private keeps the page private, but the frontend must
     reach the API, so use **Public** for the demo).
2. In the new Space, open **Settings → Variables and secrets** and add these as **secrets**
   (values from your local `.env`):
   - `GOOGLE_API_KEY`
   - `LIVEKIT_URL`
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`

   Don't add `PORT` or `HOST` — the Space must listen on its default port 7860.
3. Create a Hugging Face **access token** with *write* permission:
   <https://huggingface.co/settings/tokens>. Git uses it as your password when you push.
4. In PowerShell, from the project folder:

   ```powershell
   git lfs install
   git clone https://huggingface.co/spaces/<hf-user>/loanmate-backend ..\loanmate-backend
   .\deploy\prepare_space.ps1 -SpaceDir ..\loanmate-backend
   cd ..\loanmate-backend
   git add -A
   git commit -m "Deploy LoanMate backend"
   git push
   ```

   When asked to sign in, use your Hugging Face username and the access token.
5. The Space builds automatically (about 5–10 minutes the first time). When it shows
   **Running**, open `https://<hf-user>-loanmate-backend.hf.space/health` — it should say
   `{"status":"ok",...}`. (The Space's own page may show `{"detail":"Not Found"}` — that's
   normal: the backend is an API with no home page. `/docs` lists every endpoint.)

To update the backend later, run step 4 again from `.\deploy\prepare_space.ps1` onward.

## 2. Frontend on Vercel

1. Push the project to GitHub. Vercel deploys from a branch — merge the feature branch into
   `main`, or choose the branch in Vercel's settings.
2. Go to <https://vercel.com/new>, import the GitHub repository.
3. **Root Directory:** `frontend/web` (click *Edit* next to it). Framework: Next.js (detected).
4. **Environment Variables:** add
   `NEXT_PUBLIC_API_BASE` = `https://<hf-user>-loanmate-backend.hf.space` (no trailing slash).
5. Click **Deploy**. Open the `https://<project>.vercel.app` link it gives you.

If you change `NEXT_PUBLIC_API_BASE` later, redeploy — the value is built into the page.

## 2b. Everything on Streamlit Community Cloud (no separate backend)

The Streamlit app starts the FastAPI backend and the Gemini Live voice worker as child
processes inside its own container. The voice worker only connects *out* to LiveKit Cloud,
so nothing besides the Streamlit page needs to be public.

1. Push the project to GitHub (Streamlit deploys from a branch).
2. Go to <https://share.streamlit.io>, sign in with GitHub, and click **Create app** →
   **Deploy a public app from GitHub**.
   - **Repository / Branch:** your repo and `main`
   - **Main file path:** `frontend/app.py`
   - **App URL:** pick a name — this becomes `https://<app-name>.streamlit.app`
3. Open **Advanced settings**:
   - **Python version:** 3.12
   - **Secrets:** paste the four keys, with the values from your local `.env`:

     ```toml
     GOOGLE_API_KEY = "..."
     LIVEKIT_URL = "wss://....livekit.cloud"
     LIVEKIT_API_KEY = "..."
     LIVEKIT_API_SECRET = "..."
     ```

     Don't add `API_BASE` — leaving it out is what tells the app to run the backend itself.
4. Click **Deploy**. The first build installs `frontend/requirements.txt` (a few minutes);
   the first page load after that shows "Starting LoanMate…" for about 20–60 seconds while
   the backend starts.

Already deployed with an `API_BASE` secret? Open the app menu → **Settings → Secrets**,
replace it with the four keys above, and save — the app restarts. Every push to the branch
redeploys automatically.

To use a separately hosted backend instead (section 1), set only
`API_BASE = "https://<your-backend-url>"` (no trailing slash) as the secret.

## 3. Test it

Open the Vercel or Streamlit URL → allow the microphone → pick a customer → **Call LoanMate**.
If the home screen shows a red message, the frontend can't reach the backend:
- **Streamlit (single app):** check that all four keys are in the app's secrets and there is
  no `API_BASE` secret, then open **Manage app** (bottom right) to read the logs. A
  `registered worker` line means the voice worker is up.
- **Vercel:** check the Space is **Running** and `NEXT_PUBLIC_API_BASE` matches its URL exactly.

## Good to know

- **Sleeping:** a free Space sleeps after a period of no traffic. The first visit then takes
  a minute or two to wake up — open it a few minutes before your demo.
- **Data resets:** call records and any data edits are lost when the Space restarts. The demo
  data in `backend/data/mock_data.json` is rebuilt from the repository each time.
- **Free-tier limits:** LiveKit and Gemini free plans have usage caps — fine for demos.
- **Public link = your keys' quota:** anyone with the Vercel link can make calls that use your
  Gemini and LiveKit quotas. Share it only with the people who need it.
- **Not deployed:** the local Whisper speech-to-text. The deployed backend uses
  `requirements-deploy.txt`, which leaves it out.
- **Streamlit sleeps too:** a Community Cloud app with no visitors for a while goes to sleep;
  the first visitor clicks a wake-up button and waits about a minute.
- **Test locally first (optional):** from the project folder, with the venv active, run
  `python deploy\space_app.py` (with `PORT=7860` set, or it uses your `.env` port) — it starts
  exactly what the Space runs. Open <http://localhost:7860/health>.
- **Paid Docker hosting instead:** the `Dockerfile` in the project root builds the same
  backend as one container, for a Docker Space or any other Docker host.
