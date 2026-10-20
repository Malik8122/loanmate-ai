"""
Direction-specific call handling for the legacy (Streamlit / LiveKit
STT -> LLM -> TTS) voice path — the keyword-based counterpart of the
CALL PURPOSE sections in backend/voice_agent/prompts.py.

- Inbound (customer called the bank): detect requests the bank must
  action (statement, NOC, complaint, human callback, ...) and raise a
  service request with a reference number.
- Outbound (bank called the customer for one campaign): open with the
  campaign's purpose, recognise the customer's response (busy, not
  interested, wrong person, will pay, already paid, ...), record the
  call outcome, and reply with the matching script.

Like backend/agents/intent.py this is plain substring matching —
transparent and zero-latency, covering English, Hindi and Hinglish.
"""

from __future__ import annotations

from backend.agents.nlu import parse_amount

# ── Inbound: service requests ─────────────────────────────────────────
# Checked in order; more specific phrases first.
SERVICE_REQUEST_KEYWORDS: list[tuple[str, list[str]]] = [
    ("fraud_report", ["fraud", "scam", "someone asked for my otp", "unauthorised", "unauthorized", "dhokha"]),
    ("complaint", ["complaint", "complain", "shikayat", "grievance"]),
    ("no_dues_certificate", ["no dues", "no-dues", "noc", "no objection", "closure certificate"]),
    ("foreclosure_quote", ["foreclosure quote", "foreclosure letter", "foreclosure statement", "payoff amount", "close my loan"]),
    ("interest_certificate", ["interest certificate", "tax certificate", "provisional certificate"]),
    ("document_return", ["original documents", "property documents", "documents back", "papers back", "kagaz wapas"]),
    ("account_statement", ["account statement", "loan statement", "statement chahiye", "send me a statement", "repayment schedule"]),
    ("emi_date_change", ["change my emi date", "change emi date", "emi date change", "emi ki date badal"]),
    ("update_contact_details", ["update my address", "change my address", "update my mobile", "change my mobile", "update my email", "change my email"]),
    ("restructuring_request", ["can't pay", "cannot pay", "unable to pay", "lost my job", "restructure", "restructuring", "pay nahi kar", "naukri chali gayi"]),
]


def classify_service_request(text: str) -> str | None:
    msg = " " + text.lower().strip() + " "
    for request_type, keywords in SERVICE_REQUEST_KEYWORDS:
        if any(kw in msg for kw in keywords):
            return request_type
    return None


_SERVICE_REQUEST_REPLIES = {
    "fraud_report": (
        "I'm sorry to hear that. Please call the national cyber fraud helpline 1930 right away, and never share an OTP or PIN with anyone. "
        "I've also logged a fraud report with the bank, reference number {ref}.",
        "Yeh sunkar afsos hua. Kripya turant cyber fraud helpline 1930 par call kijiye, aur kisi ko bhi OTP ya PIN mat bataiye. "
        "Maine bank mein fraud report bhi darj kar di hai, reference number {ref} hai.",
    ),
    "complaint": (
        "I'm sorry about that. I've registered your complaint, reference number {ref}. If it isn't resolved within 30 days, you can escalate it to the RBI Ombudsman.",
        "Iske liye maafi chahte hain. Maine aapki complaint darj kar li hai, reference number {ref} hai. Agar 30 din mein hal na ho, toh aap RBI Ombudsman ke paas ja sakte hain.",
    ),
    "human_callback": (
        "Sure, I've requested a callback from one of our loan officers, reference number {ref}.",
        "Zaroor, maine hamare loan officer se callback request kar diya hai, reference number {ref} hai.",
    ),
    "restructuring_request": (
        "I understand, and thank you for telling us early. I've raised a request for our team to discuss repayment options with you, reference number {ref}.",
        "Main samajh sakta hoon, aur samay par batane ke liye dhanyavaad. Maine aapke liye repayment options par baat karne ki request daal di hai, reference number {ref} hai.",
    ),
}
_DEFAULT_SERVICE_REPLY = (
    "Done — I've raised a request for your {label}, reference number {ref}.",
    "Ho gaya — maine aapke {label} ke liye request daal di hai, reference number {ref} hai.",
)


