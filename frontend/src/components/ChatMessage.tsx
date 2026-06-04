"use client";

import { lazy, memo, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useChatStore,
  VOICE_PERSONAS,
  type ChatTurn,
  type Citation,
  type TriageResult,
} from "@/store/useChatStore";
import {
  AlertTriangleIcon,
  PhoneIcon,
  ThumbsUpIcon,
  ThumbsDownIcon,
  VolumeIcon,
  VolumeOffIcon,
} from "./Icons";
import {
  speak,
  speakRedFlagAlert,
  speakTriageSummary,
  isTTSAvailable,
  isSpeaking,
  stopSpeaking,
} from "@/lib/voiceOutput";
import { t } from "@/lib/i18n";

// Lazy-load diagrams — only loaded when a response includes diagram content
const HealthDiagram = lazy(() => import("./HealthDiagrams"));

interface ChatMessageProps {
  turn: ChatTurn;
  onFeedback?: (turnId: string, rating: number) => void;
}

// ── Section type detection for semantic styling ────
const SECTION_TYPES: Record<string, string> = {
  assessment: "section-assessment",
  guidance: "section-guidance",
  "when to refer": "section-refer",
  "sources": "section-sources",
  "treatment": "section-guidance",
  "prevention": "section-guidance",
  "danger signs": "section-refer",
  "follow-up": "section-followup",
  "referral": "section-refer",
  "home management": "section-guidance",
  "important": "section-refer",
  "warning": "section-refer",
  "note": "section-note",
  "confidence": "section-confidence",
};

function getSectionClass(title: string): string {
  const lower = title.toLowerCase();
  for (const [key, cls] of Object.entries(SECTION_TYPES)) {
    if (lower.includes(key)) return cls;
  }
  return "section-default";
}

// ── Allowed image hosts (must match CSP img-src) ────
const ALLOWED_IMG_HOSTS = [
  "musawo.ai",
  "localhost",
  "tile.openstreetmap.org",
];

function isAllowedImageSrc(src: string): boolean {
  if (src.startsWith("/") || src.startsWith("data:") || src.startsWith("blob:")) return true;
  try {
    const url = new URL(src);
    return ALLOWED_IMG_HOSTS.some((h) => url.hostname === h || url.hostname.endsWith(`.${h}`));
  } catch {
    return false;
  }
}

// ── Inline citations: [1] / [1, 2] → superscript anchors to the Sources panel ──
function linkCitations(s: string): string {
  return s.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_m, nums: string) =>
    nums
      .split(/\s*,\s*/)
      .map((n) => `<a href="#cite-${n}" class="cite-ref" data-cite="${n}">${n}</a>`)
      .join("")
  );
}

// ── Inline formatting shared by paragraphs and table cells ──
function renderInline(s: string): string {
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
  s = s.replace(/`(.+?)`/g, '<code class="inline-code">$1</code>');
  return linkCitations(s);
}

// ── Markdown tables → responsive <table> (CSS stacks it to cards on mobile) ──
// A GitHub-style table is a header row, a separator row (dashes/colons/pipes),
// then data rows. We extract it BEFORE paragraph/<br> passes and swap in a token
// so the finished <table> never gets mangled or wrapped in a <p>.
const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$/;

function splitTableCells(row: string): string[] {
  let r = row.trim();
  if (r.startsWith("|")) r = r.slice(1);
  if (r.endsWith("|")) r = r.slice(0, -1);
  return r.split("|").map((c) => c.trim());
}

function cellAlign(sepCell: string): string {
  const c = sepCell.trim();
  const left = c.startsWith(":");
  const right = c.endsWith(":");
  if (left && right) return "center";
  if (right) return "right";
  if (left) return "left";
  return "";
}

function extractTables(src: string, store: string[]): string {
  const lines = src.split("\n");
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const header = lines[i];
    const sep = lines[i + 1];
    if (
      header &&
      sep != null &&
      header.includes("|") &&
      TABLE_SEP.test(sep) &&
      splitTableCells(header).length >= 2
    ) {
      const headers = splitTableCells(header);
      const aligns = splitTableCells(sep).map(cellAlign);
      const rows: string[][] = [];
      let j = i + 2;
      for (; j < lines.length; j++) {
        const l = lines[j];
        if (!l || !l.includes("|") || TABLE_SEP.test(l)) break;
        rows.push(splitTableCells(l));
      }
      const thead =
        "<thead><tr>" +
        headers
          .map((h, k) => {
            const a = aligns[k] ? ` style="text-align:${aligns[k]}"` : "";
            return `<th${a}>${renderInline(h)}</th>`;
          })
          .join("") +
        "</tr></thead>";
      const tbody =
        "<tbody>" +
        rows
          .map(
            (cells) =>
              "<tr>" +
              headers
                .map((h, k) => {
                  const a = aligns[k] ? ` style="text-align:${aligns[k]}"` : "";
                  const label = h.replace(/"/g, "&quot;");
                  return `<td data-label="${label}"${a}>${renderInline(cells[k] || "")}</td>`;
                })
                .join("") +
              "</tr>"
          )
          .join("") +
        "</tbody>";
      const token = `@@MDTABLE${store.length}@@`;
      store.push(
        `<div class="md-table-wrap"><table class="md-table">${thead}${tbody}</table></div>`
      );
      // Surround the token with blank lines so it becomes its own paragraph.
      out.push("", token, "");
      i = j - 1;
    } else {
      out.push(header);
    }
  }
  return out.join("\n");
}

