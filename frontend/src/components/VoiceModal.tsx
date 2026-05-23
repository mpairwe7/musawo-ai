"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import { useChatStore } from "@/store/useChatStore";
import { t } from "@/lib/i18n";
import { MicIcon, CheckIcon, XIcon } from "./Icons";
import {
  isOnDeviceSTTAvailable,
  transcribeAudio,
  audioBufferFromBlob,
} from "@/lib/onDeviceSTT";

type STTMode = "sunbird" | "on-device" | "browser";

/**
 * Floating voice modal with animated waveform, live transcription,
 * and approve/cancel buttons. Grok voice-mode inspired.
 */

const LANG_MAP: Record<string, string> = {
  en: "en-US",
  lg: "en-US",
  nyn: "en-US",
  sw: "sw-KE",
};

export default memo(function VoiceModal() {
  const open = useChatStore((s) => s.voiceModalOpen);
  const setOpen = useChatStore((s) => s.setVoiceModalOpen);
  const setSpeechState = useChatStore((s) => s.setSpeechState);
  const locale = useChatStore((s) => s.locale);
  const setMessage = useChatStore((s) => s.setMessage);
  const message = useChatStore((s) => s.message);

  const [transcript, setTranscript] = useState("");
  const [interim, setInterim] = useState("");
  const [isListening, setIsListening] = useState(false);
  const isListeningRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [usingSunbird, setUsingSunbird] = useState(false);
  const [sunbirdProcessing, setSunbirdProcessing] = useState(false);
  const [sttMode, setSTTMode] = useState<STTMode>("sunbird");
  const recognitionRef = useRef<any>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number>(0);
  const streamRef = useRef<MediaStream | null>(null);

  // Sunbird STT is the DEFAULT for all languages (better accuracy, native support)
  // Browser Web Speech API is the fallback if Sunbird is unavailable

  // Start recognition when modal opens — always try Sunbird first
  useEffect(() => {
    if (!open) return;
    setTranscript("");
    setInterim("");
    setError(null);
    setSunbirdProcessing(false);
    startSunbirdRecording();
    startAudioVisualizer();

    return () => {
      stopRecognition();
      stopSunbirdRecording();
      stopVisualizer();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // ── Sunbird STT (record audio → send to backend → get transcription) ──

  const startSunbirdRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Try webm first, fall back to other formats
      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : MediaRecorder.isTypeSupported("audio/mp4")
        ? "audio/mp4"
        : "";
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start(500);
      isListeningRef.current = true;
      setIsListening(true);
      setUsingSunbird(true);
      setSpeechState("listening");
      setInterim(locale === "lg" ? "Yogera..." : locale === "sw" ? "Sema..." : locale === "nyn" ? "Yogera..." : "Speak now...");
    } catch {
      // Sunbird recording failed — flag for browser fallback
      console.warn("Sunbird recording unavailable, will use browser STT");
      setUsingSunbird(false);
      setError(null);
      // Browser fallback handled below
      const SpeechRecognitionAPI =
        typeof window !== "undefined"
          ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
          : null;
      if (SpeechRecognitionAPI) {
        const recognition = new SpeechRecognitionAPI();
        recognitionRef.current = recognition;
        recognition.lang = LANG_MAP[locale] || "en-US";
        recognition.interimResults = true;
        recognition.continuous = true;
        recognition.onresult = (event: any) => {
          let f = "", im = "";
          for (let i = 0; i < event.results.length; i++) {
            if (event.results[i].isFinal) f += event.results[i][0].transcript + " ";
            else im += event.results[i][0].transcript;
          }
          if (f) setTranscript((prev) => prev + f);
          setInterim(im);
        };
        recognition.onend = () => {
          if (recognitionRef.current && isListeningRef.current) {
            try { recognition.start(); } catch { /* ignore */ }
          }
        };
        isListeningRef.current = true;
        setIsListening(true);
        setSpeechState("listening");
        recognition.start();
      } else {
        setError(t("voice_not_supported", locale));
        setSpeechState("unavailable");
      }
    }
  }, [locale, setSpeechState]);

  const stopSunbirdRecording = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    isListeningRef.current = false;
    setIsListening(false);
  }, []);

  const transcribeWithSunbird = useCallback(async (): Promise<string> => {
    // Stop recording and collect audio
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    // Wait briefly for final chunks
    await new Promise((r) => setTimeout(r, 300));

    const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
    if (audioBlob.size < 1000) return ""; // Too short

    setSunbirdProcessing(true);
    setInterim(locale === "lg" ? "Okukola transcription..." : locale === "sw" ? "Inaandika..." : "Transcribing...");

    // If offline and on-device model is ready, use it directly
    if (!navigator.onLine && isOnDeviceSTTAvailable()) {
      try {
        setSTTMode("on-device");
        setInterim("Transcribing offline...");
        const audioData = await audioBufferFromBlob(audioBlob);
        const text = await transcribeAudio(audioData, locale === "lg" ? "en" : locale);
        return text;
      } catch (err) {
        console.warn("On-device STT failed:", err);
        return (transcript + interim).trim();
      } finally {
        setSunbirdProcessing(false);
      }
    }

    try {
      setSTTMode("sunbird");
      const formData = new FormData();
      formData.append("audio", audioBlob, "voice.webm");
      formData.append("language", locale);

      const resp = await fetch("/api/v1/voice/stt", { method: "POST", body: formData });
      if (!resp.ok) throw new Error(`STT failed: ${resp.status}`);
      const data = await resp.json();
      return data.text || "";
    } catch (err) {
      console.warn("Sunbird STT failed:", err);
      // Fallback to on-device STT if available
      if (isOnDeviceSTTAvailable()) {
        try {
          setSTTMode("on-device");
          setInterim("Trying offline model...");
          const audioData = await audioBufferFromBlob(audioBlob);
          return await transcribeAudio(audioData, locale === "lg" ? "en" : locale);
        } catch {
          // Fall through to browser transcript
        }
      }
      setSTTMode("browser");
      return (transcript + interim).trim();
    } finally {
      setSunbirdProcessing(false);
    }
  }, [locale, transcript, interim]);

  // ── Browser Web Speech API (English fallback) ──

  const startRecognition = useCallback(() => {
    const SpeechRecognitionAPI =
      typeof window !== "undefined"
        ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
        : null;

    if (!SpeechRecognitionAPI) {
      setError(t("voice_not_supported", locale));
      setSpeechState("unavailable");
      return;
    }

    try {
      const recognition = new SpeechRecognitionAPI();
      recognitionRef.current = recognition;
      recognition.lang = LANG_MAP[locale] || "en-US";
      recognition.interimResults = true;
      recognition.continuous = true;
      recognition.maxAlternatives = 1;

      recognition.onresult = (event: any) => {
        let finalText = "";
        let interimText = "";
        for (let i = 0; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) {
            finalText += result[0].transcript + " ";
          } else {
            interimText += result[0].transcript;
          }
        }
        if (finalText) setTranscript((prev) => prev + finalText);
        setInterim(interimText);
      };

      recognition.onerror = (event: any) => {
        const err = event?.error || "unknown";
        if (err !== "no-speech" && err !== "aborted") {
          setError(`Voice error: ${err}`);
        }
      };

      recognition.onend = () => {
        if (recognitionRef.current && isListeningRef.current) {
          try { recognition.start(); } catch { /* ignore */ }
        }
      };

      isListeningRef.current = true;
      setIsListening(true);
      setUsingSunbird(false);
      setSpeechState("listening");
      recognition.start();
    } catch {
      setError(t("voice_error", locale));
      setSpeechState("error");
    }
  }, [locale, setSpeechState]);

  const stopRecognition = useCallback(() => {
    isListeningRef.current = false;
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch { /* ignore */ }
      recognitionRef.current = null;
    }
    setIsListening(false);
    setSpeechState("idle");
  }, [setSpeechState]);

  // Audio visualizer for waveform
  const startAudioVisualizer = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;
      drawWaveform();
    } catch {
      // Visualizer is cosmetic - don't block on failure
    }
  }, []);

  const drawWaveform = useCallback(() => {
    const canvas = canvasRef.current;
    const analyser = analyserRef.current;
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      animFrameRef.current = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(dataArray);

      const { width, height } = canvas;
      ctx.clearRect(0, 0, width, height);

      const barCount = 48;
      const barWidth = width / barCount - 2;
      const centerY = height / 2;

      for (let i = 0; i < barCount; i++) {
        const dataIndex = Math.floor((i / barCount) * bufferLength);
        const value = dataArray[dataIndex] / 255;
        const barHeight = Math.max(3, value * centerY * 0.85);

        // Gradient from green to amber based on intensity
        const hue = 140 - value * 50; // green to yellow-green
        ctx.fillStyle = `hsla(${hue}, 70%, 55%, ${0.5 + value * 0.5})`;

        const x = i * (barWidth + 2) + 1;
        // Draw symmetrical bars from center
        ctx.beginPath();
        ctx.roundRect(x, centerY - barHeight, barWidth, barHeight * 2, 2);
        ctx.fill();
      }
    };
    draw();
  }, []);

  const stopVisualizer = useCallback(() => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    analyserRef.current = null;
  }, []);

  const handleApprove = useCallback(async () => {
    let fullText = "";
    if (usingSunbird) {
      // Send recorded audio to Sunbird STT for transcription
      fullText = await transcribeWithSunbird();
      stopSunbirdRecording();
    } else {
      fullText = (transcript + interim).trim();
      stopRecognition();
    }
    if (fullText) {
      setMessage(message ? `${message} ${fullText}` : fullText);
    }
    stopVisualizer();
    setSpeechState("idle");
    setOpen(false);
  }, [usingSunbird, transcript, interim, message, setMessage, stopRecognition, stopSunbirdRecording, transcribeWithSunbird, stopVisualizer, setSpeechState, setOpen]);

  const handleCancel = useCallback(() => {
    stopRecognition();
    stopSunbirdRecording();
    stopVisualizer();
    setSpeechState("idle");
    setOpen(false);
  }, [stopRecognition, stopSunbirdRecording, stopVisualizer, setSpeechState, setOpen]);

  // Escape key to cancel
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, handleCancel]);

  if (!open) return null;

  const displayText = transcript + interim;

  return (
    <div className="voice-modal-backdrop" onClick={handleCancel}>
      <div
        className="voice-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Voice input"
      >
        {/* Pulsing ring + mic icon */}
        <div className="voice-orb">
          <div className="voice-pulse-ring" />
          <div className="voice-pulse-ring voice-pulse-ring-2" />
          <div className="voice-mic-circle">
            <MicIcon width={32} height={32} />
          </div>
        </div>

        {/* Waveform canvas */}
        <canvas
          ref={canvasRef}
          className="voice-waveform"
          width={320}
          height={80}
          aria-hidden="true"
        />

        {/* Status text + STT mode badge */}
        <p className="voice-status" aria-live="polite">
          {error || (sunbirdProcessing
            ? (sttMode === "on-device" ? "Offline transcription..." : t("voice_listening", locale))
            : isListening ? t("voice_listening", locale) : t("voice_starting", locale))}
        </p>
        {isListening && (
          <span
            style={{
              fontSize: "0.65rem",
              padding: "0.15rem 0.5rem",
              borderRadius: "999px",
              background: sttMode === "on-device"
                ? "rgba(59, 130, 246, 0.2)"
                : "rgba(34, 197, 94, 0.15)",
              color: sttMode === "on-device"
                ? "var(--accent-blue, #3B82F6)"
                : "var(--accent-green, #22C55E)",
              fontWeight: 700,
              letterSpacing: "0.03em",
              textTransform: "uppercase",
            }}
          >
            {sttMode === "on-device" ? "Offline" : sttMode === "sunbird" ? "Sunbird" : "Browser"}
          </span>
        )}

        {/* Live transcription */}
        <div className="voice-transcript" aria-live="polite" aria-atomic="false">
          {displayText || (
            <span className="voice-transcript-placeholder">
              {t("voice_speak_now", locale)}
            </span>
          )}
        </div>

        {/* Action buttons */}
        <div className="voice-actions">
          <button
            className="voice-action-btn voice-cancel"
            onClick={handleCancel}
            aria-label={t("voice_cancel", locale)}
            type="button"
          >
            <XIcon width={22} height={22} />
            <span>{t("voice_cancel", locale)}</span>
          </button>
          <button
            className="voice-action-btn voice-approve"
            onClick={handleApprove}
            disabled={!displayText.trim()}
            aria-label={t("voice_send", locale)}
            type="button"
          >
            <CheckIcon width={22} height={22} />
            <span>{t("voice_send", locale)}</span>
          </button>
        </div>
      </div>
    </div>
  );
});
