"""
Vercel Serverless Function — POST /api/chat
Handles chat messages via LangChain Pandas Agent + OpenRouter.
"""

import os
import json
import time
import traceback
import requests
import pandas as pd
from http.server import BaseHTTPRequestHandler

from langchain_openai import ChatOpenAI
from langchain_experimental.agents import create_pandas_dataframe_agent


def _clean_env(value: str) -> str:
    return value.strip().replace("\n", "").replace("\r", "")

# ── Config from Vercel Environment Variables ──────────────────────────────────
OPENROUTER_API_KEY = _clean_env(os.environ.get("OPENROUTER_API_KEY", ""))
OPENROUTER_MODEL = _clean_env(os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
OPENROUTER_BASE_URL = _clean_env(os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
OPENROUTER_SITE_URL = _clean_env(os.environ.get("OPENROUTER_SITE_URL", ""))
OPENROUTER_APP_NAME = _clean_env(os.environ.get("OPENROUTER_APP_NAME", "Survey Chatbot"))
GOOGLE_API_KEY   = _clean_env(os.environ.get("GOOGLE_API_KEY", ""))
GOOGLE_SHEET_ID  = _clean_env(os.environ.get("GOOGLE_SHEET_ID", "1ABWgQgUzBKHr1Gd9mGUJ4TgeYj-M8KFrE1cP9gjyl4s"))
GOOGLE_SHEET_TAB = _clean_env(os.environ.get("GOOGLE_SHEET_TAB", "Form Responses 1"))

# Simple in-memory cache (persists within the same function instance warm window)
_cached_df   = None
_cache_time  = 0.0
CACHE_TTL    = 60  # seconds

AGENT_PREFIX = """
You are an expert environmental data analyst for a survey about plastic bag usage
in Pune, India. The survey is titled:
"Awareness and Readiness to use Sustainable alternatives to plastic bags in Pune."

You have access to a live pandas DataFrame called `df` containing all survey responses.

CRITICAL RULES:
1. ALWAYS calculate answers dynamically from the DataFrame. NEVER invent statistics.
2. For percentages: (df['column'].value_counts(normalize=True) * 100).round(1)
3. For counts: df['column'].value_counts()
4. For total: len(df)
5. Always mention the current total number of responses.
6. Give clear, conversational answers.
7. If you cannot find a column, run df.columns.tolist() first.
"""


def load_df():
    global _cached_df, _cache_time
    if _cached_df is not None and (time.time() - _cache_time) < CACHE_TTL:
        return _cached_df

    tab = requests.utils.quote(GOOGLE_SHEET_TAB)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{GOOGLE_SHEET_ID}"
        f"/values/{tab}?key={GOOGLE_API_KEY}"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    rows = resp.json().get("values", [])
    headers = rows[0]
    records = [
        dict(zip(headers, row + [""] * (len(headers) - len(row))))
        for row in rows[1:]
    ]
    _cached_df  = pd.DataFrame(records)
    _cache_time = time.time()
    return _cached_df


def get_answer(message: str, history: str) -> tuple[str, int]:
    df  = load_df()
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

    common_kwargs = dict(
        llm=llm,
        df=df,
        prefix=AGENT_PREFIX,
        verbose=False,
        allow_dangerous_code=True,
        handle_parsing_errors=True,
        max_iterations=10,
    )

    prompt = f"Previous conversation:\n{history}\n\nUser: {message}" if history else message
    from langchain.agents import AgentType as LegacyAgentType

    is_groq = "api.groq.com" in OPENROUTER_BASE_URL.lower()
    is_gpt_oss = "gpt-oss" in OPENROUTER_MODEL.lower()

    if is_groq or is_gpt_oss:
        # Groq + GPT-OSS: force ReAct-only to avoid tool-call schema mismatch errors.
        agent_candidates = [
            LegacyAgentType.ZERO_SHOT_REACT_DESCRIPTION,
        ]
    else:
        agent_candidates = [
            "tool-calling",
            LegacyAgentType.OPENAI_FUNCTIONS,
            LegacyAgentType.ZERO_SHOT_REACT_DESCRIPTION,
        ]

    last_error = None
    for agent_type in agent_candidates:
        try:
            agent = create_pandas_dataframe_agent(
                **common_kwargs,
                agent_type=agent_type,
            )
        except Exception as e:
            last_error = e
            continue

        try:
            answer = agent.run(prompt)
            return answer, len(df)
        except Exception as e:
            err = str(e)
            if (
                ("python_repl_ast" in err and "missing properties: 'query'" in err)
                or "Tool choice is none, but model called a tool" in err
            ):
                last_error = e
                continue
            raise

    raise last_error or RuntimeError("Failed to generate response with all agent fallbacks")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

    def do_POST(self):
        length  = int(self.headers.get("Content-Length", 0))
        body    = json.loads(self.rfile.read(length))
        message = body.get("message", "").strip()
        history = body.get("history", "")

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
            answer, total = get_answer(message, history)
            self._json({"response": answer, "total_responses": total})
        except Exception as e:
            traceback.print_exc()
            self._error(500, f"OpenRouter error: {e}")

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *args):
        pass  # silence default Apache-style access logs
