/**
 * Tests for SSE parser used in page.tsx streaming.
 * Validates correct parsing of Server-Sent Events protocol.
 */

import { describe, it, expect } from "vitest";

// Extract parseSSEBuffer from page.tsx logic for testing
interface SSEEvent {
  event: string;
  data: string;
}

function parseSSEBuffer(buffer: string): {
  events: SSEEvent[];
  remaining: string;
} {
  const events: SSEEvent[] = [];
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

describe("parseSSEBuffer", () => {
  it("parses single data event", () => {
    const { events, remaining } = parseSSEBuffer("data: hello world\n\n");
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("data");
    expect(events[0].data).toBe("hello world");
    expect(remaining).toBe("");
  });

  it("parses named event with data", () => {
    const { events } = parseSSEBuffer("event: metadata\ndata: {\"mode\":\"vht\"}\n\n");
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("metadata");
    expect(events[0].data).toBe("{\"mode\":\"vht\"}");
  });

  it("handles multiple events in one buffer", () => {
    const buf = "event: metadata\ndata: {}\n\ndata: token1\n\ndata: token2\n\n";
    const { events } = parseSSEBuffer(buf);
    expect(events).toHaveLength(3);
    expect(events[0].event).toBe("metadata");
    expect(events[1].data).toBe("token1");
    expect(events[2].data).toBe("token2");
  });

  it("preserves incomplete chunk as remaining", () => {
    const { events, remaining } = parseSSEBuffer("data: complete\n\ndata: incom");
    expect(events).toHaveLength(1);
    expect(remaining).toBe("data: incom");
  });

  it("handles empty buffer", () => {
    const { events, remaining } = parseSSEBuffer("");
    expect(events).toHaveLength(0);
    expect(remaining).toBe("");
  });

  it("handles grounding event with JSON", () => {
    const buf = 'event: grounding\ndata: {"faithfulness_score":0.85,"grounding_warning":false}\n\n';
    const { events } = parseSSEBuffer(buf);
    expect(events).toHaveLength(1);
    const parsed = JSON.parse(events[0].data);
    expect(parsed.faithfulness_score).toBe(0.85);
    expect(parsed.grounding_warning).toBe(false);
  });

  it("handles done event with empty data", () => {
    const { events } = parseSSEBuffer("event: done\ndata: \n\n");
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("done");
  });

  it("handles multiline data fields", () => {
    const buf = "data: line one\ndata: line two\n\n";
    const { events } = parseSSEBuffer(buf);
    expect(events).toHaveLength(1);
    expect(events[0].data).toBe("line one\nline two");
  });

  it("ignores blank lines between events", () => {
    const buf = "data: first\n\n\n\ndata: second\n\n";
    const { events } = parseSSEBuffer(buf);
    expect(events).toHaveLength(2);
  });

  it("handles rapid streaming chunks", () => {
    // Simulate multiple chunks arriving
    let buffer = "";
    const allEvents: SSEEvent[] = [];

    buffer += "event: metadata\ndata: {}\n\n";
    let result = parseSSEBuffer(buffer);
    allEvents.push(...result.events);
    buffer = result.remaining;

    buffer += "data: Hello ";
    result = parseSSEBuffer(buffer);
    allEvents.push(...result.events);
    buffer = result.remaining;

    buffer += "world\n\n";
    result = parseSSEBuffer(buffer);
    allEvents.push(...result.events);

    expect(allEvents).toHaveLength(2);
    expect(allEvents[0].event).toBe("metadata");
    expect(allEvents[1].data).toBe("Hello world");
  });
});
