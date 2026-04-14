"use client";

import { memo, useCallback } from "react";
import { useChatStore } from "@/store/useChatStore";

interface SettingsPanelProps {
  onClose: () => void;
}

export default memo(function SettingsPanel({ onClose }: SettingsPanelProps) {
  const chat = useChatStore((s) => s.chat);
  const clearChat = useChatStore((s) => s.clearChat);
  const isOnline = useChatStore((s) => s.isOnline);

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
      // Clear IndexedDB
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
    <div className="panel settings-panel" role="dialog" aria-label="Settings">
      <div className="panel-header">
        <h2>Settings</h2>
        <button className="panel-close" onClick={onClose} aria-label="Close">
          &times;
        </button>
      </div>

      <div className="panel-body">
        {/* Status */}
        <div className="settings-section">
          <h3>Status</h3>
          <div className="settings-row">
            <span>Connection</span>
            <span className={isOnline ? "text-green" : "text-gold"}>
              {isOnline ? "Online" : "Offline"}
            </span>
          </div>
          <div className="settings-row">
            <span>Messages</span>
            <span>{chat.length} turns</span>
          </div>
        </div>

        {/* Data management */}
        <div className="settings-section">
          <h3>Data</h3>
          <button className="settings-btn" onClick={handleClearChat}>
            Clear chat history
          </button>
          <button className="settings-btn danger" onClick={handleClearCache}>
            Clear offline cache
          </button>
        </div>

        {/* About */}
        <div className="settings-section">
          <h3>About Musawo AI</h3>
          <p className="settings-about">
            Community Health Navigator for rural Uganda. Built with official
            Ministry of Health guidelines.
          </p>
          <p className="settings-about">
            <strong>This is health guidance only — not a medical diagnosis.</strong>
          </p>
          <p className="settings-about">
            Emergency: <a href="tel:0800100263">0800 100 263</a> (toll-free)
          </p>
        </div>
      </div>
    </div>
  );
});
