import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Verifies English narration goes through the server (/v1/voice/tts → Cloudflare
// MeloTTS) first, and falls back to the browser when the server is unavailable.

describe("voiceOutput — English narration routing", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let playMock: ReturnType<typeof vi.fn>;
  let audioSrcs: string[];

  beforeEach(() => {
    vi.resetModules();
    audioSrcs = [];
    playMock = vi.fn().mockResolvedValue(undefined);
    // Mock the Audio element the module uses to play returned audio.
    (globalThis as unknown as { Audio: unknown }).Audio = class {
      onended: (() => void) | null = null;
      onerror: (() => void) | null = null;
      paused = false;
      constructor(src: string) {
        audioSrcs.push(src);
      }
      pause() {}
      play() {
        return playMock();
      }
    };
    fetchMock = vi.fn();
    (globalThis as unknown as { fetch: unknown }).fetch = fetchMock;
    // jsdom has no Web Speech API — stub what the module touches.
    (window as unknown as { speechSynthesis: unknown }).speechSynthesis = {
      cancel: vi.fn(),
      speak: vi.fn(),
      resume: vi.fn(),
      getVoices: () => [],
      addEventListener: vi.fn(),
      paused: false,
      speaking: false,
    };
    (globalThis as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance =
      class {
        lang = "";
        rate = 1;
        pitch = 1;
        volume = 1;
        voice: unknown = null;
        onend: (() => void) | null = null;
        constructor(public text: string) {}
      };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls the server MeloTTS endpoint for English and plays the audio", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ audio_url: "data:audio/mpeg;base64,QUJD", backend: "cloudflare-melotts" }),
    });
    const { speak } = await import("../lib/voiceOutput");
    speak("Take ORS and zinc.", "en");

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, opts] = fetchMock.mock.calls[0] as [string, { body: string }];
    expect(url).toBe("/api/v1/voice/tts");
    expect(JSON.parse(opts.body).locale).toBe("en");
    await vi.waitFor(() => expect(playMock).toHaveBeenCalled());
    expect(audioSrcs[0]).toBe("data:audio/mpeg;base64,QUJD");
    // server path was used → browser TTS not invoked
    expect((window as unknown as { speechSynthesis: { speak: ReturnType<typeof vi.fn> } }).speechSynthesis.speak)
      .not.toHaveBeenCalled();
  });

  it("falls back to browser speechSynthesis when the server fails", async () => {
    fetchMock.mockRejectedValue(new Error("network down"));
    const { speak } = await import("../lib/voiceOutput");
    speak("hello", "en");

    await vi.waitFor(() =>
      expect(
        (window as unknown as { speechSynthesis: { speak: ReturnType<typeof vi.fn> } }).speechSynthesis.speak,
      ).toHaveBeenCalled(),
    );
  });
});
