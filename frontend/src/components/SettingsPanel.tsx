"use client";

import { memo, useCallback, useEffect, useState } from "react";
import { useChatStore } from "@/store/useChatStore";
import { t } from "@/lib/i18n";

interface SettingsPanelProps {
  onClose: () => void;
}

const APP_VERSION = "2.2.0";

export default memo(function SettingsPanel({ onClose }: SettingsPanelProps) {
  const chat = useChatStore((s) => s.chat);
  const clearChat = useChatStore((s) => s.clearChat);
  const isOnline = useChatStore((s) => s.isOnline);
  const ttsEnabled = useChatStore((s) => s.ttsEnabled);
  const setTtsEnabled = useChatStore((s) => s.setTtsEnabled);
  const sessions = useChatStore((s) => s.sessions);
  const locale = useChatStore((s) => s.locale);

  const [fontSize, setFontSize] = useState(() => {
    if (typeof window !== "undefined") return localStorage.getItem("musawo-font-size") || "normal";
    return "normal";
  });
  const [highContrast, setHighContrast] = useState(() => {
    if (typeof window !== "undefined") return localStorage.getItem("musawo-high-contrast") === "true";
    return false;
  });

  // Apply font size + high contrast to document
  useEffect(() => {
    document.documentElement.setAttribute("data-font", fontSize);
    localStorage.setItem("musawo-font-size", fontSize);
  }, [fontSize]);

  useEffect(() => {
    document.documentElement.setAttribute("data-contrast", highContrast ? "high" : "normal");
    localStorage.setItem("musawo-high-contrast", String(highContrast));
  }, [highContrast]);

  const handleClearChat = useCallback(() => {
    if (window.confirm("Clear all chat history? This cannot be undone.")) {
      clearChat();
    }
  }, [clearChat]);

  const handleClearCache = useCallback(async () => {
    if (window.confirm("Clear offline cache? Cached responses will be removed.")) {
      if ("caches" in window) {
        const keys = await caches.keys();
        await Promise.all(keys.filter((k) => k.startsWith("musawo-")).map((k) => caches.delete(k)));
      }
      const dbs = await indexedDB.databases();
      for (const db of dbs) {
        if (db.name?.startsWith("musawo")) {
          indexedDB.deleteDatabase(db.name);
        }
      }
      window.location.reload();
    }
  }, []);

  return (
    <div className="panel settings-panel" role="dialog" aria-label={t("settings_title", locale)}>
      <div className="panel-header">
        <h2>{t("settings_title", locale)}</h2>
        <button className="panel-close" onClick={onClose} aria-label="Close">
          &times;
        </button>
      </div>

      <div className="panel-body">
        {/* Status */}
        <div className="settings-section">
          <h3>{t("settings_status", locale)}</h3>
          <div className="settings-row">
            <span>{t("settings_connection", locale)}</span>
            <span className={isOnline ? "text-green" : "text-gold"}>
              {isOnline ? t("settings_online", locale) : t("settings_offline", locale)}
            </span>
          </div>
          <div className="settings-row">
            <span>{t("settings_messages", locale)}</span>
            <span>{chat.length} turns</span>
          </div>
          <div className="settings-row">
            <span>{t("settings_conversations", locale)}</span>
            <span>{sessions.length} saved</span>
          </div>
        </div>

        {/* Accessibility */}
        <div className="settings-section">
          <h3>{t("settings_accessibility", locale)}</h3>
          <div className="settings-row">
            <span>{t("settings_tts", locale)}</span>
            <label className="toggle-label">
              <input
                type="checkbox"
                checked={ttsEnabled}
                onChange={(e) => setTtsEnabled(e.target.checked)}
                className="toggle-input"
              />
              <span className="toggle-switch" />
            </label>
          </div>
          <div className="settings-row">
            <span>{t("settings_font_size", locale)}</span>
            <select
              value={fontSize}
              onChange={(e) => setFontSize(e.target.value)}
              className="settings-select"
              aria-label={t("settings_font_size", locale)}
            >
              <option value="small">Small</option>
              <option value="normal">Normal</option>
              <option value="large">Large</option>
            </select>
          </div>
          <div className="settings-row">
            <span>{t("settings_high_contrast", locale)}</span>
            <label className="toggle-label">
              <input
                type="checkbox"
                checked={highContrast}
                onChange={(e) => setHighContrast(e.target.checked)}
                className="toggle-input"
              />
              <span className="toggle-switch" />
            </label>
          </div>
        </div>

        {/* Data management */}
        <div className="settings-section">
          <h3>{t("settings_data", locale)}</h3>
          <button className="settings-btn" onClick={handleClearChat}>
            {t("settings_clear_chat", locale)}
          </button>
          <button className="settings-btn danger" onClick={handleClearCache}>
            {t("settings_clear_cache", locale)}
          </button>
        </div>

        {/* About */}
        <div className="settings-section">
          <h3>{t("settings_about", locale)}</h3>
          <p className="settings-about">
            {t("settings_about_description", locale)}
          </p>
          <p className="settings-about">
            <strong>{t("settings_about_disclaimer", locale)}</strong>
          </p>
          <p className="settings-about">
            {t("settings_about_emergency", locale)} <a href="tel:0800100263">0800 100 263</a> (toll-free)
          </p>
          <p className="settings-about settings-version">
            Version {APP_VERSION}
          </p>
        </div>
      </div>
    </div>
  );
});
