"""
=============================================================================
Survey Data Analysis Chatbot — FastAPI Backend
=============================================================================
Survey: "Awareness and Readiness to use Sustainable alternatives to
         plastic bags in Pune"

SETUP CHECKLIST (read before running):
  1. Copy .env.example → .env and fill in your values
  2. Place your credentials.json (Google service account) in this folder
  3. Share your Google Sheet with the service account email
  4. pip install -r requirements.txt
  5. python main.py
=============================================================================
"""

import os
import time
import logging
import re
import json
from typing import Optional
from pathlib import Path

import requests
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# LangChain imports
from langchain_openai import ChatOpenAI
from langchain_experimental.agents import create_pandas_dataframe_agent

from prompts.chart_system_prompt import CHART_SYSTEM_PROMPT


class SessionMemory:
    """Minimal in-process chat memory with a fixed window size."""

    def __init__(self, k: int = 10):
        self.k = k
        self._turns: list[tuple[str, str]] = []

    def load_memory_variables(self, _inputs: dict) -> dict:
        recent_turns = self._turns[-self.k:]
        history_lines: list[str] = []
        for user_msg, ai_msg in recent_turns:
            history_lines.append(f"User: {user_msg}")
            history_lines.append(f"Assistant: {ai_msg}")
        return {"chat_history": "\n".join(history_lines)}

    def save_context(self, inputs: dict, outputs: dict) -> None:
        user_msg = str(inputs.get("input", "")).strip()
        ai_msg = str(outputs.get("output", "")).strip()
        if user_msg or ai_msg:
            self._turns.append((user_msg, ai_msg))

# ---------------------------------------------------------------------------
# Load environment variables from .env file
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# CONFIGURATION — Edit your .env file, NOT this file directly
# ---------------------------------------------------------------------------

# OpenRouter API key (https://openrouter.ai/keys)
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

# OpenRouter endpoint and model
OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

# Optional OpenRouter attribution headers
OPENROUTER_SITE_URL: str = os.getenv("OPENROUTER_SITE_URL", "")
OPENROUTER_APP_NAME: str = os.getenv("OPENROUTER_APP_NAME", "Survey Chatbot")

# Google Sheet ID — the long ID from your sheet URL between /d/ and /edit
# URL: https://docs.google.com/spreadsheets/d/<THIS_PART>/edit
GOOGLE_SHEET_ID: str = os.getenv(
    "GOOGLE_SHEET_ID",
    "1ABWgQgUzBKHr1Gd9mGUJ4TgeYj-M8KFrE1cP9gjyl4s"  # Your sheet ID (pre-filled)
)

# Google API Key — no JSON file needed, no service account needed
# Get from: Google Cloud Console → APIs & Services → Credentials → + Create Credentials → API Key
# Make sure Google Sheets API is enabled and your sheet is set to "Anyone with the link can view"
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

# Name of the worksheet tab (default "Form Responses 1" for Google Forms)
GOOGLE_SHEET_TAB: str = os.getenv("GOOGLE_SHEET_TAB", "Form Responses 1")

# How many seconds before refreshing data from Google Sheets
CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "60"))

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Survey Chatbot API",
    description="LangChain Pandas Agent over Pune plastic bag survey data",
    version="1.0.0",
)

# Allow all origins so the Next.js dev server (localhost:3000) can connect.
# In production, replace "*" with your actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # e.g. ["https://yourapp.com"] in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# DataFrame cache
# ---------------------------------------------------------------------------
_cached_df: Optional[pd.DataFrame] = None
_cache_timestamp: float = 0.0


def load_dataframe() -> pd.DataFrame:
    """
    Fetch survey data from Google Sheets using the Sheets REST API v4.

    No credentials.json required — uses a plain Google API Key.

    Requirements:
      1. GOOGLE_API_KEY set in your .env (from Google Cloud Console → Credentials → API Key)
      2. Google Sheets API enabled in your Google Cloud project
      3. Your Google Sheet shared as "Anyone with the link → Viewer"
    """
    if not GOOGLE_API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY is not set. "
            "Go to Google Cloud Console → APIs & Services → Credentials → "
            "+ Create Credentials → API Key, then add it to your .env file."
        )

    if not GOOGLE_SHEET_ID:
        raise ValueError("GOOGLE_SHEET_ID is not set in your .env file.")

    # URL-encode the tab name to handle spaces (e.g. "Form Responses 1" → "Form+Responses+1")
    tab = requests.utils.quote(GOOGLE_SHEET_TAB)

    # Google Sheets API v4 — values endpoint
    # Returns all data from the specified tab as a list of rows
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{GOOGLE_SHEET_ID}"
        f"/values/{tab}?key={GOOGLE_API_KEY}"
    )

    response = requests.get(url, timeout=15)

    if response.status_code == 403:
        raise ValueError(
            "Google Sheets API returned 403 Forbidden. "
            "Make sure: (1) Google Sheets API is enabled in your Cloud project, "
            "(2) your sheet is set to 'Anyone with the link can view', "
            "(3) your API key is correct."
        )
    if response.status_code == 404:
        raise ValueError(
            f"Sheet not found (404). Check GOOGLE_SHEET_ID and GOOGLE_SHEET_TAB in your .env. "
            f"Tab name used: '{GOOGLE_SHEET_TAB}'"
        )

    response.raise_for_status()
    data = response.json()

    rows = data.get("values", [])
    if not rows or len(rows) < 2:
        raise ValueError(
            "The Google Sheet appears to be empty or has no response rows. "
            "Make sure the sheet has a header row and at least one form response."
        )

    # First row is the header, remaining rows are responses
    headers = rows[0]
    records = []
    for row in rows[1:]:
        # Pad short rows with empty strings (some fields may be blank)
        padded = row + [""] * (len(headers) - len(row))
        records.append(dict(zip(headers, padded)))

    df = pd.DataFrame(records)
    logger.info(f"Loaded {len(df)} responses via Google Sheets API (tab: '{GOOGLE_SHEET_TAB}').")
    return df


def get_cached_dataframe() -> pd.DataFrame:
    """
    Return the cached DataFrame if it's still fresh (< CACHE_TTL_SECONDS old).
    Otherwise reload from Google Sheets.

    This prevents hammering the Google Sheets API on every chat message
    while still capturing new form responses regularly.
    """
    global _cached_df, _cache_timestamp

    age = time.time() - _cache_timestamp
    if _cached_df is None or age >= CACHE_TTL_SECONDS:
        logger.info("Cache expired or empty — reloading from Google Sheets...")
        _cached_df = load_dataframe()
        _cache_timestamp = time.time()
    else:
        logger.info(f"Using cached DataFrame ({age:.0f}s old, TTL={CACHE_TTL_SECONDS}s).")

    return _cached_df


