"""
BFSI Loan & EMI Voice Assistant — Streamlit Frontend
"""

import streamlit as st
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="BFSI Voice Assistant",
    page_icon="🏦",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A5F;
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
        background-color: #E0F2FE;
        padding: 0.75rem 1rem;
        border-radius: 12px;
        margin: 0.4rem 0;
    }
    .chat-assistant {
        background-color: #F0FDF4;
        padding: 0.75rem 1rem;
        border-radius: 12px;
        margin: 0.4rem 0;
    }
    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .status-ok { background: #D1FAE5; color: #065F46; }
    .status-err { background: #FEE2E2; color: #991B1B; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "selected_customer" not in st.session_state:
    st.session_state.selected_customer = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def check_health() -> bool:
    """Ping the backend health endpoint."""
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def fetch_customers() -> list[dict]:
    """Fetch customer list from backend."""
    try:
        resp = requests.get(f"{API_BASE}/api/customer/list", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def send_text_query(customer_id: str, text: str, language: str = "en") -> dict:
    """Send a text query to the voice assistant endpoint."""
    try:
        resp = requests.post(
            f"{API_BASE}/api/voice/query/text",
            json={"customer_id": customer_id, "text": text, "language": language},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"reply_text": f"⚠️ Error: {exc}", "language": language}


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
st.markdown('<p class="main-header">🏦 BFSI Loan & EMI Voice Assistant</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Ask about your loans, EMIs, due dates, and more — in English or Hindi</p>', unsafe_allow_html=True)

# Sidebar — backend status & customer selector
with st.sidebar:
    st.header("⚙️ Settings")

    # Health check
    healthy = check_health()
    if healthy:
        st.markdown('<span class="status-badge status-ok">🟢 Backend Online</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-badge status-err">🔴 Backend Offline</span>', unsafe_allow_html=True)
        st.info("Start the backend with:\n```\nuvicorn backend.main:app --reload\n```")

    st.divider()

    # Customer selector
    st.subheader("👤 Select Customer")
    customers = fetch_customers()

    if customers:
        customer_options = {f"{c['name']}  ({c['customer_id']})": c["customer_id"] for c in customers}
        selected_label = st.selectbox("Customer", list(customer_options.keys()))
        st.session_state.selected_customer = customer_options[selected_label]
    else:
        st.session_state.selected_customer = st.text_input("Customer ID", value="CUST001")

    st.divider()

    # Language
    language = st.radio("🌐 Language", ["English", "Hindi / Hinglish"], index=0)
    lang_code = "en" if language == "English" else "hi"

    st.divider()

    # Microphone placeholder
    st.subheader("🎙️ Voice Input")
    st.caption("Microphone integration coming soon. Use the text box below for now.")

    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.rerun()


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
chat_container = st.container()

with chat_container:
    for msg in st.session_state.messages:
        role = msg["role"]
        css_class = "chat-user" if role == "user" else "chat-assistant"
        icon = "🧑" if role == "user" else "🤖"
        st.markdown(f'<div class="{css_class}">{icon} {msg["content"]}</div>', unsafe_allow_html=True)

# Input area
user_input = st.chat_input("Type your loan / EMI question here...")

if user_input:
    # Add user message
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Get response from backend
    result = send_text_query(
        customer_id=st.session_state.selected_customer,
        text=user_input,
        language=lang_code,
    )

    # Add assistant reply
    st.session_state.messages.append({"role": "assistant", "content": result["reply_text"]})

    st.rerun()
