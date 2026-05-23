"use client";

/**
 * HealthDiagrams — Inline SVG health illustrations for Musawo AI.
 *
 * Works fully offline (no external images). Each diagram is a self-contained
 * React component that renders clinical illustrations suitable for VHTs,
 * mothers, and community health workers in rural Uganda.
 *
 * Usage in markdown responses: ::diagram[key]
 * Usage in React: <HealthDiagram diagramKey="danger_signs" />
 */

import { memo, type SVGProps } from "react";

// ── Diagram registry ────────────────────────────────────────────────────

export interface DiagramMeta {
  title: string;
  caption?: string;
  variant?: "default" | "danger" | "maternal";
}

export const DIAGRAM_REGISTRY: Record<string, DiagramMeta> = {
  danger_signs: {
    title: "Danger Signs in Children",
    caption: "If you see ANY of these signs, REFER the child IMMEDIATELY.",
    variant: "danger",
  },
  ors_preparation: {
    title: "How to Prepare ORS",
    caption: "Mix 1 sachet with 1 litre of clean water. Give small sips frequently.",
  },
  handwashing: {
    title: "Proper Handwashing Steps",
    caption: "Wash hands with soap for at least 20 seconds at all 5 critical times.",
  },
  breathing_count: {
    title: "Counting Breathing Rate",
    caption: "Count breaths for ONE FULL MINUTE while the child is calm.",
  },
  breastfeeding: {
    title: "Correct Breastfeeding Position",
    caption: "Baby's body faces mother, mouth covers the full areola, chin touches breast.",
    variant: "maternal",
  },
  malaria_rdt: {
    title: "How to Use an RDT",
    caption: "Rapid Diagnostic Test for malaria. Follow these steps carefully.",
  },
  fever_assessment: {
    title: "Fever Assessment",
    caption: "Check temperature and look for danger signs. Treat or refer based on severity.",
    variant: "danger",
  },
  immunization_schedule: {
    title: "Uganda Immunization Schedule",
    caption: "Vaccines given at birth, 6, 10, 14 weeks, and 9 months.",
  },
  dehydration_check: {
    title: "Checking for Dehydration",
    caption: "Look at the eyes, check skin pinch, and observe if the child can drink.",
    variant: "danger",
  },
  birth_preparedness: {
    title: "Birth Preparedness Plan",
    caption: "Every pregnant woman should prepare before 36 weeks.",
    variant: "maternal",
  },
};

// ── SVG Illustrations ───────────────────────────────────────────────────

