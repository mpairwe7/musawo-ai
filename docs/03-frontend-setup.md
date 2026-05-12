# 3. Frontend Setup — Musawo AI

Next.js 16 PWA with offline-first design for rural Uganda deployment.

## Tech Stack

| Component | Version |
|-----------|---------|
| Next.js | 16.2.3 |
| React | 19.2.0 |
| Zustand | 5.0.5 |
| TanStack Query | 5.99.0 |
| IndexedDB (idb) | 8.0.0 |

## Routes

| Path | Page | Description |
|------|------|-------------|
| `/` | `page.tsx` | Main chat interface with mode selector |

## Components (15)

| Component | Purpose |
|-----------|---------|
| ModeSelector | VHT / Maternal / Community mode picker |
| ClinicFinder | GPS-based health facility locator |
| ChatInput | Message input with voice recording |
| ChatMessage | Message display with citations |
| VoiceModal | Voice chat UI with waveform |
| StarterPrompts | Contextual prompt suggestions |
| SettingsPanel | App settings (language, theme) |
| MaternalTracker | Pregnancy week tracker |
| MedicationReminders | Medication reminder manager |
| HealthDiagrams | Educational health diagrams |
| InstallPrompt | PWA install prompt |
| ServiceWorkerRegistrar | Offline caching |
| Providers | TanStack Query + context |
| Icons | SVG icon library |

## PWA Features

- Offline-first with service worker caching
- IndexedDB for conversation persistence
- Install prompt for home screen
- Safe area support for notch devices
- Dynamic viewport height (100dvh)
