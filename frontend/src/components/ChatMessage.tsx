"use client";

import { memo, useEffect, useRef } from "react";
import {
  type ChatTurn,
  type Citation,
  type TriageResult,
} from "@/store/useChatStore";
import {
  AlertTriangleIcon,
  PhoneIcon,
  ThumbsUpIcon,
  ThumbsDownIcon,
} from "./Icons";
import {
  speakRedFlagAlert,
  speakTriageSummary,
  isTTSAvailable,
} from "@/lib/voiceOutput";

interface ChatMessageProps {
  turn: ChatTurn;
  onFeedback?: (turnId: string, rating: number) => void;
}

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    green: "badge-green",
    yellow: "badge-yellow",
    red: "badge-red",
  };
  const labels: Record<string, string> = {
    green: "Manage at Home",
    yellow: "Monitor / Follow Up",
    red: "REFER NOW",
  };
  return (
    <span className={`severity-badge ${colors[severity] || ""}`}>
      {severity === "red" && <AlertTriangleIcon width={14} height={14} />}
      {labels[severity] || severity}
    </span>
  );
}

function TriageCard({ triage }: { triage: TriageResult }) {
  const spokenRef = useRef(false);

  // Auto-speak red-flag alerts when triage card first renders
  useEffect(() => {
    if (spokenRef.current || !isTTSAvailable()) return;
    spokenRef.current = true;

    if (triage.severity === "red" && triage.red_flags.length > 0) {
      speakRedFlagAlert(triage.red_flags.map((rf) => rf.symptom));
    } else {
      speakTriageSummary(
        triage.severity,
        triage.manage_at_home,
        triage.refer_reasons
      );
    }
  }, [triage]);

  return (
    <div className={`triage-card triage-${triage.severity}`}>
      <div className="triage-header">
        <SeverityBadge severity={triage.severity} />
        {triage.severity === "red" && (
          <a href="tel:0800100263" className="emergency-call">
            <PhoneIcon width={14} height={14} />
            Call Health Hotline
          </a>
        )}
      </div>

      {triage.red_flags.length > 0 && (
        <div className="triage-section">
          <strong>Danger Signs Detected:</strong>
          <ul>
            {triage.red_flags.map((rf, i) => (
              <li key={i} className="red-flag-item">
                <AlertTriangleIcon width={12} height={12} />
                <span>{rf.symptom} &mdash; {rf.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {triage.manage_at_home.length > 0 && (
        <div className="triage-section">
          <strong>Home Management:</strong>
          <ul>
            {triage.manage_at_home.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {triage.refer_reasons.length > 0 && (
        <div className="triage-section">
          <strong>Referral Reasons:</strong>
          <ul>
            {triage.refer_reasons.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {triage.follow_up && (
        <p className="triage-followup">
          <strong>Follow-up:</strong> {triage.follow_up}
        </p>
      )}
    </div>
  );
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <details className="citations">
      <summary>Sources ({citations.length})</summary>
      <ul>
        {citations.map((c, i) => (
          <li key={i} className="citation-item">
            <span className="citation-ref">{c.ref}</span>
            <span className="citation-source">{c.source}</span>
            {c.section && (
              <span className="citation-section"> &mdash; {c.section}</span>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default memo(
  function ChatMessage({ turn, onFeedback }: ChatMessageProps) {
    const isAssistant = turn.role === "assistant";

    return (
      <div className={`bubble ${turn.role}`} role="article">
        <div className="bubble-header">
          <span className="role-label">
            {isAssistant ? "Musawo" : "You"}
          </span>
          {turn.confidence != null && isAssistant && (
            <span
              className={`confidence-badge ${
                turn.confidence >= 0.7
                  ? "high"
                  : turn.confidence >= 0.4
                  ? "medium"
                  : "low"
              }`}
            >
              {turn.confidence >= 0.7
                ? "HIGH"
                : turn.confidence >= 0.4
                ? "MEDIUM"
                : "LOW"}{" "}
              confidence
            </span>
          )}
        </div>

        <div className="bubble-content">{turn.content}</div>

        {/* Triage card (VHT mode) */}
        {turn.triage && <TriageCard triage={turn.triage} />}

        {/* Escalation banner */}
        {turn.escalationRequired && (
          <div className="escalation-banner" role="alert">
            <AlertTriangleIcon width={16} height={16} />
            <span>
              Please visit the nearest health facility or call{" "}
              <a href="tel:0800100263">
                <strong>0800 100 263</strong>
              </a>{" "}
              (toll-free)
            </span>
          </div>
        )}

        {/* Grounding warning */}
        {turn.groundingWarning && (
          <p className="grounding-warning">
            This response may not be fully supported by official guidelines.
            Please verify with a health worker.
          </p>
        )}

        {/* Citations */}
        {turn.citations && <CitationList citations={turn.citations} />}

        {/* Feedback buttons */}
        {isAssistant && onFeedback && (
          <div className="feedback-row">
            <button
              className="feedback-btn"
              onClick={() => onFeedback(turn.id, 1)}
              aria-label="Helpful"
            >
              <ThumbsUpIcon width={14} height={14} />
            </button>
            <button
              className="feedback-btn"
              onClick={() => onFeedback(turn.id, -1)}
              aria-label="Not helpful"
            >
              <ThumbsDownIcon width={14} height={14} />
            </button>
          </div>
        )}
      </div>
    );
  },
  (prev, next) =>
    prev.turn.id === next.turn.id &&
    prev.turn.content === next.turn.content &&
    prev.turn.citations?.length === next.turn.citations?.length &&
    prev.turn.faithfulnessScore === next.turn.faithfulnessScore
);