function DangerSignsSVG(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 320 180" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      {/* Background */}
      <rect width="320" height="180" rx="12" fill="#1a0f0a" fillOpacity="0.3" />

      {/* Grid of 4 danger sign icons */}
      {/* Convulsions */}
      <g transform="translate(30, 20)">
        <circle cx="30" cy="30" r="26" fill="#E74C3C" fillOpacity="0.15" stroke="#E74C3C" strokeWidth="2" />
        <path d="M20 30 L25 22 L30 35 L35 18 L40 30" stroke="#E74C3C" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        <text x="30" y="72" textAnchor="middle" fill="#c4a882" fontSize="9" fontWeight="600">Convulsions</text>
      </g>

      {/* Not drinking */}
      <g transform="translate(110, 20)">
        <circle cx="30" cy="30" r="26" fill="#E74C3C" fillOpacity="0.15" stroke="#E74C3C" strokeWidth="2" />
        <path d="M22 24 C22 24 25 38 30 38 C35 38 38 24 38 24" stroke="#E74C3C" strokeWidth="2" fill="none" />
        <line x1="20" y1="20" x2="40" y2="40" stroke="#E74C3C" strokeWidth="2.5" strokeLinecap="round" />
        <text x="30" y="72" textAnchor="middle" fill="#c4a882" fontSize="9" fontWeight="600">Can&apos;t Drink</text>
      </g>

      {/* Vomiting everything */}
      <g transform="translate(190, 20)">
        <circle cx="30" cy="30" r="26" fill="#E74C3C" fillOpacity="0.15" stroke="#E74C3C" strokeWidth="2" />
        <circle cx="30" cy="26" r="8" stroke="#E74C3C" strokeWidth="2" fill="none" />
        <path d="M24 36 L20 44 M30 36 L30 44 M36 36 L40 44" stroke="#E74C3C" strokeWidth="1.5" strokeLinecap="round" />
        <text x="30" y="72" textAnchor="middle" fill="#c4a882" fontSize="9" fontWeight="600">Vomits All</text>
      </g>

      {/* Unconscious/lethargic */}
      <g transform="translate(30, 90)">
        <circle cx="30" cy="30" r="26" fill="#E74C3C" fillOpacity="0.15" stroke="#E74C3C" strokeWidth="2" />
        <circle cx="30" cy="26" r="8" stroke="#E74C3C" strokeWidth="2" fill="none" />
        <path d="M24 24 L28 24 M32 24 L36 24" stroke="#E74C3C" strokeWidth="1.5" strokeLinecap="round" />
        <text x="30" y="72" textAnchor="middle" fill="#c4a882" fontSize="9" fontWeight="600">Unconscious</text>
      </g>

      {/* Chest indrawing */}
      <g transform="translate(110, 90)">
        <circle cx="30" cy="30" r="26" fill="#E74C3C" fillOpacity="0.15" stroke="#E74C3C" strokeWidth="2" />
        <path d="M20 28 Q25 22 30 28 Q35 22 40 28 M20 34 Q25 28 30 34 Q35 28 40 34" stroke="#E74C3C" strokeWidth="1.5" fill="none" />
        <path d="M30 20 L30 40" stroke="#E74C3C" strokeWidth="1.5" strokeDasharray="3 2" />
        <text x="30" y="72" textAnchor="middle" fill="#c4a882" fontSize="9" fontWeight="600">Chest Indraw</text>
      </g>

      {/* High fever */}
      <g transform="translate(190, 90)">
        <circle cx="30" cy="30" r="26" fill="#E74C3C" fillOpacity="0.15" stroke="#E74C3C" strokeWidth="2" />
        <rect x="27" y="18" width="6" height="24" rx="3" stroke="#E74C3C" strokeWidth="1.5" fill="none" />
        <rect x="28.5" y="28" width="3" height="12" rx="1.5" fill="#E74C3C" />
        <circle cx="30" cy="40" r="2" fill="#E74C3C" />
        <text x="30" y="72" textAnchor="middle" fill="#c4a882" fontSize="9" fontWeight="600">High Fever</text>
      </g>

      {/* REFER label */}
      <rect x="240" y="95" width="70" height="24" rx="6" fill="#E74C3C" />
      <text x="275" y="111" textAnchor="middle" fill="white" fontSize="10" fontWeight="800">REFER NOW</text>
    </svg>
  );
}