def service_request_reply(request_type: str, label: str, reference: str, language: str) -> str:
    en, hi = _SERVICE_REQUEST_REPLIES.get(request_type, _DEFAULT_SERVICE_REPLY)
    template = hi if language == "hi" else en
    # Spell the reference out digit by digit so TTS reads "S R 4 5 ..." rather than a large number.
    spoken_ref = " ".join(reference)
    return template.format(ref=spoken_ref, label=label.lower())


# ── Outbound: campaign openers ────────────────────────────────────────
_OPENERS = {
    "emi_reminder": (
        "Hello, this is LoanMate calling from your bank with a quick reminder about your upcoming {loan_type} EMI. Am I speaking with {name}?",
        "Namaste, main LoanMate, aapke bank se bol raha hoon. Aapke {loan_type} ki aane wali EMI ka ek chhota sa reminder dena tha. Kya meri baat {name} ji se ho rahi hai?",
    ),
    "overdue_followup": (
        "Hello, this is LoanMate calling from your bank. May I speak with {name}? It's regarding your {loan_type} account.",
        "Namaste, main LoanMate, aapke bank se bol raha hoon. Kya meri baat {name} ji se ho sakti hai? Yeh aapke {loan_type} account ke baare mein hai.",
    ),
    "kyc_update": (
        "Hello, this is LoanMate calling from your bank about a pending KYC update on your account. Am I speaking with {name}?",
        "Namaste, main LoanMate, aapke bank se bol raha hoon. Aapke account mein KYC update pending hai, usi ke baare mein call kiya hai. Kya meri baat {name} ji se ho rahi hai?",
    ),
    "product_update": (
        "Hello, this is LoanMate calling from your bank. Am I speaking with {name}? I have a quick update about a top-up option on your {loan_type} — is this a good time?",
        "Namaste, main LoanMate, aapke bank se bol raha hoon. Kya meri baat {name} ji se ho rahi hai? Aapke {loan_type} par ek top-up option ke baare mein chhoti si jaankari deni thi — kya abhi baat karna theek rahega?",
    ),
}


def outbound_opener(reason: str, customer_name: str, loan_type: str | None, language: str) -> str:
    en, hi = _OPENERS.get(reason, _OPENERS["emi_reminder"])
    template = hi if language == "hi" else en
    return template.format(name=customer_name, loan_type=loan_type or "loan")


# ── Outbound: customer responses -> outcome ──────────────────────────
# Order matters: refusals and identity problems are checked before
# agreement, so "no, not now, call later" isn't read as a yes.
_OUTCOME_KEYWORDS: list[tuple[str, list[str]]] = [
    ("wrong_person", ["wrong number", "wrong person", "not me", "no one by that name", "galat number", "main nahi hoon", "woh yahan nahi"]),
    ("do_not_call", ["don't call me", "do not call", "stop calling", "call mat karo", "phone mat karna"]),
    ("not_interested", ["not interested", "no thanks", "no thank you", "interest nahi", "nahi chahiye"]),
    ("callback_requested", ["call later", "call me later", "busy", "call back", "callback", "baad mein", "abhi nahi", "not a good time", "driving", "in a meeting"]),
    ("already_paid", ["already paid", "paid it", "pay kar diya", "bhar diya", "already done", "already updated", "kar diya hai"]),
    ("dispute", ["wrong amount", "not correct", "dispute", "galat hai", "i don't owe"]),
    ("payment_difficulty", ["can't pay", "cannot pay", "unable to pay", "lost my job", "financial problem", "paise nahi", "pay nahi kar", "naukri chali gayi", "difficult"]),
    ("will_pay_on_time", ["on time", "auto debit", "auto-debit", "balance hai", "balance rahega"]),
    ("promise_to_pay", ["will pay on", "pay by", "pay on", "next week", "salary", "tak pay", "tak bhar", "kar dunga", "kar dungi"]),
    ("interested", ["interested", "tell me more", "sounds good", "batao", "haan bataiye"]),
]

