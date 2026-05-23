"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

// ── Types ──────────────────────────────────────────────────────────────

export type Mode = "vht" | "maternal" | "community";
export type Locale = "en" | "lg" | "nyn" | "sw";
export type SpeechState = "idle" | "listening" | "unavailable" | "error";

export interface VoicePersona {
  id: string;
  name: string;
  lang: string;
  langCode: string;
  gender: "female" | "male";
  sample: string;
  flag: string;
}

export const VOICE_PERSONAS: VoicePersona[] = [
  { id: "en-f", name: "English \u2014 Female", lang: "English", langCode: "en-US", gender: "female", sample: "Welcome to Musawo AI. How can I help you today?", flag: "\ud83c\uddfa\ud83c\uddec" },
  { id: "en-m", name: "English \u2014 Male", lang: "English", langCode: "en-US", gender: "male", sample: "I am here to help with your health questions.", flag: "\ud83c\uddfa\ud83c\uddec" },
  { id: "lg-f", name: "Luganda \u2014 Female", lang: "Luganda", langCode: "lg-UG", gender: "female", sample: "Tukusanyukidde. Nkuyambe ntya leero?", flag: "\ud83c\uddfa\ud83c\uddec" },
  { id: "nyn-m", name: "Runyankole \u2014 Male", lang: "Runyankole", langCode: "nyn-UG", gender: "male", sample: "Ninyenda kukugumikiriza n\u2019obuhaise bwawe.", flag: "\ud83c\uddfa\ud83c\uddec" },
  { id: "sw-m", name: "Swahili \u2014 Male", lang: "Swahili", langCode: "sw-KE", gender: "male", sample: "Karibu Musawo AI. Naweza kukusaidia vipi?", flag: "\ud83c\uddf0\ud83c\uddea" },
];

export interface Citation {
  ref: string;
  source: string;
  page?: string;
  section?: string;
  passage?: string;
}

export interface RedFlag {
  symptom: string;
  severity: "green" | "yellow" | "red";
  action: string;
  detail: string;
}

export interface TriageResult {
  severity: "green" | "yellow" | "red";
  red_flags: RedFlag[];
  manage_at_home: string[];
  refer_reasons: string[];
  follow_up?: string;
}

// ── Response cleaning (strip LLM chain-of-thought) ──────────────────

const THINKING_SIGNALS = [
  /^(okay|alright|hmm|well|right|sure|let me|now,)/i,
  /^the user (is |want|ask)/i,
  /^i (need|should|also|will|can|have) /i,
  /^(looking at|checking|passage |but it|but the|it (also|doesn|mention))/i,
  /passage \[?\d/i,
  /^so,? (the|i |none|based|from)/i,
  /^since (the|none|it|this|there)/i,
  /^(therefore|however|also|additionally),? (note|the|i )/i,
  /^(the (main|key|relevant) point|the answer|my response)/i,
  /not (list|mention|provide|explain|specify|include)/i,
];

function looksLikeThinking(block: string): boolean {
  const trimmed = block.trimStart();
  if (!trimmed) return true;
  return THINKING_SIGNALS.some((rx) => rx.test(trimmed));
}

export function cleanResponse(text: string): string {
  let cleaned = text.trim();
  if (!cleaned) return cleaned;
  const blocks = cleaned.split('\n\n').filter((b) => b.trim());
  if (blocks.length < 2 || !looksLikeThinking(blocks[0])) return cleaned;
  const tags = blocks.map((b) => looksLikeThinking(b));
  let lastAnswerEnd = blocks.length - 1;
  while (lastAnswerEnd >= 0 && tags[lastAnswerEnd]) lastAnswerEnd--;
  if (lastAnswerEnd < 0) return cleaned;
  let lastAnswerStart = lastAnswerEnd;
  for (let i = lastAnswerEnd - 1; i >= 0; i--) {
    if (!tags[i]) lastAnswerStart = i;
    else break;
  }
  cleaned = blocks.slice(lastAnswerStart).filter((_, i) => !tags[lastAnswerStart + i]).join('\n\n').trim();
  return cleaned || text.trim();
}

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  mode?: Mode;
  citations?: Citation[];
  faithfulnessScore?: number | null;
  triage?: TriageResult | null;
  escalationRequired?: boolean;
  groundingWarning?: boolean;
  confidence?: number;
}

