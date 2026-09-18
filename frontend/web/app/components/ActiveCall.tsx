"use client";

import { useMemo } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
  useLocalParticipant,
  useTranscriptions,
} from "@livekit/components-react";
import VoiceOrb, { OrbState } from "./VoiceOrb";

const AGENT_STATE_TO_ORB: Record<string, OrbState> = {
  connecting: "connecting",
  "pre-connect-buffering": "connecting",
  initializing: "connecting",
  idle: "listening",
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
  disconnected: "connecting",
  failed: "connecting",
};

const AGENT_STATE_LABEL: Record<string, string> = {
  connecting: "Connecting…",
  "pre-connect-buffering": "Connecting…",
  initializing: "Connecting…",
  idle: "Listening…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  disconnected: "Reconnecting…",
  failed: "Connection issue",
};

export default function ActiveCall({
  serverUrl,
  token,
  onEndCall,
}: {
  serverUrl: string;
  token: string;
  onEndCall: () => void;
}) {
  return (
    <LiveKitRoom
      serverUrl={serverUrl}
      token={token}
      audio
      connect
      onDisconnected={onEndCall}
      className="flex-1 flex flex-col"
    >
      <RoomAudioRenderer />
      <CallUI onEndCall={onEndCall} />
    </LiveKitRoom>
  );
}

function CallUI({ onEndCall }: { onEndCall: () => void }) {
  const { state } = useVoiceAssistant();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const rawTranscriptions = useTranscriptions();

  const transcript = useMemo(() => {
    return [...rawTranscriptions]
      .sort((a, b) => (a.streamInfo.timestamp ?? 0) - (b.streamInfo.timestamp ?? 0))
      .slice(-6);
  }, [rawTranscriptions]);

  const orbState = AGENT_STATE_TO_ORB[state] ?? "connecting";
  const label = AGENT_STATE_LABEL[state] ?? "Connecting…";
  const connected = state !== "connecting" && state !== "disconnected" && state !== "failed";

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-8 px-6 text-center">
      {connected && (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 text-emerald-400 text-xs font-medium px-3 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          Connected
        </span>
      )}

      <VoiceOrb state={orbState} size={150} />
      <p className="text-white/70 text-lg">{label}</p>

      {transcript.length > 0 && (
        <div className="w-full max-w-sm text-left space-y-1.5 max-h-32 overflow-y-auto text-sm text-white/50">
          {transcript.map((seg) => (
            <p key={seg.streamInfo.id} className="truncate">
              {seg.participantInfo.identity?.startsWith("agent-") ? "LoanMate: " : "You: "}
              {seg.text}
            </p>
          ))}
        </div>
      )}

      <div className="flex gap-4 items-center">
        <button
          onClick={() => localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
          className="rounded-full bg-white/10 border border-white/15 hover:bg-white/15 transition-colors px-5 py-3 text-sm font-medium"
        >
          {isMicrophoneEnabled ? "🎤 Mute" : "🔇 Unmute"}
        </button>
        <button
          onClick={onEndCall}
          className="rounded-full bg-red-500/90 hover:bg-red-500 transition-colors px-6 py-3 text-sm font-medium"
        >
          ⏹ End Call
        </button>
      </div>
    </div>
  );
}
