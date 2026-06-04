/**
 * Musawo AI — Voice Output (Text-to-Speech) Service
 *
 * Speaks danger signs and red-flag alerts aloud using Web Speech Synthesis.
 * Critical for VHTs working at night or in low-light conditions,
 * and for low-literacy users who cannot read responses.
 */

const LANG_MAP: Record<string, string> = {
  en: "en-UG",
  lg: "lg-UG",
  nyn: "nyn-UG",
  sw: "sw-KE",
};

// Red-flag phrases that should always be spoken with urgency
const URGENT_PHRASES = [
  "REFER NOW",
  "REFER IMMEDIATELY",
  "danger sign",
  "emergency",
  "call 0800 100 263",
  "go to the health facility",
  "life-threatening",
];

let currentUtterance: SpeechSynthesisUtterance | null = null;
let cachedVoices: SpeechSynthesisVoice[] = [];

export function isTTSAvailable(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

// Pre-load voices (async on Chrome/Edge, sync on Firefox/Safari)
function ensureVoices(): SpeechSynthesisVoice[] {
  if (cachedVoices.length > 0) return cachedVoices;
  if (!isTTSAvailable()) return [];
  cachedVoices = window.speechSynthesis.getVoices();
  return cachedVoices;
}

// Listen for async voice loading (Chrome fires this after page load)
if (typeof window !== "undefined" && "speechSynthesis" in window) {
  window.speechSynthesis.addEventListener?.("voiceschanged", () => {
    cachedVoices = window.speechSynthesis.getVoices();
  });
}

export function stopSpeaking(): void {
  if (isTTSAvailable()) {
    window.speechSynthesis.cancel();
    currentUtterance = null;
  }
  // Also stop server-TTS audio if playing
  if (typeof serverAudio !== "undefined" && serverAudio) {
    serverAudio.pause();
    serverAudio = null;
  }
}

export function isSpeaking(): boolean {
  const browserSpeaking = isTTSAvailable() && window.speechSynthesis.speaking;
  const serverPlaying = typeof serverAudio !== "undefined" && serverAudio !== null && !serverAudio.paused;
  return browserSpeaking || serverPlaying;
}

// ── Server TTS: Sunbird native voices (lg/nyn/sw) + Cloudflare MeloTTS (English) ──

let serverAudio: HTMLAudioElement | null = null;

/**
 * Try server-side TTS via /v1/voice/tts: Sunbird native voices for Ugandan
 * languages, Cloudflare MeloTTS for English (returned as a base64 data URL).
 * Returns true if it played, false to fall back to browser speechSynthesis.
 */
async function tryServerTTS(
  text: string,
  locale: string,
  onEnd?: () => void,
): Promise<boolean> {
  // Server handles Luganda/Runyankole/Swahili (Sunbird) and English (MeloTTS).
  if (!["lg", "nyn", "sw", "en", "eng"].includes(locale)) return false;
  if (text.length > 2000) return false;

  try {
    const resp = await fetch("/api/v1/voice/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text.slice(0, 2000), locale }),
      // Fall back to browser TTS quickly if the server is slow/unreachable.
      signal: AbortSignal.timeout(10000),
    });
    if (!resp.ok) return false;
    const data = await resp.json();
    if (!data.audio_url) return false;

    // Play the returned audio (Sunbird signed URL or MeloTTS base64 data URL)
    if (serverAudio) { serverAudio.pause(); serverAudio = null; }
    serverAudio = new Audio(data.audio_url);
    serverAudio.onended = () => { serverAudio = null; onEnd?.(); };
    serverAudio.onerror = () => { serverAudio = null; onEnd?.(); };
    await serverAudio.play();
    return true;
  } catch {
    return false; // Fall back to browser TTS
  }
}

/**
 * Speak text aloud. If urgent, uses higher pitch and rate.
 * Tries server TTS first (Sunbird voices for Ugandan languages, Cloudflare
 * MeloTTS for English), then falls back to browser speechSynthesis.
 */
export function speak(
  text: string,
  locale: string = "en",
  options: { urgent?: boolean; onEnd?: () => void; gender?: "female" | "male"; langCode?: string } = {}
): void {
  // Server TTS first — Sunbird native voices for Ugandan languages, Cloudflare
  // MeloTTS for English (consistent quality; works where browser TTS is poor or
  // absent, e.g. some Android WebViews). Browser speechSynthesis is the fallback.
  if (["lg", "nyn", "sw", "en", "eng"].includes(locale)) {
    tryServerTTS(text, locale, options.onEnd).then((handled) => {
      if (!handled) {
        console.warn("Server TTS unavailable, falling back to browser");
        speakBrowser(text, locale, options);
      }
    });
    return;
  }
  speakBrowser(text, locale, options);
}

