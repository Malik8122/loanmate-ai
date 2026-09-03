"""
BFSI Loan & EMI Voice Assistant — Streamlit Frontend
"""

import streamlit as st
import requests
import uuid
import time
from audio_recorder_streamlit import audio_recorder

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
import os

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(
    page_title="BFSI Voice",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    :root {
        --primary-color: #0f3c6c;
        --secondary-color: #1e88e5;
        --background-color: #f8f9fa;
        --text-color: #333333;
    }
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: var(--primary-color);
        text-align: center;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #6B7280;
        text-align: center;
        margin-bottom: 2rem;
    }
    .chat-user {
        background-color: #E3F2FD;
        padding: 0.75rem 1rem;
        border-radius: 12px;
        margin: 0.4rem 0;
        color: var(--text-color);
        border: 1px solid #BBDEFB;
    }
    .chat-assistant {
        background-color: #F1F8E9;
        padding: 0.75rem 1rem;
        border-radius: 12px;
        margin: 0.4rem 0;
        color: var(--text-color);
        border: 1px solid #DCEDC8;
    }
    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .status-ok { background: #E8F5E9; color: #2E7D32; border: 1px solid #A5D6A7;}
    .status-err { background: #FFEBEE; color: #C62828; border: 1px solid #EF9A9A;}
    .escalate-banner {
        background-color: #FFF3E0;
        color: #E65100;
        padding: 0.75rem;
        border-radius: 8px;
        margin: 1rem 0;
        border: 1px solid #FFE0B2;
        font-weight: bold;
        text-align: center;
    }
    .info-panel {
        background-color: #ffffff;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .info-label {
        font-size: 0.85rem;
        color: #757575;
        margin-bottom: 0.2rem;
    }
    .info-value {
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--primary-color);
        margin-bottom: 0.8rem;
    }

    /* --- Phone Call Simulator ------------------------------------------ */
    .call-phone-frame {
        max-width: 440px;
        margin: 0 auto;
        background: linear-gradient(180deg, #123a63 0%, #0b1f38 100%);
        border-radius: 28px;
        padding: 2rem 1.75rem;
        color: #ffffff;
        text-align: center;
        box-shadow: 0 12px 32px rgba(0,0,0,0.35);
    }
    .call-avatar {
        width: 92px;
        height: 92px;
        border-radius: 50%;
        background: #1e88e5;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2.4rem;
        margin: 0 auto 1rem;
    }
    .call-avatar.pulsing {
        animation: call-pulse 1.4s infinite;
    }
    @keyframes call-pulse {
        0%   { box-shadow: 0 0 0 0 rgba(30,136,229,0.65); }
        70%  { box-shadow: 0 0 0 22px rgba(30,136,229,0); }
        100% { box-shadow: 0 0 0 0 rgba(30,136,229,0); }
    }
    .call-name { font-size: 1.3rem; font-weight: 700; margin-bottom: 0.15rem; }
    .call-number { font-size: 0.9rem; color: #B0BEC5; margin-bottom: 0.75rem; }
    .call-status-dialing { color: #FFD54F; font-weight: 600; letter-spacing: 0.5px; }
    .call-status-connected { color: #66BB6A; font-weight: 600; letter-spacing: 0.5px; }
    .call-status-ended { color: #EF9A9A; font-weight: 600; letter-spacing: 0.5px; }
    .call-timer {
        font-size: 1.5rem;
        font-family: 'Courier New', monospace;
        letter-spacing: 2px;
        margin-top: 0.4rem;
        color: #ffffff;
    }
    .call-live-tag {
        font-size: 0.85rem;
        color: #90CAF9;
        margin-top: 0.3rem;
        min-height: 1.2rem;
    }
    .call-transcript {
        text-align: left;
        max-height: 340px;
        overflow-y: auto;
        margin-top: 1.25rem;
        padding-right: 0.25rem;
    }
    .call-bubble-user {
        background: #1e88e5;
        color: #ffffff;
        padding: 0.55rem 0.9rem;
        border-radius: 14px 14px 2px 14px;
        margin: 0.3rem 0;
        max-width: 82%;
        margin-left: auto;
    }
    .call-bubble-assistant {
        background: #2d3f52;
        color: #ffffff;
        padding: 0.55rem 0.9rem;
        border-radius: 14px 14px 14px 2px;
        margin: 0.3rem 0;
        max-width: 82%;
        margin-right: auto;
    }
    .call-ended-card {
        max-width: 440px;
        margin: 2rem auto;
        text-align: center;
        padding: 2rem;
        border-radius: 20px;
        background: #f1f8e9;
        border: 1px solid #dcedc8;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I am your BFSI virtual assistant. How can I help you today?"}]
if "selected_customer" not in st.session_state:
    st.session_state.selected_customer = None
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "escalated" not in st.session_state:
    st.session_state.escalated = False

# Call Simulator state
if "call_state" not in st.session_state:
    st.session_state.call_state = "idle"  # idle | dialing | connected | ended
if "call_messages" not in st.session_state:
    st.session_state.call_messages = []
if "call_session_id" not in st.session_state:
    st.session_state.call_session_id = str(uuid.uuid4())
if "call_muted" not in st.session_state:
    st.session_state.call_muted = False
if "call_speaker_on" not in st.session_state:
    st.session_state.call_speaker_on = True
if "call_greeted" not in st.session_state:
    st.session_state.call_greeted = False
if "call_escalated" not in st.session_state:
    st.session_state.call_escalated = False
if "call_start_ts" not in st.session_state:
    st.session_state.call_start_ts = None
if "call_end_ts" not in st.session_state:
    st.session_state.call_end_ts = None
if "call_last_audio" not in st.session_state:
    st.session_state.call_last_audio = None
if "call_pending_audio_b64" not in st.session_state:
    st.session_state.call_pending_audio_b64 = None
if "call_phone_number" not in st.session_state:
    st.session_state.call_phone_number = ""

GREETING_TEXT = "Hello! Welcome to Unity Bank. I'm your AI Loan & EMI Assistant. May I know your name?"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def check_health() -> bool:
    """Ping the backend health endpoint."""
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False

@st.cache_data(ttl=60)
def fetch_customers() -> list[dict]:
    """Fetch customer list from backend."""
    try:
        resp = requests.get(f"{API_BASE}/api/customer/list", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []

def fetch_loan_summary(customer_id: str) -> dict | None:
    try:
        resp = requests.get(f"{API_BASE}/api/loan/summary/{customer_id}", timeout=5)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None

def send_text_query(customer_id: str, text: str, language: str = "en") -> dict:
    """Send a text query to the voice assistant endpoint."""
    try:
        resp = requests.post(
            f"{API_BASE}/api/voice/query/text",
            json={
                "customer_id": customer_id,
                "text": text,
                "language": language,
                "session_id": st.session_state.session_id
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"reply_text": "I'm having trouble connecting right now. Please try again later.", "intent": "error", "escalate": False}

def send_audio_query(customer_id: str, audio_bytes: bytes, language: str = "auto", session_id: str | None = None) -> dict:
    """Send an audio query to the voice assistant endpoint."""
    try:
        files = {"audio": ("audio.wav", audio_bytes, "audio/wav")}
        data = {
            "customer_id": customer_id,
            "language": language,
            "session_id": session_id or st.session_state.session_id,
        }
        resp = requests.post(
            f"{API_BASE}/api/voice/query/audio",
            data=data,
            files=files,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"reply_text": "Sorry, there was an error processing your voice. Please try again.", "intent": "error", "escalate": False}

def synthesize_tts(text: str, language: str = "en") -> str | None:
    """Synthesize speech for a scripted line (e.g. the call's opening greeting)."""
    try:
        resp = requests.post(
            f"{API_BASE}/api/voice/tts",
            json={"text": text, "language": language},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("audio_base64")
    except Exception:
        return None

def format_currency(amount):
    return f"₹{amount:,.2f}"

def reset_chat():
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I am your BFSI virtual assistant. How can I help you today?"}]
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.escalated = False

def reset_call():
    st.session_state.call_state = "idle"
    st.session_state.call_messages = []
    st.session_state.call_session_id = str(uuid.uuid4())
    st.session_state.call_muted = False
    st.session_state.call_speaker_on = True
    st.session_state.call_greeted = False
    st.session_state.call_escalated = False
    st.session_state.call_start_ts = None
    st.session_state.call_end_ts = None
    st.session_state.call_last_audio = None
    st.session_state.call_pending_audio_b64 = None

def format_mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
st.markdown('<p class="main-header">🏦 Unity Bank Voice Assistant</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Ask about loans, EMIs, or outstanding balances</p>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    # Health check
    healthy = check_health()
    if healthy:
        st.markdown('<div style="text-align:center; margin-bottom: 1rem;"><span class="status-badge status-ok">🟢 System Online</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align:center; margin-bottom: 1rem;"><span class="status-badge status-err">🔴 System Offline</span></div>', unsafe_allow_html=True)

    # Customer selector
    st.subheader("👤 Current Customer")
    customers = fetch_customers()

    if customers:
        customer_options = {f"{c['name']}": c["customer_id"] for c in customers}
        customer_phones = {c["customer_id"]: c.get("phone", "") for c in customers}

        # Reset chat if customer changes
        current_cust = st.session_state.selected_customer

        selected_label = st.selectbox("Select Profile", list(customer_options.keys()), label_visibility="collapsed")
        new_cust = customer_options[selected_label]

        if current_cust != new_cust:
            st.session_state.selected_customer = new_cust
            st.session_state.call_phone_number = customer_phones.get(new_cust, "")
            # Clear chat when switching users, unless it's the first load
            if current_cust is not None:
                reset_chat()
                st.rerun()
        elif not st.session_state.call_phone_number:
            st.session_state.call_phone_number = customer_phones.get(new_cust, "")

    else:
        st.warning("Could not connect to backend.")

    st.divider()

    # Loan Context Panel
    if st.session_state.selected_customer and healthy:
        st.subheader("💼 Account Overview")
        summary = fetch_loan_summary(st.session_state.selected_customer)
        if summary:
             st.markdown(f"""
             <div class="info-panel">
                <div class="info-label">Active Loans</div>
                <div class="info-value">{summary['total_loans']}</div>

                <div class="info-label">Total Outstanding</div>
                <div class="info-value">{format_currency(summary['total_outstanding'])}</div>

                <div class="info-label">Monthly EMI</div>
                <div class="info-value">{format_currency(summary['total_monthly_emi'])}</div>
             </div>
             """, unsafe_allow_html=True)
        else:
             st.info("No active loans found.")

    st.divider()

    # Settings
    st.subheader("⚙️ Preferences")
    language = st.radio("Language", ["English", "Hindi / Hinglish", "Auto Detect"], index=2, horizontal=True)

    if language == "English":
        lang_code = "en"
    elif language.startswith("Hindi"):
        lang_code = "hi"
    else:
        lang_code = "auto"


# ---------------------------------------------------------------------------
# Tabs: Chat Assistant  |  Phone Call Simulator
# ---------------------------------------------------------------------------
tab_chat, tab_call = st.tabs(["💬 Chat Assistant", "📞 Call Simulator"])

# =============================================================================
# TAB 1 — Chat Assistant (existing text/voice chat experience)
# =============================================================================
with tab_chat:
    chat_container = st.container(height=440, border=False)

    with chat_container:
        if st.session_state.escalated:
             st.markdown('<div class="escalate-banner">🎧 Connecting you to a human loan specialist... Please hold.</div>', unsafe_allow_html=True)

        for msg in st.session_state.messages:
            role = msg["role"]
            css_class = "chat-user" if role == "user" else "chat-assistant"
            icon = "🧑" if role == "user" else "🏦"
            st.markdown(f'<div class="{css_class}"><b>{icon}</b> &nbsp; {msg["content"]}</div>', unsafe_allow_html=True)

    # Suggested Questions
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("What loans do you offer?", use_container_width=True):
            st.session_state.prefill = "What loans do you offer?"
    with col2:
        if st.button("Meri EMI kitni hai?", use_container_width=True):
             st.session_state.prefill = "Meri EMI kitni hai?"
    with col3:
        if st.button("How much is outstanding?", use_container_width=True):
            st.session_state.prefill = "How much is outstanding?"
    with col4:
        if st.button("I want to apply for a loan", use_container_width=True):
             st.session_state.prefill = "I want to apply for a loan"

    # Input area
    prefill_val = st.session_state.get("prefill", "")
    user_input = st.chat_input("Type your question here...", key="chat_input")

    # Handle prefill logic since st.chat_input doesn't accept a default value directly.
    # We use a slight workaround: If a button was clicked, we process it immediately.
    if prefill_val and not user_input:
        user_input = prefill_val
        st.session_state.prefill = "" # clear it

    mic_col, reset_col = st.columns([3, 1])
    with mic_col:
        st.caption("🎙️ Or record a voice message:")
        audio_bytes = audio_recorder(text="Click to record", recording_color="#E65100", neutral_color="#0f3c6c", icon_size="2x", key="chat_mic")
    with reset_col:
        st.write("")
        if st.button("🗑️ New Conversation", use_container_width=True):
            reset_chat()
            st.rerun()

    if user_input:
        if not st.session_state.escalated:
            # Add user message
            st.session_state.messages.append({"role": "user", "content": user_input})

            # Get response from backend
            result = send_text_query(
                customer_id=st.session_state.selected_customer or "CUST001",
                text=user_input,
                language=lang_code,
            )

            # Add assistant reply
            st.session_state.messages.append({"role": "assistant", "content": result["reply_text"]})

            if result.get("escalate"):
                st.session_state.escalated = True

            if result.get("audio_base64"):
                st.session_state.last_audio = result["audio_base64"]

            st.rerun()

    # Handle voice input
    if audio_bytes and not st.session_state.escalated:
        # This prevents an infinite loop if Streamlit re-renders with the same audio_bytes
        if "last_recorded_audio" not in st.session_state or st.session_state.last_recorded_audio != audio_bytes:
            st.session_state.last_recorded_audio = audio_bytes

            with st.spinner("Processing voice..."):
                result = send_audio_query(
                    customer_id=st.session_state.selected_customer or "CUST001",
                    audio_bytes=audio_bytes,
                    language=lang_code,
                )

                user_text = result.get("transcribed_text") or "(Unclear audio)"

                # Add user message
                st.session_state.messages.append({"role": "user", "content": f"🗣️ {user_text}"})

                # Add assistant reply
                st.session_state.messages.append({"role": "assistant", "content": result["reply_text"]})

                if result.get("escalate"):
                    st.session_state.escalated = True

                if result.get("audio_base64"):
                    st.session_state.last_audio = result["audio_base64"]

                st.rerun()

    # Play audio if available
    if "last_audio" in st.session_state and st.session_state.last_audio:
        audio_b64 = st.session_state.last_audio
        # Clear it so it only plays once
        st.session_state.last_audio = None

        html = f"""
        <audio autoplay>
        <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
        </audio>
        """
        st.markdown(html, unsafe_allow_html=True)


# =============================================================================
# TAB 2 — Phone Call Simulator (Phase 3)
# =============================================================================
with tab_call:
    customers_by_id = {c["customer_id"]: c for c in customers} if customers else {}
    active_customer = customers_by_id.get(st.session_state.selected_customer, {})
    customer_display_name = active_customer.get("name", "Customer")

    # ---- IDLE: enter a number and place the call --------------------------
    if st.session_state.call_state == "idle":
        st.markdown('<div class="call-phone-frame">', unsafe_allow_html=True)
        st.markdown('<div class="call-avatar">📞</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="call-name">{customer_display_name}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.write("")
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            st.session_state.call_phone_number = st.text_input(
                "Phone number",
                value=st.session_state.call_phone_number,
                placeholder="+91-9876543210",
            )
            if st.button("📞 Call Customer", use_container_width=True, type="primary"):
                st.session_state.call_state = "dialing"
                st.rerun()
        st.caption("This is a free, local simulation — no real call is made and no telephony provider is used.")

    # ---- DIALING: brief calling animation, then auto-connect --------------
    elif st.session_state.call_state == "dialing":
        st.markdown(f"""
        <div class="call-phone-frame">
            <div class="call-avatar pulsing">📱</div>
            <div class="call-name">{customer_display_name}</div>
            <div class="call-number">{st.session_state.call_phone_number or "Unknown number"}</div>
            <div class="call-status-dialing">Calling...</div>
        </div>
        """, unsafe_allow_html=True)
        time.sleep(1.6)
        st.session_state.call_state = "connected"
        st.session_state.call_start_ts = time.time()
        st.rerun()

    # ---- ENDED: summary card ------------------------------------------------
    elif st.session_state.call_state == "ended":
        duration = format_mmss((st.session_state.call_end_ts or 0) - (st.session_state.call_start_ts or 0))
        st.markdown(f"""
        <div class="call-ended-card">
            <div style="font-size:2rem;">📴</div>
            <div style="font-size:1.2rem; font-weight:700; margin-top:0.5rem;">Call Ended</div>
            <div style="color:#558B2F; margin-top:0.25rem;">Duration: {duration}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📝 Call Transcript", expanded=True):
            for msg in st.session_state.call_messages:
                css_class = "chat-user" if msg["role"] == "user" else "chat-assistant"
                icon = "🧑" if msg["role"] == "user" else "🏦"
                st.markdown(f'<div class="{css_class}"><b>{icon}</b> &nbsp; {msg["content"]}</div>', unsafe_allow_html=True)

        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            if st.button("📞 New Call", use_container_width=True, type="primary"):
                reset_call()
                st.rerun()

    # ---- CONNECTED: the live call screen -----------------------------------
    elif st.session_state.call_state == "connected":
        # AI greets first, exactly once per call.
        if not st.session_state.call_greeted:
            greeting_audio = synthesize_tts(GREETING_TEXT, "en")
            st.session_state.call_messages.append({"role": "assistant", "content": GREETING_TEXT})
            st.session_state.call_pending_audio_b64 = greeting_audio
            st.session_state.call_greeted = True

        elapsed_ms = int((st.session_state.call_start_ts or time.time()) * 1000)
        st.markdown(f"""
        <div class="call-phone-frame" style="padding-bottom: 0.5rem;">
            <div class="call-avatar">🏦</div>
            <div class="call-name">{customer_display_name}</div>
            <div class="call-number">{st.session_state.call_phone_number or "Unknown number"}</div>
            <div class="call-status-connected">● Connected</div>
        </div>
        """, unsafe_allow_html=True)
        # A real <script> tag never executes inside st.markdown (it's inserted via
        # innerHTML, which browsers ignore for <script>), so the live ticking
        # timer needs an actual iframe via components.html instead.
        st.components.v1.html(f"""
        <div id="call-timer" style="font-family:'Courier New',monospace; font-size:1.5rem;
             letter-spacing:2px; text-align:center; color:#ffffff; background:#123a63;
             margin:0; padding:0.4rem 0;">00:00</div>
        <script>
        const start = {elapsed_ms};
        function tick() {{
            const el = document.getElementById('call-timer');
            const diff = Math.max(0, Math.floor((Date.now() - start) / 1000));
            const m = String(Math.floor(diff / 60)).padStart(2, '0');
            const s = String(diff % 60).padStart(2, '0');
            el.textContent = m + ':' + s;
        }}
        tick();
        setInterval(tick, 1000);
        </script>
        """, height=50)

        # Status line
        if st.session_state.call_pending_audio_b64 and st.session_state.call_speaker_on:
            status_text = "🔊 AI Speaking..."
        elif st.session_state.call_escalated:
            status_text = "🎧 Connecting you to a human agent..."
        elif st.session_state.call_muted:
            status_text = "🔇 Microphone muted"
        else:
            status_text = "🎙️ Listening... (tap the mic to speak)"
        st.markdown(f'<div class="call-live-tag">{status_text}</div>', unsafe_allow_html=True)

        # Live transcript
        transcript_html = '<div class="call-transcript">'
        for msg in st.session_state.call_messages:
            bubble = "call-bubble-user" if msg["role"] == "user" else "call-bubble-assistant"
            icon = "🧑" if msg["role"] == "user" else "🏦"
            transcript_html += f'<div class="{bubble}"><b>{icon}</b> &nbsp; {msg["content"]}</div>'
        transcript_html += '</div>'
        st.markdown(transcript_html, unsafe_allow_html=True)

        if st.session_state.call_escalated:
            st.markdown('<div class="escalate-banner">🎧 Connecting you to a human loan specialist... Please hold.</div>', unsafe_allow_html=True)

        st.write("")

        # Mic input (hidden while muted or escalated)
        call_audio_bytes = None
        if not st.session_state.call_muted and not st.session_state.call_escalated:
            call_audio_bytes = audio_recorder(
                text="Tap to speak",
                recording_color="#E65100",
                neutral_color="#1e88e5",
                icon_size="2x",
                key="call_mic",
            )

        # Controls row: Mute | Speaker | End Call
        c1, c2, c3 = st.columns(3)
        with c1:
            mute_label = "🔇 Unmute" if st.session_state.call_muted else "🎙️ Mute"
            if st.button(mute_label, use_container_width=True, key="call_mute_btn"):
                st.session_state.call_muted = not st.session_state.call_muted
                st.rerun()
        with c2:
            speaker_label = "🔈 Speaker Off" if st.session_state.call_speaker_on else "🔊 Speaker On"
            if st.button(speaker_label, use_container_width=True, key="call_speaker_btn"):
                st.session_state.call_speaker_on = not st.session_state.call_speaker_on
                st.rerun()
        with c3:
            if st.button("🔴 End Call", use_container_width=True, key="call_end_btn"):
                st.session_state.call_state = "ended"
                st.session_state.call_end_ts = time.time()
                st.session_state.call_pending_audio_b64 = None
                st.rerun()

        # Process new user speech
        if call_audio_bytes and call_audio_bytes != st.session_state.call_last_audio:
            st.session_state.call_last_audio = call_audio_bytes

            with st.spinner("Transcribing and thinking..."):
                result = send_audio_query(
                    customer_id=st.session_state.selected_customer or "CUST001",
                    audio_bytes=call_audio_bytes,
                    language=lang_code,
                    session_id=st.session_state.call_session_id,
                )

            user_text = result.get("transcribed_text") or "(Unclear audio)"
            st.session_state.call_messages.append({"role": "user", "content": f"🗣️ {user_text}"})
            st.session_state.call_messages.append({"role": "assistant", "content": result["reply_text"]})

            if result.get("escalate"):
                st.session_state.call_escalated = True

            st.session_state.call_pending_audio_b64 = result.get("audio_base64")
            st.rerun()

        # Autoplay pending assistant audio exactly once
        if st.session_state.call_pending_audio_b64 and st.session_state.call_speaker_on:
            audio_b64 = st.session_state.call_pending_audio_b64
            st.session_state.call_pending_audio_b64 = None
            st.markdown(
                f'<audio autoplay><source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3"></audio>',
                unsafe_allow_html=True,
            )
        elif st.session_state.call_pending_audio_b64:
            # Speaker muted — drop the pending clip without playing it.
            st.session_state.call_pending_audio_b64 = None
