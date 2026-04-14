"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useTransition,
} from "react";
import { useChatStore, createTurn, type Locale } from "@/store/useChatStore";
import { useHealth, useFeedback } from "@/hooks/useApi";
import { registerSW, requestBackgroundSync } from "@/lib/serviceWorkerRegistration";
import {
  cacheResponse,
  getCachedResponse,
  queueOfflineMessage,
} from "@/lib/offlineDb";
import ChatMessage from "@/components/ChatMessage";
import ChatInput from "@/components/ChatInput";
import ModeSelector from "@/components/ModeSelector";
import StarterPrompts from "@/components/StarterPrompts";
import MaternalTracker from "@/components/MaternalTracker";
import ClinicFinder from "@/components/ClinicFinder";
import MedicationReminders from "@/components/MedicationReminders";
import SettingsPanel from "@/components/SettingsPanel";
import InstallPrompt from "@/components/InstallPrompt";
import { LoadingDots, WifiOffIcon, HeartIcon, MapPinIcon, StethoscopeIcon } from "@/components/Icons";
import { useAgenticTriage } from "@/hooks/useApi";

const API_BASE = "/api";

const LOCALE_LABELS: Record<string, string> = {
  en: "EN",
  lg: "LG",
  nyn: "NY",
  sw: "SW",
};

// ── Proper SSE line parser ────────────────────────────────────────────

interface SSEEvent {
  event: string;
  data: string;
}

function parseSSEBuffer(buffer: string): { events: SSEEvent[]; remaining: string } {
  const events: SSEEvent[] = [];
  // SSE events are separated by double newlines
  const parts = buffer.split("\n\n");
  const remaining = parts.pop() || "";

  for (const part of parts) {
    if (!part.trim()) continue;
    let eventType = "data";
    let data = "";
    for (const line of part.split("\n")) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        data += (data ? "\n" : "") + line.slice(5).trim();
      }
    }
    if (data || eventType !== "data") {
      events.push({ event: eventType, data });
    }
  }
  return { events, remaining };
}