# ---------------------------------------------------------------------------
# LangChain Agent
# ---------------------------------------------------------------------------

# Strong system prompt — instructs the agent to always calculate from data,
# never hallucinate, and respond conversationally with survey context.
AGENT_PREFIX = """
You are an expert environmental data analyst for a survey about plastic bag usage
in Pune, India. The survey is titled:
"Awareness and Readiness to use Sustainable alternatives to plastic bags in Pune."

You have access to a live pandas DataFrame called `df` containing all survey responses.

===================== CRITICAL RULES — NEVER BREAK THESE =====================

1. ALWAYS calculate answers dynamically from the DataFrame.
   NEVER invent, estimate, or guess statistics from memory.

2. For percentages:
   (df['column'].value_counts(normalize=True) * 100).round(1)

3. For counts:
   df['column'].value_counts()

4. For total responses:
   len(df)

5. For multi-select columns (comma-separated values in one cell):
   df['column'].str.split(',').explode().str.strip().value_counts()

6. Always mention the current total number of responses for context.
   Example: "Based on our {len(df)} current responses, roughly 79% are students."

7. Give clear, conversational answers. Be friendly and insightful.
   After stating the number, briefly explain what it means in context.

8. If you cannot find a column, run df.columns.tolist() to see available columns,
   then pick the closest match and explain which column you used.

9. Output formatting rules:
    - Do NOT use HTML tags (no <br>, <table>, etc.).
    - Do NOT include code blocks.
    - Use short headings and plain bullets.
    - Keep spacing compact and readable.

=================== SURVEY QUESTION → COLUMN MAPPING ========================

Q1  → Age Group
Q2  → Occupation
Q3  → Approximate Monthly Household Income (or similar income column)
Q4  → PMC ban / plastic ban awareness
Q5  → Sustainable alternatives familiar with (multi-select)
Q6  → Harm rating on a scale of 1–5
Q7  → Frequency of using single-use plastic bags
Q8  → Where they receive plastic bags
Q9  → What they do with plastic bags after bringing home
Q10 → Own a reusable shopping bag
Q11 → How often carry reusable bag
Q12 → Price point to refuse a plastic bag
Q13 → Willingness to pay for a sustainable bag
Q14 → Items ready to replace plastic bags for (multi-select)
Q15 → Main reasons still use plastic bags (multi-select, top 2)
Q16 → What would encourage switch to sustainable bags

==============================================================================
"""


def _create_llm() -> ChatOpenAI:
    """Create ChatOpenAI client with provider-specific headers."""
    default_headers = {}
    if OPENROUTER_SITE_URL:
        default_headers["HTTP-Referer"] = OPENROUTER_SITE_URL
    if OPENROUTER_APP_NAME:
        default_headers["X-Title"] = OPENROUTER_APP_NAME

    return ChatOpenAI(
        model=OPENROUTER_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,
        default_headers=default_headers or None,
    )


def create_agent(df: pd.DataFrame, agent_type: str = "tool-calling"):
    """
    Build a LangChain Pandas DataFrame Agent using OpenRouter.

    The agent can write and execute Python/pandas code against the DataFrame
    to answer any natural-language question about the survey data.
    """
    if not OPENROUTER_API_KEY:
        raise ValueError(
            "OPENROUTER_API_KEY is not set. Get yours at https://openrouter.ai/keys "
            "and add it to your .env file."
        )

    # OpenAI-compatible client with deterministic output.
    llm = _create_llm()

    common_kwargs = dict(
        llm=llm,
        df=df,
        prefix=AGENT_PREFIX,
        verbose=True,               # Set False in production to reduce server logs
        allow_dangerous_code=True,  # Required to let the agent run pandas code
        max_iterations=10,          # Prevents infinite loops
    )

    # Newer LangChain releases prefer string-based agent types.
    # Fall back to legacy AgentType enum for older versions.
    try:
        agent = create_pandas_dataframe_agent(
            **common_kwargs,
            agent_type=agent_type,
        )
    except Exception:
        from langchain.agents import AgentType as LegacyAgentType

        fallback_type = (
            LegacyAgentType.OPENAI_FUNCTIONS
            if agent_type == "tool-calling"
            else LegacyAgentType.ZERO_SHOT_REACT_DESCRIPTION
        )
        agent = create_pandas_dataframe_agent(
            **common_kwargs,
            agent_type=fallback_type,
        )

    return agent


def _build_df_summary(df: pd.DataFrame, top_n: int = 10) -> str:
    """Create a compact text summary so LLM can answer without tool execution."""
    parts = [f"Total responses: {len(df)}", f"Columns: {', '.join(df.columns.tolist())}"]
    for col in df.columns:
        series = df[col].fillna("").astype(str).str.strip()
        non_empty = series[series != ""]
        if non_empty.empty:
            continue
        top = non_empty.value_counts().head(top_n)
        top_text = "; ".join([f"{k} ({v})" for k, v in top.items()])
        parts.append(f"{col}: {top_text}")
    return "\n".join(parts)


def _is_general_chat(message: str) -> bool:
    """Detect casual prompts that should bypass dataframe-agent parsing."""
    m = message.strip().lower()
    patterns = [
        r"^thanks?\b",
        r"^thank\s+you\b",
        r"^ok(ay)?\b",
        r"^hi\b|^hello\b|^hey\b",
        r"\bhow are you\b",
        r"\bwho are you\b",
        r"\bwhat can you do\b",
        r"\bgood (morning|afternoon|evening|night)\b",
    ]
    return any(re.search(p, m) for p in patterns)


def _direct_chat_reply(message: str, history: str, df: pd.DataFrame) -> str:
    """Fallback plain response path that avoids tool/output parser issues."""
    summary = _build_df_summary(df, top_n=5)
    prompt = (
        "You are a helpful assistant for a Pune plastic-bag survey chatbot. "
        "If the user is chatting casually, respond naturally and briefly. "
        "If the user asks a survey question, answer from the survey summary only. "
        "Do not use HTML or code blocks.\n\n"
        f"Survey summary:\n{summary}\n\n"
        f"Previous conversation:\n{history}\n\n"
        f"User message: {message}"
    )
    raw = _create_llm().invoke(prompt)
    return getattr(raw, "content", str(raw))


