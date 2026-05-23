"use client";

import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";
import { useShallow } from "zustand/react/shallow";
import { useChatStore, createTurn, type Locale, type Citation, type ChatTurn, type Session } from "@/store/useChatStore";
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
import InstallPrompt from "@/components/InstallPrompt";
import { LoadingDots, WifiOffIcon, HeartIcon, MapPinIcon, StethoscopeIcon, SearchIcon, VolumeIcon } from "@/components/Icons";
import { useAgenticTriage } from "@/hooks/useApi";
import VoiceModal from "@/components/VoiceModal";
import VoicePersonnelModal from "@/components/VoicePersonnelModal";

// Lazy-loaded panels — only fetched when opened (reduces initial bundle ~40KB)
const ClinicFinder = lazy(() => import("@/components/ClinicFinder"));
const MedicationReminders = lazy(() => import("@/components/MedicationReminders"));
const SettingsPanel = lazy(() => import("@/components/SettingsPanel"));

const API_BASE = "/api";

const LOCALE_LABELS: Record<string, string> = {
  en: "EN",
  lg: "LG",
  nyn: "NY",
  sw: "SW",
};

const MODE_LABELS: Record<string, { label: string; color: string }> = {
  vht: { label: "VHT Triage", color: "var(--accent-red)" },
  maternal: { label: "Maternal Care", color: "var(--accent-pink)" },
  community: { label: "Community Health", color: "var(--accent-green)" },
};

// ── Proper SSE line parser ────────────────────────────────────────────

interface SSEEvent {
  event: string;
  data: string;
}

function parseSSEBuffer(buffer: string): { events: SSEEvent[]; remaining: string } {
  const events: SSEEvent[] = [];
  // Normalize \r\n to \n, then split on double newline (SSE event boundary)
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const remaining = parts.pop() || "";

  for (const part of parts) {
    if (!part.trim()) continue;
    let eventType = "data";
    let data = "";
    for (const line of part.split("\n")) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        // SSE spec: strip at most ONE leading space from field value
        const raw = line.slice(5);
        const value = raw.startsWith(" ") ? raw.slice(1) : raw;
        data += (data ? "\n" : "") + value;
      }
    }
    // Push event if there's data OR it's a named event (like "done")
    if (data !== "" || eventType !== "data") {
      events.push({ event: eventType, data });
    }
  }
  return { events, remaining };
}