export default function HomePage() {
  const chat = useChatStore((s) => s.chat);
  const addTurn = useChatStore((s) => s.addTurn);
  const clearChat = useChatStore((s) => s.clearChat);
  const message = useChatStore((s) => s.message);
  const setMessage = useChatStore((s) => s.setMessage);
  const mode = useChatStore((s) => s.mode);
  const locale = useChatStore((s) => s.locale);
  const setLocale = useChatStore((s) => s.setLocale);
  const isOnline = useChatStore((s) => s.isOnline);
  const setOnline = useChatStore((s) => s.setOnline);
  const pregnancyWeek = useChatStore((s) => s.pregnancyWeek);

  const [isStreaming, setIsStreaming] = useState(false);
  const [showClinics, setShowClinics] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [agenticMode, setAgenticMode] = useState(false);
  const [syncToast, setSyncToast] = useState<string | null>(null);
  const [, startTransition] = useTransition();
  const chatEndRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const sessionIdRef = useRef<string>("");
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const streamTurnIdRef = useRef<string>("");

  const { data: health } = useHealth();
  const triageMutation = useAgenticTriage();
  const feedback = useFeedback();

  // Register service worker on mount
  useEffect(() => {
    registerSW();
  }, []);

  // Online/offline detection
  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    setOnline(navigator.onLine);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, [setOnline]);

  // Restore session ID
  useEffect(() => {
    const stored = sessionStorage.getItem("musawo-session-id");
    if (stored) sessionIdRef.current = stored;
  }, []);

  // Dynamic html lang attribute for screen readers
  useEffect(() => {
    const langMap: Record<string, string> = { en: "en", lg: "lg", nyn: "nyn", sw: "sw" };
    document.documentElement.lang = langMap[locale] || "en";
  }, [locale]);

  // Debounced auto-scroll — only fires once per 100ms during streaming
  useEffect(() => {
    if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
    scrollTimerRef.current = setTimeout(() => {
      chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 100);
    return () => { if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current); };
  }, [chat]);

  // Escape key closes open panels
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showClinics) setShowClinics(false);
        else if (showSettings) setShowSettings(false);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [showClinics, showSettings]);

  // Listen for background sync completion
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type === "SYNC_COMPLETE" && e.data.synced > 0) {
        setSyncToast(`${e.data.synced} offline message(s) synced`);
        setTimeout(() => setSyncToast(null), 4000);
      }
    };
    navigator.serviceWorker?.addEventListener("message", handler);
    return () => navigator.serviceWorker?.removeEventListener("message", handler);
  }, []);

  // Auto-enable agentic mode for VHT
  useEffect(() => {
    if (mode === "vht") setAgenticMode(true);
    else setAgenticMode(false);
  }, [mode]);

  // ── Send message ────────────────────────────────────────────────────

  const handleSend = useCallback(async () => {
    const query = message.trim();
    if (!query || isStreaming) return;

    setMessage("");
    addTurn(createTurn("user", query, { mode }));
    setIsStreaming(true);

    // ── Agentic triage path (VHT mode) ──────────────────────────
    if (agenticMode && mode === "vht" && isOnline) {
      try {
        const result = await triageMutation.mutateAsync({
          query,
          mode,
          locale,
          session_id: sessionIdRef.current || undefined,
        });
        if (result.session_id) {
          sessionIdRef.current = result.session_id;
          sessionStorage.setItem("musawo-session-id", result.session_id);
        }
        addTurn(
          createTurn("assistant", result.response, {
            mode,
            triage: result.triage as unknown as undefined,
            escalationRequired: result.triage?.severity === "red",
          })
        );
      } catch {
        addTurn(
          createTurn("assistant",
            "Triage service unavailable. Falling back to standard mode.\n\n" +
            "For emergencies, call **0800 100 263**.",
            { mode }
          )
        );
      }
      setIsStreaming(false);
      composerRef.current?.focus();
      return;
    }

    // Offline path: check cache or queue
    if (!isOnline) {
      const cached = await getCachedResponse(query, mode);
      if (cached) {
        addTurn(
          createTurn("assistant", cached.response, {
            mode,
            citations: cached.citations as unknown as undefined,
          })
        );
      } else {
        await queueOfflineMessage(query, mode, locale);
        requestBackgroundSync();
        addTurn(
          createTurn("assistant",
            "You are offline. Your message has been saved and will be sent when you reconnect.\n\n" +
            "For emergencies, call **0800 100 263** (toll-free).",
            { mode }
          )
        );
      }
      setIsStreaming(false);
      return;
    }

    // Online path: SSE streaming with proper parser
    try {
      const res = await fetch(`${API_BASE}/v1/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          mode,
          locale,
          session_id: sessionIdRef.current || undefined,
          pregnancy_week: mode === "maternal" ? pregnancyWeek : undefined,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No reader");

      const decoder = new TextDecoder();
      let sseBuffer = "";
      let fullAnswer = "";
      let metadata: Record<string, unknown> | null = null;
      let groundingData: Record<string, unknown> | null = null;

      // Create streaming turn placeholder with atomic update
      const turnId = `stream-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      streamTurnIdRef.current = turnId;
      addTurn(createTurn("assistant", "", { mode, id: turnId } as Record<string, unknown>));
      // Override the ID to our stream marker
      useChatStore.setState((s) => {
        const last = s.chat[s.chat.length - 1];
        if (!last) return s;
        return { chat: [...s.chat.slice(0, -1), { ...last, id: turnId }] };
      });

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        sseBuffer += decoder.decode(value, { stream: true });
        const { events, remaining } = parseSSEBuffer(sseBuffer);
        sseBuffer = remaining;

        for (const sse of events) {
          switch (sse.event) {
            case "metadata":
              try {
                metadata = JSON.parse(sse.data);
                if (metadata?.session_id) {
                  sessionIdRef.current = metadata.session_id as string;
                  sessionStorage.setItem("musawo-session-id", metadata.session_id as string);
                }
              } catch { /* ignore parse errors */ }
              break;

            case "grounding":
              try { groundingData = JSON.parse(sse.data); } catch { /* ignore */ }
              break;

            case "data":
              if (sse.data) fullAnswer += sse.data;
              break;

            case "error":
              fullAnswer = sse.data || "An error occurred.";
              break;

            case "done":
              break;
          }
        }

        // Atomic streaming turn update via functional setState
        if (fullAnswer) {
          const currentAnswer = fullAnswer;
          useChatStore.setState((s) => {
            const idx = s.chat.findIndex((t) => t.id === turnId);
            if (idx === -1) return s;
            const updated = [...s.chat];
            updated[idx] = { ...updated[idx], content: currentAnswer };
            return { chat: updated };
          });
        }
      }

      // Finalize: atomic update with all metadata
      useChatStore.setState((s) => {
        const idx = s.chat.findIndex((t) => t.id === turnId);
        if (idx === -1) return s;
        const updated = [...s.chat];
        updated[idx] = {
          ...updated[idx],
          id: turnId.replace("stream-", "final-"),
          content: fullAnswer,
          citations: (metadata?.citations as unknown[]) || [],
          faithfulnessScore: groundingData?.faithfulness_score as number | undefined,
          groundingWarning: groundingData?.grounding_warning as boolean | undefined,
          escalationRequired:
            (groundingData?.escalation_required as boolean) ||
            ((metadata?.red_flags as string[])?.length > 0),
          triage: metadata?.triage as unknown as undefined,
          confidence: undefined,
        };
        return { chat: updated };
      });
      streamTurnIdRef.current = "";

      // Cache for offline
      if (fullAnswer) {
        cacheResponse(query, mode, fullAnswer, (metadata?.citations as unknown[]) || []);
      }

    } catch (err) {
      console.error("Stream failed, trying sync fallback:", err);
      streamTurnIdRef.current = "";

      // Fallback: sync API
      try {
        const res = await fetch(`${API_BASE}/v1/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query, mode, locale,
            session_id: sessionIdRef.current || undefined,
          }),
        });
        const data = await res.json();

        if (data.session_id) {
          sessionIdRef.current = data.session_id;
          sessionStorage.setItem("musawo-session-id", data.session_id);
        }

        addTurn(
          createTurn("assistant", data.answer, {
            mode: data.mode,
            citations: data.citations,
            faithfulnessScore: data.faithfulness_score,
            triage: data.triage,
            escalationRequired: data.escalation_required,
            confidence: data.confidence,
          })
        );
      } catch {
        addTurn(
          createTurn("assistant",
            "I'm having trouble connecting to the server. " +
            "Please try again, or call the health hotline: **0800 100 263**.",
            { mode }
          )
        );
      }
    } finally {
      setIsStreaming(false);
      // Restore focus to input after every response
      requestAnimationFrame(() => composerRef.current?.focus());
    }
  }, [message, mode, locale, isOnline, isStreaming, pregnancyWeek, agenticMode, addTurn, setMessage, triageMutation]);

  // ── Feedback handler ────────────────────────────────────────────────

  const handleFeedback = useCallback(
    (turnId: string, rating: number) => {
      feedback.mutate({
        session_id: sessionIdRef.current,
        turn_id: turnId,
        rating,
      });
    },
    [feedback]
  );

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <main id="main-content" className="app">
      {/* PWA install prompt */}
      <InstallPrompt />

      {/* Header */}
      <header className="header">
        <div className="header-left">
          <HeartIcon width={28} height={28} className="logo-icon" />
          <div>
            <h1 className="app-title">Musawo AI</h1>
            <p className="app-subtitle">Community Health Navigator</p>
          </div>
        </div>

        <div className="header-right">
          {/* Online status */}
          {!isOnline && (
            <span className="offline-badge" role="status" aria-live="assertive">
              <WifiOffIcon width={14} height={14} />
              Offline
            </span>
          )}

          {/* Service status */}
          {health && (
            <span
              className={`status-dot ${health.status === "ok" ? "online" : "degraded"}`}
              title={`Service: ${health.status}`}
              role="status"
              aria-label={`Service ${health.status}`}
            />
          )}

          {/* Clear chat */}
          {chat.length > 0 && (
            <button
              className="header-icon-btn"
              onClick={() => { if (window.confirm("Clear all messages?")) clearChat(); }}
              aria-label="Clear chat"
              title="Clear chat"
            >
              <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          )}

          {/* Clinic finder toggle */}
          <button
            className="header-icon-btn"
            onClick={() => setShowClinics((v) => !v)}
            aria-label="Find nearest clinic"
            aria-pressed={showClinics}
          >
            <MapPinIcon width={18} height={18} />
          </button>

          {/* Settings toggle */}
          <button
            className="header-icon-btn"
            onClick={() => setShowSettings((v) => !v)}
            aria-label="Settings"
            aria-pressed={showSettings}
          >
            <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z" />
            </svg>
          </button>

          {/* Locale switcher */}
          <div className="locale-switch" role="radiogroup" aria-label="Language">
            {(["en", "lg", "nyn", "sw"] as Locale[]).map((l) => (
              <button
                key={l}
                role="radio"
                aria-checked={locale === l}
                className={`locale-btn ${locale === l ? "active" : ""}`}
                onClick={() => startTransition(() => setLocale(l))}
              >
                {LOCALE_LABELS[l]}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Sync toast notification */}
      {syncToast && (
        <div className="sync-toast" role="status" aria-live="polite">
          {syncToast}
        </div>
      )}

      {/* Offline warning banner — prominent, blocks-style */}
      {!isOnline && (
        <div className="offline-banner" role="alert">
          <WifiOffIcon width={18} height={18} />
          <div>
            <strong>You are offline</strong>
            <p>Responses will come from cached data. For emergencies, call <a href="tel:0800100263">0800 100 263</a></p>
          </div>
        </div>
      )}

      {/* Mode selector */}
      <ModeSelector />

      {/* Agentic triage toggle (VHT mode) */}
      {mode === "vht" && (
        <div className="agentic-toggle">
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={agenticMode}
              onChange={(e) => setAgenticMode(e.target.checked)}
              className="toggle-input"
            />
            <span className="toggle-switch" />
            <StethoscopeIcon width={16} height={16} />
            <span>Guided Assessment (iCCM Agent)</span>
          </label>
          {agenticMode && (
            <p className="agentic-hint">
              I&apos;ll guide you step-by-step through the iCCM triage protocol: Assess, Classify, Treat or Refer.
            </p>
          )}
        </div>
      )}

      {/* Panels */}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
      {showClinics && <ClinicFinder onClose={() => setShowClinics(false)} />}

      {/* Maternal tracker (only in maternal mode) */}
      <MaternalTracker />

      {/* Medication reminders (community mode) */}
      {mode === "community" && <MedicationReminders />}

      {/* Chat area */}
      <div className="chat-area" role="region" aria-live="polite" aria-label="Health conversation">
        {/* Empty state — show when no messages */}
        {chat.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">
              <HeartIcon width={48} height={48} />
            </div>
            <h2 className="empty-state-title">Welcome to Musawo AI</h2>
            <p className="empty-state-subtitle">
              Your community health navigator. Ask me about symptoms, medications,
              maternal care, or child health — in English or Luganda.
            </p>
          </div>
        )}

        <StarterPrompts />

        {chat.map((turn) => (
          <ChatMessage
            key={turn.id}
            turn={turn}
            onFeedback={handleFeedback}
          />
        ))}

        {isStreaming && !streamTurnIdRef.current && (
          <div className="bubble assistant streaming" role="status" aria-label="Musawo is thinking">
            <div className="bubble-header">
              <div className="bubble-header-left">
                <span className="role-avatar assistant">M</span>
                <span className="role-label">Musawo</span>
              </div>
            </div>
            <div className="typing-indicator">
              <LoadingDots />
              <span className="typing-label">Searching health guidelines...</span>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isStreaming} ref={composerRef} />

      {/* Emergency footer */}
      <footer className="emergency-footer">
        <a href="tel:0800100263" className="emergency-link">
          Emergency? Call <strong>0800 100 263</strong> (toll-free)
        </a>
      </footer>
    </main>
  );
}
