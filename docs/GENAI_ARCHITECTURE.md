# LoanMate AI — Backend & Generative AI Architecture

This document explains how the FastAPI backend works end to end, and precisely which
generative AI / LLM components are used where, how they're prompted, what guardrails
exist against hallucination, and what is deliberately *not* used (no vector DB, no
LangChain, no persistent memory).

There are **two parallel voice pipelines** in this codebase: a legacy cascaded
pipeline (STT → LLM → TTS, still used by the Streamlit demo) and the current
primary pipeline (a single audio-native LLM via LiveKit + Gemini Live, used by the
React app). Both are documented below, since both are live code paths.

---

## 1. High-level architecture

```
                                   ┌─────────────────────────────┐
                                   │   FastAPI backend (main.py)  │
                                   │                              │
  React (frontend/web/)  ───HTTP──►  /api/realtime/token          │──► LiveKit Cloud (WebRTC)
  "primary app"                    │                              │        │
                                   │  /api/livekit/*  (legacy)     │        │
  Streamlit (frontend/app.py) ─────►  /api/voice/*                │        ▼
  "legacy/admin demo"              │  /api/loan/*                 │   LiveKit Agents worker
                                   │  /api/customer/*              │   (realtime_agent.py)
                                   │  /api/apply/*                 │        │
                                   └─────────────────────────────┘        ▼
                                                                   Gemini Live (gemini-3.8-live)
```

FastAPI itself never touches raw audio for the primary path — it only issues LiveKit
tokens and resolves customer data. All real-time media, turn-taking, and speech
generation happens between the browser, LiveKit Cloud, and a separate Python worker
process that holds the actual Gemini Live connection.

### Directory map

```
backend/
  main.py                    FastAPI app, CORS, router registration
  config.py                  Env var loading (.env) — GOOGLE_API_KEY, LIVEKIT_*, etc.
  routes/
    realtime.py              PRIMARY — issues LiveKit tokens w/ agent auto-dispatch
    livekit.py               LEGACY — token + explicit start/stop-agent + transcript polling
    voice.py                 LEGACY — text/audio query endpoints (used by Streamlit chat)
    loan.py                  Deterministic loan/EMI REST endpoints (calculator, no LLM)
    customer.py              Demo customer list/lookup
    apply.py                 Mock loan application submission
  voice_agent/
    realtime_agent.py        PRIMARY — LiveKit Agents worker, Gemini Live, tools, prompts wiring
    call_context.py          CallContext dataclass — single source of truth for who/why
    prompts.py               Prompt builders (system instructions, greetings)
    agent.py                 LEGACY — custom RMS-VAD + faster-whisper + Gemini text + edge-tts
    prototype_cloud_tts.py   Isolated (unused) Google Cloud TTS evaluation prototype
  services/
    llm_service.py           LEGACY — Gemini text chat, JSON-mode, template/fallback narration
    stt_service.py           LEGACY — faster-whisper wrapper
    tts_service.py           LEGACY — edge-tts wrapper
    voice_service.py         LEGACY — wires STT → orchestrator → TTS for /api/voice/*
    loan_service.py          Reads mock_data.json / loan_knowledge.json (no AI)
    livekit_service.py       LiveKit token/credential handling
    agent_manager.py         LEGACY — in-process asyncio task lifecycle for agent.py
    call_transcript_store.py In-memory transcript buffer (legacy live-call transcript)
    session_store.py         In-memory per-session Gemini chat history (legacy)
  agents/
    orchestrator.py          LEGACY — routes text → intent → tool → LLM narration
    intent.py                Keyword-based intent classifier (NOT ML/LLM)
    language.py              Language resolution heuristics
    nlu.py                   Regex-based amount/tenure extraction from text
    glossary.py              Static financial-term glossary lookup
  tools/
    loan_tools.py            Pure functions reading a resolved customer_context dict
    calculator_tools.py      Pure EMI/prepayment/eligibility math (no AI)
  data/
    mock_data.json           Demo customers + loans
    loan_knowledge.json      Structured product catalogue + general FAQs
  models/schemas.py          Pydantic request/response models
prompts/
  system_prompt.txt          LEGACY system prompt text file
frontend/
  web/                       PRIMARY — Next.js + React + LiveKit React SDK
  app.py                     LEGACY — Streamlit chat/voice demo
```

---

## 2. Primary pipeline — realtime voice (React + Gemini Live)