def _select_agent_candidates() -> list:
    """Use the most stable agent mode across providers/models."""
    return ["zero-shot-react-description"]


# ---------------------------------------------------------------------------
# Conversation memory store (in-process; resets on server restart)
# ---------------------------------------------------------------------------

# Keyed by session_id — each browser tab/user gets their own memory
_conversation_memories: dict[str, SessionMemory] = {}


def get_or_create_memory(session_id: str) -> SessionMemory:
    """
    Return existing memory for this session, or create a new one.
    k=10 keeps the last 10 turns (5 user + 5 AI) in context window.
    """
    if session_id not in _conversation_memories:
        _conversation_memories[session_id] = SessionMemory(k=10)
        logger.info(f"Created new memory for session '{session_id}'.")
    return _conversation_memories[session_id]


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"  # Frontend sends a unique ID per browser tab


class ChatResponse(BaseModel):
    response: str
    session_id: str
    total_responses: int


class StatsResponse(BaseModel):
    total_responses: int
    columns: list
    cache_age_seconds: int
    error: Optional[str] = None


class ChartRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChartResponse(BaseModel):
    type: str = "chart"
    data: dict
    session_id: str
    total_responses: int


_CHART_PALETTE = [
    "#6366f1",
    "#8b5cf6",
    "#ec4899",
    "#f59e0b",
    "#10b981",
    "#3b82f6",
    "#f43f5e",
    "#14b8a6",
    "#64748b",
    "#0ea5e9",
]


def _series_is_numeric(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.notna().sum() >= max(3, int(0.6 * len(series)))


def _build_schema_hint(df: pd.DataFrame) -> str:
    lines: list[str] = []
    for col in df.columns:
        series = df[col].fillna("").astype(str).str.strip()
        non_empty = series[series != ""]
        if non_empty.empty:
            lines.append(f"- {col}: empty")
            continue

        if _series_is_numeric(non_empty):
            numeric = pd.to_numeric(non_empty, errors="coerce").dropna()
            lines.append(
                f"- {col}: numeric (min={numeric.min():.1f}, max={numeric.max():.1f}, non_null={len(numeric)})"
            )
        else:
            unique_count = non_empty.nunique()
            sample_values = ", ".join(non_empty.value_counts().head(5).index.tolist())
            lines.append(
                f"- {col}: categorical (unique={unique_count}, top={sample_values})"
            )
    return "\n".join(lines)


def _build_column_profile(df: pd.DataFrame) -> str:
    profile: list[str] = []
    for col in df.columns:
        series = df[col].fillna("").astype(str).str.strip()
        non_empty = series[series != ""]
        if non_empty.empty:
            continue

        if _series_is_numeric(non_empty):
            numeric = pd.to_numeric(non_empty, errors="coerce").dropna()
            profile.append(
                f"{col}: mean={numeric.mean():.2f}, median={numeric.median():.2f}, std={numeric.std(ddof=0):.2f}"
            )
        else:
            top = non_empty.value_counts().head(8)
            top_text = "; ".join([f"{k} ({v})" for k, v in top.items()])
            profile.append(f"{col}: {top_text}")
    return "\n".join(profile)


def _extract_json_object(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Model returned invalid JSON payload.")
    return text[start : end + 1]


def _sanitize_chart_config(config: dict) -> dict:
    if "error" in config:
        return {
            "error": str(config.get("error", "Unable to build chart.")),
            "suggestion": str(config.get("suggestion", "Try rephrasing with exact survey columns.")),
        }

    chart_type = str(config.get("chart_type", "bar"))
    allowed_types = {
        "bar",
        "clustered_column",
        "horizontal_bar",
        "clustered_bar",
        "line",
        "pie",
        "donut",
        "scatter",
        "bubble",
        "area",
        "stacked_bar",
        "radar",
        "heatmap",
        "pyramid",
        "funnel",
        "waterfall",
        "gantt",
        "histogram",
        "bullet",
        "gauge",
        "diverging_bar",
        "comparison",
        "venn",
    }
    if chart_type not in allowed_types:
        chart_type = "bar"

    colors = config.get("colors") if isinstance(config.get("colors"), list) else []
    clean_colors = [str(c) for c in colors if isinstance(c, str) and c.startswith("#")]
    if not clean_colors:
        clean_colors = _CHART_PALETTE

    raw_data = config.get("data") if isinstance(config.get("data"), list) else []
    data = []
    for idx, item in enumerate(raw_data[:20]):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "Unknown"))
        try:
            value = float(item.get("value", 0))
        except (TypeError, ValueError):
            continue
        data.append(
            {
                "category": category,
                "value": round(value, 1),
                "color_index": int(item.get("color_index", idx)) % len(clean_colors),
                "x": item.get("x"),
                "y": item.get("y"),
                "z": item.get("z"),
                "size": item.get("size"),
                "target": item.get("target"),
                "min": item.get("min"),
                "max": item.get("max"),
                "start": item.get("start"),
                "end": item.get("end"),
                "group": item.get("group"),
                "label": item.get("label"),
                "series": item.get("series"),
            }
        )

    if not data:
        return {
            "error": "No chartable data returned.",
            "suggestion": "Try asking for counts by one survey column.",
        }

    title = str(config.get("title", "Survey chart?"))
    if not title.endswith("?"):
        title = title.rstrip(".") + "?"

    return {
        "chart_type": chart_type,
        "title": title,
        "x_label": str(config.get("x_label", "Category")),
        "y_label": str(config.get("y_label", "Value")),
        "legend_title": str(config.get("legend_title", "Survey Data")),
        "colors": clean_colors,
        "data": data,
        "tooltip_format": str(
            config.get("tooltip_format", "{category}: {value}")
        ),
        "show_grid": bool(config.get("show_grid", True)),
        "show_legend": bool(config.get("show_legend", True)),
        "note": str(config.get("note", "Generated from current survey responses."))[:140],
    }


def _is_time_series_request(user_message: str) -> bool:
    msg = user_message.lower()
    time_words = ["timestamp", "time", "date", "daily", "monthly", "trend", "over time"]
    response_words = ["response", "responses", "count", "counts", "submissions"]
    return any(w in msg for w in time_words) and any(w in msg for w in response_words)


