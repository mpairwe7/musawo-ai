"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

const API_BASE = "/api";

// ── Health check ──────────────────────────────────────────────────────

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/health`);
      if (!res.ok) throw new Error("Health check failed");
      return res.json();
    },
    refetchInterval: 60_000,
    retry: 1,
  });
}

// ── Modes ─────────────────────────────────────────────────────────────

export function useModes() {
  return useQuery({
    queryKey: ["modes"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/v1/modes`);
      if (!res.ok) throw new Error("Failed to fetch modes");
      return res.json();
    },
    staleTime: Infinity,
  });
}

// ── Facilities ────────────────────────────────────────────────────────

export function useFacilities(district?: string) {
  return useQuery({
    queryKey: ["facilities", district],
    queryFn: async () => {
      const params = district ? `?district=${encodeURIComponent(district)}` : "";
      const res = await fetch(`${API_BASE}/v1/facilities${params}`);
      if (!res.ok) throw new Error("Failed to fetch facilities");
      return res.json();
    },
    staleTime: 300_000, // 5 minutes
  });
}

// ── Emergency contacts ────────────────────────────────────────────────

export function useEmergencyContacts() {
  return useQuery({
    queryKey: ["emergency-contacts"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/v1/emergency-contacts`);
      if (!res.ok) throw new Error("Failed to fetch contacts");
      return res.json();
    },
    staleTime: Infinity,
  });
}

// ── Agentic triage ───────────────────────────────────────────────────

export interface TriageResponse {
  response: string;
  phase: string;
  triage: Record<string, unknown> | null;
  follow_up_question: string | null;
  assessment_complete: boolean;
  session_id: string;
}

export function useAgenticTriage() {
  return useMutation({
    mutationFn: async (data: {
      query: string;
      mode: string;
      locale: string;
      session_id?: string;
    }): Promise<TriageResponse> => {
      const res = await fetch(`${API_BASE}/v1/triage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(`Triage failed: ${res.status}`);
      return res.json();
    },
  });
}

// ── Feedback ──────────────────────────────────────────────────────────

export function useFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      session_id: string;
      turn_id: string;
      rating: number;
      comment?: string;
    }) => {
      const res = await fetch(`${API_BASE}/v1/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error("Feedback failed");
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["health"] });
    },
  });
}