function ORSPreparationSVG(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 320 140" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      <rect width="320" height="140" rx="12" fill="#1a0f0a" fillOpacity="0.3" />

      {/* Step 1: Sachet */}
      <g transform="translate(20, 25)">
        <rect x="10" y="10" width="40" height="55" rx="4" stroke="#43A047" strokeWidth="2" fill="rgba(67,160,71,0.1)" />
        <text x="30" y="42" textAnchor="middle" fill="#43A047" fontSize="8" fontWeight="700">ORS</text>
        <path d="M30 65 L30 75" stroke="#43A047" strokeWidth="1.5" strokeDasharray="3 2" />
        <text x="30" y="90" textAnchor="middle" fill="#c4a882" fontSize="8">1 sachet</text>
      </g>

      {/* Arrow */}
      <path d="M80 50 L100 50" stroke="#D4A843" strokeWidth="2" markerEnd="url(#arrowG)" />
      <defs><marker id="arrowG" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#D4A843" /></marker></defs>

      {/* Step 2: 1 Litre water */}
      <g transform="translate(105, 15)">
        <path d="M10 20 L10 75 Q10 80 15 80 L45 80 Q50 80 50 75 L50 20 Z" stroke="#1976D2" strokeWidth="2" fill="rgba(25,118,210,0.08)" />
        <path d="M15 40 Q30 35 45 40" stroke="#1976D2" strokeWidth="1" fill="none" />
        <text x="30" y="60" textAnchor="middle" fill="#1976D2" fontSize="8" fontWeight="700">1 L</text>
        <text x="30" y="100" textAnchor="middle" fill="#c4a882" fontSize="8">Clean water</text>
      </g>

      {/* Arrow */}
      <path d="M165 50 L185 50" stroke="#D4A843" strokeWidth="2" markerEnd="url(#arrowG)" />

      {/* Step 3: Mix */}
      <g transform="translate(190, 15)">
        <path d="M10 20 L10 75 Q10 80 15 80 L45 80 Q50 80 50 75 L50 20 Z" stroke="#43A047" strokeWidth="2" fill="rgba(67,160,71,0.08)" />
        <path d="M20 50 Q30 44 40 50 Q30 56 20 50" stroke="#43A047" strokeWidth="1.5" fill="none" />
        <path d="M25 35 L35 45 M35 35 L25 45" stroke="#D4A843" strokeWidth="1.5" />
        <text x="30" y="100" textAnchor="middle" fill="#c4a882" fontSize="8">Stir well</text>
      </g>

      {/* Arrow */}
      <path d="M250 50 L270 50" stroke="#D4A843" strokeWidth="2" markerEnd="url(#arrowG)" />

      {/* Step 4: Small sips */}
      <g transform="translate(272, 25)">
        <path d="M5 15 Q5 55 20 55 Q35 55 35 15" stroke="#43A047" strokeWidth="2" fill="rgba(67,160,71,0.1)" />
        <circle cx="20" cy="8" r="7" stroke="#c4a882" strokeWidth="1.5" fill="none" />
        <text x="20" y="75" textAnchor="middle" fill="#c4a882" fontSize="8">Small sips</text>
      </g>
    </svg>
  );
}

function HandwashingSVG(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 320 120" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      <rect width="320" height="120" rx="12" fill="#1a0f0a" fillOpacity="0.3" />

      {/* 5 steps in a row */}
      {[
        { label: "Wet hands", icon: "M25 50 Q25 35 25 30 Q30 20 35 30 L35 50 L40 40 Q45 55 25 55 Z" },
        { label: "Apply soap", icon: "M25 45 Q30 30 35 45 M22 50 Q30 40 38 50" },
        { label: "Scrub 20s", icon: "M22 42 L38 42 M22 48 L38 48 M25 36 L35 54 M35 36 L25 54" },
        { label: "Rinse clean", icon: "M30 30 L30 55 M25 35 L30 40 L35 35 M25 45 L30 50 L35 45" },
        { label: "Air dry", icon: "M25 35 L35 35 M25 42 L35 42 M25 49 L35 49 M30 30 L30 55" },
      ].map((step, i) => (
        <g key={i} transform={`translate(${10 + i * 62}, 10)`}>
          <circle cx="30" cy="38" r="22" fill="rgba(67,160,71,0.1)" stroke="#43A047" strokeWidth="1.5" />
          <path d={step.icon} stroke="#43A047" strokeWidth="1.5" strokeLinecap="round" fill="none" />
          <text x="30" y="72" textAnchor="middle" fill="#c4a882" fontSize="7.5" fontWeight="600">{i + 1}. {step.label}</text>
          {/* Step number */}
          <circle cx="12" cy="20" r="8" fill="#43A047" />
          <text x="12" y="23.5" textAnchor="middle" fill="white" fontSize="8" fontWeight="800">{i + 1}</text>
        </g>
      ))}

      {/* Bottom note */}
      <text x="160" y="105" textAnchor="middle" fill="#a08b78" fontSize="8">Before eating, after toilet, before cooking, after nappy change, after handling animals</text>
    </svg>
  );
}

