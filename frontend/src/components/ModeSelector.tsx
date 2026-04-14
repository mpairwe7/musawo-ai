"use client";

import { memo, useTransition } from "react";
import { useChatStore, type Mode } from "@/store/useChatStore";
import { StethoscopeIcon, BabyIcon, HeartIcon } from "./Icons";

const MODES: {
  id: Mode;
  label: string;
  label_lg: string;
  icon: typeof HeartIcon;
  color: string;
  description: string;
}[] = [
  {
    id: "vht",
    label: "VHT Triage",
    label_lg: "Okulambula VHT",
    icon: StethoscopeIcon,
    color: "#E74C3C",
    description: "Symptom assessment & iCCM protocols for VHTs",
  },
  {
    id: "maternal",
    label: "Maternal Care",
    label_lg: "Obujjanjabi bw'Abakyala",
    icon: BabyIcon,
    color: "#E91E63",
    description: "Pregnancy, birth & newborn guidance",
  },
  {
    id: "community",
    label: "Community Health",
    label_lg: "Obulamu bw'Ekitundu",
    icon: HeartIcon,
    color: "#2E7D32",
    description: "General health, medications & clinic finder",
  },
];

export default memo(function ModeSelector() {
  const mode = useChatStore((s) => s.mode);
  const setMode = useChatStore((s) => s.setMode);
  const locale = useChatStore((s) => s.locale);
  const [, startTransition] = useTransition();

  return (
    <div className="mode-selector" role="radiogroup" aria-label="Health mode">
      {MODES.map((m) => {
        const Icon = m.icon;
        const isActive = mode === m.id;
        return (
          <button
            key={m.id}
            role="radio"
            aria-checked={isActive}
            className={`mode-card ${isActive ? "active" : ""}`}
            style={{ "--mode-color": m.color } as React.CSSProperties}
            onClick={() => startTransition(() => setMode(m.id))}
          >
            <Icon width={24} height={24} />
            <span className="mode-label">
              {locale === "lg" ? m.label_lg : m.label}
            </span>
            <span className="mode-desc">{m.description}</span>
          </button>
        );
      })}
    </div>
  );
});
