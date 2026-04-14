"use client";

import { memo } from "react";
import { useChatStore } from "@/store/useChatStore";
import { BabyIcon, AlertTriangleIcon } from "./Icons";

const MILESTONES: {
  week: number;
  label: string;
  label_lg: string;
  action: string;
}[] = [
  { week: 12, label: "First ANC Visit", label_lg: "Okwebuuza okw'olubereberye", action: "Blood tests, ultrasound, iron + folic acid" },
  { week: 20, label: "Second ANC Visit", label_lg: "Okwebuuza okw'okubiri", action: "Anomaly scan, tetanus vaccine" },
  { week: 26, label: "Third ANC Visit", label_lg: "Okwebuuza okw'okusatu", action: "Check blood pressure, baby growth" },
  { week: 30, label: "Fourth ANC Visit", label_lg: "Okwebuuza okw'okuna", action: "Birth preparedness plan" },
  { week: 34, label: "Fifth ANC Visit", label_lg: "Okwebuuza okw'okutaano", action: "Review birth plan, check baby position" },
  { week: 36, label: "Sixth ANC Visit", label_lg: "Okwebuuza okw'omukaaga", action: "Weekly check-ups begin" },
  { week: 38, label: "Seventh ANC Visit", label_lg: "Okwebuuza okw'omusanvu", action: "Final preparations" },
  { week: 40, label: "Expected Due Date", label_lg: "Enaku z'okuzaala", action: "Stay close to facility" },
];

const DANGER_SIGNS = [
  "Severe headache that won't go away",
  "Blurred vision or seeing spots",
  "Vaginal bleeding",
  "Severe abdominal pain",
  "High fever",
  "Swollen face, hands, or feet",
  "Baby not moving",
  "Water breaking before labour",
];

export default memo(function MaternalTracker() {
  const mode = useChatStore((s) => s.mode);
  const pregnancyWeek = useChatStore((s) => s.pregnancyWeek);
  const setPregnancyWeek = useChatStore((s) => s.setPregnancyWeek);
  const locale = useChatStore((s) => s.locale);

  if (mode !== "maternal") return null;

  const nextMilestone = MILESTONES.find(
    (m) => !pregnancyWeek || m.week >= pregnancyWeek
  );

  return (
    <div className="maternal-tracker">
      <div className="maternal-header">
        <BabyIcon width={20} height={20} />
        <h3>{locale === "lg" ? "Okugoberereza Olubuto" : "Pregnancy Tracker"}</h3>
      </div>

      <div className="week-selector">
        <label htmlFor="pregnancy-week">
          {locale === "lg" ? "Wiki z'olubuto:" : "Pregnancy week:"}
        </label>
        <input
          id="pregnancy-week"
          type="number"
          min={1}
          max={45}
          value={pregnancyWeek || ""}
          onChange={(e) =>
            setPregnancyWeek(e.target.value ? parseInt(e.target.value) : null)
          }
          placeholder="e.g. 28"
          className="week-input"
        />
      </div>

      {pregnancyWeek && (
        <div className="trimester-badge">
          {pregnancyWeek <= 12
            ? "First Trimester"
            : pregnancyWeek <= 27
            ? "Second Trimester"
            : "Third Trimester"}
        </div>
      )}

      {/* Progress bar */}
      {pregnancyWeek && (
        <div className="progress-track">
          <div
            className="progress-fill"
            style={{ width: `${Math.min((pregnancyWeek / 40) * 100, 100)}%` }}
          />
          <span className="progress-label">
            Week {pregnancyWeek} / 40
          </span>
        </div>
      )}

      {/* Next milestone */}
      {nextMilestone && (
        <div className="next-milestone">
          <strong>
            {locale === "lg" ? "Ekiddako:" : "Next:"}{" "}
            {locale === "lg" ? nextMilestone.label_lg : nextMilestone.label}
          </strong>
          <p>Week {nextMilestone.week} &mdash; {nextMilestone.action}</p>
        </div>
      )}

      {/* Danger signs */}
      <details className="danger-signs">
        <summary>
          <AlertTriangleIcon width={14} height={14} />
          {locale === "lg"
            ? "Bubonero bw'Akabi — Genda mu Ddwaliro Amangu!"
            : "Danger Signs — Go to Facility Immediately!"}
        </summary>
        <ul>
          {DANGER_SIGNS.map((sign, i) => (
            <li key={i}>{sign}</li>
          ))}
        </ul>
      </details>
    </div>
  );
});
