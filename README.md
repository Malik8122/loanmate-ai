# 🏦 BFSI Loan & EMI Voice Assistant

A conversational voice assistant for the Banking, Financial Services & Insurance (BFSI) domain. Helps customers query loan details, EMI amounts, due dates, and outstanding balances through natural voice or text interactions — in **English** and **Hindi/Hinglish**.

---

## Architecture

```text
┌──────────────┐       HTTP        ┌──────────────────────────────┐
│   Streamlit  │ ◄──────────────► │       FastAPI Backend         │
│   Frontend   │                   │                              │
│  (frontend/) │                   │  ┌────────┐  ┌───────────┐  │
│              │                   │  │ Routes  │  │ Services  │  │
│  • Chat UI   │                   │  │ voice   │  │ STT       │  │
│  • Customer  │                   │  │ loan    │  │ LLM       │  │
│    selector  │                   │  │ customer│  │ TTS       │  │
│  • 🎙 Voice  │                   │  └────────┘  │ Voice Orch│  │
│   (planned)  │                   │              └───────────┘  │
└──────────────┘                   │  ┌────────┐  ┌───────────┐  │
                                   │  │ Models │  │   Data    │  │
                                   │  │schemas │  │ mock_data │  │
                                   │  └────────┘  └───────────┘  │
                                   └──────────────────────────────┘
```

---

## Folder Structure

```text
BFSI-Voice-Assistant/
│
├── backend/
│   ├── main.py              # FastAPI app + health check
│   ├── config.py            # Centralised settings (.env)
│   ├── routes/
│   │   ├── voice.py         # Voice query endpoints
│   │   ├── loan.py          # Loan / EMI endpoints
│   │   └── customer.py      # Customer info endpoints
│   ├── services/
│   │   ├── voice_service.py # STT → LLM → TTS orchestrator
│   │   ├── llm_service.py   # LLM conversation layer
│   │   ├── stt_service.py   # Speech-to-Text
│   │   └── tts_service.py   # Text-to-Speech
│   ├── data/
│   │   └── mock_data.json   # Mock customers & loans
│   └── models/
│       └── schemas.py       # Pydantic schemas
│
├── frontend/
│   └── app.py               # Streamlit chat UI
│
├── prompts/
│   └── system_prompt.txt    # LLM system prompt
│
├── tests/
│   └── test_basic.py        # Pytest smoke tests
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Local Setup

### Prerequisites

- Python 3.11+
- pip

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/Conversational-Voice-Agent.git
cd Conversational-Voice-Agent
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
# Edit .env and add your API keys
```

---

## Running the Application

### Start the FastAPI backend

```bash
uvicorn backend.main:app --reload
```

The API will be available at **http://localhost:8000**.  
Interactive docs at **http://localhost:8000/docs**.

### Verify health check

```bash
curl http://localhost:8000/health
# → {"status":"ok","service":"bfsi-voice-assistant"}
```

### Start the Streamlit frontend

```bash
streamlit run frontend/app.py
```

The UI will open at **http://localhost:8501**.

### Run tests

```bash
pytest tests/ -v
```

---

## Current Status

| Component        | Status        |
|------------------|---------------|
| FastAPI backend  | ✅ Running     |
| Mock data        | ✅ Ready       |
| Customer API     | ✅ Working     |
| Loan / EMI API   | ✅ Working     |
| Streamlit UI     | ✅ Basic chat  |
| STT integration  | 🔲 Planned    |
| LLM integration  | 🔲 Planned    |
| TTS integration  | 🔲 Planned    |
| Telephony        | 🔲 Planned    |

---

## License

See [LICENSE](LICENSE) for details.
