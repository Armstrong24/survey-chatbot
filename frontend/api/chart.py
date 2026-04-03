"""
Vercel Serverless Function - POST /api/chart
Generates chart configuration JSON from survey data.
"""

import os
import json
import time
import re
import requests
import pandas as pd
from http.server import BaseHTTPRequestHandler
from langchain_openai import ChatOpenAI


def _clean_env(value: str) -> str:
    return value.strip().replace("\n", "").replace("\r", "")


OPENROUTER_API_KEY = _clean_env(os.environ.get("OPENROUTER_API_KEY", ""))
OPENROUTER_MODEL = _clean_env(os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
OPENROUTER_BASE_URL = _clean_env(os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
OPENROUTER_SITE_URL = _clean_env(os.environ.get("OPENROUTER_SITE_URL", ""))
OPENROUTER_APP_NAME = _clean_env(os.environ.get("OPENROUTER_APP_NAME", "Survey Chatbot"))
GOOGLE_API_KEY = _clean_env(os.environ.get("GOOGLE_API_KEY", ""))
GOOGLE_SHEET_ID = _clean_env(os.environ.get("GOOGLE_SHEET_ID", "1ABWgQgUzBKHr1Gd9mGUJ4TgeYj-M8KFrE1cP9gjyl4s"))
GOOGLE_SHEET_TAB = _clean_env(os.environ.get("GOOGLE_SHEET_TAB", "Form Responses 1"))

CACHE_TTL = 60
_cached_df = None
_cache_time = 0.0

CHART_PALETTE = [
    "#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981",
    "#3b82f6", "#f43f5e", "#14b8a6", "#64748b", "#0ea5e9",
]

CHART_SYSTEM_PROMPT = """
You are an expert data visualization assistant for survey analytics.
Return ONLY valid JSON.

Expected shape:
{
  "chart_type": "bar" | "horizontal_bar" | "line" | "pie" | "donut" | "scatter" | "area" | "stacked_bar",
  "title": "question-like title ending with ?",
  "x_label": "label",
  "y_label": "label",
  "legend_title": "legend",
  "colors": ["#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#3b82f6"],
  "data": [{"category": "text", "value": 12.3, "color_index": 0}],
  "tooltip_format": "{category}: {value}",
  "show_grid": true,
  "show_legend": true,
  "note": "brief insight"
}

If impossible, return:
{"error": "reason", "suggestion": "what to ask instead"}

Rules:
- Never invent columns
- Max 20 data points
- Use provided schema and profile

Schema:
{{SCHEMA_HINT}}

Profile:
{{COLUMN_PROFILE}}

User question:
{{USER_QUESTION}}
"""


def load_df() -> pd.DataFrame:
    global _cached_df, _cache_time
    if _cached_df is not None and (time.time() - _cache_time) < CACHE_TTL:
        return _cached_df

    tab = requests.utils.quote(GOOGLE_SHEET_TAB)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{GOOGLE_SHEET_ID}/values/{tab}?key={GOOGLE_API_KEY}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    rows = resp.json().get("values", [])
    headers = rows[0]
    records = [
        dict(zip(headers, row + [""] * (len(headers) - len(row))))
        for row in rows[1:]
    ]

    _cached_df = pd.DataFrame(records)
    _cache_time = time.time()
    return _cached_df


def _series_is_numeric(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.notna().sum() >= max(3, int(0.6 * len(series)))


def _build_schema_hint(df: pd.DataFrame) -> str:
    lines = []
    for col in df.columns:
        s = df[col].fillna("").astype(str).str.strip()
        s = s[s != ""]
        if s.empty:
            lines.append(f"- {col}: empty")
            continue
        if _series_is_numeric(s):
            n = pd.to_numeric(s, errors="coerce").dropna()
            lines.append(f"- {col}: numeric (min={n.min():.1f}, max={n.max():.1f}, non_null={len(n)})")
        else:
            lines.append(f"- {col}: categorical (unique={s.nunique()})")
    return "\n".join(lines)


def _build_column_profile(df: pd.DataFrame) -> str:
    lines = []
    for col in df.columns:
        s = df[col].fillna("").astype(str).str.strip()
        s = s[s != ""]
        if s.empty:
            continue
        if _series_is_numeric(s):
            n = pd.to_numeric(s, errors="coerce").dropna()
            lines.append(f"{col}: mean={n.mean():.2f}, median={n.median():.2f}")
        else:
            top = s.value_counts().head(8)
            lines.append(f"{col}: " + "; ".join([f"{k} ({v})" for k, v in top.items()]))
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    payload = text.strip()
    if payload.startswith("```"):
        payload = re.sub(r"^```(?:json)?", "", payload, flags=re.IGNORECASE).strip()
        if payload.endswith("```"):
            payload = payload[:-3].strip()
    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Invalid JSON response from model")
    return json.loads(payload[start:end + 1])


def _sanitize(config: dict) -> dict:
    if "error" in config:
        return {
            "error": str(config.get("error", "Unable to build chart.")),
            "suggestion": str(config.get("suggestion", "Try asking with exact column names.")),
        }

    colors = config.get("colors") if isinstance(config.get("colors"), list) else []
    colors = [c for c in colors if isinstance(c, str) and c.startswith("#")]
    if not colors:
        colors = CHART_PALETTE

    raw_data = config.get("data") if isinstance(config.get("data"), list) else []
    data = []
    for idx, item in enumerate(raw_data[:20]):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "Unknown"))
        try:
            value = round(float(item.get("value", 0)), 1)
        except (TypeError, ValueError):
            continue
        data.append({
            "category": category,
            "value": value,
            "color_index": int(item.get("color_index", idx)) % len(colors),
            "x": item.get("x"),
            "y": item.get("y"),
            "series": item.get("series"),
        })

    if not data:
        return {
            "error": "No chartable data returned.",
            "suggestion": "Ask for counts by a single categorical column.",
        }

    title = str(config.get("title", "Survey chart?"))
    if not title.endswith("?"):
        title = title.rstrip(".") + "?"

    return {
        "chart_type": str(config.get("chart_type", "bar")),
        "title": title,
        "x_label": str(config.get("x_label", "Category")),
        "y_label": str(config.get("y_label", "Value")),
        "legend_title": str(config.get("legend_title", "Survey Data")),
        "colors": colors,
        "data": data,
        "tooltip_format": str(config.get("tooltip_format", "{category}: {value}")),
        "show_grid": bool(config.get("show_grid", True)),
        "show_legend": bool(config.get("show_legend", True)),
        "note": str(config.get("note", "Generated from current survey responses."))[:140],
    }


def _generate_chart_config(message: str) -> tuple[dict, int]:
    df = load_df()
    headers = {}
    if OPENROUTER_SITE_URL:
        headers["HTTP-Referer"] = OPENROUTER_SITE_URL
    if OPENROUTER_APP_NAME:
        headers["X-Title"] = OPENROUTER_APP_NAME

    llm = ChatOpenAI(
        model=OPENROUTER_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,
        default_headers=headers or None,
    )

    prompt = (
        CHART_SYSTEM_PROMPT.replace("{{SCHEMA_HINT}}", _build_schema_hint(df))
        .replace("{{COLUMN_PROFILE}}", _build_column_profile(df))
        .replace("{{USER_QUESTION}}", message)
    )

    raw = llm.invoke(prompt)
    config = _sanitize(_extract_json(getattr(raw, "content", str(raw))))
    return config, len(df)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        message = body.get("message", "").strip()
        session_id = body.get("session_id", "default")

        if not message:
            self._error(400, "message is required")
            return
        if not OPENROUTER_API_KEY:
            self._error(503, "OPENROUTER_API_KEY not configured in Vercel env vars")
            return
        if not GOOGLE_API_KEY:
            self._error(503, "GOOGLE_API_KEY not configured in Vercel env vars")
            return

        try:
            config, total = _generate_chart_config(message)
            self._json({
                "type": "chart",
                "data": config,
                "session_id": session_id,
                "total_responses": total,
            })
        except Exception as e:
            self._error(500, f"Chart generation error: {e}")

    def _json(self, data: dict):
        payload = json.dumps(data).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, code: int, msg: str):
        payload = json.dumps({"detail": msg}).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *args):
        pass
