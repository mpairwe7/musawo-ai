"use client";

import { memo, useCallback, useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export default memo(function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Check if already dismissed this session
    if (sessionStorage.getItem("musawo-install-dismissed")) {
      setDismissed(true);
      return;
    }

    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  const handleInstall = useCallback(async () => {
    if (!deferredPrompt) return;
    await deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === "accepted") {
      setDeferredPrompt(null);
    }
    setDismissed(true);
    sessionStorage.setItem("musawo-install-dismissed", "1");
  }, [deferredPrompt]);

  const handleDismiss = useCallback(() => {
    setDismissed(true);
    sessionStorage.setItem("musawo-install-dismissed", "1");
  }, []);

  if (!deferredPrompt || dismissed) return null;

  return (
    <div className="install-prompt" role="banner">
      <p>Install Musawo AI for offline access</p>
      <div className="install-actions">
        <button className="install-btn" onClick={handleInstall}>
          Install
        </button>
        <button className="install-dismiss" onClick={handleDismiss} aria-label="Dismiss install prompt">
          Not now
        </button>
      </div>
    </div>
  );
});
