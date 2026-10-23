"""
LoanMate AI — Conversational Voice Loan Assistant — Streamlit Frontend

This is a voice-first product: the user talks to LoanMate, and loan
information is delivered through conversation, not banking dashboard
widgets. The UI is intentionally minimal — a home screen with two call
entry points, an active-call screen built around a voice orb, and an
ended screen. Loan details, calculators, applications etc. all remain
real backend/agent capabilities, reachable only by asking LoanMate.
"""

import json
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import os

import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EMBEDDED_PORT = 8765
_BACKEND_SECRETS = ("GOOGLE_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")


def _secrets() -> dict:
    try:
        return dict(st.secrets)
    except Exception:  # no secrets.toml — normal for local runs
        return {}


def _resolve_api_base() -> str:
    """Where the backend lives:
    - API_BASE (secret or env var) — a separately hosted backend;
    - otherwise, if the API keys are in Streamlit secrets — a backend this app
      starts itself (single-app deploy on Streamlit Community Cloud);
    - otherwise the local dev backend.
    """
    secrets = _secrets()
    explicit = secrets.get("API_BASE") or os.getenv("API_BASE")
    if explicit:
        return explicit.rstrip("/")
    if all(secrets.get(k) for k in _BACKEND_SECRETS):
        return f"http://127.0.0.1:{EMBEDDED_PORT}"
    return "http://localhost:8000"


API_BASE = _resolve_api_base()
EMBEDDED_BACKEND = API_BASE == f"http://127.0.0.1:{EMBEDDED_PORT}"
EMBEDDED_LOG = Path(tempfile.gettempdir()) / "loanmate_backend.log"


def backend_diagnosis() -> str:
    """What the error screen shows: which backend mode is active and why it may be failing.
    Names secrets but never prints their values."""
    secrets = _secrets()
    if secrets.get("API_BASE") or os.getenv("API_BASE"):
        return (f"Mode: external backend at `{API_BASE}`. To run the backend inside this app instead, "
                "remove `API_BASE` from the app's secrets and add the four API keys.")
    if not EMBEDDED_BACKEND:
        missing = [k for k in _BACKEND_SECRETS if not secrets.get(k)]
        return ("Mode: local development backend (`http://localhost:8000`). "
                f"To run the backend inside this app, add these secrets: {', '.join(missing)}.")
    lines = ["Mode: built-in backend (started by this app)."]
    try:
        tail = EMBEDDED_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        lines.append("Last backend log lines:\n```\n" + "\n".join(tail) + "\n```")
    except OSError:
        lines.append("The backend has not written a log yet.")
    return "\n\n".join(lines)


@st.cache_resource(show_spinner=False)
def _launch_embedded_backend() -> subprocess.Popen:
    """Start the FastAPI backend + Gemini Live voice worker (deploy/space_app.py)
    as a child process. Cached, so every session and rerun shares one backend."""
    env = {**os.environ, **{k: str(v) for k, v in _secrets().items() if isinstance(v, (str, int, float))}}
    env.update(
        PORT=str(EMBEDDED_PORT),
        HOST="127.0.0.1",
        PYTHONPATH=str(PROJECT_ROOT),
        # Keep the voice worker small on a shared container (see run_worker).
        LOANMATE_WORKER_IDLE_PROCESSES=env.get("LOANMATE_WORKER_IDLE_PROCESSES", "1"),
        LOANMATE_WORKER_LOAD_THRESHOLD=env.get("LOANMATE_WORKER_LOAD_THRESHOLD", "1.0"),
    )
    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "deploy" / "space_app.py")],
        cwd=PROJECT_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )

    # Copy backend output to the app's own log (Manage app) and to a file the
    # error screen can show.
    def _tee() -> None:
        with open(EMBEDDED_LOG, "w", encoding="utf-8") as log:
            for line in proc.stdout:
                sys.stdout.write(line)
                log.write(line)
                log.flush()

    threading.Thread(target=_tee, daemon=True, name="loanmate-backend-log").start()
    return proc


def ensure_embedded_backend(timeout_s: int = 180) -> bool:
    """Make sure the embedded backend is running and answering; restart it if it died."""
    proc = _launch_embedded_backend()
    if proc.poll() is not None:
        _launch_embedded_backend.clear()
        proc = _launch_embedded_backend()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{API_BASE}/health", timeout=2).ok:
                return True
        except Exception:
            pass
        if proc.poll() is not None:
            return False
        time.sleep(1)
    return False