function BreathingCountSVG(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 320 140" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      <rect width="320" height="140" rx="12" fill="#1a0f0a" fillOpacity="0.3" />

      {/* Clock */}
      <g transform="translate(20, 20)">
        <circle cx="40" cy="40" r="35" stroke="#D4A843" strokeWidth="2" fill="rgba(212,168,67,0.06)" />
        <text x="40" y="14" textAnchor="middle" fill="#D4A843" fontSize="8">60 seconds</text>
        <line x1="40" y1="40" x2="40" y2="14" stroke="#D4A843" strokeWidth="2" strokeLinecap="round" />
        <line x1="40" y1="40" x2="58" y2="40" stroke="#c4a882" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="40" cy="40" r="3" fill="#D4A843" />
      </g>

      {/* Thresholds */}
      <g transform="translate(120, 15)">
        <rect x="0" y="0" width="180" height="50" rx="8" fill="rgba(249,168,37,0.08)" stroke="#F9A825" strokeWidth="1.5" />
        <text x="90" y="16" textAnchor="middle" fill="#F9A825" fontSize="9" fontWeight="700">Fast Breathing Thresholds</text>
        <text x="90" y="30" textAnchor="middle" fill="#c4a882" fontSize="8">2-12 months: 50+ breaths/min</text>
        <text x="90" y="42" textAnchor="middle" fill="#c4a882" fontSize="8">1-5 years: 40+ breaths/min</text>
      </g>

      {/* Instructions */}
      <g transform="translate(120, 75)">
        <rect x="0" y="0" width="180" height="50" rx="8" fill="rgba(67,160,71,0.08)" stroke="#43A047" strokeWidth="1.5" />
        <text x="90" y="16" textAnchor="middle" fill="#43A047" fontSize="9" fontWeight="700">How to Count</text>
        <text x="90" y="30" textAnchor="middle" fill="#c4a882" fontSize="8">Child must be calm (not crying)</text>
        <text x="90" y="42" textAnchor="middle" fill="#c4a882" fontSize="8">Watch chest rise and fall = 1 breath</text>
      </g>
    </svg>
  );
}