# Per-campaign mapping of a generic "yes / sure / will do" to that campaign's success outcome.
_AFFIRMATIVE = ["yes", "sure", "okay", "ok ", "will do", "haan", "ji haan", "theek hai", "zaroor", "done"]
_AFFIRMATIVE_OUTCOME = {
    "emi_reminder": "will_pay_on_time",
    "kyc_update": "will_update_kyc",
    "product_update": "interested",
}


def classify_outbound_response(text: str, reason: str, allowed_outcomes: set[str]) -> str | None:
    """Map the customer's reply on an outbound call to a call outcome, or
    None if it's something else (e.g. a question the normal tools answer).
    """
    msg = " " + text.lower().strip() + " "
    if reason == "kyc_update" and any(kw in msg for kw in ["already updated", "already done", "kar diya hai"]):
        return "already_updated"
    for outcome, keywords in _OUTCOME_KEYWORDS:
        if outcome in allowed_outcomes and any(kw in msg for kw in keywords):
            return outcome
    affirmative = _AFFIRMATIVE_OUTCOME.get(reason)
    if affirmative in allowed_outcomes and any(kw in msg for kw in _AFFIRMATIVE):
        return affirmative
    return None


def promised_amount(text: str) -> float | None:
    return parse_amount(text)


# ── Outbound: right-party confirmation ───────────────────────────────
_IDENTITY_YES = ["yes", "speaking", "this is", "that's me", "it's me", "haan", "ji haan", "bol raha", "bol rahi", "main hi", "ji boliye", "haan ji"]
_IDENTITY_NO = ["no ", "nope", "nahi", "not here", "not available"]


def classify_identity_reply(text: str) -> str | None:
    """"confirmed", "wrong_person", or None (unclear — ask again)."""
    msg = " " + text.lower().strip() + " "
    if any(kw in msg for kw in _OUTCOME_KEYWORDS[0][1]):  # explicit wrong-number phrases
        return "wrong_person"
    if any(kw in msg for kw in _IDENTITY_YES):
        return "confirmed"
    if msg.strip().startswith(("no", "nahi", "nope")) or any(kw in msg for kw in _IDENTITY_NO):
        return "wrong_person"
    return None


def identity_retry(customer_name: str, language: str) -> str:
    if language == "hi":
        return f"Maaf kijiye, kya meri baat {customer_name} ji se ho rahi hai?"
    return f"Sorry, just to confirm — am I speaking with {customer_name}?"


def _inr(amount: float | int | None) -> str:
    """Indian digit grouping: 2870000 -> 28,70,000."""
    if amount is None:
        return "-"
    n = int(round(amount))
    s = str(n)
    if len(s) <= 3:
        return f"₹{s}"
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join(groups + [tail])


def purpose_message(reason: str, loan: dict | None, first_name: str, language: str) -> str:
    """What LoanMate says once the right person is confirmed — the actual
    reason for the call, with the customer's real figures.
    """
    loan = loan or {}
    loan_type = loan.get("loan_type") or "loan"
    emi = _inr(loan.get("emi"))
    due = loan.get("due_date") or "the due date"
    outstanding = _inr(loan.get("outstanding_amount"))
    hi = language == "hi"
    if reason == "emi_reminder":
        if hi:
            return f"Dhanyavaad {first_name} ji. Aapke {loan_type} ki {emi} ki EMI {due} ko due hai. Kya tab tak account mein payment ka intezaam ho jayega?"
        return f"Thanks, {first_name}. Your {loan_type} EMI of {emi} is due on {due}. Will the payment be ready in your account by then?"
    if reason == "overdue_followup":
        if hi:
            return f"Dhanyavaad {first_name} ji. Aapke {loan_type} account mein {emi} ki EMI overdue hai. Kya aap bata sakte hain ki payment kab tak ho payega?"
        return f"Thank you, {first_name}. Your {loan_type} account shows an overdue EMI of {emi}. Could you tell me when you'll be able to make the payment?"
    if reason == "kyc_update":
        if hi:
            return f"Dhanyavaad {first_name} ji. Aapka KYC verification pending hai — RBI ke niyam ke anusaar bank ko KYC update rakhna hota hai, warna kuch services ruk sakti hain. Kya aap is hafte KYC update kar payenge?"
        return f"Thank you, {first_name}. Your KYC verification is pending — RBI rules require banks to keep KYC up to date, otherwise some account services can be restricted. Would you be able to update it this week?"
    # product_update
    if hi:
        return f"Dhanyavaad {first_name} ji. Aapke {loan_type} par aap ek top-up loan le sakte hain — usi loan par extra funds, eligibility ke anusaar. Kya aap chahenge ki ek loan specialist aapko details bataye?"
    return f"Thank you, {first_name}. On your {loan_type} you may be able to take a top-up loan — additional funds on your existing loan, subject to eligibility. Would you like a loan specialist to share the details?"