This is the pipeline actually used by the React app for both inbound ("Call
LoanMate") and outbound ("Bank is Calling You") calls.

```
1. Browser calls  GET /api/realtime/token?customer_id=&call_mode=&outbound_reason=&language=
   (backend/routes/realtime.py)
        │
        ▼
2. Backend validates customer_id against LoanService.get_customer_with_loans()
   (404 if unknown — the browser can only SELECT a demo customer, never supply
   name/loan data directly)
        │
        ▼
3. Backend issues a LiveKit access token whose RoomConfiguration embeds a
   RoomAgentDispatch(agent_name="loanmate-realtime", metadata={customer_id,
   call_mode, outbound_reason, language})
        │
        ▼
4. Browser connects to LiveKit Cloud with that token (@livekit/components-react,
   LiveKitRoom + audio=true — mic auto-published, no push-to-talk)
        │
        ▼
5. LiveKit Cloud sees the room-config dispatch request and starts the registered
   "loanmate-realtime" worker (a SEPARATE long-running Python process —
   `python -m backend.voice_agent.realtime_agent dev|start`) inside that room,
   handing it the metadata as ctx.job.metadata
        │
        ▼
6. entrypoint() in realtime_agent.py:
     - parses metadata → build_call_context() → CallContext (call_context.py)
     - resolves the REAL customer record again server-side (LoanService)
     - builds LoanMateAgent(call_context, customer_context) — an Agent subclass
       with 10 @function_tool methods bound to this customer's data
     - creates AgentSession(llm=RealtimeModel(model="gemini-3.8-live", voice="Puck",
       language=en-IN/hi-IN/None, api_key=GOOGLE_API_KEY))
     - session.start(agent, room=ctx.room)  → opens the Gemini Live WebSocket
     - session.generate_reply(instructions=<mode-specific opening line>) → the
       agent speaks FIRST, before the user says anything
        │
        ▼
7. From here on, ALL of speech recognition, language understanding, tool-call
   decisions, and speech synthesis happen INSIDE Gemini Live — one continuous
   audio-in/audio-out WebSocket. LiveKit just relays audio frames both ways and
   exposes state (listening/thinking/speaking) natively via AgentSession events,
   consumed by the React app's useVoiceAssistant() hook — no custom VAD, no
   custom state machine.
        │
        ▼
8. When the model decides a customer question needs real data, it calls one of
   the bound @function_tool methods (plain Python, see §5) and speaks the
   returned string back — the LLM never invents a number.
```

**Key files:** `backend/routes/realtime.py`, `backend/voice_agent/realtime_agent.py`,
`backend/voice_agent/call_context.py`, `backend/voice_agent/prompts.py`.

**Why a separate worker process?** LiveKit Agents' architecture requires a
persistent worker registered with LiveKit Cloud that gets dispatched per-room;
it is not something FastAPI's request/response cycle can host itself. In dev you
run three processes: `uvicorn` (backend), `python -m backend.voice_agent.realtime_agent dev`
(the worker), and `npm run dev` (frontend).

---

## 3. Legacy pipeline — cascaded STT → LLM → TTS (Streamlit)

Still fully functional, used by `frontend/app.py`. Two entry points:

**A) Text or short-audio query (`/api/voice/query/text`, `/api/voice/query/audio`,
`backend/services/voice_service.py`):**
```
audio_bytes ──► STTService (faster-whisper, model_size="tiny", CPU/int8)
                     │
                     ▼
              transcript text
                     │
                     ▼
      AgentOrchestrator.handle()  (backend/agents/orchestrator.py)
        1. resolve_response_language()          — language.py
        2. classify_intent(text)                — intent.py (keyword matching, NOT ML)
        3. if intent maps to a known tool → run it (loan_tools.py / calculator_tools.py)
             → LLMService.phrase_tool_result()   — narrate the tool's exact numbers
           else → LLMService.generate_response()  — open-ended Gemini chat
                     │
                     ▼
              TTSService.synthesize() (edge-tts) ──► audio bytes back to client
```

**B) Live voice call (`backend/voice_agent/agent.py`, dispatched via
`backend/routes/livekit.py` + `agent_manager.py` as an in-process asyncio task,
not a separate worker):** same STT → orchestrator → TTS chain, but streaming —
custom RMS-based voice-activity detection buffers the caller's mic audio, waits
for a silence gap, transcribes the utterance, runs the same orchestrator, then
speaks the reply back in 20ms LiveKit audio frames (chunked so a
barge-in `asyncio.Task.cancel()` genuinely stops mid-sentence).

This pipeline is kept for the Streamlit demo and as a working fallback reference,
not because it's the recommended architecture going forward.

---