def _find_time_column(df: pd.DataFrame) -> tuple[Optional[str], Optional[pd.Series]]:
    name_hint_cols = [
        col
        for col in df.columns
        if any(k in col.lower() for k in ["timestamp", "date", "time", "submitted", "created"])
    ]
    candidate_cols = name_hint_cols if name_hint_cols else list(df.columns)

    for col in candidate_cols:
        raw = df[col].fillna("").astype(str).str.strip()
        parsed = pd.to_datetime(raw, errors="coerce")
        valid_ratio = parsed.notna().mean()
        if valid_ratio >= 0.5:
            return col, parsed

    return None, None


def _build_time_series_fallback(df: pd.DataFrame, user_message: str) -> Optional[dict]:
    col, parsed = _find_time_column(df)
    if not col or parsed is None:
        return None

    ts = parsed.dropna()
    if ts.empty:
        return None

    # Use daily counts for short ranges; switch to monthly when daily points are too many.
    day_counts = ts.dt.strftime("%Y-%m-%d").value_counts().sort_index()
    if len(day_counts) > 20:
        series = ts.dt.to_period("M").astype(str).value_counts().sort_index()
        x_label = f"{col} (month)"
        note = "Auto-aggregated by month for readability"
    else:
        series = day_counts
        x_label = f"{col} (day)"
        note = "Counts of responses over time"

    if len(series) > 20:
        series = series.tail(20)
        note = "Showing latest 20 periods"

    data = [
        {
            "category": str(idx),
            "value": round(float(val), 1),
            "color_index": i % len(_CHART_PALETTE),
        }
        for i, (idx, val) in enumerate(series.items())
    ]

    title = f"How do responses change over {col}?"
    if "over" in user_message.lower() and "timestamp" in user_message.lower():
        title = "How do responses change over timestamp?"

    return {
        "chart_type": "line",
        "title": title,
        "x_label": x_label,
        "y_label": "Number of Responses",
        "legend_title": "Responses",
        "colors": _CHART_PALETTE,
        "data": data,
        "tooltip_format": "{category}: {value} responses",
        "show_grid": True,
        "show_legend": False,
        "note": note,
    }


def _find_column(df: pd.DataFrame, keywords: list[str]) -> Optional[str]:
    cols = list(df.columns)
    lowers = {c: c.lower() for c in cols}
    for kw in keywords:
        for c in cols:
            if kw in lowers[c]:
                return c
    return None


def _to_bool_series(series: pd.Series) -> pd.Series:
    yes_tokens = ["yes", "aware", "willing", "own", "always", "often", "true", "1"]
    no_tokens = ["no", "not", "never", "false", "0"]
    s = series.fillna("").astype(str).str.strip().str.lower()

    def parse(v: str) -> Optional[bool]:
        if not v:
            return None
        if any(tok in v for tok in yes_tokens):
            return True
        if any(tok in v for tok in no_tokens):
            return False
        return None

    parsed = s.map(parse)
    return parsed


def _willingness_to_score(series: pd.Series) -> pd.Series:
    s = series.fillna("").astype(str).str.strip()
    numeric = pd.to_numeric(s, errors="coerce")
    if numeric.notna().mean() >= 0.4:
        return numeric.fillna(numeric.median() if numeric.notna().any() else 0)

    lower = s.str.lower()

    def map_text(v: str) -> float:
        if not v:
            return 0.0
        if "not" in v and "willing" in v:
            return 1.0
        if "very" in v and "willing" in v:
            return 5.0
        if "willing" in v:
            return 4.0
        if "maybe" in v or "neutral" in v:
            return 3.0
        if "low" in v or "less" in v or "small" in v:
            return 2.0
        if "high" in v or "more" in v or "premium" in v:
            return 4.5
        return 3.0

    return lower.map(map_text)


def _extract_scaled_number(text: str) -> Optional[float]:
    t = str(text or "").strip().lower()
    if not t:
        return None

    multiplier = 1.0
    if "lakh" in t or "lac" in t:
        multiplier = 100000.0
    elif "crore" in t:
        multiplier = 10000000.0
    elif re.search(r"\bk\b", t):
        multiplier = 1000.0

    nums = re.findall(r"-?\d+(?:\.\d+)?", t.replace(",", ""))
    if not nums:
        return None

    vals = [float(n) * multiplier for n in nums]
    if len(vals) >= 2:
        return (vals[0] + vals[1]) / 2.0
    return vals[0]


def _series_to_numeric_flexible(series: pd.Series) -> pd.Series:
    s = series.fillna("").astype(str).str.strip()
    n = pd.to_numeric(s, errors="coerce")
    missing = n.isna()
    if missing.any():
        n.loc[missing] = s.loc[missing].map(_extract_scaled_number)
    return n


def _requested_chart_type(message: str) -> Optional[str]:
    m = message.lower()
    mapping = [
        ("clustered column", "clustered_column"),
        ("clustered bar", "clustered_bar"),
        ("horizontal bar", "horizontal_bar"),
        ("stacked bar", "stacked_bar"),
        ("comparison", "comparison"),
        ("histogram", "histogram"),
        ("venn", "venn"),
        ("bullet", "bullet"),
        ("gantt", "gantt"),
        ("heatmap", "heatmap"),
        ("radar", "radar"),
        ("funnel", "funnel"),
        ("pyramid", "pyramid"),
        ("waterfall", "waterfall"),
        ("gauge", "gauge"),
        ("diverging", "diverging_bar"),
        ("bubble", "bubble"),
        ("scatter", "scatter"),
        ("donut", "donut"),
        ("pie", "pie"),
        ("area", "area"),
        ("line", "line"),
        ("bar", "bar"),
    ]
    for needle, ctype in mapping:
        if needle in m:
            return ctype
    return None


