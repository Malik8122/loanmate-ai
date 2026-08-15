"""
BFSI Loan & EMI Voice Assistant — Streamlit Frontend
"""

import streamlit as st
import requests
import uuid
import base64
from audio_recorder_streamlit import audio_recorder

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="BFSI Voice GAI Project",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
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

def send_audio_query(customer_id: str, audio_bytes: bytes, language: str = "auto") -> dict:
    """Send an audio query to the voice assistant endpoint."""
    try:
        files = {"audio": ("audio.wav", audio_bytes, "audio/wav")}
        data = {
            "customer_id": customer_id,
            "language": language,
            "session_id": st.session_state.session_id
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

def format_currency(amount):
    return f"₹{amount:,.2f}"

def reset_chat():
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I am your BFSI virtual assistant. How can I help you today?"}]
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.escalated = False


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
        
        # Reset chat if customer changes
        current_cust = st.session_state.selected_customer
        
        selected_label = st.selectbox("Select Profile", list(customer_options.keys()), label_visibility="collapsed")
        new_cust = customer_options[selected_label]
        
        if current_cust != new_cust:
            st.session_state.selected_customer = new_cust
            # Clear chat when switching users, unless it's the first load
            if current_cust is not None:
                reset_chat()
                st.rerun()
                
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
    lang_code_map = {"English": "en", "Hindi / Hinglish": "hi", "Auto Detect": "auto"}
    lang_code = lang_code_map[language]
    
    st.markdown("🎙️ **Voice Input**")
    audio_bytes = audio_recorder(text="Click to record", recording_color="#E65100", neutral_color="#0f3c6c", icon_size="2x")
    
    if st.button("🗑️ Start New Conversation", use_container_width=True):
        reset_chat()
        st.rerun()


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
chat_container = st.container(height=500, border=False)

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
