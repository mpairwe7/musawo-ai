/**
 * Robust API client with exponential backoff, jitter, and error classification.
 * Designed for unreliable networks common in rural Uganda deployments.
 */

const API_BASE = "/api";

// ── Error classification ──────────────────────────────────────────────

export type ApiErrorType = "network" | "timeout" | "server" | "client" | "unknown";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly type: ApiErrorType,
    public readonly status?: number,
    public readonly retryable: boolean = false
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function classifyError(error: unknown, status?: number): ApiError {
  if (error instanceof ApiError) return error;

  if (error instanceof TypeError && "message" in error) {
    // Network errors (offline, DNS failure, CORS)
    if (
      error.message.includes("Failed to fetch") ||
      error.message.includes("NetworkError") ||
      error.message.includes("Load failed")
    ) {
      return new ApiError("Network error — check your connection", "network", undefined, true);
    }
  }

  if (error instanceof DOMException && error.name === "AbortError") {
    return new ApiError("Request timed out", "timeout", undefined, true);
  }

  if (status !== undefined) {
    if (status >= 500) {
      return new ApiError(`Server error (${status})`, "server", status, true);
    }
    if (status === 429) {
      return new ApiError("Rate limited — please wait", "server", status, true);
    }
    if (status >= 400) {
      return new ApiError(`Client error (${status})`, "client", status, false);
    }
  }

  const msg = error instanceof Error ? error.message : String(error);
  return new ApiError(msg, "unknown", undefined, false);
}

// ── Retry with exponential backoff + jitter ───────────────────────────

interface RetryOptions {
  maxAttempts?: number;
  baseDelay?: number;
  maxDelay?: number;
  timeout?: number;
}

const DEFAULT_RETRY: Required<RetryOptions> = {
  maxAttempts: 5,
  baseDelay: 500,
  maxDelay: 15000,
  timeout: 30000,
};

function jitter(delay: number): number {
  // Full jitter: random between 0 and delay
  return Math.random() * delay;
}

export async function fetchWithRetry(
  url: string,
  init?: RequestInit,
  options?: RetryOptions
): Promise<Response> {
  const opts = { ...DEFAULT_RETRY, ...options };
  let lastError: ApiError | null = null;

  for (let attempt = 0; attempt < opts.maxAttempts; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), opts.timeout);

    try {
      const response = await fetch(url, {
        ...init,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        return response;
      }

      lastError = classifyError(null, response.status);

      // Don't retry client errors (4xx except 429)
      if (!lastError.retryable) {
        throw lastError;
      }
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof ApiError) {
        lastError = error;
        if (!error.retryable) throw error;
      } else {
        lastError = classifyError(error);
        if (!lastError.retryable) throw lastError;
      }
    }

    // Exponential backoff with full jitter
    if (attempt < opts.maxAttempts - 1) {
      const delay = jitter(Math.min(opts.baseDelay * 2 ** attempt, opts.maxDelay));
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError ?? new ApiError("Max retries exceeded", "unknown", undefined, false);
}

// ── Typed API methods ─────────────────────────────────────────────────

export interface ChatRequest {
  query: string;
  mode: string;
  locale?: string;
  session_id?: string;
}

export interface ChatResponse {
  response: string;
  confidence: string;
  citations: Array<{ ref: string; source: string; section: string }>;
  triage: Record<string, unknown> | null;
  session_id: string;
  escalation?: boolean;
  grounding_warning?: string;
}

export async function apiChat(
  data: ChatRequest,
  options?: RetryOptions
): Promise<ChatResponse> {
  const res = await fetchWithRetry(
    `${API_BASE}/v1/chat`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    },
    { ...options, maxAttempts: options?.maxAttempts ?? 3 }
  );
  return res.json();
}

export async function apiHealth(options?: RetryOptions): Promise<{ status: string; llm_ready: boolean }> {
  const res = await fetchWithRetry(`${API_BASE}/health`, undefined, {
    ...options,
    maxAttempts: 2,
    timeout: 10000,
  });
  return res.json();
}

export async function apiFacilities(
  district?: string,
  options?: RetryOptions
): Promise<unknown[]> {
  const params = district ? `?district=${encodeURIComponent(district)}` : "";
  const res = await fetchWithRetry(`${API_BASE}/v1/facilities${params}`, undefined, options);
  return res.json();
}
