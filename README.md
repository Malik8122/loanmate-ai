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

## Inbound vs Outbound Calls

The two call directions have different purposes, prompts, tools and records:

| | Inbound — customer calls the bank | Outbound — bank calls the customer |
|---|---|---|
| Who leads | The customer | LoanMate, with one campaign purpose |
| Purpose | Service desk: answer questions, resolve requests | `emi_reminder`, `overdue_followup`, `kyc_update` or `product_update` (top-up offer); `auto` picks from the account state |
| Opening | "How can I help you today?" — no pitching | States purpose, then confirms it is speaking to the right person before sharing any account detail |
| Agent-only tool | `raise_service_request` (statement, NOC, complaint, fraud report, human callback, ...) with a reference number | `record_call_outcome` (promise to pay, callback, not interested, do not call, wrong person, ...) |
| Rules | No cross-selling unless the customer asks | Respects busy / not interested / do-not-call; overdue calls follow RBI fair-recovery rules (no threats) |

Prompts live in `backend/voice_agent/prompts.py` (realtime path) and `backend/agents/call_flow.py` (legacy path). Service requests and call outcomes are written to `backend/data/call_records.jsonl` and served at `GET /api/calls/records`; `GET /api/calls/purposes` lists the purposes and outcomes.

## Knowledge Base

`backend/knowledge/` holds the RAG documents, one folder per type:

- `loan_products/`, `policies/`, `faq/`, `documents/` — LoanMate Bank's own (fictional demo) products and policies.
- `regulations/` — public RBI rules that apply to all Indian banks: prepayment/foreclosure charges, penal charges, Key Fact Statement and APR, repo-linked rates and EMI reset, document return after closure, NPA and fair recovery, KYC, digital lending.
- `customer_protection/` — RBI Ombudsman and grievance redressal, fraud safety, credit scores and bureaus.
- `government_schemes/` — PMAY-U 2.0 interest subsidy, education-loan schemes, tax benefits on loans.

Public-information documents name their source and a "last reviewed" date. Rebuild the vector index after editing any document:

```bash
python -m backend.rag.ingest     # rebuild the FAISS index
python -m backend.rag.eval_set   # check retrieval quality
```

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
