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
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain.agents import AgentType
from langchain.memory import ConversationBufferWindowMemory

# ---------------------------------------------------------------------------
# Load environment variables from .env file
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# CONFIGURATION — Edit your .env file, NOT this file directly
# ---------------------------------------------------------------------------

# Get from https://aistudio.google.com/app/apikey  (free tier available)
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

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


def create_agent(df: pd.DataFrame):
    """
    Build a LangChain Pandas DataFrame Agent using Gemini 1.5 Flash.

    The agent can write and execute Python/pandas code against the DataFrame
    to answer any natural-language question about the survey data.
    """
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set. Get yours at https://aistudio.google.com/ "
            "and add it to your .env file."
        )

    # Using Gemini 1.5 Flash — fast and cost-effective for data analysis tasks
    # temperature=0 ensures deterministic, factual answers
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=GEMINI_API_KEY,  # Loaded from .env — never hardcode this
        temperature=0,
        convert_system_message_to_human=True,
    )

    agent = create_pandas_dataframe_agent(
        llm=llm,
        df=df,
        agent_type=AgentType.OPENAI_FUNCTIONS,
        prefix=AGENT_PREFIX,
        verbose=True,           # Set False in production to reduce server logs
        allow_dangerous_code=True,  # Required to let the agent run pandas code
        handle_parsing_errors=True, # Gracefully handles LLM formatting errors
        max_iterations=10,          # Prevents infinite loops
    )

    return agent


# ---------------------------------------------------------------------------
# Conversation memory store (in-process; resets on server restart)
# ---------------------------------------------------------------------------

# Keyed by session_id — each browser tab/user gets their own memory
_conversation_memories: dict[str, ConversationBufferWindowMemory] = {}


def get_or_create_memory(session_id: str) -> ConversationBufferWindowMemory:
    """
    Return existing memory for this session, or create a new one.
    k=10 keeps the last 10 turns (5 user + 5 AI) in context window.
    """
    if session_id not in _conversation_memories:
        _conversation_memories[session_id] = ConversationBufferWindowMemory(
            k=10,
            memory_key="chat_history",
            return_messages=False,
        )
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

        # Step 2: Build agent
        agent = create_agent(df)

        # Step 3: Build prompt with conversation history for context
        memory = get_or_create_memory(request.session_id)
        history = memory.load_memory_variables({}).get("chat_history", "")

        if history:
            full_prompt = (
                f"Previous conversation:\n{history}\n\n"
                f"User's new question: {request.message}"
            )
        else:
            full_prompt = request.message

        logger.info(f"[{request.session_id}] Q: {request.message}")

        # Step 4: Run agent
        result = agent.run(full_prompt)

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
