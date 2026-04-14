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

export function isTTSAvailable(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function stopSpeaking(): void {
  if (isTTSAvailable()) {
    window.speechSynthesis.cancel();
    currentUtterance = null;
  }
}

export function isSpeaking(): boolean {
  return isTTSAvailable() && window.speechSynthesis.speaking;
}

/**
 * Speak text aloud. If urgent, uses higher pitch and rate.
 */
export function speak(
  text: string,
  locale: string = "en",
  options: { urgent?: boolean; onEnd?: () => void } = {}
): void {
  if (!isTTSAvailable()) return;

  // Stop any current speech
  stopSpeaking();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = LANG_MAP[locale] || "en-UG";

  if (options.urgent) {
    utterance.rate = 0.95; // Slightly slower for clarity
    utterance.pitch = 1.2; // Slightly higher for urgency
    utterance.volume = 1.0; // Full volume
  } else {
    utterance.rate = 0.9;
    utterance.pitch = 1.0;
    utterance.volume = 0.9;
  }

  // Try to find a voice for the locale
  const voices = window.speechSynthesis.getVoices();
  const langCode = LANG_MAP[locale] || "en";
  const matchedVoice = voices.find(
    (v) => v.lang.startsWith(langCode.split("-")[0])
  );
  if (matchedVoice) {
    utterance.voice = matchedVoice;
  }

  if (options.onEnd) {
    utterance.onend = options.onEnd;
  }

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