## 4. Generative AI / LLM inventory

| Model | SDK | Where | Role |
|---|---|---|---|
| **`gemini-3.8-live`** | `livekit-plugins-google` → `RealtimeModel` (Gemini Live / Multimodal Live API) | `realtime_agent.py` | **Primary.** One model does ASR + reasoning + tool-calling + TTS over a single WebSocket — audio in, audio out, no separate STT/TTS |
| **`gemini-3.6-flash`** | `google-generativeai` (deprecated SDK, `genai.GenerativeModel`) | `llm_service.py` | Legacy text chat: open-ended conversation fallback, and (only for tool names with no template) narrating a tool result in natural language |
| **`faster-whisper`** ("tiny", CTranslate2, local CPU) | `faster-whisper` | `stt_service.py` | Legacy speech-to-text only — not generative, a discriminative ASR model, listed here because it's part of the AI stack |
| **`edge-tts`** (Microsoft Edge read-aloud) | `edge-tts` | `tts_service.py` | Legacy text-to-speech only — not generative in the LLM sense, a cloud TTS service |

**Not used, evaluated but not adopted:** Google Cloud Text-to-Speech (Chirp 3 HD
Indian voices) — prototyped in isolation (`prototype_cloud_tts.py`) but blocked by
missing GCP credentials in this environment and never wired into production.

**Not used at all:** LangChain / LlamaIndex or any agent framework, any vector
database or embeddings, OpenAI or any non-Google LLM, any hosted "AI phone" platform.

---

## 5. Agentic tool-calling (how the LLM touches real data)

Both pipelines follow the same core principle: **the LLM never computes a number
itself — it only calls a tool and narrates the tool's return value.** This is the
single most important anti-hallucination design decision in the project.

**Realtime path** — native function calling. `LoanMateAgent` (in
`realtime_agent.py`) subclasses LiveKit Agents' `Agent` and exposes 10 methods
decorated `@function_tool()`:

| Tool | Backs onto |
|---|---|
| `get_emi` | `loan_tools.get_emi()` |
| `get_outstanding_balance` | `loan_tools.get_outstanding_balance()` |
| `get_next_payment` | `loan_tools.get_next_payment()` |
| `get_loan_status` | `loan_tools.get_loan_status()` |
| `get_remaining_tenure` | `loan_tools.get_remaining_tenure()` |
| `get_payment_history` | `loan_tools.get_payment_history()` |
| `calculate_prepayment` | `calculator_tools.calculate_prepayment()` |
| `compare_tenures` | `calculator_tools.compare_tenures()` |
| `calculate_loan_eligibility` | `calculator_tools.calculate_loan_eligibility()` |
| `get_bank_info` | keyword search over `loan_knowledge.json` (see §6) |

Gemini Live decides *when* to call a tool purely from conversation context and
the tool's docstring (parsed via `docstring_parser` to build the JSON schema the
model sees) — there is no separate intent classifier in this path. Each tool
closes over `self._customer_context`, a dict already scoped to one validated
customer, so a tool can't be pointed at someone else's data.

**Legacy path** — manual routing, not model-native function calling.
`backend/agents/intent.py` does **keyword substring matching** (e.g. "outstanding",
"baki kitna", "emi kab") to classify intent *before* any LLM call, and
`orchestrator.py` runs the matching tool directly in Python. The LLM is invoked
only afterward, to phrase the result — and even that is skipped for every
currently known tool name via hand-written templates in
`llm_service._template_phrase()` (both English and Hindi/Hinglish phrasings),
saving a full network+inference round trip on the hottest path. Gemini is only
called for genuinely open-ended conversation or a hypothetical future
unrecognized tool name.

---

## 6. Retrieval / knowledge grounding — lightweight, not vector RAG

There is **no embedding-based retrieval-augmented generation** in this project —
no vector store, no similarity search, no chunking pipeline. What exists instead:

- **`get_bank_info(topic)`** (realtime path, `realtime_agent.py`): does a plain
  substring/keyword match of the requested `topic` against
  `backend/data/loan_knowledge.json` (`loan_products` — 5 product types with
  rates/eligibility/documents; `general_faqs` — 6 Q&A pairs on foreclosure,
  missed EMI, applying, etc.) and returns up to 3 matching entries as text for
  the model to narrate. This grounds "what products do you offer / what is
  foreclosure / what documents do I need" style questions in real structured
  data instead of the model's own (unverifiable, possibly wrong) training
  knowledge about this specific bank.
