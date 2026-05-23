/**
 * Voice service — AudioRecorder + STT/TTS API client.
 * Portable across Musawo, Magezi, HustleCoach.
 */

const SAMPLE_RATE = 16000;

export class AudioRecorder {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private chunks: Float32Array[] = [];

  async start(): Promise<void> {
    this.chunks = [];
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, sampleRate: SAMPLE_RATE },
    });
    this.context = new AudioContext({ sampleRate: SAMPLE_RATE });
    const source = this.context.createMediaStreamSource(this.stream);
    this.processor = this.context.createScriptProcessor(4096, 1, 1);
    this.processor.onaudioprocess = (e) => {
      this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };
    source.connect(this.processor);
    this.processor.connect(this.context.destination);
  }

  stop(): ArrayBuffer {
    this.processor?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.context?.close();
    const total = this.chunks.reduce((n, c) => n + c.length, 0);
    const merged = new Float32Array(total);
    let offset = 0;
    for (const c of this.chunks) {
      merged.set(c, offset);
      offset += c.length;
    }
    // Convert to PCM16 LE
    const pcm16 = new ArrayBuffer(merged.length * 2);
    const view = new DataView(pcm16);
    for (let i = 0; i < merged.length; i++) {
      const s = Math.max(-1, Math.min(1, merged[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    this.chunks = [];
    return pcm16;
  }

  /** Stream PCM16 chunks to a callback (for WebSocket). */
  async startStreaming(onChunk: (pcm16: ArrayBuffer) => void): Promise<() => void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, sampleRate: SAMPLE_RATE },
    });
    const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
    const source = ctx.createMediaStreamSource(this.stream);
    const proc = ctx.createScriptProcessor(1024, 1, 1);
    proc.onaudioprocess = (e) => {
      const float32 = e.inputBuffer.getChannelData(0);
      const buf = new ArrayBuffer(float32.length * 2);
      const dv = new DataView(buf);
      for (let i = 0; i < float32.length; i++) {
        const s = Math.max(-1, Math.min(1, float32[i]));
        dv.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      }
      onChunk(buf);
    };
    source.connect(proc);
    proc.connect(ctx.destination);
    return () => {
      proc.disconnect();
      this.stream?.getTracks().forEach((t) => t.stop());
      ctx.close();
    };
  }
}

/** Play PCM16 or WAV audio bytes. */
export async function playAudio(data: ArrayBuffer, sampleRate = 24000): Promise<void> {
  const ctx = new AudioContext({ sampleRate });
  try {
    const buf = await ctx.decodeAudioData(data.slice(0));
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.start();
    await new Promise((resolve) => (src.onended = resolve));
  } finally {
    ctx.close();
  }
}

export type VoiceWSConfig = {
  language?: string;
  vadSensitivity?: "low" | "medium" | "high";
  ttsEnabled?: boolean;
};

export type VoiceWSEvent = {
  type: string;
  [key: string]: unknown;
};

export type VoiceWSListener = (event: VoiceWSEvent) => void;

/**
 * WebSocket client for streaming voice chat.
 * Handles reconnection, audio streaming, and event dispatch.
 */
export class VoiceWebSocket {
  private ws: WebSocket | null = null;
  private listeners: VoiceWSListener[] = [];
  private audioListeners: ((data: ArrayBuffer) => void)[] = [];
  private reconnectAttempts = 0;
  private maxReconnects = 5;
  private url: string;

  constructor(url: string) {
    this.url = url;
  }

  connect(config: VoiceWSConfig = {}): void {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = this.url.startsWith("ws") ? this.url : `${protocol}//${window.location.host}${this.url}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.ws?.send(
        JSON.stringify({
          type: "session_start",
          language: config.language ?? "en",
          vad_sensitivity: config.vadSensitivity ?? "medium",
          tts_enabled: config.ttsEnabled ?? true,
        })
      );
    };

    this.ws.onmessage = (e) => {
      if (e.data instanceof Blob) {
        e.data.arrayBuffer().then((buf) => this.audioListeners.forEach((l) => l(buf)));
      } else {
        try {
          const event = JSON.parse(e.data) as VoiceWSEvent;
          this.listeners.forEach((l) => l(event));
        } catch {}
      }
    };

    this.ws.onclose = () => {
      if (this.reconnectAttempts < this.maxReconnects) {
        const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
        this.reconnectAttempts++;
        setTimeout(() => this.connect(config), delay);
      }
    };
  }

  sendAudio(pcm16: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(pcm16);
    }
  }

  bargeIn(): void {
    this.ws?.send(JSON.stringify({ type: "barge_in" }));
  }

  disconnect(): void {
    this.maxReconnects = 0;
    this.ws?.send(JSON.stringify({ type: "session_end" }));
    this.ws?.close();
    this.ws = null;
  }

  onEvent(listener: VoiceWSListener): () => void {
    this.listeners.push(listener);
    return () => { this.listeners = this.listeners.filter((l) => l !== listener); };
  }

  onAudio(listener: (data: ArrayBuffer) => void): () => void {
    this.audioListeners.push(listener);
    return () => { this.audioListeners = this.audioListeners.filter((l) => l !== listener); };
  }
}
