/**
 * On-device Speech-to-Text via @xenova/transformers (whisper-tiny).
 * Enables fully offline voice input — critical for rural Uganda deployment.
 *
 * The Whisper model (~50MB) runs entirely in the browser via ONNX Runtime WASM.
 * Model files are cached in IndexedDB for offline reuse.
 */

export type ModelStatus = "not-loaded" | "loading" | "ready" | "error";

type ProgressCallback = (info: {
  status: string;
  progress: number;
  file?: string;
  loaded?: number;
  total?: number;
}) => void;

let worker: Worker | null = null;
let modelStatus: ModelStatus = "not-loaded";
let pendingResolve: ((text: string) => void) | null = null;
let pendingReject: ((err: Error) => void) | null = null;
let progressCallback: ProgressCallback | null = null;

function getWorker(): Worker {
  if (!worker) {
    worker = new Worker(
      new URL("../workers/whisperWorker.ts", import.meta.url),
      { type: "module" }
    );
    worker.onmessage = handleMessage;
    worker.onerror = (e) => {
      modelStatus = "error";
      pendingReject?.(new Error(e.message));
      pendingReject = null;
      pendingResolve = null;
    };
  }
  return worker;
}

function handleMessage(e: MessageEvent): void {
  const { type } = e.data;

  switch (type) {
    case "progress":
      progressCallback?.(e.data);
      break;

    case "ready":
      modelStatus = "ready";
      // Resolve any pending init promise
      pendingResolve?.("");
      pendingResolve = null;
      pendingReject = null;
      break;

    case "result":
      pendingResolve?.(e.data.text || "");
      pendingResolve = null;
      pendingReject = null;
      break;

    case "error":
      modelStatus = "error";
      pendingReject?.(new Error(e.data.message));
      pendingReject = null;
      pendingResolve = null;
      break;
  }
}

/** Get the current model status. */
export function getModelStatus(): ModelStatus {
  return modelStatus;
}

/** Check if on-device STT is available (model loaded and ready). */
export function isOnDeviceSTTAvailable(): boolean {
  return modelStatus === "ready";
}

/**
 * Load the Whisper model. Downloads ~50MB on first use, cached in IndexedDB.
 * Call this proactively (e.g., from Settings) so the model is ready when needed.
 */
export function loadWhisperModel(onProgress?: ProgressCallback): Promise<void> {
  if (modelStatus === "ready") return Promise.resolve();
  if (modelStatus === "loading") {
    // Already loading — just update the progress callback
    if (onProgress) progressCallback = onProgress;
    return new Promise((resolve, reject) => {
      pendingResolve = () => resolve();
      pendingReject = reject;
    });
  }

  modelStatus = "loading";
  if (onProgress) progressCallback = onProgress;

  return new Promise<void>((resolve, reject) => {
    pendingResolve = () => resolve();
    pendingReject = reject;
    getWorker().postMessage({ type: "init" });
  });
}

/**
 * Transcribe audio using the on-device Whisper model.
 * @param audio - Float32Array of audio samples at 16kHz
 * @param language - Language code (e.g., "en", "lg")
 * @returns Transcribed text
 */
export function transcribeAudio(
  audio: Float32Array,
  language: string = "en"
): Promise<string> {
  if (modelStatus !== "ready") {
    return Promise.reject(new Error("Model not loaded. Call loadWhisperModel() first."));
  }

  return new Promise((resolve, reject) => {
    pendingResolve = resolve;
    pendingReject = reject;
    getWorker().postMessage({ type: "transcribe", audio, language }, [audio.buffer]);
  });
}

/**
 * Convert a Blob of recorded audio to Float32Array at 16kHz for Whisper.
 */
export async function audioBufferFromBlob(blob: Blob): Promise<Float32Array> {
  const arrayBuffer = await blob.arrayBuffer();
  const audioCtx = new AudioContext({ sampleRate: 16000 });
  const decoded = await audioCtx.decodeAudioData(arrayBuffer);
  const channelData = decoded.getChannelData(0);
  await audioCtx.close();
  return channelData;
}

/** Terminate the worker and release resources. */
export function disposeOnDeviceSTT(): void {
  worker?.terminate();
  worker = null;
  modelStatus = "not-loaded";
  pendingResolve = null;
  pendingReject = null;
  progressCallback = null;
}
