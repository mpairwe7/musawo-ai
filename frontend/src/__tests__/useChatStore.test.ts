/**
 * Tests for Zustand chat store — state management correctness.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore, createTurn } from "../store/useChatStore";

describe("useChatStore", () => {
  beforeEach(() => {
    // Reset store to initial state
    useChatStore.setState({
      message: "",
      chat: [],
      mode: "community",
      locale: "en",
      speechState: "idle",
      pregnancyWeek: null,
      isOnline: true,
    });
  });

  it("starts with empty chat", () => {
    expect(useChatStore.getState().chat).toHaveLength(0);
  });

  it("adds turns to chat", () => {
    const turn = createTurn("user", "Hello");
    useChatStore.getState().addTurn(turn);
    expect(useChatStore.getState().chat).toHaveLength(1);
    expect(useChatStore.getState().chat[0].role).toBe("user");
  });

  it("limits chat to 200 turns", () => {
    for (let i = 0; i < 210; i++) {
      useChatStore.getState().addTurn(createTurn("user", `msg ${i}`));
    }
    expect(useChatStore.getState().chat.length).toBeLessThanOrEqual(200);
  });

  it("clears chat", () => {
    useChatStore.getState().addTurn(createTurn("user", "test"));
    useChatStore.getState().clearChat();
    expect(useChatStore.getState().chat).toHaveLength(0);
  });

  it("sets mode", () => {
    useChatStore.getState().setMode("vht");
    expect(useChatStore.getState().mode).toBe("vht");
  });

  it("sets locale", () => {
    useChatStore.getState().setLocale("lg");
    expect(useChatStore.getState().locale).toBe("lg");
  });

  it("sets pregnancy week", () => {
    useChatStore.getState().setPregnancyWeek(28);
    expect(useChatStore.getState().pregnancyWeek).toBe(28);
  });

  it("sets online status", () => {
    useChatStore.getState().setOnline(false);
    expect(useChatStore.getState().isOnline).toBe(false);
  });

  it("sets message", () => {
    useChatStore.getState().setMessage("test query");
    expect(useChatStore.getState().message).toBe("test query");
  });
});

describe("createTurn", () => {
  it("creates turn with unique id", () => {
    const t1 = createTurn("user", "hello");
    const t2 = createTurn("user", "hello");
    expect(t1.id).not.toBe(t2.id);
  });

  it("sets role and content", () => {
    const turn = createTurn("assistant", "ORS dosage is...");
    expect(turn.role).toBe("assistant");
    expect(turn.content).toBe("ORS dosage is...");
  });

  it("includes timestamp", () => {
    const before = Date.now();
    const turn = createTurn("user", "test");
    expect(turn.timestamp).toBeGreaterThanOrEqual(before);
  });

  it("merges extra fields", () => {
    const turn = createTurn("assistant", "response", {
      mode: "vht",
      confidence: 0.85,
    });
    expect(turn.mode).toBe("vht");
    expect(turn.confidence).toBe(0.85);
  });
});