function BreastfeedingSVG(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 320 140" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      <rect width="320" height="140" rx="12" fill="#1a0f0a" fillOpacity="0.3" />

      {/* Position indicators */}
      <g transform="translate(20, 15)">
        <text x="0" y="12" fill="#E91E63" fontSize="10" fontWeight="700">Correct Position</text>

        {/* Check marks with labels */}
        {[
          "Baby faces mother (tummy to tummy)",
          "Mouth covers full areola (not just nipple)",
          "Chin touches breast",
          "Lower lip turned outward",
          "Baby's ear, shoulder, hip in line",
        ].map((text, i) => (
          <g key={i} transform={`translate(0, ${24 + i * 18})`}>
            <circle cx="8" cy="4" r="7" fill="rgba(67,160,71,0.15)" />
            <path d={`M4 4 L7 7 L12 1`} stroke="#43A047" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none" />
            <text x="20" y="8" fill="#c4a882" fontSize="8.5">{text}</text>
          </g>
        ))}
      </g>

      {/* Warning signs */}
      <g transform="translate(200, 15)">
        <text x="0" y="12" fill="#E74C3C" fontSize="10" fontWeight="700">Warning Signs</text>

        {[
          "Clicking sounds",
          "Nipple pain/cracking",
          "Baby pulls away often",
        ].map((text, i) => (
          <g key={i} transform={`translate(0, ${24 + i * 18})`}>
            <circle cx="8" cy="4" r="7" fill="rgba(231,76,60,0.15)" />
            <text x="4" y="8" fill="#E74C3C" fontSize="10" fontWeight="700">!</text>
            <text x="20" y="8" fill="#c4a882" fontSize="8.5">{text}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}

function ImmunizationScheduleSVG(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 320 160" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      <rect width="320" height="160" rx="12" fill="#1a0f0a" fillOpacity="0.3" />

      {/* Timeline */}
      <line x1="30" y1="30" x2="290" y2="30" stroke="#43A047" strokeWidth="2" />

      {/* Milestones */}
      {[
        { x: 30, label: "Birth", vaccines: "BCG, OPV-0" },
        { x: 80, label: "6 wk", vaccines: "Penta-1, PCV-1" },
        { x: 130, label: "10 wk", vaccines: "Penta-2, PCV-2" },
        { x: 180, label: "14 wk", vaccines: "Penta-3, IPV" },
        { x: 225, label: "6 mo", vaccines: "Vit A" },
        { x: 270, label: "9 mo", vaccines: "MR-1, YF" },
      ].map((m, i) => (
        <g key={i}>
          <circle cx={m.x} cy={30} r="6" fill="#43A047" />
          <text x={m.x} y={22} textAnchor="middle" fill="#43A047" fontSize="7" fontWeight="700">{m.label}</text>
          <text x={m.x} y={48} textAnchor="middle" fill="#c4a882" fontSize="6.5">{m.vaccines}</text>
        </g>
      ))}

      {/* Legend */}
      <g transform="translate(20, 70)">
        <rect x="0" y="0" width="280" height="75" rx="8" fill="rgba(67,160,71,0.05)" stroke="#43A047" strokeWidth="1" />
        <text x="140" y="16" textAnchor="middle" fill="#43A047" fontSize="8" fontWeight="700">KEY VACCINES BY AGE</text>
        <text x="10" y="32" fill="#c4a882" fontSize="7">BCG = Tuberculosis | OPV = Oral Polio | Penta = DPT-HepB-Hib</text>
        <text x="10" y="44" fill="#c4a882" fontSize="7">PCV = Pneumococcal | IPV = Injectable Polio | MR = Measles-Rubella</text>
        <text x="10" y="56" fill="#c4a882" fontSize="7">YF = Yellow Fever | Vit A = Vitamin A supplement</text>
        <text x="10" y="68" fill="#D4A843" fontSize="7" fontWeight="600">Pregnant women: TT1-TT5 (Tetanus Toxoid) at ANC visits</text>
      </g>
    </svg>
  );
}

function DehydrationCheckSVG(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 320 140" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      <rect width="320" height="140" rx="12" fill="#1a0f0a" fillOpacity="0.3" />

      {/* 3 checks */}
      {[
        { x: 15, title: "Eyes", normal: "Normal", danger: "Sunken", color: "#43A047" },
        { x: 115, title: "Skin Pinch", normal: "Goes back fast", danger: "Goes back slowly", color: "#F9A825" },
        { x: 215, title: "Drinking", normal: "Drinks normally", danger: "Can't drink / very thirsty", color: "#E74C3C" },
      ].map((check, i) => (
        <g key={i} transform={`translate(${check.x}, 12)`}>
          <rect x="0" y="0" width="90" height="115" rx="8" fill="rgba(0,0,0,0.15)" stroke={check.color} strokeWidth="1.5" />
          <text x="45" y="18" textAnchor="middle" fill={check.color} fontSize="10" fontWeight="700">{check.title}</text>

          {/* Normal */}
          <rect x="8" y="26" width="74" height="32" rx="4" fill="rgba(67,160,71,0.08)" />
          <circle cx="18" cy="42" r="5" fill="#43A047" />
          <text x="16" y="45" textAnchor="middle" fill="white" fontSize="7" fontWeight="800">✓</text>
          <text x="50" y="40" textAnchor="middle" fill="#c4a882" fontSize="7">{check.normal}</text>

          {/* Danger */}
          <rect x="8" y="64" width="74" height="40" rx="4" fill="rgba(231,76,60,0.08)" />
          <circle cx="18" cy="78" r="5" fill="#E74C3C" />
          <text x="16" y="81" textAnchor="middle" fill="white" fontSize="7" fontWeight="800">!</text>
          <text x="50" y="78" textAnchor="middle" fill="#E74C3C" fontSize="7" fontWeight="600">{check.danger}</text>
          <text x="50" y="96" textAnchor="middle" fill="#c4a882" fontSize="6">{i === 2 ? "→ REFER" : "→ ORS"}</text>
        </g>
      ))}
    </svg>
  );
}

function BirthPreparednessSVG(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 320 120" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      <rect width="320" height="120" rx="12" fill="#1a0f0a" fillOpacity="0.3" />
      <text x="160" y="16" textAnchor="middle" fill="#E91E63" fontSize="9" fontWeight="700">PREPARE BEFORE 36 WEEKS</text>

      {/* 4 pillars */}
      {[
        { icon: "M20 15 L20 30 L30 30 L30 15 Z", label: "Health Facility", desc: "Identify where to deliver" },
        { icon: "M15 22 L25 14 L35 22 L35 30 L15 30 Z", label: "Transport", desc: "Plan how to get there" },
        { icon: "M20 14 Q25 10 30 14 L30 30 L20 30 Z", label: "Blood Donor", desc: "Find a compatible donor" },
        { icon: "M18 20 L32 20 M18 25 L32 25 M22 15 L28 15 L28 30 L22 30 Z", label: "Savings", desc: "Save money for costs" },
      ].map((item, i) => (
        <g key={i} transform={`translate(${10 + i * 78}, 28)`}>
          <rect x="2" y="0" width="72" height="78" rx="8" fill="rgba(233,30,99,0.06)" stroke="rgba(233,30,99,0.2)" strokeWidth="1" />
          <g transform="translate(22, 8)">
            <path d={item.icon} stroke="#E91E63" strokeWidth="1.5" fill="rgba(233,30,99,0.1)" />
          </g>
          <text x="38" y="52" textAnchor="middle" fill="#E91E63" fontSize="8" fontWeight="700">{item.label}</text>
          <text x="38" y="66" textAnchor="middle" fill="#c4a882" fontSize="6.5">{item.desc}</text>
        </g>
      ))}
    </svg>
  );
}

