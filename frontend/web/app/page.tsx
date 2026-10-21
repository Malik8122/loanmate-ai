"use client";

import { useCallback, useState } from "react";
import Home from "./components/Home";
import { OutboundCalling, IncomingCall } from "./components/OutboundFlow";
import ActiveCall from "./components/ActiveCall";
import {
  API_BASE,
  fetchRealtimeToken,
  newSessionId,
  Customer,
  TokenResponse,
  CallMode,
  OutboundReason,
} from "./lib/api";
import { Language } from "./components/LanguagePills";

type Screen =
  | { name: "home" }
  | { name: "outbound-calling"; language: Language; reason: OutboundReason; customer: Customer }
  | { name: "incoming-call"; language: Language; reason: OutboundReason; customer: Customer }
  | { name: "connecting" }
  | { name: "active-call"; token: TokenResponse }
  | { name: "ended" };

export default function Page() {
  const [screen, setScreen] = useState<Screen>({ name: "home" });
  const [error, setError] = useState<string | null>(null);

  const startCall = useCallback(
    async (mode: CallMode, language: Language, customer: Customer, reason?: OutboundReason) => {
      setError(null);
      setScreen({ name: "connecting" });
      try {
        const token = await fetchRealtimeToken(newSessionId(), mode, language, customer.customer_id, reason);
        setScreen({ name: "active-call", token });
      } catch (err) {
        console.error(err);
        const detail = err instanceof Error ? err.message : String(err);
        setError(`Couldn't start the call (${detail}). Check the backend is running at ${API_BASE}.`);
        setScreen({ name: "home" });
      }
    },
    [],
  );

  const endCall = useCallback(() => {
    setScreen({ name: "ended" });
  }, []);

  return (
    <div className="flex-1 flex flex-col">
      {screen.name === "home" && error && (
        <div
          role="alert"
          className="mx-auto mt-6 max-w-md rounded-xl border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200"
        >
          {error}
        </div>
      )}

      {screen.name === "home" && (
        <Home
          onCallLoanMate={(language, customer) => startCall("inbound", language, customer)}
          onBankIsCallingYou={(language, reason, customer) =>
            setScreen({ name: "outbound-calling", language, reason, customer })
          }
        />
      )}

      {screen.name === "outbound-calling" && (
        <OutboundCalling
          onReady={() =>
            setScreen({
              name: "incoming-call",
              language: screen.language,
              reason: screen.reason,
              customer: screen.customer,
            })
          }
        />
      )}

      {screen.name === "incoming-call" && (
        <IncomingCall
          customerName={screen.customer.name}
          onAccept={() => startCall("outbound", screen.language, screen.customer, screen.reason)}
          onDecline={() => setScreen({ name: "home" })}
        />
      )}

      {screen.name === "connecting" && (
        <div className="flex-1 flex items-center justify-center text-white/60">Connecting…</div>
      )}

      {screen.name === "active-call" && (
        <ActiveCall
          serverUrl={screen.token.url}
          token={screen.token.token}
          onEndCall={endCall}
        />
      )}

      {screen.name === "ended" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-6 text-center">
          <p className="text-white/70 text-lg">Call ended</p>
          <button
            onClick={() => setScreen({ name: "home" })}
            className="rounded-2xl bg-white text-black font-medium px-6 py-3"
          >
            Back to Home
          </button>
        </div>
      )}
    </div>
  );
}