_OUTCOME_REPLIES = {
    "wrong_person": (
        "I'm sorry for the trouble. Could you please ask them to call their bank when convenient? Thank you, have a good day.",
        "Pareshani ke liye maafi chahta hoon. Kripya unhe apne bank ko call karne ke liye keh dijiye. Dhanyavaad.",
    ),
    "do_not_call": (
        "Understood, I've noted that you don't want these calls. Sorry for the interruption, have a good day.",
        "Samajh gaya, maine note kar liya hai ki aapko aise call nahi chahiye. Takleef ke liye maafi, aapka din shubh ho.",
    ),
    "not_interested": (
        "No problem at all, thank you for your time. Have a good day.",
        "Koi baat nahi, aapke samay ke liye dhanyavaad. Aapka din shubh ho.",
    ),
    "callback_requested": (
        "Of course, I'll arrange a call back at a better time. Thank you!",
        "Zaroor, main aapko kisi aur samay call back karwa doonga. Dhanyavaad!",
    ),
    "already_paid": (
        "Thank you for confirming! I've noted it, and it will reflect once the payment is processed.",
        "Confirm karne ke liye dhanyavaad! Maine note kar liya hai, payment process hote hi update ho jayega.",
    ),
    "already_updated": (
        "Thank you! I've noted it, and our team will verify the update.",
        "Dhanyavaad! Maine note kar liya hai, hamari team update verify kar legi.",
    ),
    "dispute": (
        "I understand. I've noted that you disagree with the dues, and our team will review the account and get back to you.",
        "Main samajh gaya. Maine note kar liya hai ki aap dues se sahmat nahi hain, hamari team account check karke aapse sampark karegi.",
    ),
    "payment_difficulty": (
        "I'm sorry to hear that, and thank you for telling me. I've noted it so our team can discuss repayment options with you — please reach out before the due date if you can.",
        "Yeh sunkar afsos hua, aur batane ke liye dhanyavaad. Maine note kar liya hai taaki hamari team aapse repayment options par baat kar sake.",
    ),
    "promise_to_pay": (
        "Thank you, I've noted your commitment to pay. Paying on time helps avoid penal charges and keeps your credit score healthy.",
        "Dhanyavaad, maine aapka payment commitment note kar liya hai. Samay par payment se penal charges nahi lagte aur credit score achha rehta hai.",
    ),
    "will_pay_on_time": (
        "Great, thank you! Just keep enough balance in your auto-debit account before the due date. Have a good day.",
        "Bahut achha, dhanyavaad! Bas due date se pehle auto-debit account mein balance rakhiyega. Aapka din shubh ho.",
    ),
    "will_update_kyc": (
        "Thank you! You can update your KYC at any branch, through net banking, or by video KYC. Please never share an OTP or Aadhaar number over a call.",
        "Dhanyavaad! Aap KYC kisi bhi branch, net banking, ya video KYC se update kar sakte hain. Kripya kisi call par OTP ya Aadhaar number mat bataiye.",
    ),
    "interested": (
        "Great! I've noted your interest, and a loan specialist will call you with the details. Approval depends on the bank's assessment after you apply.",
        "Bahut achha! Maine aapki interest note kar li hai, ek loan specialist aapko details ke saath call karenge. Approval apply karne ke baad bank ke assessment par depend karega.",
    ),
}


def outcome_reply(outcome: str, language: str) -> str:
    en, hi = _OUTCOME_REPLIES.get(outcome, _OUTCOME_REPLIES["not_interested"])
    return hi if language == "hi" else en
