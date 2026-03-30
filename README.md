# Pune Plastic Bag Survey — Data Analysis Chatbot

> Ask plain-English questions about your live survey data and get dynamically calculated answers powered by Gemini AI.

---

## Architecture

```
Browser (Next.js + Tailwind)
        │
        │  HTTP (REST)
        ▼
FastAPI Backend (Python)
        │
        ├── gspread ──────────► Google Sheets (live data)
        │
        └── LangChain Pandas Agent ──► Gemini 1.5 Flash
```

---

## Project Structure

```
/
├── backend/
│   ├── main.py               ← FastAPI server (all backend logic)
│   ├── requirements.txt      ← Python dependencies
│   ├── .env.example          ← Copy to .env and fill in your keys
│   └── credentials.json      ← YOUR Google service account key (you add this)
│
├── frontend/
│   ├── app/
│   │   ├── layout.tsx        ← Root layout
│   │   ├── page.tsx          ← Main chat page
│   │   └── globals.css       ← Tailwind + custom animations
│   ├── components/
│   │   ├── Sidebar.tsx       ← Project info + live count + suggestions
│   │   ├── MessageBubble.tsx ← Chat message component
│   │   └── TypingIndicator.tsx ← Animated dots while AI thinks
│   ├── lib/
│   │   └── api.ts            ← Typed API client
│   ├── package.json
│   ├── tailwind.config.ts
│   └── .env.local.example    ← Copy to .env.local and fill in backend URL
│
└── README.md
```

---

## Setup: Step-by-Step

### Part 1 — Google Cloud Setup (one-time)

**Step 1: Create a Google Cloud Project**
1. Go to https://console.cloud.google.com/
2. Create a new project (or use an existing one)

**Step 2: Enable APIs**
1. In the left menu: APIs & Services → Enable APIs
2. Enable: **Google Sheets API**
3. Enable: **Google Drive API**

**Step 3: Create a Service Account**
1. IAM & Admin → Service Accounts → Create Service Account
2. Give it any name (e.g. `survey-chatbot`)
3. Skip the optional role grants and click Done

**Step 4: Download the credentials JSON**
1. Click on your new service account
2. Keys tab → Add Key → Create new key → JSON
3. A `credentials.json` file will download
4. **Place it in the `backend/` folder**

**Step 5: Share your Google Sheet with the service account**
1. Open `credentials.json` and copy the `client_email` value
   (it looks like `survey-chatbot@your-project.iam.gserviceaccount.com`)
2. Open your Google Sheet
3. Share it with that email address (Viewer access is enough)

---

### Part 2 — Backend Setup

```bash
cd backend

# 1. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your .env file
cp .env.example .env
```

Now open `backend/.env` and fill in your values:

```env
# From https://aistudio.google.com/app/apikey
GEMINI_API_KEY=AIza...your_key_here...

# Exact name of your Google Sheet (the title, NOT the URL)
GOOGLE_SHEET_NAME=Form Responses 1

# Path to your service account credentials file
CREDENTIALS_JSON_PATH=credentials.json
```

**Run the backend:**

```bash
python main.py
# OR
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Verify it works: open http://localhost:8000/health → should return `{"status": "ok"}`

Check live count: open http://localhost:8000/stats → shows total responses

---

### Part 3 — Frontend Setup

```bash
cd frontend

# 1. Install Node dependencies
npm install

# 2. Create your .env.local file
cp .env.local.example .env.local
```

The default `.env.local` points to `http://localhost:8000`. If your backend is
running locally, no changes needed.

**Run the frontend:**

```bash
npm run dev
```

Open http://localhost:3000 — you should see the chat interface.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `SpreadsheetNotFound` | Share the sheet with the service account's `client_email` |
| `GOOGLE_SHEET_NAME is not set` | Add `GOOGLE_SHEET_NAME` to your `.env` file |
| `GEMINI_API_KEY is not set` | Add your Gemini key to `.env` |
| `credentials.json not found` | Place the file in the `backend/` folder |
| `CORS error` in browser | Make sure the FastAPI backend is running on port 8000 |
| AI gives wrong numbers | The sheet column names may differ — ask "What columns are available?" |

---

## Adding Your Google Sheet URL Later

When you have the Google Sheet link:

1. Open the sheet
2. Look at the **tab name at the bottom** (e.g. "Form Responses 1")
3. Set `GOOGLE_SHEET_NAME=Form Responses 1` in `backend/.env`

That's it — the backend uses the sheet name to find it, not the URL.

---

## Environment Variables Reference

### Backend (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Gemini API key from aistudio.google.com |
| `GOOGLE_SHEET_NAME` | Yes | Exact name of the Google Sheet tab |
| `CREDENTIALS_JSON_PATH` | Yes | Path to service account JSON (default: `credentials.json`) |
| `CACHE_TTL_SECONDS` | No | How often to refresh data (default: 60) |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | URL of the FastAPI backend (default: `http://localhost:8000`) |

---

## How It Works

1. **Data Loading**: On first chat message, the backend authenticates with Google Sheets using the service account, fetches all responses as a Pandas DataFrame, and caches it for 60 seconds.

2. **Agent**: A LangChain Pandas DataFrame Agent wraps the DataFrame with a Gemini 1.5 Flash LLM. The agent can write and execute Python/pandas code dynamically to answer any question.

3. **Memory**: Each browser tab gets its own `session_id`. The backend stores a `ConversationBufferWindowMemory` (last 10 turns) per session. Follow-up questions ("What about the second reason?") work because the previous context is injected into each prompt.

4. **Frontend**: Next.js 14 App Router + Tailwind CSS. The sidebar polls `/stats` every 30 seconds to show the live response count. Messages fade in with animation. A typing indicator (animated dots) shows while the agent is computing.
