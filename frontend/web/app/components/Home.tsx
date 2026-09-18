"use client";

import { useState } from "react";
import VoiceOrb from "./VoiceOrb";
import LanguagePills, { Language } from "./LanguagePills";
import { OutboundReason } from "../lib/api";

const OUTBOUND_REASONS: { value: OutboundReason; label: string }[] = [
  { value: "emi_reminder", label: "EMI Reminder" },
  { value: "product_update", label: "Product Update" },
];

export default function Home({
  onCallLoanMate,
  onBankIsCallingYou,
}: {
  onCallLoanMate: (language: Language) => void;
  onBankIsCallingYou: (language: Language, reason: OutboundReason) => void;
}) {
  const [language, setLanguage] = useState<Language>("english");
  const [outboundReason, setOutboundReason] = useState<OutboundReason>("emi_reminder");

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-10 px-6 text-center">
      <div className="space-y-2">
        <h1 className="text-4xl font-semibold tracking-tight">LoanMate</h1>
        <p className="text-white/60 text-sm">Your Conversational Loan Assistant</p>
      </div>

      <VoiceOrb state="idle" size={160} />

      <div className="flex flex-col gap-3 w-full max-w-xs">
        <button
          onClick={() => onCallLoanMate(language)}
          className="rounded-2xl bg-white text-black font-medium py-3.5 hover:bg-white/90 transition-colors"
        >
          🎙 Call LoanMate
        </button>
        <button
          onClick={() => onBankIsCallingYou(language, outboundReason)}
          className="rounded-2xl bg-white/10 border border-white/15 text-white font-medium py-3.5 hover:bg-white/15 transition-colors"
        >
          📞 Bank is Calling You
        </button>

        <div className="flex justify-center gap-2 pt-1">
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
