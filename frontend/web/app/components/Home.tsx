"use client";

import { useEffect, useState } from "react";
import VoiceOrb from "./VoiceOrb";
import LanguagePills, { Language } from "./LanguagePills";
import { Customer, OutboundReason, fetchCustomers } from "../lib/api";

const OUTBOUND_REASONS: { value: OutboundReason; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "emi_reminder", label: "EMI Reminder" },
  { value: "overdue_followup", label: "Overdue" },
  { value: "kyc_update", label: "KYC Update" },
  { value: "product_update", label: "Top-up Offer" },
];

// Shown until the customer list loads (or if the backend can't be reached).
const FALLBACK_CUSTOMERS: Customer[] = [{ customer_id: "CUST001", name: "Rajesh Kumar" }];

export default function Home({
  onCallLoanMate,
  onBankIsCallingYou,
}: {
  onCallLoanMate: (language: Language, customer: Customer) => void;
  onBankIsCallingYou: (language: Language, reason: OutboundReason, customer: Customer) => void;
}) {
  const [language, setLanguage] = useState<Language>("english");
  const [outboundReason, setOutboundReason] = useState<OutboundReason>("auto");
  const [customers, setCustomers] = useState<Customer[]>(FALLBACK_CUSTOMERS);
  const [customerId, setCustomerId] = useState("CUST001");

  useEffect(() => {
    fetchCustomers()
      .then(setCustomers)
      .catch((err) => console.error(err));
  }, []);

  const customer = customers.find((c) => c.customer_id === customerId) ?? customers[0];

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-10 px-6 text-center">
      <div className="space-y-2">
        <h1 className="text-4xl font-semibold tracking-tight">LoanMate</h1>
        <p className="text-white/60 text-sm">Your Conversational Loan Assistant</p>
      </div>

      <VoiceOrb state="idle" size={160} />

      <div className="flex flex-col gap-3 w-full max-w-xs">
        <label className="flex flex-col gap-1.5 text-left">
          <span className="text-xs font-medium uppercase tracking-wider text-white/50">Customer</span>
          <select
            value={customer.customer_id}
            onChange={(e) => setCustomerId(e.target.value)}
            className="rounded-xl bg-white/10 border border-white/15 text-white px-3 py-2.5 text-sm focus:outline-none focus:border-white/40"
          >
            {customers.map((c) => (
              <option key={c.customer_id} value={c.customer_id} className="bg-neutral-900">
                {c.name} ({c.customer_id})
              </option>
            ))}
          </select>
        </label>

        <button
          onClick={() => onCallLoanMate(language, customer)}
          className="rounded-2xl bg-white text-black font-medium py-3.5 hover:bg-white/90 transition-colors"
        >
          🎙 Call LoanMate
        </button>
        <button
          onClick={() => onBankIsCallingYou(language, outboundReason, customer)}
          className="rounded-2xl bg-white/10 border border-white/15 text-white font-medium py-3.5 hover:bg-white/15 transition-colors"
        >
          📞 Bank is Calling You
        </button>

        <div className="flex flex-wrap justify-center gap-2 pt-1">
          {OUTBOUND_REASONS.map((r) => (
            <button
              key={r.value}
              onClick={() => setOutboundReason(r.value)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                outboundReason === r.value
                  ? "bg-white/90 text-black border-white/90"
                  : "bg-transparent text-white/40 border-white/10 hover:text-white/70"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <LanguagePills value={language} onChange={setLanguage} />
    </div>
  );
}