- **Legacy path**: `llm_service._get_system_prompt()` takes a different, cruder
  approach — it dumps the *entire* `loan_knowledge.json` verbatim into the
  system prompt on every call (`--- KNOWLEDGE BASE ---` section), rather than
  retrieving a relevant subset. This works at the current tiny data size but
  would not scale — it is context-stuffing, not retrieval.

If asked directly "do you use RAG": the honest answer is *keyword-based lookup
over a small structured JSON file, functioning as lightweight retrieval — not
embedding/vector-based RAG.*

**Customer context is not retrieved at all** — it's resolved once per call from
`mock_data.json` via `LoanService.get_customer_with_loans()` and injected
directly as a structured block (see §7). This is context-injection, distinct
from retrieval.

---

## 7. Prompt architecture

**Realtime path — `backend/voice_agent/prompts.py`** is the single source of
truth for everything the model is told:

- `build_system_instructions(context: CallContext)` — persona ("warm,
  professional Indian bank representative... not robotic, not salesy"),
  concrete good/bad phrasing examples, a literal `CUSTOMER CONTEXT:` block
  (name / customer ID / loan ID), identity-question rules, the
  tools-vs-general-knowledge rule, the no-Urdu rule, the Hinglish vocabulary
  rule, and the barge-in rule ("stop immediately and listen").
- `build_inbound_instructions(context)` — a short greeting directive used as the
  very first `generate_reply()` call ("Hi, you're connected with LoanMate...",
  explicitly "do not pitch anything").
- `build_outbound_instructions(context, reason)` — reason-specific opening
  directives (`product_update` vs `emi_reminder`), each with a concrete example
  sentence and an instruction to vary the exact wording so it doesn't sound
  scripted.

`CallContext` (`call_context.py`) is a frozen dataclass — `customer_id`,
`customer_name`, `loan_id`, `call_mode` ("inbound"/"outbound"),
`outbound_reason` ("product_update"/"emi_reminder"/None), `language`
("english"/"hindi"/"hinglish") — built once per call from server-validated data
and never mutated. It also derives `gemini_language_code` (`en-IN`/`hi-IN`/`None`)
and `first_name` (for natural greetings, "Hi Rajesh" not "Hi Rajesh Kumar").

**Legacy path — `prompts/system_prompt.txt`** plus a dynamically appended
knowledge-base + customer-context JSON blob (see §6), read fresh on every
`LLMService._get_system_prompt()` call.

---

## 8. Multilingual handling

No translation model and no separate language classifier feeding the LLM.
Support for English / Hindi / Hinglish is achieved entirely through:
1. Gemini's native multilingual understanding (both models understand and can
   generate all three without extra tooling).
2. `language_code` passed to Gemini Live (`en-IN` / `hi-IN`) to bias locale
   behavior — **explicitly documented as a locale hint, not a guarantee of an
   Indian-accented voice** (voice identity/accent and language locale are two
   different knobs — see `docs` from the voice-comparison work; Gemini Live's
   named voices like "Puck"/"Kore" have no documented Indian-accent variant).
3. For **Hinglish**, `gemini_language_code` is deliberately left `None`
   (auto-detect) rather than pinned to either locale, so the model can
   naturally code-switch within a sentence instead of being forced into one
   language's phonology.
4. Explicit prompt instructions to never use Urdu script/vocabulary — there is
   no Urdu-specific code path anywhere in the project.

The legacy path's `_fallback_response()` and `_template_phrase()` do their
Hindi/English branching with a simple `language == "hi"` flag and hand-written
bilingual strings — no model involved there at all.

---

## 9. Session / customer context & memory

- **Realtime path:** context is per-call and ephemeral. `CallContext` is built
  fresh from `ctx.job.metadata` every time a new room is dispatched; there is no
  persistence across calls, no long-term user memory, no vector store of past
  conversations. Gemini Live's own conversation state lives only inside that
  one WebSocket session and disappears when the call ends.
- **Legacy path:** `SessionStore` (`session_store.py`) keeps a plain in-memory
  Python list of Gemini chat-history turns keyed by `session_id` — this is
  **process memory, not a database**; it's lost on backend restart and never
  shared across processes. It exists only so a multi-turn text/voice chat on
  one Streamlit session remembers earlier turns within that session.