export interface Session {
  id: string;
  title: string;
  mode: Mode;
  chat: ChatTurn[];
  createdAt: number;
  updatedAt: number;
}

interface ChatState {
  // UI state
  message: string;
  setMessage: (m: string) => void;
  chat: ChatTurn[];
  addTurn: (turn: ChatTurn) => void;
  clearChat: () => void;

  // Mode & locale
  mode: Mode;
  setMode: (m: Mode) => void;
  locale: Locale;
  setLocale: (l: Locale) => void;

  // Speech & voice
  speechState: SpeechState;
  setSpeechState: (s: SpeechState) => void;
  voiceModalOpen: boolean;
  setVoiceModalOpen: (open: boolean) => void;
  voicePersonnelOpen: boolean;
  setVoicePersonnelOpen: (open: boolean) => void;
  selectedVoice: string;
  setSelectedVoice: (id: string) => void;
  ttsEnabled: boolean;
  setTtsEnabled: (enabled: boolean) => void;

  // Maternal tracking
  pregnancyWeek: number | null;
  setPregnancyWeek: (w: number | null) => void;

  // Online status
  isOnline: boolean;
  setOnline: (o: boolean) => void;

  // Session management
  sessions: Session[];
  activeSessionId: string | null;
  sidebarOpen: boolean;
  createNewSession: () => void;
  switchSession: (id: string) => void;
  deleteSession: (id: string) => void;
  setSidebarOpen: (open: boolean) => void;
}

// ── Helpers ────────────────────────────────────────────────────────────

export function createTurn(
  role: "user" | "assistant",
  content: string,
  extra?: Partial<ChatTurn>
): ChatTurn {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content,
    timestamp: Date.now(),
    ...extra,
  };
}

// ── Store ──────────────────────────────────────────────────────────────

