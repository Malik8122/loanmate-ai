"use client";

import { useEffect, useState } from "react";
import VoiceOrb from "./VoiceOrb";

export function OutboundCalling({ onReady }: { onReady: () => void }) {
  useEffect(() => {
    const t = setTimeout(onReady, 1300);
    return () => clearTimeout(t);
  }, [onReady]);

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 px-6 text-center">
      <VoiceOrb state="connecting" size={140} />
      <p className="text-white/70 text-lg">LoanMate is calling...</p>
    </div>
  );
}

export function IncomingCall({
  customerName,
  onAccept,
  onDecline,
}: {
  customerName: string;
  onAccept: () => void;
  onDecline: () => void;
}) {
  const [ringing, setRinging] = useState(true);
  useEffect(() => {
    const t = setInterval(() => setRinging((r) => !r), 700);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-8 px-6 text-center">
      <p className="text-white/50 text-sm uppercase tracking-widest">Incoming Call</p>
      <VoiceOrb state={ringing ? "listening" : "idle"} size={150} />
      <div>
        <p className="text-2xl font-semibold">LoanMate</p>
        <p className="text-white/60 text-sm">AI Loan Assistant · calling {customerName}</p>
      </div>
      <div className="flex gap-4 w-full max-w-xs">
        <button
          onClick={onDecline}
          className="flex-1 rounded-2xl bg-red-500/90 hover:bg-red-500 text-white font-medium py-3.5 transition-colors"
        >
          Decline
        </button>
        <button
          onClick={onAccept}
          className="flex-1 rounded-2xl bg-emerald-500/90 hover:bg-emerald-500 text-white font-medium py-3.5 transition-colors"
        >
          Accept
        </button>
      </div>
    </div>
  );
}