st.set_page_config(
    page_title="LoanMate",
    page_icon="🎙️",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------------------
# Design system (CSS)
# ---------------------------------------------------------------------------
def inject_css(dark: bool):
    theme_vars = (
        """
        --bg: #0B1220; --surface: #121B2E; --surface-2: #0F1830;
        --navy: #0B1F3A; --royal: #4C7CFF; --royal-dark: #2F5FE0;
        --accent-soft: rgba(76,124,255,0.16);
        --text: #E7ECF7; --text-muted: #93A0BE; --border: #223154;
        --success: #22C55E; --danger: #F87171;
        """
        if dark
        else """
        --bg: #F3F6FC; --surface: #FFFFFF; --surface-2: #F5F8FF;
        --navy: #0B1F3A; --royal: #3D63EC; --royal-dark: #2748C4;
        --accent-soft: #E9EFFF;
        --text: #16213E; --text-muted: #6B7686; --border: #E4E9F5;
        --success: #16A34A; --danger: #DC2626;
        """
    )

    st.markdown(
        f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        :root {{ {theme_vars} }}

        html, body, [class*="css"] {{ font-family: 'Inter', -apple-system, sans-serif; }}
        .stApp {{ background: var(--bg); }}
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{ display: none; }}
        div[data-testid="stToolbar"] {{ display: none; }}
        div[data-testid="stDecoration"] {{ display: none; }}
        .block-container {{ padding-top: 2rem; padding-bottom: 2rem; max-width: 620px; }}

        button[kind="secondary"] {{
            background: transparent !important; color: var(--text) !important;
            border: 1px solid transparent !important; font-weight: 600 !important;
            box-shadow: none !important; border-radius: 12px !important;
        }}
        button[kind="secondary"]:hover {{ background: var(--accent-soft) !important; color: var(--royal) !important; }}
        button[kind="primary"] {{
            background: var(--royal) !important; border: none !important; color: white !important;
            font-weight: 700 !important; box-shadow: 0 4px 16px rgba(76,124,255,0.3) !important;
            border-radius: 12px !important;
        }}
        button[data-testid="stPopoverButton"] {{
            background: var(--surface) !important; color: var(--text-muted) !important;
            border: 1px solid var(--border) !important; border-radius: 999px !important;
            font-weight: 600 !important; font-size: 0.8rem !important;
        }}
        div[data-baseweb="popover"] {{ background: var(--surface) !important; }}
        div[data-testid="stPopoverBody"] {{ background: var(--surface) !important; border: 1px solid var(--border) !important; }}
        div[data-baseweb="select"] > div {{ background: var(--surface) !important; border-color: var(--border) !important; color: var(--text) !important; }}
        label, .stMarkdown p {{ color: var(--text) !important; }}
        .element-container {{ transition: none !important; opacity: 1 !important; }}

        /* ---------------- Top-right utility row ---------------- */
        .lm-topbar {{ display: flex; justify-content: flex-end; gap: 0.5rem; margin-bottom: 0.5rem; }}

        /* ---------------- Brand ---------------- */
        .lm-brand-wrap {{ text-align: center; margin: 1.5rem 0 0.5rem 0; }}
        .lm-brand {{ font-size: 2.1rem; font-weight: 800; color: var(--text); margin: 0; letter-spacing: -0.02em; }}
        .lm-tagline {{ font-size: 1rem; color: var(--text-muted); margin: 0.3rem 0 0 0; font-weight: 500; }}
        .lm-sub {{ font-size: 0.88rem; color: var(--text-muted); margin: 0.6rem 0 0 0; }}

        /* ---------------- Voice orb ---------------- */
        .lm-orb-wrap {{ display: flex; justify-content: center; align-items: center; margin: 1.6rem 0; height: 150px; position: relative; }}
        .lm-orb {{
            width: 96px; height: 96px; border-radius: 50%; position: relative;
            background: radial-gradient(circle at 35% 30%, #7DA0FF, var(--royal) 55%, var(--royal-dark) 100%);
            box-shadow: 0 0 0 0 rgba(76,124,255,0.4);
            display: flex; align-items: center; justify-content: center;
            transition: transform 0.3s ease;
        }}
        .lm-orb-icon {{ font-size: 2rem; }}
        .lm-orb.idle {{ animation: lm-breathe 3.5s ease-in-out infinite; }}
        .lm-orb.connecting {{ animation: lm-pulse-ring 1.1s ease-out infinite; }}
        .lm-orb.listening {{ animation: lm-pulse-ring 1.6s ease-out infinite; }}
        .lm-orb.processing {{ animation: lm-spin 1.4s linear infinite; }}
        .lm-orb.speaking {{ animation: lm-pulse-ring 0.7s ease-out infinite; }}
        .lm-orb.muted {{ filter: grayscale(0.7); opacity: 0.7; animation: none; }}
        .lm-orb.ended {{ opacity: 0.35; animation: none; }}
        @keyframes lm-breathe {{
            0%, 100% {{ transform: scale(1); }} 50% {{ transform: scale(1.04); }}
        }}
        @keyframes lm-pulse-ring {{
            0% {{ box-shadow: 0 0 0 0 rgba(76,124,255,0.45); }}
            70% {{ box-shadow: 0 0 0 22px rgba(76,124,255,0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(76,124,255,0); }}
        }}
        @keyframes lm-spin {{
            0% {{ transform: rotate(0deg) scale(1); }} 50% {{ transform: rotate(180deg) scale(1.03); }} 100% {{ transform: rotate(360deg) scale(1); }}
        }}
        .lm-state-label {{ text-align: center; font-size: 0.92rem; font-weight: 600; color: var(--text-muted); margin-top: -0.4rem; margin-bottom: 0.8rem; min-height: 1.3em; }}
        .lm-connected-badge {{ text-align: center; margin-bottom: 0.3rem; }}
        .lm-connected-badge span {{
            display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.78rem; font-weight: 700;
            color: var(--success); background: rgba(34,197,94,0.12); padding: 0.2rem 0.7rem; border-radius: 999px;
        }}
        .lm-dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--success); display: inline-block; }}

        /* ---------------- CTA cards ---------------- */
        .lm-cta-card {{
            background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
            padding: 1.1rem 1.3rem; margin-bottom: 0.9rem; box-shadow: 0 4px 18px rgba(16,24,40,0.05);
            display: flex; align-items: center; gap: 0.9rem;
        }}
        .lm-cta-icon {{
            width: 46px; height: 46px; border-radius: 13px; flex-shrink: 0;
            background: var(--accent-soft); color: var(--royal);
            display: flex; align-items: center; justify-content: center; font-size: 1.4rem;
        }}
        .lm-cta-title {{ font-size: 1.02rem; font-weight: 700; color: var(--text); margin: 0; }}
        .lm-cta-sub {{ font-size: 0.82rem; color: var(--text-muted); margin: 0; }}
        .st-key-cta_call_btn, .st-key-cta_outbound_btn {{ margin-top: -7.4rem; margin-bottom: 0.9rem; position: relative; z-index: 1; }}
        .st-key-cta_call_btn div[data-testid="stButton"] > button,
        .st-key-cta_outbound_btn div[data-testid="stButton"] > button {{
            width: 100% !important; background: transparent !important; border: none !important;
            color: transparent !important; height: 84px !important; margin-top: 0 !important;
            box-shadow: none !important; cursor: pointer;
        }}
        .st-key-cta_call_btn div[data-testid="stButton"] > button:hover,
        .st-key-cta_outbound_btn div[data-testid="stButton"] > button:hover {{
            background: rgba(76,124,255,0.06) !important; border-radius: 18px !important;
        }}

        /* ---------------- Language pills ---------------- */
        .st-key-lang_row div[data-testid="stButton"] > button[kind="secondary"] {{
            background: transparent !important; border: none !important; color: var(--text-muted) !important;
            font-size: 0.85rem !important; font-weight: 600 !important; padding: 0.1rem 0.5rem !important;
            box-shadow: none !important;
        }}
        .st-key-lang_row div[data-testid="stButton"] > button[kind="primary"] {{
            background: transparent !important; color: var(--royal) !important; box-shadow: none !important;
            font-size: 0.85rem !important; padding: 0.1rem 0.5rem !important;
        }}

        /* ---------------- Trust line ---------------- */
        .lm-trust {{ text-align: center; font-size: 0.76rem; color: var(--text-muted); margin-top: 1.6rem; }}

        /* ---------------- Incoming call card ---------------- */
        .lm-incoming-wrap {{ text-align: center; margin-top: 1.5rem; }}
        .lm-incoming-icon {{ font-size: 2.4rem; margin-bottom: 0.4rem; animation: lm-ring 1s ease-in-out infinite; }}
        @keyframes lm-ring {{ 0%, 100% {{ transform: rotate(0deg); }} 25% {{ transform: rotate(-12deg); }} 75% {{ transform: rotate(12deg); }} }}
        .lm-incoming-label {{ font-size: 0.85rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.3rem; }}
        .lm-incoming-name {{ font-size: 1.5rem; font-weight: 800; color: var(--text); margin: 0.2rem 0 0.1rem 0; }}
        .lm-incoming-role {{ font-size: 0.88rem; color: var(--text-muted); margin-bottom: 0.3rem; }}
        .lm-incoming-quote {{ font-size: 0.9rem; color: var(--text); font-style: italic; margin-bottom: 1.4rem; }}
        .lm-demo-badge {{
            display: inline-block; font-size: 0.7rem; font-weight: 700; color: var(--text-muted);
            background: var(--surface-2); border: 1px solid var(--border); border-radius: 999px;
            padding: 0.15rem 0.6rem; margin-bottom: 0.8rem;
        }}

        /* ---------------- Ended screen ---------------- */
        .lm-ended-wrap {{ text-align: center; margin-top: 2rem; }}

        @media (max-width: 480px) {{
            .lm-brand {{ font-size: 1.7rem; }}
        }}
    </style>
    """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def init_state():
    defaults = {
        "call_state": "idle",  # idle | outbound_calling | outbound_incoming | connecting | ended
        "call_direction": None,  # "inbound" | "outbound"
        "outbound_reason": "auto",  # why the bank is calling (outbound only)
        "session_id": None,
        "selected_customer": None,
        "dark_mode": False,
        "lang_choice": "English",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _now() -> str:
    return datetime.now().strftime("%I:%M %p")


def new_session_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Backend helpers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def check_health() -> bool:
    # Generous timeout: a free Hugging Face Space takes a while to answer while it wakes up.
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=15)
        return resp.status_code == 200
    except Exception:
        return False


@st.cache_data(ttl=20)
def fetch_livekit_status() -> bool:
    try:
        resp = requests.get(f"{API_BASE}/api/livekit/status", timeout=3)
        if resp.status_code == 200:
            return bool(resp.json().get("configured"))
        return False
    except Exception:
        return False


@st.cache_data(ttl=60)
def fetch_customers() -> list[dict]:
    try:
        resp = requests.get(f"{API_BASE}/api/customer/list", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def fetch_realtime_token(customer_id: str, session_id: str, call_mode: str, language: str, outbound_reason: str | None) -> dict | None:
    """Token for the realtime (Gemini Live) path. Its room config makes LiveKit Cloud
    dispatch the voice agent automatically, so there is no separate start/stop call."""
    params = {"customer_id": customer_id, "session_id": session_id, "call_mode": call_mode, "language": language}
    if call_mode == "outbound" and outbound_reason:
        params["outbound_reason"] = outbound_reason
    try:
        resp = requests.get(f"{API_BASE}/api/realtime/token", params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


# Why the bank is calling — each outbound purpose runs a different script and
# records a different call outcome. "auto" lets the backend pick from the
# customer's account state (overdue loan > pending KYC > EMI reminder).
OUTBOUND_REASONS = {
    "auto": "Auto (based on account)",
    "emi_reminder": "EMI reminder",
    "overdue_followup": "Overdue payment follow-up",
    "kyc_update": "KYC update",
    "product_update": "Top-up loan offer",
}


def send_text_query(customer_id: str, text: str, language: str) -> dict:
    try:
        resp = requests.post(
            f"{API_BASE}/api/voice/query/text",
            json={"customer_id": customer_id, "text": text, "language": language, "session_id": st.session_state.get("session_id") or "text-fallback"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"reply_text": "I couldn't reach LoanMate right now. Please try again.", "escalate": False}


def lang_choice_to_code(choice: str) -> str:
    return {"English": "en", "हिन्दी": "hi", "Hinglish": "hi"}.get(choice, "auto")


def lang_choice_to_realtime(choice: str) -> str:
    return {"English": "english", "हिन्दी": "hindi", "Hinglish": "hinglish"}.get(choice, "english")


# ---------------------------------------------------------------------------
# Render: top utility bar (theme + demo persona — small and out of the way)
# ---------------------------------------------------------------------------
def render_topbar(customers: list[dict]):
    col_gap, col_theme, col_persona = st.columns([3, 1, 2])
    with col_theme:
        if st.button("☾" if not st.session_state.dark_mode else "☀", key="theme_toggle"):
            st.session_state.dark_mode = not st.session_state.dark_mode
            st.rerun()
    with col_persona:
        if customers:
            names = {c["name"]: c["customer_id"] for c in customers}
            current_id = st.session_state.selected_customer or customers[0]["customer_id"]
            current_name = next((n for n, i in names.items() if i == current_id), customers[0]["name"])
            with st.popover(f"Demo: {current_name.split()[0]} ▾", use_container_width=True):
                st.caption("This demo dataset has a few sample customers — pick who LoanMate is talking to.")
                choice = st.selectbox("Customer", list(names.keys()), index=list(names.keys()).index(current_name), label_visibility="collapsed")
                if names[choice] != st.session_state.selected_customer:
                    st.session_state.selected_customer = names[choice]
                    st.rerun()


# ---------------------------------------------------------------------------
# Render: home screen
# ---------------------------------------------------------------------------
def render_home(voice_ready: bool):
    st.markdown(
        """
        <div class="lm-brand-wrap">
            <p class="lm-brand">LoanMate</p>
            <p class="lm-tagline">Conversational Voice AI</p>
            <p class="lm-sub">Talk naturally with your AI loan assistant.</p>
        </div>
        <div class="lm-orb-wrap"><div class="lm-orb idle"><span class="lm-orb-icon">🎙️</span></div></div>
        <p class="lm-state-label">How can I help you?</p>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="lm-cta-card">
            <div class="lm-cta-icon">🎙️</div>
            <div><p class="lm-cta-title">Call LoanMate</p><p class="lm-cta-sub">Start a conversation</p></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="cta_call_btn"):
        call_clicked = st.button("Call LoanMate", key="call_loanmate_btn", use_container_width=True, disabled=not voice_ready)

    st.markdown(
        """
        <div class="lm-cta-card">
            <div class="lm-cta-icon">📞</div>
            <div><p class="lm-cta-title">Bank is Calling You</p><p class="lm-cta-sub">Receive an AI call</p></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="cta_outbound_btn"):
        outbound_clicked = st.button("Bank is Calling You", key="outbound_btn", use_container_width=True, disabled=not voice_ready)
    st.session_state.outbound_reason = st.selectbox(
        "Why is the bank calling?",
        options=list(OUTBOUND_REASONS),
        format_func=OUTBOUND_REASONS.get,
        index=list(OUTBOUND_REASONS).index(st.session_state.outbound_reason),
        key="outbound_reason_select",
    )

    if not voice_ready:
        st.caption("⚠️ Voice calling needs LiveKit credentials configured on the server (see .env).")

    with st.container(key="lang_row"):
        lang_cols = st.columns(3)
        for col, label in zip(lang_cols, ["English", "हिन्दी", "Hinglish"]):
            with col:
                is_active = st.session_state.lang_choice == label
                if st.button(label, key=f"lang_{label}", type="primary" if is_active else "secondary"):
                    st.session_state.lang_choice = label
                    st.rerun()
    st.markdown(
        f'<p class="lm-trust">🔒 Your conversation is processed securely. &middot; Language: {st.session_state.lang_choice}</p>',
        unsafe_allow_html=True,
    )

    if call_clicked:
        st.session_state.call_direction = "inbound"
        st.session_state.call_state = "connecting"
        st.session_state.session_id = new_session_id()
        st.rerun()

    if outbound_clicked:
        st.session_state.call_direction = "outbound"
        st.session_state.call_state = "outbound_calling"
        st.session_state.session_id = new_session_id()
        st.rerun()

    with st.expander("Or type a quick question instead"):
        text = st.text_input("Type your question", label_visibility="collapsed", placeholder="e.g. What is my EMI?")
        if st.button("Send", key="text_fallback_send") and text.strip():
            customer_id = st.session_state.selected_customer or "CUST001"
            result = send_text_query(customer_id, text, lang_choice_to_code(st.session_state.lang_choice))
            st.info(result.get("reply_text", ""))


# ---------------------------------------------------------------------------
# Render: outbound "calling" transition + incoming call card
# ---------------------------------------------------------------------------
def render_outbound_calling():
    st.markdown(
        """
        <div class="lm-incoming-wrap">
            <div class="lm-incoming-icon">📞</div>
            <p class="lm-incoming-name">LoanMate is calling...</p>
            <p class="lm-incoming-role">Preparing your AI call</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    time.sleep(1.3)
    st.session_state.call_state = "outbound_incoming"
    st.rerun()


def render_outbound_incoming(customer_name: str):
    st.markdown(
        f"""
        <div class="lm-incoming-wrap">
            <span class="lm-demo-badge">AI Call Demo</span>
            <p class="lm-incoming-label">Incoming Call</p>
            <div class="lm-incoming-icon">📞</div>
            <p class="lm-incoming-name">LoanMate</p>
            <p class="lm-incoming-role">AI Loan Assistant</p>
            <p class="lm-incoming-quote">"LoanMate is calling you, {customer_name.split()[0]}"</p>
            <p class="lm-incoming-role">Regarding: {OUTBOUND_REASONS.get(st.session_state.outbound_reason, "Your loan")}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_decline, col_accept = st.columns(2)
    with col_decline:
        if st.button("Decline", key="decline_btn", use_container_width=True):
            st.session_state.call_state = "idle"
            st.session_state.call_direction = None
            st.rerun()
    with col_accept:
        if st.button("Accept", key="accept_btn", type="primary", use_container_width=True):
            st.session_state.call_state = "connecting"
            st.rerun()


# ---------------------------------------------------------------------------
# Render: active call (real LiveKit widget with voice orb, states, transcript)
# ---------------------------------------------------------------------------
def render_call_widget(livekit_url: str, token: str):
    payload = json.dumps({"url": livekit_url, "token": token})

    html = f"""
    <style>
        body {{ margin: 0; font-family: 'Inter', -apple-system, sans-serif; background: transparent; }}
        .wrap {{ text-align: center; color: #E7ECF7; padding: 16px 12px; background: #0B1220; border-radius: 18px; }}
        .status-badge {{ display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700;
            color: #22C55E; background: rgba(34,197,94,0.14); padding: 3px 12px; border-radius: 999px; margin-bottom: 6px; }}
        .dot {{ width: 7px; height: 7px; border-radius: 50%; background: #22C55E; }}
        .orb {{ width: 96px; height: 96px; border-radius: 50%; margin: 10px auto; position: relative;
            background: radial-gradient(circle at 35% 30%, #7DA0FF, #4C7CFF 55%, #2F5FE0 100%);
            display: flex; align-items: center; justify-content: center; font-size: 30px; transition: filter 0.2s ease; }}
        .orb.muted {{ filter: grayscale(0.7); opacity: 0.7; }}
        .orb.ended {{ opacity: 0.35; }}
        .orb.connecting {{ animation: pulse 1.1s ease-out infinite; }}
        .orb.listening {{ animation: pulse 1.6s ease-out infinite; }}
        .orb.speaking {{ animation: pulse 0.7s ease-out infinite; }}
        .orb.processing {{ animation: spin 1.4s linear infinite; }}
        @keyframes pulse {{ 0% {{ box-shadow: 0 0 0 0 rgba(76,124,255,0.45); }} 70% {{ box-shadow: 0 0 0 22px rgba(76,124,255,0); }} 100% {{ box-shadow: 0 0 0 0 rgba(76,124,255,0); }} }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        .state-label {{ font-size: 14px; font-weight: 600; color: #93A0BE; min-height: 1.3em; margin-bottom: 10px; }}
        .error-box {{ background: rgba(220,38,38,0.15); border: 1px solid rgba(220,38,38,0.4); border-radius: 10px;
            padding: 8px 12px; font-size: 13px; margin: 8px 0; }}
        .mute-btn {{ background: rgba(255,255,255,0.08); border: 1px solid #223154; color: #E7ECF7; border-radius: 12px;
            padding: 8px 18px; font-weight: 700; font-size: 13px; cursor: pointer; }}
        .mute-btn.muted {{ background: #D97706; border-color: #D97706; }}
        .transcript {{ text-align: left; margin-top: 16px; border-top: 1px solid #223154; padding-top: 10px;
            max-height: 160px; overflow-y: auto; font-size: 13px; }}
        .transcript .row {{ margin-bottom: 8px; }}
        .transcript .who {{ font-weight: 700; color: #93A0BE; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }}
        .transcript .text {{ color: #E7ECF7; margin-top: 1px; }}
    </style>
    <div class="wrap">
        <div id="badge" class="status-badge" style="display:none;"><span class="dot"></span><span>Connected</span></div>
        <div class="orb connecting" id="orb"><span id="orb-icon">🎙️</span></div>
        <div class="state-label" id="state-label">Connecting...</div>
        <div id="error-box"></div>
        <button class="mute-btn" id="mute-btn">🎤 Mute</button>
        <div class="transcript" id="transcript"></div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/livekit-client@2.22.3/dist/livekit-client.umd.js"></script>
    <script>
    (function() {{
        const cfg = {payload};
        const orb = document.getElementById('orb');
        const label = document.getElementById('state-label');
        const badge = document.getElementById('badge');
        const errorBox = document.getElementById('error-box');
        const muteBtn = document.getElementById('mute-btn');
        const transcriptEl = document.getElementById('transcript');

        let room = null;
        let micEnabled = true;
        let currentState = 'connecting';
        const segmentRows = {{}};

        // The realtime LoanMate worker (LiveKit Agents) publishes its state as the
        // agent participant's 'lk.agent.state' attribute.
        const AGENT_STATE = {{
            initializing: ['connecting', 'Connecting...'],
            idle: ['listening', 'Listening...'],
            listening: ['listening', 'Listening...'],
            thinking: ['processing', 'Thinking...'],
            speaking: ['speaking', 'Speaking...'],
        }};

        function isAgent(p) {{ return !!p && (p.isAgent || (p.identity || '').startsWith('agent-')); }}
        function setOrb(state) {{
            currentState = state;
            orb.className = 'orb ' + state + (micEnabled ? '' : ' muted');
        }}
        function setLabel(text) {{ label.textContent = text; }}
        function showError(text) {{ errorBox.innerHTML = '<div class="error-box">' + text + '</div>'; }}

        function applyAgentState(state) {{
            const mapped = AGENT_STATE[state];
            if (!mapped) return;
            badge.style.display = 'inline-flex';
            setOrb(mapped[0]);
            setLabel(mapped[1]);
        }}

        function segmentRow(id, fromAgent) {{
            if (segmentRows[id]) return segmentRows[id];
            const row = document.createElement('div');
            row.className = 'row';
            const who = document.createElement('div');
            who.className = 'who';
            who.textContent = fromAgent ? 'LoanMate' : 'You';
            const text = document.createElement('div');
            text.className = 'text';
            row.appendChild(who); row.appendChild(text);
            transcriptEl.appendChild(row);
            segmentRows[id] = text;
            return text;
        }}

        async function connect() {{
            if (!window.LivekitClient) {{
                showError('Unable to load the voice client. Check your connection and try again.');
                setLabel('Connection failed');
                return;
            }}
            const {{ Room, RoomEvent, Track }} = window.LivekitClient;
            room = new Room();

            room.on(RoomEvent.Disconnected, () => {{
                setLabel('The call has ended.');
                setOrb('ended');
            }});

            room.on(RoomEvent.TrackSubscribed, (track) => {{
                if (track.kind === Track.Kind.Audio) {{
                    const el = track.attach();
                    el.autoplay = true;
                    document.body.appendChild(el);
                }}
            }});

            room.on(RoomEvent.ParticipantAttributesChanged, (changed, participant) => {{
                if (isAgent(participant) && changed['lk.agent.state']) applyAgentState(changed['lk.agent.state']);
            }});
            room.on(RoomEvent.ParticipantConnected, (participant) => {{
                if (isAgent(participant)) applyAgentState(participant.attributes['lk.agent.state'] || 'initializing');
            }});

            // Live captions: the agent forwards both sides' transcription as text
            // streams on 'lk.transcription', one stream per spoken segment.
            room.registerTextStreamHandler('lk.transcription', async (reader, participantInfo) => {{
                const attrs = reader.info.attributes || {{}};
                const id = attrs['lk.segment_id'] || reader.info.id;
                const el = segmentRow(id, (participantInfo.identity || '').startsWith('agent-'));
                let text = '';
                for await (const chunk of reader) {{
                    text += chunk;
                    el.textContent = text;
                    transcriptEl.scrollTop = transcriptEl.scrollHeight;
                }}
            }});

            try {{
                setLabel('Connecting...');
                await room.connect(cfg.url, cfg.token);
                setLabel('Requesting microphone access...');
                await room.localParticipant.setMicrophoneEnabled(true);
                badge.style.display = 'inline-flex';
                setLabel('Waiting for LoanMate to join...');
                for (const p of room.remoteParticipants.values()) {{
                    if (isAgent(p)) applyAgentState(p.attributes['lk.agent.state'] || 'initializing');
                }}
            }} catch (err) {{
                console.error(err);
                const msg = String(err).toLowerCase();
                if (msg.includes('permission') || msg.includes('notallowed')) {{
                    showError('Microphone access was denied. Please allow microphone access to continue.');
                    setLabel('Microphone access required');
                }} else {{
                    showError('Unable to connect to the voice service.');
                    setLabel('Connection failed');
                }}
                setOrb('ended');
            }}
        }}

        muteBtn.addEventListener('click', async () => {{
            if (!room) return;
            micEnabled = !micEnabled;
            await room.localParticipant.setMicrophoneEnabled(micEnabled);
            muteBtn.classList.toggle('muted', !micEnabled);
            muteBtn.textContent = micEnabled ? '🎤 Mute' : '🔇 Unmute';
            setOrb(currentState);
        }});

        // Leave the room as soon as Streamlit removes this widget (End Call),
        // so the agent session ends right away instead of timing out.
        window.addEventListener('pagehide', () => {{ if (room) room.disconnect(); }});

        connect();
    }})();
    </script>
    """
    st.iframe(html, height=440)


def render_active_call(customer_id: str, session_id: str, call_direction: str):
    token_key = f"_token_data_{session_id}"

    if token_key not in st.session_state:
        st.session_state[token_key] = fetch_realtime_token(
            customer_id,
            session_id,
            call_direction,
            lang_choice_to_realtime(st.session_state.lang_choice),
            st.session_state.outbound_reason,
        )
    token_data = st.session_state[token_key]

    if not token_data:
        st.error("Unable to connect to the voice service.")
    else:
        render_call_widget(token_data["url"], token_data["token"])

    if st.button("⏹ End Call", key="end_call_btn", type="primary", use_container_width=True):
        st.session_state.call_state = "ended"
        st.session_state.pop(token_key, None)
        st.rerun()


# ---------------------------------------------------------------------------
# Render: ended screen
# ---------------------------------------------------------------------------
def render_ended():
    st.markdown(
        """
        <div class="lm-ended-wrap">
            <div class="lm-orb-wrap"><div class="lm-orb ended"><span class="lm-orb-icon">🎙️</span></div></div>
            <p class="lm-state-label">Conversation ended</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Start New Conversation", type="primary", use_container_width=True):
        st.session_state.call_state = "idle"
        st.session_state.call_direction = None
        st.session_state.session_id = None
        st.rerun()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def main():
    init_state()
    inject_css(st.session_state.dark_mode)

    if EMBEDDED_BACKEND:
        with st.spinner("Starting LoanMate — the first load after a restart takes about a minute..."):
            ensure_embedded_backend()

    healthy = check_health()
    if not healthy:
        st.markdown('<p class="lm-brand-wrap"><span class="lm-brand">LoanMate</span></p>', unsafe_allow_html=True)
        st.error("Unable to connect to the voice service. If the backend is hosted on a free plan it may be waking up — try again in a minute.")
        if st.button("Retry", type="primary", use_container_width=True):
            check_health.clear()
            st.rerun()
        with st.expander("Details for troubleshooting"):
            st.markdown(backend_diagnosis())
        return

    voice_ready = fetch_livekit_status()
    customers = fetch_customers()
    if customers and not st.session_state.selected_customer:
        st.session_state.selected_customer = customers[0]["customer_id"]
    customer_id = st.session_state.selected_customer or "CUST001"
    customer_name = next((c["name"] for c in customers if c["customer_id"] == customer_id), "there")

    render_topbar(customers)

    state = st.session_state.call_state
    if state == "idle":
        render_home(voice_ready)
    elif state == "outbound_calling":
        render_outbound_calling()
    elif state == "outbound_incoming":
        render_outbound_incoming(customer_name)
    elif state == "connecting":
        render_active_call(customer_id, st.session_state.session_id, st.session_state.call_direction)
    elif state == "ended":
        render_ended()


if __name__ == "__main__":
    main()