def _coerce_chart_for_renderer(config: dict, message: str) -> dict:
    if "error" in config:
        return config

    ctype = str(config.get("chart_type", "bar"))
    data = config.get("data") if isinstance(config.get("data"), list) else []
    if not data:
        return {
            "chart_type": "bar",
            "title": "What is the total number of responses?",
            "x_label": "Metric",
            "y_label": "Count",
            "legend_title": "Survey Data",
            "colors": _CHART_PALETTE,
            "data": [{"category": "Responses", "value": 1.0, "color_index": 0}],
            "tooltip_format": "{category}: {value}",
            "show_grid": True,
            "show_legend": False,
            "note": "Fallback chart generated automatically",
        }

    # Ensure grouped chart variants have series; otherwise convert to a simple bar.
    if ctype in {"comparison", "clustered_column", "clustered_bar", "stacked_bar"}:
        has_series = any(isinstance(d.get("series"), str) and str(d.get("series", "")).strip() for d in data)
        if not has_series:
            config["chart_type"] = "bar"
            config["note"] = "Series breakdown unavailable; showing single-series comparison"

    if ctype in {"scatter", "bubble"}:
        for i, d in enumerate(data):
            d["x"] = float(d.get("x", i + 1) or (i + 1))
            d["y"] = float(d.get("y", d.get("value", 0)) or 0)
            d["z"] = float(d.get("z", d.get("size", d.get("value", 1))) or 1)

    if ctype == "gantt":
        for i, d in enumerate(data):
            start = d.get("start")
            end = d.get("end")
            start_num = float(start if start is not None else i * 7)
            end_num = float(end if end is not None else start_num + max(1.0, float(d.get("value", 1) or 1)))
            d["start"] = start_num
            d["end"] = max(start_num + 0.5, end_num)

    if ctype == "bullet":
        vals = [float(d.get("value", 0) or 0) for d in data]
        target = round(float(sum(vals) / max(1, len(vals))), 1)
        for d in data:
            if d.get("target") is None:
                d["target"] = target

    if ctype == "gauge":
        d0 = data[0]
        d0["min"] = float(d0.get("min", 0) or 0)
        d0["max"] = float(d0.get("max", 100) or 100)

    normalized_title = str(config.get("title", "Survey chart?")).strip()
    if not normalized_title:
        normalized_title = "Survey chart?"
    if not normalized_title.endswith("?"):
        normalized_title = normalized_title.rstrip(".") + "?"
    config["title"] = normalized_title
    return config


