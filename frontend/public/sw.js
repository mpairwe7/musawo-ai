/**
 * Musawo AI — Service Worker (Offline-first PWA)
 *
 * Strategy:
 * - App shell: Cache-first (HTML, CSS, JS, fonts)
 * - API responses: Network-first with IndexedDB fallback
 * - Knowledge base: Cache-first (long-lived health content)
 * - Images/icons: Cache-first
 */

const CACHE_VERSION = "musawo-v1";
const APP_SHELL_CACHE = `${CACHE_VERSION}-shell`;
const API_CACHE = `${CACHE_VERSION}-api`;
const KB_CACHE = `${CACHE_VERSION}-kb`;

// App shell resources to precache
const APP_SHELL_URLS = [
  "/",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

// ── Install: precache app shell ────────────────────────────────────────

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(APP_SHELL_CACHE)
      .then((cache) => cache.addAll(APP_SHELL_URLS))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: clean old caches ─────────────────────────────────────────

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith("musawo-") && key !== APP_SHELL_CACHE && key !== API_CACHE && key !== KB_CACHE)
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch: routing strategy ────────────────────────────────────────────

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET and cross-origin
  if (event.request.method !== "GET") return;
  if (url.origin !== self.location.origin) return;

  // API calls: network-first → cache fallback
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirstWithCache(event.request, API_CACHE));
    return;
  }

  // Knowledge base / health data: cache-first
  if (url.pathname.startsWith("/kb/") || url.pathname.includes("knowledge")) {
    event.respondWith(cacheFirst(event.request, KB_CACHE));
    return;
  }

  // Everything else (app shell): cache-first → network fallback
  event.respondWith(cacheFirst(event.request, APP_SHELL_CACHE));
});

// ── Strategies ─────────────────────────────────────────────────────────

async function networkFirstWithCache(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;

    // Offline fallback response for chat API
    if (request.url.includes("/v1/chat")) {
      return new Response(
        JSON.stringify({
          answer:
            "You are currently offline. Your message has been saved and will be sent when you reconnect. For emergencies, call 0800 100 263.",
          mode: "community",
          locale: "en",
          confidence: 0,
          citations: [],
          escalation_required: false,
          disclaimer:
            "This is an offline response. Please seek in-person care for urgent issues.",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    return new Response("Offline", { status: 503 });
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // For navigation requests, return cached index
    if (request.mode === "navigate") {
      const index = await caches.match("/");
      if (index) return index;
    }
    return new Response("Offline", { status: 503 });
  }
}

// ── Background sync (queue offline messages) ───────────────────────────

self.addEventListener("sync", (event) => {
  if (event.tag === "sync-messages") {
    event.waitUntil(syncOfflineMessages());
  }
});

async function syncOfflineMessages() {
  // Open IndexedDB directly from service worker
  const db = await new Promise((resolve, reject) => {
    const req = indexedDB.open("musawo-offline", 1);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });

  const tx = db.transaction("offlineQueue", "readonly");
  const store = tx.objectStore("offlineQueue");
  const allItems = await new Promise((resolve) => {
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => resolve([]);
  });

  if (!allItems || allItems.length === 0) {
    db.close();
    return;
  }

  let synced = 0;
  for (const item of allItems) {
    try {
      const res = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: item.query,
          mode: item.mode,
          locale: item.locale,
        }),
      });

      if (res.ok) {
        // Delete synced message from queue
        const delTx = db.transaction("offlineQueue", "readwrite");
        delTx.objectStore("offlineQueue").delete(item.id);
        synced++;
      }
    } catch {
      // Network still unavailable — stop trying
      break;
    }
  }

  db.close();

  // Notify all clients
  const clients = await self.clients.matchAll();
  for (const client of clients) {
    client.postMessage({ type: "SYNC_COMPLETE", synced });
  }
}

// ── Push notifications (future: medication reminders) ──────────────────

self.addEventListener("push", (event) => {
  const data = event.data?.json() || {};
  const title = data.title || "Musawo AI";
  const options = {
    body: data.body || "You have a health reminder",
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-72.png",
    tag: data.tag || "musawo-notification",
    data: data.url || "/",
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.openWindow(event.notification.data || "/")
  );
});
