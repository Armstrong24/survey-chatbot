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

// In local development (NEXT_PUBLIC_API_URL set), FastAPI routes are /chat and /stats.
// On Vercel (no env var), routes are exposed under /api/*.
const API_PREFIX = process.env.NEXT_PUBLIC_API_URL ? "" : "/api";

export interface ChatResponse {
  response: string;
  session_id: string;
  total_responses: number;
}

export interface ChartPoint {
  category: string;
  value: number;
  color_index?: number;
  x?: number;
  y?: number;
  series?: string;
}

export interface ChartConfig {
  chart_type?:
    | "bar"
    | "horizontal_bar"
    | "line"
    | "pie"
    | "donut"
    | "scatter"
    | "area"
    | "stacked_bar";
  title?: string;
  x_label?: string;
  y_label?: string;
  legend_title?: string;
  colors?: string[];
  data?: ChartPoint[];
  tooltip_format?: string;
  show_grid?: boolean;
  show_legend?: boolean;
  note?: string;
  error?: string;
  suggestion?: string;
}

export interface ChartResponse {
  type: "chart";
  data: ChartConfig;
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
  const res = await fetch(`${API_BASE}${API_PREFIX}/chat`, {
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
  const res = await fetch(`${API_BASE}${API_PREFIX}/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/**
 * Clear the conversation memory on the backend for this session.
 */
export async function clearChat(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}${API_PREFIX}/chat/${sessionId}`, { method: "DELETE" });
}

/**
 * Send a chart request to the backend and return chart config.
 */
export async function sendChartRequest(
  message: string,
  sessionId: string
): Promise<ChartResponse> {
  const res = await fetch(`${API_BASE}${API_PREFIX}/chart`, {
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