def _build_direct_chart(df: pd.DataFrame, message: str) -> Optional[dict]:
    m = message.lower()
    ctype = _requested_chart_type(message)

    age_col = _find_column(df, ["age"])
    own_bag_col = _find_column(df, ["own a reusable", "reusable bag", "own reusable", "own bag"])
    awareness_col = _find_column(df, ["ban awareness", "aware", "pmc ban", "plastic ban"])
    willing_col = _find_column(df, ["willingness", "willing to pay", "pay", "price point"])
    occupation_col = _find_column(df, ["occupation", "profession"])
    harm_col = _find_column(df, ["harm", "rating", "scale", "1-5"])
    income_col = _find_column(df, ["monthly household income", "monthly income", "income"])

    if ctype in {"scatter", "bubble"} and income_col and harm_col:
        x = _series_to_numeric_flexible(df[income_col])
        y = _series_to_numeric_flexible(df[harm_col])
        pairs = pd.DataFrame({"x": x, "y": y, "label": df[income_col].fillna("").astype(str).str.strip()}).dropna(subset=["x", "y"])

        if pairs.empty:
            # Fallback: map income categories to ordinal positions if range parsing fails.
            labels = df[income_col].fillna("").astype(str).str.strip()
            valid = labels[labels != ""]
            ordered = valid.drop_duplicates().tolist()
            if ordered:
                mapping = {k: i + 1 for i, k in enumerate(ordered)}
                x_ord = labels.map(lambda v: mapping.get(v.strip(), None) if isinstance(v, str) else None)
                pairs = pd.DataFrame({"x": x_ord, "y": y, "label": labels}).dropna(subset=["x", "y"])

        if not pairs.empty:
            rows = []
            for i, row in pairs.head(40).reset_index(drop=True).iterrows():
                rows.append(
                    {
                        "category": row["label"] if row["label"] else f"Point {i + 1}",
                        "value": round(float(row["y"]), 1),
                        "x": round(float(row["x"]), 2),
                        "y": round(float(row["y"]), 2),
                        "z": round(float(abs(row["y"]) or 1), 2),
                    }
                )

            return {
                "chart_type": ctype,
                "title": "How does monthly income relate to harm rating?",
                "x_label": "Monthly Income",
                "y_label": "Harm Rating (1-5)",
                "legend_title": "Income vs Harm",
                "colors": _CHART_PALETTE,
                "data": rows,
                "show_grid": True,
                "show_legend": False,
                "note": "Scatter points are built from individual response rows",
            }

    if ctype in {"comparison", "clustered_column", "clustered_bar", "stacked_bar"} and age_col and own_bag_col:
        tmp = df[[age_col, own_bag_col]].fillna("").astype(str).apply(lambda s: s.str.strip())
        tmp = tmp[(tmp[age_col] != "") & (tmp[own_bag_col] != "")]
        if not tmp.empty:
            ctab = pd.crosstab(tmp[age_col], tmp[own_bag_col])
            rows = []
            for age in ctab.index.tolist()[:10]:
                for own in ctab.columns.tolist()[:6]:
                    rows.append(
                        {
                            "category": str(age),
                            "series": str(own),
                            "value": float(ctab.loc[age, own]),
                        }
                    )
            return {
                "chart_type": ctype,
                "title": "How does reusable bag ownership vary by age group?",
                "x_label": age_col,
                "y_label": "Responses",
                "legend_title": own_bag_col,
                "colors": _CHART_PALETTE,
                "data": rows,
                "show_grid": True,
                "show_legend": True,
                "note": "Computed from live cross-tabulated survey responses",
            }

    if ctype == "histogram" and harm_col:
        s = df[harm_col].fillna("").astype(str).str.strip()
        n = pd.to_numeric(s, errors="coerce")
        if n.notna().any():
            vc = n.round(0).clip(lower=1, upper=10).value_counts().sort_index().head(20)
            rows = [{"category": str(int(idx)), "value": float(val)} for idx, val in vc.items()]
            return {
                "chart_type": "histogram",
                "title": "What is the distribution of harm ratings?",
                "x_label": "Harm Rating",
                "y_label": "Responses",
                "legend_title": "Count",
                "colors": _CHART_PALETTE,
                "data": rows,
                "show_grid": True,
                "show_legend": False,
                "note": "Histogram bins derived from actual rating values",
            }

    if ctype == "funnel" and awareness_col and own_bag_col and willing_col:
        aware = (_to_bool_series(df[awareness_col]) == True)
        own = (_to_bool_series(df[own_bag_col]) == True)
        willing = (_to_bool_series(df[willing_col]) == True)
        total = float(len(df))
        s1 = float(aware.sum())
        s2 = float((aware & own).sum())
        s3 = float((aware & own & willing).sum())
        data = [
            {"category": "Total Respondents", "value": total},
            {"category": "Aware of Ban", "value": s1},
            {"category": "Aware + Own Reusable Bag", "value": s2},
            {"category": "Aware + Own + Willing to Pay", "value": s3},
        ]
        return {
            "chart_type": "funnel",
            "title": "How does awareness convert into willingness to pay for sustainable bags?",
            "x_label": "Stage",
            "y_label": "Respondents",
            "legend_title": "Conversion Funnel",
            "colors": _CHART_PALETTE,
            "data": data,
            "show_grid": False,
            "show_legend": True,
            "note": "Funnel stages are computed from boolean overlaps in live responses",
        }

    if ctype == "pyramid":
        reasons_col = _find_column(df, ["reason", "still use plastic", "main reasons"])
        if reasons_col:
            s = df[reasons_col].fillna("").astype(str).str.strip()
            exploded = s[s != ""].str.split(",").explode().str.strip()
            vc = exploded[exploded != ""].value_counts().head(8)
            if not vc.empty:
                data = [
                    {"category": str(k), "value": float(v), "color_index": i % len(_CHART_PALETTE)}
                    for i, (k, v) in enumerate(vc.items())
                ]
                return {
                    "chart_type": "pyramid",
                    "title": "What are the top reasons people still use plastic bags?",
                    "x_label": "Reason",
                    "y_label": "Mentions",
                    "legend_title": "Top Reasons",
                    "colors": _CHART_PALETTE,
                    "data": data,
                    "show_grid": False,
                    "show_legend": True,
                    "note": "Multi-select reasons are split and counted from responses",
                }

    if ctype == "venn" and awareness_col and own_bag_col and willing_col:
        a = _to_bool_series(df[awareness_col]) == True
        b = _to_bool_series(df[own_bag_col]) == True
        c = _to_bool_series(df[willing_col]) == True
        rows = [
            {"category": "Aware of Ban", "value": float(a.sum())},
            {"category": "Own Reusable Bag", "value": float(b.sum())},
            {"category": "All Three Overlap", "value": float((a & b & c).sum())},
        ]
        return {
            "chart_type": "venn",
            "title": "How much overlap exists between awareness, ownership, and willingness to pay?",
            "x_label": "Sets",
            "y_label": "Respondents",
            "legend_title": "Overlap",
            "colors": _CHART_PALETTE,
            "data": rows,
            "show_grid": False,
            "show_legend": True,
            "note": "Overlap uses respondents positive on all three conditions",
        }

    if ctype == "bullet" and occupation_col and willing_col:
        tmp = df[[occupation_col, willing_col]].copy()
        tmp[occupation_col] = tmp[occupation_col].fillna("").astype(str).str.strip()
        tmp = tmp[tmp[occupation_col] != ""]
        tmp["score"] = _willingness_to_score(tmp[willing_col])
        grp = tmp.groupby(occupation_col)["score"].mean().sort_values(ascending=False).head(10)
        target = round(float(tmp["score"].mean()), 1) if not tmp.empty else 3.0
        rows = [{"category": str(k), "value": round(float(v), 1), "target": target} for k, v in grp.items()]
        if rows:
            return {
                "chart_type": "bullet",
                "title": "How does willingness to pay compare against target by occupation?",
                "x_label": "Score",
                "y_label": occupation_col,
                "legend_title": "Willingness Score",
                "colors": _CHART_PALETTE,
                "data": rows,
                "show_grid": True,
                "show_legend": True,
                "note": "Target is overall mean willingness score",
            }

    if ctype == "gantt":
        tcol, parsed = _find_time_column(df)
        if tcol and parsed is not None and parsed.notna().any():
            ts = parsed.dropna().sort_values()
            start = ts.min()
            end = ts.max()
            total_days = max(4, int((end - start).days) + 1)
            step = max(1, total_days // 4)
            phases = [
                "Awareness Drive",
                "Community Mobilization",
                "Retail Conversion",
                "Impact Review",
            ]
            rows = []
            cur = 0
            for i, phase in enumerate(phases):
                s = cur
                e = min(total_days, cur + step + (1 if i == len(phases) - 1 else 0))
                rows.append({"category": phase, "value": float(e - s), "start": float(s), "end": float(e)})
                cur = e
            return {
                "chart_type": "gantt",
                "title": "What campaign timeline can be derived from the response period?",
                "x_label": "Days from first response",
                "y_label": "Campaign Phase",
                "legend_title": "Duration",
                "colors": _CHART_PALETTE,
                "data": rows,
                "show_grid": True,
                "show_legend": False,
                "note": "Phases are evenly derived from observed survey response window",
            }

    return None


def _best_categorical_column(df: pd.DataFrame, exclude: set[str] | None = None) -> Optional[str]:
    ex = exclude or set()
    best_col = None
    best_score = -1
    for col in df.columns:
        if col in ex:
            continue
        s = df[col].fillna("").astype(str).str.strip()
        non_empty = s[s != ""]
        if non_empty.empty:
            continue
        if _series_is_numeric(non_empty):
            continue
        uniq = non_empty.nunique()
        if 2 <= uniq <= 40 and uniq > best_score:
            best_score = uniq
            best_col = col
    return best_col


def _best_numeric_column(df: pd.DataFrame, exclude: set[str] | None = None) -> Optional[str]:
    ex = exclude or set()
    best_col = None
    best_non_null = -1
    for col in df.columns:
        if col in ex:
            continue
        s = df[col].fillna("").astype(str).str.strip()
        n = pd.to_numeric(s, errors="coerce")
        non_null = int(n.notna().sum())
        if non_null >= 3 and non_null > best_non_null:
            best_non_null = non_null
            best_col = col
    return best_col


def _build_universal_fallback_chart(df: pd.DataFrame, message: str) -> dict:
    ctype = _requested_chart_type(message) or "bar"
    cat1 = _best_categorical_column(df)
    cat2 = _best_categorical_column(df, exclude={cat1} if cat1 else set())
    num1 = _best_numeric_column(df)
    num2 = _best_numeric_column(df, exclude={num1} if num1 else set())

    def category_counts(col: Optional[str]) -> list[dict]:
        if col:
            s = df[col].fillna("").astype(str).str.strip()
            vc = s[s != ""].value_counts().head(12)
            if not vc.empty:
                return [
                    {"category": str(k), "value": float(v), "color_index": i % len(_CHART_PALETTE)}
                    for i, (k, v) in enumerate(vc.items())
                ]
        return [{"category": "Responses", "value": float(len(df)), "color_index": 0}]

    base = category_counts(cat1)
    title = f"Auto-generated {ctype.replace('_', ' ')} chart from available survey data?"

    if ctype in {"bar", "horizontal_bar", "line", "area", "pie", "donut", "radar", "pyramid", "funnel", "histogram"}:
        data = base
    elif ctype in {"comparison", "clustered_column", "clustered_bar", "stacked_bar"} and cat1 and cat2:
        tmp = df[[cat1, cat2]].fillna("").astype(str).apply(lambda s: s.str.strip())
        tmp = tmp[(tmp[cat1] != "") & (tmp[cat2] != "")]
        ctab = pd.crosstab(tmp[cat1], tmp[cat2]).head(10)
        data = []
        for c in ctab.index:
            for s in ctab.columns[:6]:
                data.append({"category": str(c), "series": str(s), "value": float(ctab.loc[c, s])})
        if not data:
            ctype = "bar"
            data = base
    elif ctype in {"scatter", "bubble"}:
        if num1 and num2:
            n1 = pd.to_numeric(df[num1], errors="coerce")
            n2 = pd.to_numeric(df[num2], errors="coerce")
            pair = pd.DataFrame({"x": n1, "y": n2}).dropna().head(40)
            data = [
                {
                    "category": f"Point {i + 1}",
                    "value": float(row.y),
                    "x": float(row.x),
                    "y": float(row.y),
                    "z": float(abs(row.y) if ctype == "bubble" else 1),
                }
                for i, row in pair.reset_index(drop=True).iterrows()
            ]
        else:
            ctype = "bar"
            data = base
    elif ctype == "heatmap" and cat1 and cat2:
        tmp = df[[cat1, cat2]].fillna("").astype(str).apply(lambda s: s.str.strip())
        tmp = tmp[(tmp[cat1] != "") & (tmp[cat2] != "")]
        ctab = pd.crosstab(tmp[cat1], tmp[cat2]).head(10)
        data = []
        for y in ctab.index:
            for x in ctab.columns[:10]:
                data.append({"category": str(x), "series": str(y), "x": str(x), "y": str(y), "value": float(ctab.loc[y, x])})
        if not data:
            ctype = "bar"
            data = base
    elif ctype == "waterfall":
        vals = [d["value"] for d in base[:8]]
        running = 0.0
        data = []
        for i, d in enumerate(base[:8]):
            delta = float(vals[i] - (vals[i - 1] if i > 0 else 0))
            running += delta
            data.append({"category": d["category"], "value": delta})
    elif ctype == "gantt":
        data = []
        cursor = 0.0
        for d in base[:6]:
            dur = max(1.0, float(d["value"]))
            data.append({"category": d["category"], "value": dur, "start": cursor, "end": cursor + dur})
            cursor += dur
    elif ctype == "bullet":
        avg = round(sum(d["value"] for d in base) / max(1, len(base)), 1)
        data = [{"category": d["category"], "value": d["value"], "target": avg} for d in base[:10]]
    elif ctype == "gauge":
        if num1:
            n = pd.to_numeric(df[num1], errors="coerce").dropna()
            value = float(n.mean()) if not n.empty else float(len(df))
            mn = float(n.min()) if not n.empty else 0.0
            mx = float(n.max()) if not n.empty else max(100.0, value)
        else:
            value, mn, mx = float(len(df)), 0.0, float(max(100, len(df)))
        data = [{"category": "Score", "value": value, "min": mn, "max": mx}]
    elif ctype == "diverging_bar":
        avg = sum(d["value"] for d in base) / max(1, len(base))
        data = [{"category": d["category"], "value": float(d["value"] - avg)} for d in base[:10]]
    elif ctype == "venn":
        v1 = float(base[0]["value"]) if len(base) > 0 else float(len(df))
        v2 = float(base[1]["value"]) if len(base) > 1 else max(1.0, v1 * 0.8)
        overlap = max(0.0, min(v1, v2) * 0.5)
        l1 = str(base[0]["category"]) if len(base) > 0 else "Set A"
        l2 = str(base[1]["category"]) if len(base) > 1 else "Set B"
        data = [
            {"category": l1, "value": v1},
            {"category": l2, "value": v2},
            {"category": "Overlap", "value": overlap},
        ]
    else:
        ctype = "bar"
        data = base

    return {
        "chart_type": ctype,
        "title": title,
        "x_label": cat1 or "Category",
        "y_label": num1 or "Responses",
        "legend_title": cat2 or "Survey Data",
        "colors": _CHART_PALETTE,
        "data": data[:40],
        "tooltip_format": "{category}: {value}",
        "show_grid": True,
        "show_legend": True,
        "note": "Built automatically from available columns to guarantee chart output",
    }


def _generate_chart_config(df: pd.DataFrame, user_message: str) -> dict:
    direct = _build_direct_chart(df, user_message)
    if direct:
        return _coerce_chart_for_renderer(_sanitize_chart_config(direct), user_message)

    if _is_time_series_request(user_message):
        fallback = _build_time_series_fallback(df, user_message)
        if fallback:
            return _coerce_chart_for_renderer(fallback, user_message)

    schema_hint = _build_schema_hint(df)
    column_profile = _build_column_profile(df)
    prompt = (
        CHART_SYSTEM_PROMPT.replace("{{SCHEMA_HINT}}", schema_hint)
        .replace("{{COLUMN_PROFILE}}", column_profile)
        .replace("{{USER_QUESTION}}", user_message)
    )

    raw = _create_llm().invoke(prompt)
    content = getattr(raw, "content", str(raw))
    parsed = json.loads(_extract_json_object(content))
    sanitized = _coerce_chart_for_renderer(_sanitize_chart_config(parsed), user_message)

    if "error" in sanitized and _is_time_series_request(user_message):
        fallback = _build_time_series_fallback(df, user_message)
        if fallback:
            return _coerce_chart_for_renderer(fallback, user_message)

    if "error" in sanitized:
        direct = _build_direct_chart(df, user_message)
        if direct:
            return _coerce_chart_for_renderer(_sanitize_chart_config(direct), user_message)

    if "error" in sanitized:
        universal = _build_universal_fallback_chart(df, user_message)
        return _coerce_chart_for_renderer(_sanitize_chart_config(universal), user_message)

    return sanitized


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Quick liveness check — used by frontend to verify the API is up."""
    return {"status": "ok", "message": "Survey Chatbot API is running."}


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    Return live stats from the Google Sheet.
    Called by the frontend to display "Total Live Responses: X".
    """
    try:
        df = get_cached_dataframe()
        age = int(time.time() - _cache_timestamp)
        return StatsResponse(
            total_responses=len(df),
            columns=df.columns.tolist(),
            cache_age_seconds=age,
        )
    except Exception as e:
        logger.error(f"Error loading stats: {e}")
        return StatsResponse(
            total_responses=0,
            columns=[],
            cache_age_seconds=0,
            error=str(e),
        )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint. Accepts a natural-language question and returns
    a dynamically-calculated answer from the live survey DataFrame.

    Flow:
      1. Load (or return cached) DataFrame from Google Sheets
      2. Build conversation prompt with memory context
      3. Run LangChain Pandas Agent
      4. Save exchange to memory
      5. Return response
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        # Step 1: Get fresh survey data
        df = get_cached_dataframe()

        # Step 2: Build prompt with conversation history for context
        memory = get_or_create_memory(request.session_id)
        history = memory.load_memory_variables({}).get("chat_history", "")

        if history:
            full_prompt = (
                f"Previous conversation:\n{history}\n\n"
                f"User's new question: {request.message}"
            )
        else:
            full_prompt = request.message

        if _is_general_chat(request.message):
            result = _direct_chat_reply(request.message, history, df)
            memory.save_context(
                {"input": request.message},
                {"output": result},
            )
            return ChatResponse(
                response=result,
                session_id=request.session_id,
                total_responses=len(df),
            )

        logger.info(f"[{request.session_id}] Q: {request.message}")

        # Step 3: Build and run agent with provider-aware fallbacks
        last_error = None
        result = None
        for agent_type in _select_agent_candidates():
            try:
                agent = create_agent(df, agent_type=agent_type)
                result = agent.run(full_prompt)
                break
            except Exception as e:
                err = str(e)
                if (
                    "Could not parse LLM output" in err
                    or "output parsing error occurred" in err
                ):
                    result = _direct_chat_reply(request.message, history, df)
                    break
                if (
                    ("python_repl_ast" in err and "missing properties: 'query'" in err)
                    or "Tool choice is none, but model called a tool" in err
                ):
                    logger.warning(
                        f"Agent mode '{agent_type}' incompatible for this model; retrying fallback mode."
                    )
                    last_error = e
                    continue
                raise

        if result is None:
            # Final fallback: answer directly without tool execution.
            summary = _build_df_summary(df)
            fallback_prompt = (
                "You are analyzing survey data. Use ONLY the provided summary. "
                "Answer directly with counts/percentages when available. "
                "If exact value is not available, say so briefly and provide the closest insight.\n\n"
                f"Survey summary:\n{summary}\n\n"
                f"Previous conversation:\n{history}\n\n"
                f"User question: {request.message}"
            )
            raw = _create_llm().invoke(fallback_prompt)
            result = getattr(raw, "content", str(raw))

        # Step 5: Save to memory
        memory.save_context(
            {"input": request.message},
            {"output": result},
        )

        logger.info(f"[{request.session_id}] A: {result[:120]}...")

        return ChatResponse(
            response=result,
            session_id=request.session_id,
            total_responses=len(df),
        )

    except ValueError as e:
        # Configuration errors (missing API key, sheet name, etc.)
        logger.error(f"Configuration error: {e}")
        raise HTTPException(status_code=503, detail=str(e))

    except Exception as e:
        logger.error(f"Agent error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"The agent encountered an error: {str(e)}. "
                   "Try rephrasing your question.",
        )


async def _handle_chart_request(request: ChartRequest) -> ChartResponse:
    """Generate a structured chart configuration from a natural-language request."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        df = get_cached_dataframe()
        chart_config = _generate_chart_config(df, request.message)

        memory = get_or_create_memory(request.session_id)
        memory.save_context(
            {"input": request.message},
            {"output": f"[chart] {chart_config.get('title', 'Chart generated')}"},
        )

        return ChartResponse(
            data=chart_config,
            session_id=request.session_id,
            total_responses=len(df),
        )
    except ValueError as e:
        logger.error(f"Chart generation validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Unable to generate chart right now. Try a clearer chart request.",
        )


@app.post("/chart", response_model=ChartResponse)
async def chart(request: ChartRequest):
    return await _handle_chart_request(request)


@app.post("/api/chart", response_model=ChartResponse)
async def api_chart(request: ChartRequest):
    """Compatibility alias for static deployments expecting /api/* routes."""
    return await _handle_chart_request(request)


@app.delete("/chat/{session_id}")
async def clear_chat(session_id: str):
    """Clear conversation memory for a given session (called by 'Clear Chat' button)."""
    if session_id in _conversation_memories:
        del _conversation_memories[session_id]
        logger.info(f"Cleared memory for session '{session_id}'.")
    return {"status": "cleared", "session_id": session_id}


# ---------------------------------------------------------------------------
# Serve Next.js static frontend (built output from frontend/out/)
# Everything on ONE port — http://localhost:8000
# ---------------------------------------------------------------------------

# Path to the Next.js static export folder
# Run `npm run build` inside the frontend/ folder first to generate this
FRONTEND_OUT = Path(__file__).parent.parent / "frontend" / "out"

if FRONTEND_OUT.exists():
    # Serve static assets (JS, CSS, images) at /_next/
    app.mount("/_next", StaticFiles(directory=str(FRONTEND_OUT / "_next")), name="next-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        """
        Catch-all route — serves the Next.js static export for any non-API path.
        This makes http://localhost:8000 open the chat UI directly.
        """
        # Try exact file first (e.g. /favicon.ico)
        candidate = FRONTEND_OUT / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))

        # Try path/index.html for Next.js page routes
        index = FRONTEND_OUT / full_path / "index.html"
        if index.exists():
            return FileResponse(str(index))

        # Fallback to root index.html
        return FileResponse(str(FRONTEND_OUT / "index.html"))
else:
    logger.warning(
        "Frontend build not found at 'frontend/out/'. "
        "Run `cd frontend && npm run build` to generate it. "
        "API endpoints are still fully functional."
    )


# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("Survey Chatbot started — http://localhost:8000")
    logger.info(f"LLM model: {OPENROUTER_MODEL}")
    if FRONTEND_OUT.exists():
        logger.info("Frontend: serving from frontend/out/ ✓")
    else:
        logger.info("Frontend: NOT built yet — run `cd frontend && npm run build`")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    # Single command to run everything:  python main.py
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
