# Pune Plastic Bag Survey Chatbot

Ask plain-English questions about live survey responses and get data-backed answers.

## Tech Stack

- Frontend: Next.js 14, React 18, TypeScript, Tailwind CSS
- Backend: FastAPI, Pandas, LangChain Experimental Agent
- LLM Provider: OpenRouter (OpenAI-compatible endpoint)
- Data Source: Google Sheets API (reads survey responses from a sheet tab)

## Requirements

### System Requirements

- Node.js 18+
- Python 3.10+
- npm

### Runtime Requirements

- OpenRouter API key
- Google Sheets API key
- Google Sheet ID and tab name

## Project Structure

```text
.
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── package.json
│   └── .env.local.example
└── README.md
```

## Environment Variables

### Backend (`backend/.env`)

Copy `backend/.env.example` to `backend/.env` and set the values:

- `OPENROUTER_API_KEY` (required)
- `OPENROUTER_MODEL` (default: `openai/gpt-4o-mini`)
- `OPENROUTER_BASE_URL` (default: `https://openrouter.ai/api/v1`)
- `OPENROUTER_SITE_URL` (optional)
- `OPENROUTER_APP_NAME` (optional)
- `GOOGLE_API_KEY` (required)
- `GOOGLE_SHEET_ID` (required)
- `GOOGLE_SHEET_TAB` (default: `Form Responses 1`)
- `CACHE_TTL_SECONDS` (default: `60`)

### Frontend (`frontend/.env.local`)

Copy `frontend/.env.local.example` to `frontend/.env.local`:

- `NEXT_PUBLIC_API_URL=http://localhost:8000`

## How to Run

### 1. Start Backend

```powershell
cd backend
"C:/Program Files/Python313/python.exe" -m pip install -r requirements.txt
Copy-Item .env.example .env -Force
# Edit .env and add your OPENROUTER_API_KEY + Google Sheets values
& "C:/Program Files/Python313/python.exe" main.py
```

Backend should be available at `http://localhost:8000`.

Quick checks:

- `http://localhost:8000/health`
- `http://localhost:8000/stats`

### 2. Start Frontend

```powershell
cd frontend
npm install
Copy-Item .env.local.example .env.local -Force
npm run dev
```

Frontend should be available at `http://localhost:3000`.

## How It Works

1. The frontend sends chat requests to the FastAPI backend.
2. The backend fetches survey rows from Google Sheets using `GOOGLE_API_KEY`, `GOOGLE_SHEET_ID`, and `GOOGLE_SHEET_TAB`.
3. Rows are converted into a Pandas DataFrame and cached for `CACHE_TTL_SECONDS`.
4. A LangChain Pandas DataFrame agent uses OpenRouter as the model provider to compute answers from live data.
5. Session-based in-memory chat history is included so follow-up questions keep context.
6. The frontend periodically calls `/stats` to show the latest response count.

## Notes

- Local backend routes are `/chat`, `/stats`, and `/health`.
- In local development, set `NEXT_PUBLIC_API_URL` so frontend calls the FastAPI backend directly.
- If `/stats` fails, verify Google Sheets values in `backend/.env`.
