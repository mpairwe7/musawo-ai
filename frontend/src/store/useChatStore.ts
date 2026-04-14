"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

// ── Types ──────────────────────────────────────────────────────────────

export type Mode = "vht" | "maternal" | "community";
export type Locale = "en" | "lg" | "nyn" | "sw";
export type SpeechState = "idle" | "listening" | "unavailable" | "error";

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

  // Speech
  speechState: SpeechState;
  setSpeechState: (s: SpeechState) => void;

  // Maternal tracking
  pregnancyWeek: number | null;
  setPregnancyWeek: (w: number | null) => void;

  // Online status
  isOnline: boolean;
  setOnline: (o: boolean) => void;
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

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      message: "",
      setMessage: (message) => set({ message }),

      chat: [],
      addTurn: (turn) =>
        set((s) => ({
          chat: [...s.chat.slice(-(MAX_TURNS - 1)), turn],
        })),
      clearChat: () => set({ chat: [] }),

      mode: "community",
      setMode: (mode) => set({ mode }),

      locale: "en",
      setLocale: (locale) => set({ locale }),

      speechState: "idle",
      setSpeechState: (speechState) => set({ speechState }),

      pregnancyWeek: null,
      setPregnancyWeek: (pregnancyWeek) => set({ pregnancyWeek }),

      isOnline: true,
      setOnline: (isOnline) => set({ isOnline }),
    }),
    {
      name: "musawo-chat",
      storage: createJSONStorage(() =>
        typeof window !== "undefined" ? localStorage : ({
          getItem: () => null,
          setItem: () => {},
          removeItem: () => {},
        } as Storage)
      ),
      partialize: (s) => ({
        chat: s.chat,
        mode: s.mode,
        locale: s.locale,
        pregnancyWeek: s.pregnancyWeek,
      }),
    }
  )
);
