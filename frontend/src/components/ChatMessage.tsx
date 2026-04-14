"use client";

import { memo, useEffect, useRef, useState } from "react";
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

// ── Markdown renderer (handles headers, lists, bold, code, paragraphs) ────
function renderMarkdown(text: string): string {
  // Escape HTML
  let html = text.replace(/&/g, "&amp;").replace(/</g, "&lt;");

  // Headers: ## Header → <h3>, ### Header → <h4>
  html = html.replace(/^### (.+)$/gm, '<h4 class="md-h4">$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3 class="md-h3">$1</h3>');

  // Bold and italic
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Inline code
  html = html.replace(/`(.+?)`/g, '<code class="inline-code">$1</code>');

  // Horizontal rule
  html = html.replace(/^---$/gm, '<hr class="content-hr" />');

  // Numbered lists: 1. item → <li>
  html = html.replace(/^(\d+)\. (.+)$/gm, '<li class="md-oli" value="$1">$2</li>');
  html = html.replace(/((?:<li class="md-oli"[^>]*>.*<\/li>\n?)+)/g, (m) => `<ol class="md-ol">${m}</ol>`);

  // Bullet lists: - item → <li>
  html = html.replace(/^- (.+)$/gm, '<li class="md-li">$1</li>');
  html = html.replace(/((?:<li class="md-li">.*<\/li>\n?)+)/g, (m) => `<ul class="md-ul">${m}</ul>`);

  // Paragraphs: double newline → paragraph break
  html = html.replace(/\n\n+/g, '</p><p class="md-p">');

  // Single newlines within paragraphs → <br>
  html = html.replace(/\n/g, "<br />");

  // Wrap in paragraph
  html = `<p class="md-p">${html}</p>`;

  // Clean empty paragraphs
  html = html.replace(/<p class="md-p"><\/p>/g, "");
  html = html.replace(/<p class="md-p"><br \/><\/p>/g, "");

  return html;
}

// ── Severity Badge ────────────────────────────────────────────────────

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

// ── Triage Card ───────────────────────────────────────────────────────

function TriageCard({ triage }: { triage: TriageResult }) {
  const spokenRef = useRef(false);

  useEffect(() => {
    if (spokenRef.current || !isTTSAvailable()) return;
    spokenRef.current = true;
    if (triage.severity === "red" && triage.red_flags.length > 0) {
      speakRedFlagAlert(triage.red_flags.map((rf) => rf.symptom));
    } else {
      speakTriageSummary(triage.severity, triage.manage_at_home, triage.refer_reasons);
    }
  }, [triage]);

  return (
    <div className={`triage-card triage-${triage.severity}`}>
      <div className="triage-header">
        <SeverityBadge severity={triage.severity} />
        {triage.severity === "red" && (
          <a href="tel:0800100263" className="emergency-call">
            <PhoneIcon width={14} height={14} />
            Call Hotline
          </a>
        )}
      </div>
      {triage.red_flags.length > 0 && (
        <div className="triage-section">
          <strong>Danger Signs:</strong>
          <ul>
            {triage.red_flags.map((rf, i) => (
              <li key={i} className="red-flag-item">
                <AlertTriangleIcon width={12} height={12} />
                <span>{rf.symptom}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {triage.manage_at_home.length > 0 && (
        <div className="triage-section">
          <strong>Home Management:</strong>
          <ul>{triage.manage_at_home.map((item, i) => <li key={i}>{item}</li>)}</ul>
        </div>
      )}
      {triage.refer_reasons.length > 0 && (
        <div className="triage-section">
          <strong>Referral:</strong>
          <ul>{triage.refer_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </div>
      )}
      {triage.follow_up && <p className="triage-followup"><strong>Follow-up:</strong> {triage.follow_up}</p>}
    </div>
  );
}

// ── Citation List ─────────────────────────────────────────────────────

function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <details className="citations">
      <summary className="citations-summary">
        <span className="citations-icon">📋</span>
        Sources ({citations.length})
      </summary>
      <ul className="citations-list">
        {citations.map((c, i) => (
          <li key={i} className="citation-item">
            <span className="citation-ref">{c.ref}</span>
            <span className="citation-source">{c.source}</span>
            {c.section && <span className="citation-section"> — {c.section}</span>}
          </li>
        ))}
      </ul>
    </details>
  );
}

// ── Main Message Component ────────────────────────────────────────────

export default memo(
  function ChatMessage({ turn, onFeedback }: ChatMessageProps) {
    const isAssistant = turn.role === "assistant";
    const [collapsed, setCollapsed] = useState(false);
    const [voted, setVoted] = useState<number | null>(null);

    const handleVote = (rating: number) => {
      setVoted(rating);
      onFeedback?.(turn.id, rating);
    };

    return (
      <div className={`bubble ${turn.role} ${collapsed ? "collapsed" : ""}`} role="article">
        {/* Header row */}
        <div className="bubble-header">
          <div className="bubble-header-left">
            <span className={`role-avatar ${turn.role}`}>
              {isAssistant ? "M" : "Y"}
            </span>
            <span className="role-label">{isAssistant ? "Musawo" : "You"}</span>
            {turn.confidence != null && isAssistant && (
              <span className={`confidence-badge ${
                turn.confidence >= 0.7 ? "high" : turn.confidence >= 0.4 ? "medium" : "low"
              }`}>
                {turn.confidence >= 0.7 ? "HIGH" : turn.confidence >= 0.4 ? "MED" : "LOW"}
              </span>
            )}
          </div>
          {isAssistant && turn.content.length > 200 && (
            <button
              className="collapse-btn"
              onClick={() => setCollapsed(!collapsed)}
              aria-label={collapsed ? "Expand message" : "Collapse message"}
            >
              {collapsed ? "▼ Expand" : "▲ Collapse"}
            </button>
          )}
        </div>

        {/* Triage card (pinned above content) */}
        {turn.triage && <TriageCard triage={turn.triage} />}

        {/* Escalation banner */}
        {turn.escalationRequired && (
          <div className="escalation-banner" role="alert">
            <AlertTriangleIcon width={16} height={16} />
            <span>
              Visit the nearest health facility or call{" "}
              <a href="tel:0800100263"><strong>0800 100 263</strong></a>
            </span>
          </div>
        )}

        {/* Content */}
        {!collapsed && (
          <div
            className="bubble-content"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(turn.content) }}
          />
        )}
        {collapsed && (
          <div className="bubble-content collapsed-preview">
            {turn.content.slice(0, 120)}...
          </div>
        )}

        {/* Grounding warning */}
        {turn.groundingWarning && (
          <p className="grounding-warning">
            ⚠ This response may not be fully supported by official guidelines.
          </p>
        )}

        {/* Citations */}
        {turn.citations && <CitationList citations={turn.citations as Citation[]} />}

        {/* Feedback + timestamp */}
        {isAssistant && (
          <div className="bubble-footer">
            <span className="bubble-time">
              {new Date(turn.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
            {onFeedback && (
              <div className="feedback-row">
                <button
                  className={`feedback-btn ${voted === 1 ? "voted" : ""}`}
                  onClick={() => handleVote(1)}
                  aria-label="Helpful"
                  disabled={voted !== null}
                >
                  <ThumbsUpIcon width={14} height={14} />
                </button>
                <button
                  className={`feedback-btn ${voted === -1 ? "voted-down" : ""}`}
                  onClick={() => handleVote(-1)}
                  aria-label="Not helpful"
                  disabled={voted !== null}
                >
                  <ThumbsDownIcon width={14} height={14} />
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    );
  },
  (prev, next) =>
    prev.turn.id === next.turn.id &&
    prev.turn.content === next.turn.content &&
    prev.turn.citations?.length === next.turn.citations?.length &&
    prev.turn.faithfulnessScore === next.turn.faithfulnessScore &&
    prev.turn.triage === next.turn.triage
);
