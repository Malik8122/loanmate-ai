"use client";

export type Language = "english" | "hindi" | "hinglish";

const OPTIONS: { value: Language; label: string }[] = [
  { value: "english", label: "English" },
  { value: "hindi", label: "हिन्दी" },
  { value: "hinglish", label: "Hinglish" },
];

export default function LanguagePills({
  value,
  onChange,
}: {
  value: Language;
  onChange: (v: Language) => void;
}) {
  return (
    <div className="flex gap-2">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors border ${
            value === opt.value
              ? "bg-white text-black border-white"
              : "bg-white/5 text-white/70 border-white/15 hover:bg-white/10"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
