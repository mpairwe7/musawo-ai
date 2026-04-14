/**
 * Register the Musawo service worker for offline-first PWA support.
 */

export function registerSW() {
  if (typeof window === "undefined") return;
  if (!("serviceWorker" in navigator)) {
    console.warn("Service workers not supported");
    return;
  }

  window.addEventListener("load", async () => {
    try {
      const reg = await navigator.serviceWorker.register("/sw.js", {
        scope: "/",
      });
      console.log("SW registered:", reg.scope);

      // Listen for updates
      reg.addEventListener("updatefound", () => {
        const newWorker = reg.installing;
        if (!newWorker) return;
        newWorker.addEventListener("statechange", () => {
          if (
            newWorker.state === "activated" &&
            navigator.serviceWorker.controller
          ) {
            // New version available — notify user
            console.log("New Musawo version available");
          }
        });
      });
    } catch (err) {
      console.error("SW registration failed:", err);
    }
  });

  // Listen for sync-complete messages from SW
  navigator.serviceWorker.addEventListener("message", (event) => {
    if (event.data?.type === "SYNC_COMPLETE") {
      console.log("Offline messages synced successfully");
      window.dispatchEvent(new CustomEvent("musawo-sync-complete"));
    }
  });
}

export function requestBackgroundSync() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.ready.then((reg) => {
    if ("sync" in reg) {
      (reg as any).sync.register("sync-messages");
    }
  });
}
