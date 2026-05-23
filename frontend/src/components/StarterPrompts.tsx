"use client";

import { memo } from "react";
import { useChatStore, type Mode } from "@/store/useChatStore";

const PROMPTS: Record<Mode, Record<string, string[]>> = {
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
    nyn: [
      "Omwana aine omushuija n'okuhuuha bwangu — nkore nta?",
      "ORS na Zinc bizibwa zita omwana ow'emyaka 2 aine okushaarira?",
      "Omwana aine malaria — nikki mba nimutuma omu'irwariro?",
      "Nkozesa nta RDT okukebera malaria?",
    ],
    sw: [
      "Mtoto ana homa na kupumua haraka — niainishije vipi?",
      "ORS na Zinc kwa mtoto wa miaka 2 mwenye kuharisha ni kiasi gani?",
      "Mtoto ana malaria — ni lini nimpeleke hospitali?",
      "Nitumie vipi RDT kupima malaria?",
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
    nyn: [
      "Ndi mu nda ya wiiki 28 — bubonero ki ebindi kureeba?",
      "Ntegeka nta enteganyarizo y'okuzaara?",
      "Omwana wangye tiyonka kyangu — nkore ki?",
      "Omwana omuhya ayetaaga kuzipimwa ki?",
    ],
    sw: [
      "Nina mimba ya wiki 28 — dalili gani za hatari niangalie?",
      "Nipangeje vipi mpango wa kuzaa?",
      "Mtoto wangu hanyonyi vizuri — nifanye nini?",
      "Mtoto wangu mchanga anahitaji chanjo gani?",
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
    nyn: [
      "Ninumire omutwe era ninaine omushuija — nkore ki?",
      "Nkingira nta malaria omu maka?",
      "Bubonero ki bw'obulwaire bwa sukaari?",
      "Irwariro erisinga okuba hakuuhi riri hahi?",
    ],
    sw: [
      "Nina maumivu ya kichwa na homa — nifanye nini?",
      "Ninazuiaje malaria nyumbani?",
      "Dalili za kisukari ni zipi?",
      "Hospitali ya karibu iko wapi?",
    ],
  },
};

export default memo(function StarterPrompts() {
  const mode = useChatStore((s) => s.mode);
  const locale = useChatStore((s) => s.locale);
  const setMessage = useChatStore((s) => s.setMessage);
  const chat = useChatStore((s) => s.chat);

  if (chat.length > 0) return null;

  const prompts = PROMPTS[mode]?.[locale] || PROMPTS[mode]?.en || PROMPTS.community.en;

  const LABEL: Record<string, string> = {
    en: "Quick start:",
    lg: "Tandika wano:",
    nyn: "Tandiika hanu:",
    sw: "Anza hapa:",
  };

  return (
    <div className="starter-prompts">
      <p className="starter-label">{LABEL[locale] || LABEL.en}</p>
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