// ── Markdown renderer (Grok-inspired clean typography + clinical structure) ──
function renderMarkdown(text: string): string {
  // Escape HTML (&, <, and > — > prevents stray angle brackets from forming tags)
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Extract markdown tables first; re-inserted as finished <table> at the end.
  const tables: string[] = [];
  html = extractTables(html, tables);

  // Inline diagrams: ::diagram[key] → SVG placeholder rendered by React
  // (actual SVGs injected post-render via HealthDiagram component below)
  html = html.replace(
    /::diagram\[([a-z_-]+)\]/gi,
    '<div class="diagram-slot" data-diagram="$1"></div>'
  );

  // Markdown images: ![alt](src) → <figure> with caption
  html = html.replace(
    /!\[([^\]]*)\]\(([^)]+)\)/g,
    (_m, alt: string, src: string) => {
      if (!isAllowedImageSrc(src)) {
        return `<span class="img-blocked" title="Image blocked by security policy">[Image: ${alt || "blocked"}]</span>`;
      }
      const caption = alt ? `<figcaption class="md-figcaption">${alt}</figcaption>` : "";
      return `<figure class="md-figure"><img class="md-img" src="${src}" alt="${alt}" loading="lazy" />${caption}</figure>`;
    }
  );

  // Headers: ## Header → semantic section dividers
  html = html.replace(/^### (.+)$/gm, (_m, title: string) => {
    const cls = getSectionClass(title);
    return `<h4 class="md-h4 ${cls}">${title}</h4>`;
  });
  html = html.replace(/^## (.+)$/gm, (_m, title: string) => {
    const cls = getSectionClass(title);
    return `<h3 class="md-h3 ${cls}">${title}</h3>`;
  });

  // Bold and italic
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Inline code (dosages, measurements)
  html = html.replace(/`(.+?)`/g, '<code class="inline-code">$1</code>');

  // Phone numbers → clickable links
  html = html.replace(/\b(0800\s?\d{3}\s?\d{3})\b/g, '<a href="tel:$1" class="phone-link">$1</a>');
  html = html.replace(/\b(\+256\s?\d{3}\s?\d{6})\b/g, '<a href="tel:$1" class="phone-link">$1</a>');

  // Citations: [1] / [1, 2] → superscript anchors to the Sources panel
  html = linkCitations(html);

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

  // Highlight REFER NOW as callout
  html = html.replace(
    /<strong>REFER NOW<\/strong>/g,
    '<span class="refer-now-badge">REFER NOW</span>'
  );

  // Re-insert tables OUTSIDE any <p> wrapper (a standalone token in its own paragraph)
  html = html.replace(/<p class="md-p">\s*(@@MDTABLE\d+@@)\s*<\/p>/g, "$1");
  html = html.replace(/@@MDTABLE(\d+)@@/g, (_m, n: string) => tables[Number(n)] || "");

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
  const ttsOn = useChatStore((s) => s.ttsEnabled);

  useEffect(() => {
    if (spokenRef.current || !ttsOn || !isTTSAvailable()) return;
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
        {citations.map((c, i) => {
          const n = String(c.ref ?? "").replace(/\D/g, "") || String(i + 1);
          return (
            <li key={i} id={`cite-${n}`} className="citation-item">
              <span className="citation-ref">{c.ref}</span>
              <span className="citation-source">{c.source}</span>
              {c.section && <span className="citation-section"> — {c.section}</span>}
            </li>
          );
        })}
      </ul>
    </details>
  );
}

// ── Auto-detect relevant diagrams from response content ─────────────
const DIAGRAM_TRIGGERS: Record<string, string[]> = {
  danger_signs: ["danger sign", "convulsion", "unable to drink", "chest indrawing", "unconscious", "vomiting everything"],
  ors_preparation: ["ors", "oral rehydration", "mix.*sachet", "rehydration salt"],
  handwashing: ["handwashing", "wash.*hand", "hand hygiene", "soap.*water.*20"],
  breathing_count: ["breathing rate", "count.*breath", "fast breathing", "breaths per minute"],
  breastfeeding: ["breastfeed", "latch", "breast.*position", "exclusive.*feeding"],
  malaria_rdt: ["rdt", "rapid diagnostic", "malaria test", "blood smear"],
  fever_assessment: ["high fever", "fever.*child", "temperature.*38", "febrile"],
  immunization_schedule: ["immuniz", "vaccin", "bcg", "pentavalent", "opv", "unepi"],
  dehydration_check: ["dehydrat", "skin pinch", "sunken eyes", "some dehydration", "severe dehydration"],
  birth_preparedness: ["birth.*plan", "birth.*prepar", "before.*36.*week", "delivery.*plan"],
};

