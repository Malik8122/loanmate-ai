# Deploying LoanMate AI for free

The app is deployed in two pieces on free tiers:

| Piece | Host | URL you get |
| --- | --- | --- |
| Backend API + Gemini Live voice worker | Hugging Face Spaces (Docker, free CPU) | `https://<hf-user>-<space-name>.hf.space` |
| React web app (`frontend/web`) | Vercel (Hobby plan) | `https://<project>.vercel.app` |

LiveKit Cloud (calls) and the Gemini API (AI) stay on the free plans you already use.

You need: a Hugging Face account, a Vercel account, the project on GitHub, and the four
keys from your local `.env`. Total time: about 20–30 minutes, most of it waiting for the
first backend build.

---

## 1. Backend on Hugging Face Spaces

1. Go to <https://huggingface.co/new-space>.
   - **Space name:** e.g. `loanmate-backend`
   - **SDK:** Docker → Blank
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
   `{"status":"ok",...}`.

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

## 3. Test it

Open the Vercel URL → allow the microphone → pick a customer → **Call LoanMate**. If the home
screen shows a red message, the frontend can't reach the backend: check the Space is
**Running** and that `NEXT_PUBLIC_API_BASE` matches its URL exactly.

## Good to know

- **Sleeping:** a free Space sleeps after a period of no traffic. The first visit then takes
  a minute or two to wake up — open it a few minutes before your demo.
- **Data resets:** call records and any data edits are lost when the Space restarts. The demo
  data in `backend/data/mock_data.json` is rebuilt from the repository each time.
- **Free-tier limits:** LiveKit and Gemini free plans have usage caps — fine for demos.
- **Public link = your keys' quota:** anyone with the Vercel link can make calls that use your
  Gemini and LiveKit quotas. Share it only with the people who need it.
- **Not deployed:** the Streamlit demo and its local Whisper speech-to-text. The deployed
  backend uses `requirements-deploy.txt`, which leaves them out.
- **Test locally first (optional, needs Docker):**

  ```powershell
  docker build -t loanmate-backend .
  docker run --rm -p 7860:7860 --env-file .env -e PORT=7860 loanmate-backend
  ```

  then open <http://localhost:7860/health>.