// ── Malaria RDT SVG ─────────────────────────────────────────────────────

function MalariaRDTSVG(props: SVGProps<SVGSVGElement>) {
  const steps = [
    { num: "1", label: "Clean Finger", desc: "Swab with alcohol" },
    { num: "2", label: "Prick & Collect", desc: "Use lancet, fill pipette" },
    { num: "3", label: "Add Buffer", desc: "4 drops in well" },
    { num: "4", label: "Wait 15 min", desc: "Read result lines" },
  ];
  return (
    <svg viewBox="0 0 320 160" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      <rect width="320" height="160" rx="10" fill="#0F0F0F" fillOpacity="0.3" />
      <text x="160" y="18" textAnchor="middle" fill="#22C55E" fontSize="10" fontWeight="700">HOW TO USE A RAPID DIAGNOSTIC TEST (RDT)</text>
      {steps.map((s, i) => {
        const x = 18 + i * 76;
        return (
          <g key={i}>
            <rect x={x} y="28" width="68" height="70" rx="6" fill="rgba(34,197,94,0.08)" stroke="rgba(34,197,94,0.2)" strokeWidth="0.5" />
            <circle cx={x + 34} cy="45" r="10" fill="#22C55E" />
            <text x={x + 34} y="49" textAnchor="middle" fill="white" fontSize="10" fontWeight="800">{s.num}</text>
            <text x={x + 34} y="68" textAnchor="middle" fill="#F0F0F0" fontSize="7.5" fontWeight="600">{s.label}</text>
            <text x={x + 34} y="82" textAnchor="middle" fill="#858585" fontSize="6">{s.desc}</text>
            {i < 3 && <text x={x + 72} y="60" fill="#22C55E" fontSize="14">&#8594;</text>}
          </g>
        );
      })}
      {/* Result interpretation */}
      <rect x="18" y="108" width="135" height="42" rx="6" fill="rgba(34,197,94,0.06)" stroke="rgba(34,197,94,0.15)" strokeWidth="0.5" />
      <text x="85" y="122" textAnchor="middle" fill="#22C55E" fontSize="7" fontWeight="700">NEGATIVE (1 line)</text>
      <line x1="55" y1="132" x2="115" y2="132" stroke="#22C55E" strokeWidth="2" />
      <text x="85" y="146" textAnchor="middle" fill="#858585" fontSize="6">Control line only = No malaria</text>

      <rect x="167" y="108" width="135" height="42" rx="6" fill="rgba(239,68,68,0.06)" stroke="rgba(239,68,68,0.15)" strokeWidth="0.5" />
      <text x="234" y="122" textAnchor="middle" fill="#EF4444" fontSize="7" fontWeight="700">POSITIVE (2 lines)</text>
      <line x1="200" y1="130" x2="268" y2="130" stroke="#EF4444" strokeWidth="2" />
      <line x1="200" y1="138" x2="268" y2="138" stroke="#EF4444" strokeWidth="2" />
      <text x="234" y="148" textAnchor="middle" fill="#858585" fontSize="6">Two lines = Malaria &#8594; TREAT</text>
    </svg>
  );
}

// ── Fever Assessment SVG ────────────────────────────────────────────────

function FeverAssessmentSVG(props: SVGProps<SVGSVGElement>) {
  const levels = [
    { temp: "37.5\u00b0C", label: "Mild Fever", color: "#F59E0B", action: "Monitor, fluids", bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.2)" },
    { temp: "38.5\u00b0C", label: "High Fever", color: "#EF4444", action: "Paracetamol, RDT", bg: "rgba(239,68,68,0.08)", border: "rgba(239,68,68,0.2)" },
    { temp: "39.5\u00b0C+", label: "Very High", color: "#DC2626", action: "REFER NOW", bg: "rgba(220,38,38,0.1)", border: "rgba(220,38,38,0.3)" },
  ];
  return (
    <svg viewBox="0 0 320 130" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      <rect width="320" height="130" rx="10" fill="#0F0F0F" fillOpacity="0.3" />
      <text x="160" y="18" textAnchor="middle" fill="#EF4444" fontSize="10" fontWeight="700">FEVER ASSESSMENT &amp; ACTION</text>
      {/* Thermometer icon */}
      <rect x="14" y="30" width="16" height="75" rx="8" fill="none" stroke="#858585" strokeWidth="1" />
      <rect x="17" y="55" width="10" height="47" rx="5" fill="url(#feverGrad)" />
      <circle cx="22" cy="95" r="7" fill="#EF4444" />
      <defs><linearGradient id="feverGrad" x1="0" y1="1" x2="0" y2="0"><stop offset="0%" stopColor="#EF4444"/><stop offset="100%" stopColor="#F59E0B"/></linearGradient></defs>
      {levels.map((l, i) => {
        const y = 32 + i * 32;
        return (
          <g key={i}>
            <rect x="44" y={y} width="264" height="26" rx="5" fill={l.bg} stroke={l.border} strokeWidth="0.5" />
            <text x="58" y={y + 16} fill={l.color} fontSize="9" fontWeight="800">{l.temp}</text>
            <text x="120" y={y + 16} fill="#F0F0F0" fontSize="8" fontWeight="600">{l.label}</text>
            <text x="210" y={y + 16} fill={l.color} fontSize="7.5" fontWeight="700">{l.action}</text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Diagram component map ───────────────────────────────────────────────

const DIAGRAM_COMPONENTS: Record<string, (props: SVGProps<SVGSVGElement>) => React.ReactElement> = {
  danger_signs: DangerSignsSVG,
  ors_preparation: ORSPreparationSVG,
  handwashing: HandwashingSVG,
  breathing_count: BreathingCountSVG,
  breastfeeding: BreastfeedingSVG,
  immunization_schedule: ImmunizationScheduleSVG,
  dehydration_check: DehydrationCheckSVG,
  birth_preparedness: BirthPreparednessSVG,
  malaria_rdt: MalariaRDTSVG,
  fever_assessment: FeverAssessmentSVG,
};

// ── Public component ────────────────────────────────────────────────────

interface HealthDiagramProps {
  diagramKey: string;
}

export default memo(function HealthDiagram({ diagramKey }: HealthDiagramProps) {
  const meta = DIAGRAM_REGISTRY[diagramKey];
  const DiagramSVG = DIAGRAM_COMPONENTS[diagramKey];

  if (!meta || !DiagramSVG) return null;

  const variantClass = meta.variant === "danger"
    ? "diagram-danger"
    : meta.variant === "maternal"
    ? "diagram-maternal"
    : "";

  return (
    <div className={`health-diagram ${variantClass}`}>
      <div className="diagram-title">{meta.title}</div>
      <DiagramSVG />
      {meta.caption && <div className="diagram-caption">{meta.caption}</div>}
    </div>
  );
});

// ── Export diagram keys for external use ─────────────────────────────────
export const DIAGRAM_KEYS = Object.keys(DIAGRAM_REGISTRY);
