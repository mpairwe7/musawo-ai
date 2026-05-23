"use client";

import { memo, useCallback } from "react";
import { useChatStore, VOICE_PERSONAS } from "@/store/useChatStore";
import { PlayIcon, XIcon } from "./Icons";
import { speak, stopSpeaking, isTTSAvailable } from "@/lib/voiceOutput";

/**
 * Voice personnel selection modal — lets users pick a TTS voice
 * with preview playback for each persona.
 */

export default memo(function VoicePersonnelModal() {
  const open = useChatStore((s) => s.voicePersonnelOpen);
  const setOpen = useChatStore((s) => s.setVoicePersonnelOpen);
  const selectedVoice = useChatStore((s) => s.selectedVoice);
  const setSelectedVoice = useChatStore((s) => s.setSelectedVoice);

  const handlePreview = useCallback((persona: typeof VOICE_PERSONAS[0]) => {
    if (!isTTSAvailable()) return;
    stopSpeaking();
    speak(persona.sample, persona.langCode.split("-")[0]);
  }, []);

  const handleSelect = useCallback((id: string) => {
    setSelectedVoice(id);
  }, [setSelectedVoice]);

  const handleClose = useCallback(() => {
    stopSpeaking();
    setOpen(false);
  }, [setOpen]);

  if (!open) return null;

  return (
    <div className="voice-personnel-backdrop" onClick={handleClose}>
      <div
        className="voice-personnel-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Voice selection"
      >
        <div className="vp-header">
          <h2>Choose Voice</h2>
          <button className="vp-close" onClick={handleClose} aria-label="Close" type="button">
            <XIcon width={20} height={20} />
          </button>
        </div>

        <div className="vp-list">
          {VOICE_PERSONAS.map((persona) => {
            const isSelected = selectedVoice === persona.id;
            return (
              <button
                key={persona.id}
                className={`vp-card ${isSelected ? "vp-selected" : ""}`}
                onClick={() => handleSelect(persona.id)}
                type="button"
              >
                <div className="vp-card-left">
                  <span className="vp-flag">{persona.flag}</span>
                  <div className="vp-card-info">
                    <span className="vp-name">{persona.name}</span>
                    <span className="vp-sample">{persona.sample}</span>
                  </div>
                </div>
                <div className="vp-card-right">
                  <button
                    className="vp-preview-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      handlePreview(persona);
                    }}
                    aria-label={`Preview ${persona.name}`}
                    type="button"
                  >
                    <PlayIcon width={14} height={14} />
                  </button>
                  {isSelected && <span className="vp-check-mark" />}
                </div>
              </button>
            );
          })}
        </div>

        <p className="vp-note">
          Voice output reads danger signs and triage results aloud.
          Availability depends on your device.
        </p>
      </div>
    </div>
  );
});
