"use client";

import { memo } from "react";
import { useChatStore, type Mode } from "@/store/useChatStore";

const PROMPTS: Record<Mode, { en: string[]; lg: string[] }> = {
  vht: {
    en: [
      "A child has fever and fast breathing — how do I classify?",
      "What is the ORS + Zinc dosage for a 2-year-old with diarrhoea?",
      "When should I refer a child with malaria to the health centre?",
      "How do I use an RDT to test for malaria?",
    ],
    lg: [
      "Omwana alina omusujja n'okussa mangu — nkola ntya?",
      "ORS ne Zinc zibawa zzitya omwana ow'emyaka 2 alina ekiddukaano?",
      "Omwana alina malaria — ddi lw'amutumira mu ddwaliro?",
      "Nkozesa ntya RDT okukebera malaria?",
    ],
  },
  maternal: {
    en: [
      "I'm 28 weeks pregnant — what danger signs should I watch for?",
      "How do I prepare a birth plan?",
      "My baby isn't breastfeeding well — what should I do?",
      "What immunizations does my newborn need?",
    ],
    lg: [
      "Ndi mu lubuto lwa wiiki 28 — bubonero ki bye ndeekeka?",
      "Ntegeka ntya enteekateeka y'okuzaala?",
      "Omwana wange tayonsa bulungi — nkola ntya?",
      "Omwana omutto yeetaaga zimpi?",
    ],
  },
  community: {
    en: [
      "I have a headache and fever — what should I do?",
      "How can I prevent malaria at home?",
      "What are the symptoms of diabetes?",
      "Where is the nearest health centre to me?",
    ],
    lg: [
      "Nfudde omutwe era nnina omusujja — nkola ki?",
      "Nziyiza ntya malaria mu maka?",
      "Bubonero ki ebw'obulwadde bwa sukaari?",
      "Eddwaliro erisinga okuba okumpi liri wa?",
    ],
  },
};

export default memo(function StarterPrompts() {
  const mode = useChatStore((s) => s.mode);
  const locale = useChatStore((s) => s.locale);
  const setMessage = useChatStore((s) => s.setMessage);
  const chat = useChatStore((s) => s.chat);

  if (chat.length > 0) return null;

  const lang = locale === "lg" ? "lg" : "en";
  const prompts = PROMPTS[mode]?.[lang] || PROMPTS.community.en;

  return (
    <div className="starter-prompts">
      <p className="starter-label">
        {lang === "lg" ? "Tandika wano:" : "Quick start:"}
      </p>
      <div className="starter-grid">
        {prompts.map((prompt, i) => (
          <button
            key={i}
            className="chip"
            onClick={() => setMessage(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
});
