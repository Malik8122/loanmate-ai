"use client";

import { useCallback, useState } from "react";
import Home from "./components/Home";
import { OutboundCalling, IncomingCall } from "./components/OutboundFlow";
import ActiveCall from "./components/ActiveCall";
import { fetchRealtimeToken, newSessionId, TokenResponse, CallMode, OutboundReason } from "./lib/api";
import { Language } from "./components/LanguagePills";

type Screen =
  | { name: "home" }
  | { name: "outbound-calling"; language: Language; reason: OutboundReason }
  | { name: "incoming-call"; language: Language; reason: OutboundReason }
  | { name: "connecting" }
  | { name: "active-call"; token: TokenResponse }
  | { name: "ended" };

export default function Page() {
  const [screen, setScreen] = useState<Screen>({ name: "home" });

  const startCall = useCallback(
    async (mode: CallMode, language: Language, reason?: OutboundReason) => {
      setScreen({ name: "connecting" });
      try {
        const token = await fetchRealtimeToken(newSessionId(), mode, language, reason);
        setScreen({ name: "active-call", token });
      } catch (err) {
        console.error(err);
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
      {screen.name === "home" && (
        <Home
          onCallLoanMate={(language) => startCall("inbound", language)}
          onBankIsCallingYou={(language, reason) =>
            setScreen({ name: "outbound-calling", language, reason })
          }
        />
      )}

      {screen.name === "outbound-calling" && (
        <OutboundCalling
          onReady={() =>
            setScreen({ name: "incoming-call", language: screen.language, reason: screen.reason })
          }
        />
      )}

      {screen.name === "incoming-call" && (
        <IncomingCall
          onAccept={() => startCall("outbound", screen.language, screen.reason)}
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
