/**
 * API client for the FastAPI backend.
 *
 * Base URL is read from NEXT_PUBLIC_API_URL environment variable.
 * Default: http://localhost:8000
 */

// ---------------------------------------------------------------------------
// On Vercel: API calls go to /api/* on the same origin (no env var needed).
// Local dev with FastAPI: set NEXT_PUBLIC_API_URL=http://localhost:8000
// ---------------------------------------------------------------------------
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined" ? window.location.origin : "");

export interface ChatResponse {
  response: string;
  session_id: string;
  total_responses: number;
}

export interface StatsResponse {
  total_responses: number;
  columns: string[];
  cache_age_seconds: number;
  error?: string;
}

/**
 * Send a chat message to the backend and return the AI response.
 */
export async function sendMessage(
  message: string,
  sessionId: string
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Fetch live stats (total responses count) from the backend.
 */
export async function fetchStats(): Promise<StatsResponse> {
  const res = await fetch(`${API_BASE}/api/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/**
 * Clear the conversation memory on the backend for this session.
 */
export async function clearChat(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/api/chat`, { method: "DELETE" }); // no-op on Vercel (stateless)
}
