"use client";

export type OrbState = "idle" | "connecting" | "listening" | "thinking" | "speaking";

const STATE_STYLES: Record<OrbState, string> = {
  idle: "from-indigo-500 to-blue-600 scale-100",
  connecting: "from-slate-500 to-slate-700 scale-95 animate-pulse",
  listening: "from-emerald-400 to-teal-600 scale-105",
  thinking: "from-amber-400 to-orange-600 scale-100 animate-pulse",
  speaking: "from-fuchsia-500 to-purple-700 scale-110",
};

export default function VoiceOrb({ state, size = 140 }: { state: OrbState; size?: number }) {
  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      {(state === "listening" || state === "speaking") && (
        <span
          className={`absolute inset-0 rounded-full bg-gradient-to-br ${STATE_STYLES[state]} opacity-40 animate-ping`}
        />
      )}
      <div
        className={`relative rounded-full bg-gradient-to-br ${STATE_STYLES[state]} shadow-2xl transition-all duration-300 ease-out flex items-center justify-center`}
        style={{ width: size, height: size }}
      >
        <MicIcon />
      </div>
    </div>
  );
}

function MicIcon() {
  return (
    <svg width="42" height="42" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Z"
        stroke="white"
        strokeWidth="1.6"
      />
      <path
        d="M19 11a7 7 0 0 1-14 0M12 18v3"
        stroke="white"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}
