/**
 * Musawo AI — IndexedDB offline storage layer.
 *
 * Stores conversations, cached responses, and queued messages
 * for offline-first operation using the `idb` library.
 */

import { openDB, type IDBPDatabase } from "idb";

const DB_NAME = "musawo-offline";
const DB_VERSION = 1;

interface MusawoDB {
  conversations: {
    key: string;
    value: {
      id: string;
      sessionId: string;
      role: "user" | "assistant";
      content: string;
      mode: string;
      timestamp: number;
      synced: boolean;
    };
    indexes: { "by-session": string; "by-synced": number };
  };
  cachedResponses: {
    key: string;
    value: {
      queryHash: string;
      mode: string;
      response: string;
      citations: unknown[];
      timestamp: number;
      ttl: number; // seconds
    };
    indexes: { "by-mode": string };
  };
  offlineQueue: {
    key: string;
    value: {
      id: string;
      query: string;
      mode: string;
      locale: string;
      timestamp: number;
    };
  };
  facilities: {
    key: string;
    value: {
      name: string;
      level: string;
      district: string;
      latitude: number;
      longitude: number;
      phone: string;
      services: string[];
    };
    indexes: { "by-district": string };
  };
  medicationReminders: {
    key: string;
    value: {
      id: string;
      name: string;
      dosage: string;
      frequency: string;
      nextDue: string;
      createdAt: number;
    };
  };
}

let dbInstance: IDBPDatabase<MusawoDB> | null = null;

async function getDb(): Promise<IDBPDatabase<MusawoDB>> {
  if (dbInstance) return dbInstance;

  dbInstance = await openDB<MusawoDB>(DB_NAME, DB_VERSION, {
    upgrade(db) {
      // Conversations
      const convStore = db.createObjectStore("conversations", {
        keyPath: "id",
      });
      convStore.createIndex("by-session", "sessionId");
      convStore.createIndex("by-synced", "synced");

      // Cached RAG responses
      const cacheStore = db.createObjectStore("cachedResponses", {
        keyPath: "queryHash",
      });
      cacheStore.createIndex("by-mode", "mode");

      // Offline message queue
      db.createObjectStore("offlineQueue", { keyPath: "id" });

      // Health facilities
      const facStore = db.createObjectStore("facilities", {
        keyPath: "name",
      });
      facStore.createIndex("by-district", "district");

      // Medication reminders
      db.createObjectStore("medicationReminders", { keyPath: "id" });
    },
  });

  return dbInstance;
}

// ── Conversations ──────────────────────────────────────────────────────

export async function saveMessage(msg: MusawoDB["conversations"]["value"]) {
  const db = await getDb();
  await db.put("conversations", msg);
}

export async function getSessionMessages(sessionId: string) {
  const db = await getDb();
  return db.getAllFromIndex("conversations", "by-session", sessionId);
}

export async function getUnsyncedMessages() {
  const db = await getDb();
  return db.getAllFromIndex("conversations", "by-synced", 0);
}

export async function markSynced(id: string) {
  const db = await getDb();
  const msg = await db.get("conversations", id);
  if (msg) {
    msg.synced = true;
    await db.put("conversations", msg);
  }
}

// ── Response cache ─────────────────────────────────────────────────────

function hashQuery(query: string, mode: string): string {
  // Simple hash for cache key
  let hash = 0;
  const str = `${mode}:${query.toLowerCase().trim()}`;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0;
  }
  return `q-${Math.abs(hash).toString(36)}`;
}

export async function getCachedResponse(query: string, mode: string) {
  const db = await getDb();
  const key = hashQuery(query, mode);
  const cached = await db.get("cachedResponses", key);
  if (!cached) return null;

  // Check TTL
  const age = (Date.now() - cached.timestamp) / 1000;
  if (age > cached.ttl) {
    await db.delete("cachedResponses", key);
    return null;
  }
  return cached;
}

export async function cacheResponse(
  query: string,
  mode: string,
  response: string,
  citations: unknown[],
  ttl = 86400 // 24 hours
) {
  const db = await getDb();
  await db.put("cachedResponses", {
    queryHash: hashQuery(query, mode),
    mode,
    response,
    citations,
    timestamp: Date.now(),
    ttl,
  });
}

// ── Offline queue ──────────────────────────────────────────────────────

export async function queueOfflineMessage(
  query: string,
  mode: string,
  locale: string
) {
  const db = await getDb();
  const id = `oq-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  await db.put("offlineQueue", {
    id,
    query,
    mode,
    locale,
    timestamp: Date.now(),
  });
  return id;
}

export async function getOfflineQueue() {
  const db = await getDb();
  return db.getAll("offlineQueue");
}

export async function clearOfflineQueue() {
  const db = await getDb();
  await db.clear("offlineQueue");
}

// ── Facilities ─────────────────────────────────────────────────────────

export async function cacheFacilities(
  facilities: MusawoDB["facilities"]["value"][]
) {
  const db = await getDb();
  const tx = db.transaction("facilities", "readwrite");
  for (const f of facilities) {
    await tx.store.put(f);
  }
  await tx.done;
}

export async function getFacilitiesByDistrict(district: string) {
  const db = await getDb();
  return db.getAllFromIndex("facilities", "by-district", district);
}

export async function getAllFacilities() {
  const db = await getDb();
  return db.getAll("facilities");
}

// ── Medication reminders ───────────────────────────────────────────────

export async function saveReminder(
  reminder: MusawoDB["medicationReminders"]["value"]
) {
  const db = await getDb();
  await db.put("medicationReminders", reminder);
}

export async function getReminders() {
  const db = await getDb();
  return db.getAll("medicationReminders");
}

export async function deleteReminder(id: string) {
  const db = await getDb();
  await db.delete("medicationReminders", id);
}