export default function HomePage() {
  const chat = useChatStore((s) => s.chat);
  const addTurn = useChatStore((s) => s.addTurn);
  const clearChat = useChatStore((s) => s.clearChat); // used by session mgmt
  const message = useChatStore((s) => s.message);
  const setMessage = useChatStore((s) => s.setMessage);
  const mode = useChatStore((s) => s.mode);
  const locale = useChatStore((s) => s.locale);
  const setLocale = useChatStore((s) => s.setLocale);
  const isOnline = useChatStore((s) => s.isOnline);
  const setOnline = useChatStore((s) => s.setOnline);
  const pregnancyWeek = useChatStore((s) => s.pregnancyWeek);
  const sessions = useChatStore(useShallow((s) => s.sessions));
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const sidebarOpen = useChatStore((s) => s.sidebarOpen);
  const createNewSession = useChatStore((s) => s.createNewSession);
  const switchSession = useChatStore((s) => s.switchSession);
  const deleteSession = useChatStore((s) => s.deleteSession);
  const setSidebarOpen = useChatStore((s) => s.setSidebarOpen);

  const setVoicePersonnelOpen = useChatStore((s) => s.setVoicePersonnelOpen);
  const speechState = useChatStore((s) => s.speechState);

  const [isStreaming, setIsStreaming] = useState(false);
  const [showClinics, setShowClinics] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [agenticMode, setAgenticMode] = useState(false);
  const [syncToast, setSyncToast] = useState<string | null>(null);
  const [swUpdate, setSwUpdate] = useState(false);
  const [sessionSearch, setSessionSearch] = useState("");
  const [, startTransition] = useTransition();
  const chatEndRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const sessionIdRef = useRef<string>("");
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const streamTurnIdRef = useRef<string>("");
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const chatAreaRef = useRef<HTMLDivElement>(null);
  const userScrolledRef = useRef(false);

  const { data: health } = useHealth();
  const triageMutation = useAgenticTriage();
  const feedback = useFeedback();

  const visibleSessions = useMemo(() => {
    const q = sessionSearch.trim().toLowerCase();
    const sorted = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);
    if (!q) return sorted;
    return sorted.filter((s) => s.title.toLowerCase().includes(q));
  }, [sessions, sessionSearch]);

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

  // Scroll tracking — show scroll-to-bottom when user scrolls up
  useEffect(() => {
    const el = chatAreaRef.current;
    if (!el) return;
    const onScroll = () => {
      const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
      const atBottom = gap < 80;
      setShowScrollBtn(!atBottom && chat.length > 0);
      userScrolledRef.current = !atBottom;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [chat.length]);

  // Debounced auto-scroll — respects user scroll position
  useEffect(() => {
    if (userScrolledRef.current) return;
    if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
    scrollTimerRef.current = setTimeout(() => {
      chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 100);
    return () => { if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current); };
  }, [chat]);

  const scrollToBottom = useCallback(() => {
    userScrolledRef.current = false;
    setShowScrollBtn(false);
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  // Escape key closes open panels
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (sidebarOpen) setSidebarOpen(false);
        else if (showClinics) setShowClinics(false);
        else if (showSettings) setShowSettings(false);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [sidebarOpen, showClinics, showSettings, setSidebarOpen]);

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

  // Listen for SW update event
  useEffect(() => {
    const handler = () => setSwUpdate(true);
    window.addEventListener("musawo-sw-update", handler);
    return () => window.removeEventListener("musawo-sw-update", handler);
  }, []);

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
            triage: (result.triage as ChatTurn["triage"]) ?? undefined,
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
            citations: (cached.citations as Citation[]) ?? undefined,
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
              // Accumulate all data (including whitespace-only tokens)
              fullAnswer += sse.data;
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

      // If stream produced no content, fall back to sync API
      if (!fullAnswer.trim()) {
        // Remove the empty stream turn
        useChatStore.setState((s) => ({
          chat: s.chat.filter((t) => t.id !== turnId),
        }));
        streamTurnIdRef.current = "";
        const syncRes = await fetch(`${API_BASE}/v1/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query, mode, locale,
            session_id: sessionIdRef.current || undefined,
          }),
        });
        const syncData = await syncRes.json();
        if (syncData.session_id) {
          sessionIdRef.current = syncData.session_id;
          sessionStorage.setItem("musawo-session-id", syncData.session_id);
        }
        addTurn(
          createTurn("assistant", syncData.answer, {
            mode: syncData.mode,
            citations: syncData.citations,
            faithfulnessScore: syncData.faithfulness_score,
            triage: syncData.triage,
            escalationRequired: syncData.escalation_required,
            confidence: syncData.confidence,
          })
        );
      } else {
        // Finalize: atomic update with all metadata
        useChatStore.setState((s) => {
          const idx = s.chat.findIndex((t) => t.id === turnId);
          if (idx === -1) return s;
          const updated = [...s.chat];
          updated[idx] = {
            ...updated[idx],
            id: turnId.replace("stream-", "final-"),
            content: fullAnswer,
            citations: ((metadata?.citations as unknown[]) || []) as Citation[],
            faithfulnessScore: groundingData?.faithfulness_score as number | undefined,
            groundingWarning: groundingData?.grounding_warning as boolean | undefined,
            escalationRequired:
              (groundingData?.escalation_required as boolean) ||
              ((metadata?.red_flags as string[])?.length > 0),
            triage: metadata?.triage as ChatTurn["triage"],
            confidence: undefined,
          };
          return { chat: updated };
        });
        streamTurnIdRef.current = "";

        // Sync streamed content back to the active session
        useChatStore.setState((s) => {
          if (!s.activeSessionId) return s;
          return {
            sessions: s.sessions.map((sess) =>
              sess.id === s.activeSessionId
                ? { ...sess, chat: s.chat, updatedAt: Date.now() }
                : sess
            ),
          };
        });

        // Cache for offline
        cacheResponse(query, mode, fullAnswer, (metadata?.citations as unknown[]) || []);
      }

    } catch (err) {
      console.error("Stream failed, trying sync fallback:", err);
      streamTurnIdRef.current = "";

      // Remove the orphaned empty stream turn before adding fallback
      useChatStore.setState((s) => ({
        chat: s.chat.filter((t) => !(t.id.startsWith("stream-") && !t.content)),
      }));

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

  // ── Session management ──────────────────────────────────────────────

  const handleNewChat = useCallback(() => {
    createNewSession();
    setSidebarOpen(false);
    sessionIdRef.current = "";
    sessionStorage.removeItem("musawo-session-id");
    requestAnimationFrame(() => composerRef.current?.focus());
  }, [createNewSession, setSidebarOpen]);

  const handleSwitchSession = useCallback(
    (id: string) => {
      switchSession(id);
      setSidebarOpen(false);
      sessionIdRef.current = "";
      sessionStorage.removeItem("musawo-session-id");
    },
    [switchSession, setSidebarOpen]
  );

  const handleDeleteSession = useCallback(
    (id: string) => {
      if (window.confirm("Delete this conversation?")) deleteSession(id);
    },
    [deleteSession]
  );

  const handleExportSession = useCallback((sess: Session) => {
    const lines = sess.chat.map((t) => {
      const time = new Date(t.timestamp).toLocaleString();
      const role = t.role === "user" ? "You" : "Musawo";
      return `[${time}] ${role}:\n${t.content}`;
    });
    const text = `Musawo AI — ${sess.title}\nMode: ${sess.mode}\nExported: ${new Date().toISOString()}\n\n${lines.join("\n\n---\n\n")}`;
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `musawo-${sess.title.replace(/[^a-zA-Z0-9]/g, "_").slice(0, 30)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <main id="main-content" className={`app${chat.length === 0 ? " app--empty" : ""}${isStreaming ? " streaming" : ""}`}>
      {/* PWA install prompt */}
      <InstallPrompt />

      {/* Sidebar */}
      {sidebarOpen && <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} aria-hidden="true" />}
      <aside className={`sidebar${sidebarOpen ? " open" : ""}`}>
        <div className="sidebar-header">
          <h2>Conversations</h2>
          <button className="panel-close" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar">
            &times;
          </button>
        </div>
        <button className="new-chat-btn" onClick={handleNewChat}>
          <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
          New Chat
        </button>
        <div className="sidebar-search">
          <SearchIcon width={14} height={14} />
          <input
            type="text"
            className="sidebar-search-input"
            placeholder="Search conversations..."
            value={sessionSearch}
            onChange={(e) => setSessionSearch(e.target.value)}
            aria-label="Search conversations"
          />
        </div>
        <div className="session-list">
          {sessions.length === 0 && <p className="session-empty">No conversations yet</p>}
          {visibleSessions.map((sess) => (
            <div
              key={sess.id}
              className={`session-item${sess.id === activeSessionId ? " active" : ""}`}
              onClick={() => handleSwitchSession(sess.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleSwitchSession(sess.id); } }}
            >
              <div className="session-title">{sess.title || "New Chat"}</div>
              <div className="session-meta">
                <span className="session-time">
                  {new Date(sess.updatedAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </span>
                <span className={`session-mode mode-${sess.mode}`}>{sess.mode}</span>
                <button
                  className="session-export"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleExportSession(sess);
                  }}
                  aria-label="Export conversation"
                  title="Export"
                >
                  <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" x2="12" y1="15" y2="3" />
                  </svg>
                </button>
                <button
                  className="session-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteSession(sess.id);
                  }}
                  aria-label="Delete conversation"
                >
                  &times;
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* Header — Grok-inspired: clean, minimal, functional */}
      <header className="header">
        <div className="header-left">
          <button
            className="sidebar-toggle"
            onClick={() => { console.log("toggle sidebar", !sidebarOpen); setSidebarOpen(!sidebarOpen); }}
            aria-label="Toggle conversations"
            type="button"
          >
            <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M3 12h18M3 6h18M3 18h18" />
            </svg>
          </button>
          <div className="logo-orb">
            <HeartIcon width={20} height={20} />
          </div>
          <div>
            <h1 className="app-title">Musawo AI</h1>
            <div className="header-meta">
              <span
                className="mode-badge-header"
                style={{ "--badge-color": MODE_LABELS[mode].color } as React.CSSProperties}
              >
                {MODE_LABELS[mode].label}
              </span>
              {speechState === "listening" && <span className="voice-active-dot" />}
              {!isOnline && (
                <span className="offline-badge" role="status" aria-live="assertive">
                  <WifiOffIcon width={12} height={12} />
                  Offline
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="header-right">
          {/* Locale switcher — always visible */}
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

          {/* Clinic finder */}
          <button
            className="header-icon-btn"
            onClick={() => setShowClinics((v) => !v)}
            aria-label="Find nearest clinic"
            aria-pressed={showClinics}
            title="Clinics"
          >
            <MapPinIcon width={18} height={18} />
          </button>

          {/* Settings (voice, font, etc.) */}
          <button
            className="header-icon-btn"
            onClick={() => setShowSettings((v) => !v)}
            aria-label="Settings"
            aria-pressed={showSettings}
            title="Settings"
          >
            <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z" />
            </svg>
          </button>
        </div>
      </header>

      {/* Sync toast notification */}
      {syncToast && (
        <div className="sync-toast" role="status" aria-live="polite">
          {syncToast}
        </div>
      )}

      {/* SW update notification */}
      {swUpdate && (
        <div className="sw-update-toast" role="status">
          <span>A new version is available</span>
          <button onClick={() => { setSwUpdate(false); window.location.reload(); }}>
            Update
          </button>
          <button className="sw-dismiss" onClick={() => setSwUpdate(false)} aria-label="Dismiss">
            &times;
          </button>
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

      {/* Panels (lazy-loaded slide-over with backdrop) */}
      {showSettings && (
        <Suspense fallback={null}>
          <div className="panel-backdrop" onClick={() => setShowSettings(false)} />
          <SettingsPanel onClose={() => setShowSettings(false)} />
        </Suspense>
      )}
      {showClinics && (
        <Suspense fallback={null}>
          <div className="panel-backdrop" onClick={() => setShowClinics(false)} />
          <ClinicFinder onClose={() => setShowClinics(false)} />
        </Suspense>
      )}

      {/* Maternal tracker — only show when empty or maternal mode with few messages */}
      {mode === "maternal" && chat.length <= 2 && <MaternalTracker />}

      {/* Chat area */}
      <div className="chat-area" ref={chatAreaRef} role="region" aria-live="polite" aria-label="Health conversation">
        {/* Empty state — Grok-inspired: compact, input-focused */}
        {chat.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">
              <HeartIcon width={36} height={36} />
            </div>
            <h2 className="empty-state-title">Musawo AI</h2>
            <p className="empty-state-subtitle">
              Your community health navigator for rural Uganda.
            </p>
          </div>
        )}

        {chat.length === 0 && <StarterPrompts />}

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

      {/* Scroll to bottom */}
      {showScrollBtn && (
        <button className="scroll-to-bottom" onClick={scrollToBottom} aria-label="Scroll to latest">
          <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path d="M12 5v14M19 12l-7 7-7-7" />
          </svg>
        </button>
      )}

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isStreaming} ref={composerRef} />

      {/* Mobile FAB — new chat (visible only when in a session on mobile) */}
      {chat.length > 0 && (
        <button className="mobile-fab" onClick={handleNewChat} aria-label="New chat">
          <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      )}

      {/* Voice modal */}
      <VoiceModal />
      <VoicePersonnelModal />

      {/* Emergency footer */}
      <footer className="emergency-footer">
        <a href="tel:0800100263" className="emergency-link">
          Emergency? Call <strong>0800 100 263</strong> (toll-free)
        </a>
      </footer>
    </main>
  );
}
