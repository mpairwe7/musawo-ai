/**
 * Web Worker for on-device STT via @xenova/transformers (whisper-tiny).
 * Runs in a dedicated thread to avoid blocking the UI.
 *
 * Messages:
 *   → { type: "init" }              — Load the Whisper model
 *   → { type: "transcribe", audio }  — Transcribe Float32Array audio
 *   ← { type: "progress", ... }     — Download/load progress
 *   ← { type: "ready" }             — Model loaded successfully
 *   ← { type: "result", text }      — Transcription result
 *   ← { type: "error", message }    — Error
 */

let pipeline: any = null;
let transcriber: any = null;

self.onmessage = async (e: MessageEvent) => {
  const { type } = e.data;

  if (type === "init") {
    try {
      // Dynamic import — @xenova/transformers is a large package
      const { pipeline: createPipeline, env } = await import(
        "@xenova/transformers"
      );

      // Use browser cache (IndexedDB) for model storage
      env.allowLocalModels = false;
      env.useBrowserCache = true;

      self.postMessage({ type: "progress", status: "loading", progress: 0 });

      transcriber = await createPipeline(
        "automatic-speech-recognition",
        "Xenova/whisper-tiny",
        {
          progress_callback: (progress: any) => {
            if (progress.status === "download" || progress.status === "progress") {
              self.postMessage({
                type: "progress",
                status: progress.status,
                file: progress.file,
                progress: progress.progress ?? 0,
                loaded: progress.loaded,
                total: progress.total,
              });
            }
          },
        }
      );

      self.postMessage({ type: "ready" });
    } catch (err: any) {
      self.postMessage({ type: "error", message: err?.message || String(err) });
    }
    return;
  }

  if (type === "transcribe") {
    if (!transcriber) {
      self.postMessage({ type: "error", message: "Model not loaded" });
      return;
    }

    try {
      const audio: Float32Array = e.data.audio;
      const result = await transcriber(audio, {
        language: e.data.language || "en",
        task: "transcribe",
        chunk_length_s: 30,
        stride_length_s: 5,
      });

      self.postMessage({
        type: "result",
        text: result?.text?.trim() || "",
      });
    } catch (err: any) {
      self.postMessage({ type: "error", message: err?.message || String(err) });
    }
  }
};