function speakBrowser(
  text: string,
  locale: string = "en",
  options: { urgent?: boolean; onEnd?: () => void; gender?: "female" | "male"; langCode?: string } = {}
): void {
  if (!isTTSAvailable()) return;

  // Stop any current speech
  stopSpeaking();

  // Chrome bug: speechSynthesis can get stuck. Resume it.
  if (window.speechSynthesis.paused) {
    window.speechSynthesis.resume();
  }

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = options.langCode || LANG_MAP[locale] || "en-US";

  if (options.urgent) {
    utterance.rate = 0.95;
    utterance.pitch = 1.2;
    utterance.volume = 1.0;
  } else {
    utterance.rate = 0.9;
    utterance.pitch = 1.0;
    utterance.volume = 0.9;
  }

  // Find best voice for locale + gender preference
  const voices = ensureVoices();
  const langCode = (options.langCode || LANG_MAP[locale] || "en").split("-")[0];
  const genderHint = options.gender;

  // Filter by language first
  const langVoices = voices.filter((v) => v.lang.startsWith(langCode));
  const enVoices = voices.filter((v) => v.lang.startsWith("en"));
  const pool = langVoices.length > 0 ? langVoices : enVoices;

  // Try to match gender preference via voice name heuristics
  let matchedVoice: SpeechSynthesisVoice | undefined;
  if (genderHint && pool.length > 1) {
    const genderWord = genderHint === "female" ? /female|woman|fiona|samantha|karen|zira|victoria/i : /male|man|daniel|david|james|george|mark/i;
    matchedVoice = pool.find((v) => genderWord.test(v.name) && !v.localService) || pool.find((v) => genderWord.test(v.name));
  }
  if (!matchedVoice) {
    matchedVoice = pool.find((v) => !v.localService) || pool[0];
  }
  if (matchedVoice) {
    utterance.voice = matchedVoice;
  }

  if (options.onEnd) {
    utterance.onend = options.onEnd;
  }

  // Chrome long-text bug workaround: chunk text > 200 chars
  utterance.onerror = () => {
    currentUtterance = null;
  };

  currentUtterance = utterance;
  window.speechSynthesis.speak(utterance);
}

/**
 * Speak red-flag / triage alerts with urgency.
 * Called automatically when triage severity is RED.
 */
export function speakRedFlagAlert(
  redFlags: string[],
  locale: string = "en"
): void {
  if (!isTTSAvailable() || redFlags.length === 0) return;

  const prefix =
    locale === "lg"
      ? "Obubonero bw'akabi! Genda mu ddwaliro amangu!"
      : locale === "sw"
      ? "Hatari! Nenda hospitali haraka!"
      : locale === "nyn"
      ? "Obubonero bw'akabi! Genda omu rwariro hati!"
      : "Danger signs detected! Go to the health facility immediately!";

  const flagText = redFlags.join(". ");
  const fullText = `${prefix} ${flagText}`;

  speak(fullText, locale, { urgent: true });
}

/**
 * Speak a triage result summary.
 */
export function speakTriageSummary(
  severity: string,
  manageAtHome: string[],
  referReasons: string[],
  locale: string = "en"
): void {
  if (!isTTSAvailable()) return;

  let text = "";

  if (severity === "red") {
    text =
      locale === "lg"
        ? "Omulwadde guno alina obubonero bw'akabi. Mutumire mu ddwaliro amangu."
        : `This patient has danger signs. Refer to the health facility immediately. ${referReasons.join(". ")}`;
    speak(text, locale, { urgent: true });
  } else if (severity === "yellow") {
    text =
      locale === "lg"
        ? "Kebera omulwadde buno era oddemu okumukebera mu ssaawa 24 ku 48."
        : `Monitor this patient and follow up in 24 to 48 hours. ${manageAtHome.join(". ")}`;
    speak(text, locale, { urgent: false });
  } else {
    text =
      locale === "lg"
        ? "Omulwadde ayinza okujjanjabibwa awaka."
        : `This patient can be managed at home. ${manageAtHome.join(". ")}`;
    speak(text, locale, { urgent: false });
  }
}

/**
 * Check if a response text contains urgent content that should be spoken.
 */
export function containsUrgentContent(text: string): boolean {
  const lower = text.toLowerCase();
  return URGENT_PHRASES.some((phrase) => lower.includes(phrase.toLowerCase()));
}
