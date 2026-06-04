/**
 * Register the Musawo service worker for offline-first PWA support.
 */

export function registerSW() {
  if (typeof window === "undefined") return;
  if (!("serviceWorker" in navigator)) {
    console.warn("Service workers not supported");
    return;
  }

  // If a SW already controls this page, a controller change means a NEW version
  // took over (e.g. after a redeploy). Reload once so the page runs the fresh HTML
  // and current chunk names — this auto-recovers users whose old SW was serving
  // stale cached HTML with dead chunk references. Guarded against reload loops, and
  // skipped on first-ever install (no prior controller) to avoid a needless reload.
  if (navigator.serviceWorker.controller) {
    let refreshing = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });
  }

  window.addEventListener("load", async () => {
    try {
      const reg = await navigator.serviceWorker.register("/sw.js", {
        scope: "/",
      });
      console.log("SW registered:", reg.scope);

      // Listen for updates — dispatch event so UI can show update prompt
      reg.addEventListener("updatefound", () => {
        const newWorker = reg.installing;
        if (!newWorker) return;
        newWorker.addEventListener("statechange", () => {
          if (
            newWorker.state === "activated" &&
            navigator.serviceWorker.controller
          ) {
            window.dispatchEvent(new CustomEvent("musawo-sw-update"));
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