- **No RAG-style "memory retrieval"** (e.g. "recall what this customer asked
  last week") exists anywhere in the project.

---

## 10. Guardrails and reliability engineering

- **Never let the LLM invent a number.** Every customer-specific fact or
  calculation is required by prompt instruction (realtime) or hard-coded
  routing (legacy) to go through a deterministic tool.
- **Fail fast, don't hang the call.** Legacy Gemini calls use
  `RequestOptions(retry=None, timeout=8)` and `send_message_async` — a 429/503
  fails immediately and falls through to the rule-based `_fallback_response()`
  rather than retrying with backoff for 20+ seconds of dead air (this was a
  real bug found and fixed during development).
- **Three-layer fallback on the legacy path:** Gemini JSON-mode chat → (on
  any failure/non-JSON) → deterministic keyword-based `_fallback_response()`
  (works with *zero* API key or AI at all) → for tool phrasing specifically,
  hand-written bilingual templates before ever reaching Gemini.
- **Never speak a raw exception to the user.** API errors are logged
  server-side and replaced with the fallback responder, never surfaced as TTS
  text.
- **Escalation keywords are deliberately narrow** multi-word phrases ("talk to
  a human", "connect me to an agent") — an earlier bare "agent"/"help me"
  match false-triggered on "How can you help me?" and was fixed.
- **Customer identity is never client-supplied.** The browser can only pick a
  `customer_id`; the backend re-resolves the full record server-side both at
  token-issue time and again inside the worker before building `CallContext` —
  the model only ever sees data the backend put there.

---

## 11. Data layer (no AI)

- `backend/data/mock_data.json` — demo customers (`name`, `phone`, `language`,
  `city`, `kyc_verified`) and their loans (`emi`, `outstanding_amount`,
  `due_date`, `remaining_tenure`, `interest_rate`, `loan_status`, etc.).
- `backend/data/loan_knowledge.json` — `loan_products` (5 types with rates,
  eligibility, required documents, FAQs) and `general_faqs` (6 entries).
- Both are flat JSON files read directly (`json.load`) — no database, no ORM,
  no migrations. `LoanService` is the only reader/writer.

---

## 12. Full API surface

| Route prefix | Endpoints | AI involved? |
|---|---|---|
| `/api/realtime` | `GET /token` | No LLM call here — issues a token; the LLM lives in the separate worker process |
| `/api/livekit` (legacy) | `GET /status`, `GET /token`, `POST /start-agent`, `POST /stop-agent`, `GET /transcript`, `GET /transcript/peek` | Triggers the legacy in-process voice agent (STT+LLM+TTS) |
| `/api/voice` (legacy) | `POST /query/text`, `POST /query/audio` | Full STT→LLM→TTS or text→LLM→TTS pipeline |
| `/api/loan` | EMI/summary/knowledge/calculate-emi/simulate-prepayment/compare-tenures/eligibility | Pure Python math — **no LLM at all**, callable directly by the Streamlit UI for instant calculator widgets |
| `/api/customer` | `GET /list`, `GET /{customer_id}` | No AI — plain JSON lookup |
| `/api/apply` | `POST /submit` | No AI — writes a mock application record |

---

## 13. What this project deliberately does NOT use

- No LangChain, LlamaIndex, or any agent-orchestration framework — tool-calling
  is done via the LLM SDK's own native function-calling.
- No vector database or embeddings anywhere (Pinecone, Chroma, FAISS, etc.) —
  "retrieval" is plain keyword substring matching over small JSON files.
  Making this document available doesn't imply RAG exists; it explicitly does not, in the vector sense.
  If a scaled-up version needed real semantic retrieval over a larger product
  catalogue, that would be new work, not something hiding here already.
- No persistent conversation memory / user profile store across sessions.
  No paid third-party telephony (no Twilio, no PSTN) — outbound/inbound are
  both browser-simulated via LiveKit rooms.
- No Urdu language support of any kind (explicit product requirement).
- No non-Google LLM provider.

---

## 14. Known limitations (stated plainly, not glossed over)

- Gemini Live's prebuilt voices (Puck, Kore, Charon, Aoede, Leda, Orus) have no
  documented Indian-accent variant; `language=en-IN/hi-IN` affects locale
  behavior, not necessarily perceived accent. See `voice_evaluation/` for the
  actual comparison recordings and the still-open question of whether a
  Google Cloud TTS hybrid would sound more Indian (blocked on missing GCP
  credentials as of this writing).
- The legacy pipeline's context-stuffing (dumping the whole knowledge base into
  every prompt) would not scale past this demo's data size.
- No automated test coverage for the realtime path's prompt/tool behavior —
  verification so far has been manual, simulated-audio integration testing,
  not unit tests.
- Real human-microphone testing has not been performed in this development
  environment (no audio hardware) — all voice-path verification used
  synthesized test speech through a simulated LiveKit participant.