function detectDiagrams(content: string): string[] {
  const lower = content.toLowerCase();
  const detected: string[] = [];
  for (const [key, triggers] of Object.entries(DIAGRAM_TRIGGERS)) {
    if (triggers.some((t) => new RegExp(t, "i").test(lower))) {
      detected.push(key);
    }
  }
  // Max 2 auto-detected diagrams per message to avoid clutter
  return detected.slice(0, 2);
}

// Also detect explicit ::diagram[key] in content
function extractExplicitDiagrams(content: string): string[] {
  const matches = content.match(/::diagram\[([a-z_-]+)\]/gi);
  if (!matches) return [];
  return matches.map((m) => m.replace(/::diagram\[|\]/g, ""));
}

// ── Main Message Component ────────────────────────────────────────────

export default memo(
  function ChatMessage({ turn, onFeedback }: ChatMessageProps) {
    const isAssistant = turn.role === "assistant";
    const [collapsed, setCollapsed] = useState(false);
    const [voted, setVoted] = useState<number | null>(null);
    const locale = useChatStore((s) => s.locale);
    const rootRef = useRef<HTMLDivElement>(null);

    // Clicking an inline [n] citation opens the Sources panel and scrolls to it
    const handleCiteClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
      const ref = (e.target as HTMLElement).closest<HTMLElement>(".cite-ref");
      if (!ref) return;
      e.preventDefault();
      const n = ref.getAttribute("data-cite");
      const root = rootRef.current;
      if (!root || !n) return;
      const details = root.querySelector<HTMLDetailsElement>("details.citations");
      if (details) details.open = true;
      // data-cite is always bare digits, so the id is selector-safe as-is
      root
        .querySelector(`#cite-${n.replace(/[^0-9]/g, "")}`)
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, []);

    // Detect diagrams to show
    const diagrams = useMemo(() => {
      if (!isAssistant || !turn.content) return [];
      const explicit = extractExplicitDiagrams(turn.content);
      if (explicit.length > 0) return explicit;
      return detectDiagrams(turn.content);
    }, [isAssistant, turn.content]);

    const [speaking, setSpeaking] = useState(false);
    const ttsEnabled = useChatStore((s) => s.ttsEnabled);

    const handleVote = (rating: number) => {
      setVoted(rating);
      onFeedback?.(turn.id, rating);
    };

    const handleTTS = useCallback(() => {
      if (speaking || isSpeaking()) {
        stopSpeaking();
        setSpeaking(false);
      } else {
        setSpeaking(true);
        const cleanText = turn.content
          .replace(/^##+ .+$/gm, "")
          .replace(/\*\*(.+?)\*\*/g, "$1")
          .replace(/\*(.+?)\*/g, "$1")
          .replace(/`(.+?)`/g, "$1")
          .replace(/::diagram\[[^\]]+\]/g, "")
          .replace(/---/g, "")
          .trim();
        const persona = VOICE_PERSONAS.find((p) => p.id === useChatStore.getState().selectedVoice);
        speak(cleanText, persona?.langCode?.split("-")[0] || "en", {
          urgent: turn.escalationRequired,
          onEnd: () => setSpeaking(false),
          gender: persona?.gender,
          langCode: persona?.langCode,
        });
      }
    }, [speaking, turn.content, turn.escalationRequired]);

    return (
      <div ref={rootRef} className={`bubble ${turn.role} ${collapsed ? "collapsed" : ""}`} role="article">
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
        {!collapsed && turn.content ? (
          <div
            className="bubble-content"
            onClick={handleCiteClick}
            dangerouslySetInnerHTML={{ __html: renderMarkdown(turn.content) }}
          />
        ) : !collapsed && isAssistant && !turn.content ? (
          <div className="bubble-content" style={{ color: "var(--text-3)", fontStyle: "italic" }}>
            Loading response...
          </div>
        ) : null}
        {collapsed && (
          <div className="bubble-content collapsed-preview">
            {turn.content.slice(0, 120)}...
          </div>
        )}

        {/* Health diagrams (auto-detected or explicit ::diagram[key]) */}
        {!collapsed && diagrams.length > 0 && (
          <Suspense fallback={null}>
            {diagrams.map((key) => (
              <HealthDiagram key={key} diagramKey={key} />
            ))}
          </Suspense>
        )}

        {/* Grounding warning */}
        {turn.groundingWarning && (
          <p className="grounding-warning">
            ⚠ {t("grounding_warning", locale)}
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
            <div className="feedback-row">
              {ttsEnabled && isTTSAvailable() && turn.content && (
                <button
                  className={`feedback-btn tts-btn ${speaking ? "tts-active" : ""}`}
                  onClick={handleTTS}
                  aria-label={speaking ? "Stop reading" : "Read aloud"}
                  type="button"
                >
                  {speaking ? <VolumeOffIcon width={14} height={14} /> : <VolumeIcon width={14} height={14} />}
                </button>
              )}
              {onFeedback && (
                <>
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
                </>
              )}
            </div>
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