const MAX_TURNS = 200;
const MAX_SESSIONS = 50;

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      message: "",
      setMessage: (message) => set({ message }),

      chat: [],
      addTurn: (turn) =>
        set((s) => {
          const newChat = [...s.chat.slice(-(MAX_TURNS - 1)), turn];
          let sessions = [...s.sessions];
          let activeId = s.activeSessionId;
          if (!activeId) {
            const id = `s-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
            const title =
              turn.role === "user" ? turn.content.slice(0, 60) : "New Chat";
            sessions = [
              { id, title, mode: s.mode, chat: newChat, createdAt: Date.now(), updatedAt: Date.now() },
              ...sessions,
            ].slice(0, MAX_SESSIONS);
            activeId = id;
          } else {
            sessions = sessions.map((sess) =>
              sess.id === activeId
                ? {
                    ...sess,
                    chat: newChat,
                    updatedAt: Date.now(),
                    title:
                      sess.title === "New Chat" && turn.role === "user"
                        ? turn.content.slice(0, 60)
                        : sess.title,
                  }
                : sess
            );
          }
          return { chat: newChat, sessions, activeSessionId: activeId };
        }),
      clearChat: () => set({ chat: [], activeSessionId: null, message: "" }),

      mode: "community",
      setMode: (mode) => set((s) => (s.mode === mode ? s : { mode })),

      locale: "en",
      setLocale: (locale) => set((s) => (s.locale === locale ? s : { locale })),

      speechState: "idle",
      setSpeechState: (speechState) => set((s) => (s.speechState === speechState ? s : { speechState })),
      voiceModalOpen: false,
      setVoiceModalOpen: (voiceModalOpen) => set((s) => (s.voiceModalOpen === voiceModalOpen ? s : { voiceModalOpen })),
      voicePersonnelOpen: false,
      setVoicePersonnelOpen: (voicePersonnelOpen) => set((s) => (s.voicePersonnelOpen === voicePersonnelOpen ? s : { voicePersonnelOpen })),
      selectedVoice: "en-f",
      setSelectedVoice: (selectedVoice) => set((s) => (s.selectedVoice === selectedVoice ? s : { selectedVoice })),
      ttsEnabled: true,
      setTtsEnabled: (ttsEnabled) => set((s) => (s.ttsEnabled === ttsEnabled ? s : { ttsEnabled })),

      pregnancyWeek: null,
      setPregnancyWeek: (pregnancyWeek) => set((s) => (s.pregnancyWeek === pregnancyWeek ? s : { pregnancyWeek })),

      isOnline: true,
      setOnline: (isOnline) => set((s) => (s.isOnline === isOnline ? s : { isOnline })),

      // Session management
      sessions: [],
      activeSessionId: null,
      sidebarOpen: false,
      createNewSession: () =>
        set((s) => {
          let sessions = s.activeSessionId
            ? s.sessions.map((sess) =>
                sess.id === s.activeSessionId
                  ? { ...sess, chat: s.chat, updatedAt: Date.now() }
                  : sess
              )
            : s.sessions;
          if (s.chat.length === 0 && s.activeSessionId) {
            sessions = sessions.filter((sess) => sess.id !== s.activeSessionId);
          }
          return { chat: [], sessions, activeSessionId: null, message: "" };
        }),
      switchSession: (id) =>
        set((s) => {
          if (id === s.activeSessionId) return s;
          const target = s.sessions.find((sess) => sess.id === id);
          if (!target) return s;
          let sessions = s.activeSessionId
            ? s.sessions.map((sess) =>
                sess.id === s.activeSessionId
                  ? { ...sess, chat: s.chat, updatedAt: Date.now() }
                  : sess
              )
            : s.sessions;
          if (s.chat.length === 0 && s.activeSessionId) {
            sessions = sessions.filter((sess) => sess.id !== s.activeSessionId);
          }
          return {
            chat: target.chat,
            sessions,
            activeSessionId: id,
            mode: target.mode,
            message: "",
          };
        }),
      deleteSession: (id) =>
        set((s) => {
          const sessions = s.sessions.filter((sess) => sess.id !== id);
          if (s.activeSessionId === id) {
            const next = sessions[0];
            return {
              sessions,
              chat: next ? next.chat : [],
              activeSessionId: next ? next.id : null,
            };
          }
          return { sessions };
        }),
      setSidebarOpen: (sidebarOpen) => set((s) => (s.sidebarOpen === sidebarOpen ? s : { sidebarOpen })),
    }),
    {
      name: "musawo-chat",
      storage: createJSONStorage(() =>
        typeof window !== "undefined" ? localStorage : ({
          getItem: () => null,
          setItem: () => {},
          removeItem: () => {},
        } as unknown as Storage)
      ),
      partialize: (s) => ({
        chat: s.chat,
        mode: s.mode,
        locale: s.locale,
        pregnancyWeek: s.pregnancyWeek,
        sessions: s.sessions,
        activeSessionId: s.activeSessionId,
        selectedVoice: s.selectedVoice,
        ttsEnabled: s.ttsEnabled,
      }),
      onRehydrateStorage: () => (state) => {
        // Migrate existing chat data into a session
        if (state && state.chat.length > 0 && state.sessions.length === 0) {
          const id = `s-migrated-${Date.now()}`;
          const firstUser = state.chat.find((t) => t.role === "user");
          state.sessions = [
            {
              id,
              title: firstUser ? firstUser.content.slice(0, 60) : "Previous Chat",
              mode: state.mode,
              chat: state.chat,
              createdAt: state.chat[0]?.timestamp || Date.now(),
              updatedAt: Date.now(),
            },
          ];
          state.activeSessionId = id;
        }
      },
    }
  )
);
