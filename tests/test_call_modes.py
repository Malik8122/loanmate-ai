"""
Inbound and outbound calls have different purposes:

- inbound  — customer-initiated service call: raises service requests.
- outbound — bank-initiated campaign call: confirms the right person,
  states one purpose, and records a call outcome.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.agents.orchestrator import AgentOrchestrator
from backend.main import app
from backend.services import call_records
from backend.services.llm_service import LLMService
from backend.services.loan_service import LoanService
from backend.voice_agent.call_context import build_call_context, suggest_outbound_reason
from backend.voice_agent.prompts import (
    build_inbound_instructions,
    build_outbound_instructions,
    build_system_instructions,
)


@pytest.fixture(autouse=True)
def _isolated_records(tmp_path, monkeypatch):
    monkeypatch.setattr(call_records, "RECORDS_PATH", tmp_path / "call_records.jsonl")


def _ctx(customer_id, mode, reason=None):
    return build_call_context(customer_id, LoanService.get_customer_with_loans(customer_id), mode, reason, "english")


def _handle(orch, text, customer_id, mode, reason=None, session_id="s1"):
    return asyncio.run(orch.handle(
        text=text,
        customer_context=LoanService.get_customer_with_loans(customer_id),
        language="en",
        session_id=session_id,
        call_mode=mode,
        outbound_reason=reason,
    ))


# ── Call context ───────────────────────────────────────────────────────
@pytest.mark.parametrize("customer_id,expected", [
    ("CUST005", "overdue_followup"),  # has an overdue business loan
    ("CUST004", "kyc_update"),        # KYC not verified
    ("CUST001", "emi_reminder"),      # active loans, nothing pending
])
def test_auto_outbound_reason_follows_account_state(customer_id, expected):
    assert suggest_outbound_reason(LoanService.get_customer_with_loans(customer_id)) == expected
    assert _ctx(customer_id, "outbound", "auto").outbound_reason == expected


def test_overdue_followup_is_about_the_overdue_loan():
    ctx = _ctx("CUST005", "outbound", "overdue_followup")
    assert ctx.loan_type == "Business Loan"


def test_inbound_has_no_outbound_reason():
    assert _ctx("CUST001", "inbound", "emi_reminder").outbound_reason is None


# ── Prompts ───────────────────────────────────────────────────────────
def test_inbound_and_outbound_prompts_have_different_purposes():
    inbound = build_system_instructions(_ctx("CUST001", "inbound"))
    outbound = build_system_instructions(_ctx("CUST001", "outbound", "emi_reminder"))

    assert "INBOUND SERVICE CALL" in inbound
    assert "raise_service_request" in inbound
    assert "record_call_outcome" not in inbound

    assert "OUTBOUND CALL — EMI REMINDER" in outbound
    assert "RIGHT PERSON FIRST" in outbound
    assert "record_call_outcome" in outbound
    assert "raise_service_request" not in outbound


def test_each_outbound_reason_has_its_own_goal_and_opener():
    goals = set()
    for reason in ["emi_reminder", "overdue_followup", "kyc_update", "product_update"]:
        ctx = _ctx("CUST001", "outbound", reason)
        goals.add(build_system_instructions(ctx))
        assert "Rajesh Kumar" in build_outbound_instructions(ctx)
    assert len(goals) == 4


@pytest.mark.parametrize("mode,reason", [("inbound", None), ("outbound", "emi_reminder")])
def test_chosen_language_is_enforced_for_the_whole_call(mode, reason):
    record = LoanService.get_customer_with_loans("CUST001")
    ctx = build_call_context("CUST001", record, mode, reason, "hindi")
    assert "LANGUAGE CHOSEN FOR THIS CALL: Hindi" in build_system_instructions(ctx)
    assert "WHOLE call" in build_system_instructions(ctx)
    opener = build_outbound_instructions(ctx) if mode == "outbound" else build_inbound_instructions(ctx)
    assert "entirely in natural spoken Hindi" in opener

    english = build_call_context("CUST001", record, mode, reason, "english")
    assert "LANGUAGE CHOSEN FOR THIS CALL: English" in build_system_instructions(english)


def test_overdue_prompt_forbids_threats():
    prompt = build_system_instructions(_ctx("CUST005", "outbound", "overdue_followup"))
    assert "never threaten" in prompt


# ── Outbound flow (legacy orchestrator) ───────────────────────────────
def test_outbound_emi_reminder_flow_records_promise_to_pay():
    orch = AgentOrchestrator(LLMService())
    customer = LoanService.get_customer_with_loans("CUST001")
    opener = orch.start_outbound("s1", "emi_reminder", customer, "en")
    assert "Rajesh Kumar" in opener and "₹" not in opener  # no account detail before identity check

    purpose = _handle(orch, "Yes, speaking", "CUST001", "outbound", "emi_reminder")
    assert "31,500" in purpose["reply"] and "2026-09-05" in purpose["reply"]

    done = _handle(orch, "I will pay on the 10th after my salary", "CUST001", "outbound", "emi_reminder")
    assert done["tool_used"] == "record_call_outcome"

    [record] = call_records.list_records(kind="call_outcome")
    assert record["outcome"] == "promise_to_pay"
    assert record["outbound_reason"] == "emi_reminder"


def test_outbound_wrong_person_discloses_nothing():
    orch = AgentOrchestrator(LLMService())
    orch.start_outbound("s1", "overdue_followup", LoanService.get_customer_with_loans("CUST005"), "en")
    result = _handle(orch, "No, wrong number", "CUST005", "outbound", "overdue_followup")
    assert "overdue" not in result["reply"].lower() and "₹" not in result["reply"]
    assert call_records.list_records()[0]["outcome"] == "wrong_person"


def test_outbound_busy_records_callback():
    orch = AgentOrchestrator(LLMService())
    orch.start_outbound("s1", "product_update", LoanService.get_customer_with_loans("CUST002"), "en")
    _handle(orch, "I'm busy right now, call me later", "CUST002", "outbound", "product_update")
    assert call_records.list_records()[0]["outcome"] == "callback_requested"


def test_invalid_outcome_for_campaign_is_rejected():
    with pytest.raises(ValueError):
        call_records.record_call_outcome("CUST001", "kyc_update", "promise_to_pay")


# ── Inbound flow (legacy orchestrator) ────────────────────────────────
def test_inbound_service_request_gets_reference_number():
    orch = AgentOrchestrator(LLMService())
    result = _handle(orch, "I need a no dues certificate for my loan", "CUST001", "inbound")
    assert result["tool_used"] == "raise_service_request"
    [record] = call_records.list_records(kind="service_request")
    assert record["request_type"] == "no_dues_certificate"
    assert " ".join(record["reference"]) in result["reply"]


def test_inbound_does_not_pitch_or_remind():
    orch = AgentOrchestrator(LLMService())
    result = _handle(orch, "What is my EMI?", "CUST001", "inbound")
    assert result["tool_used"] == "get_emi"
    assert call_records.list_records() == []


def test_text_chat_without_call_mode_is_unchanged():
    orch = AgentOrchestrator(LLMService())
    result = _handle(orch, "I need a no dues certificate", "CUST001", None)
    assert result["tool_used"] != "raise_service_request"
    assert call_records.list_records() == []


# ── API ───────────────────────────────────────────────────────────────
def test_calls_purposes_endpoint():
    data = TestClient(app).get("/api/calls/purposes").json()
    assert set(data["outbound"]["reasons"]) == {"emi_reminder", "overdue_followup", "kyc_update", "product_update"}
    assert "no_dues_certificate" in data["inbound"]["service_request_types"]
