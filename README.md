# Pune Plastic Bag Survey Chatbot

Ask plain-English questions about live survey responses, generate charts from prompts, and download chart visuals as PNG.

## Latest Features

- Conversational survey Q&A powered by live Google Sheets data.
- Prompt-to-chart generation (bar, line, pie, donut, area, scatter, stacked bar).
- Dedicated chart mode with chart suggestions in sidebar.
- PNG chart export directly in browser.
- Mobile-first improvements for long answers and tables.
- Responsive chart rendering for both desktop and phone screens.
- Session memory for contextual follow-up questions.

## Tech Stack

- Frontend: Next.js 14, React 18, TypeScript, Tailwind CSS
- Charts/UI: Recharts, html-to-image
- Backend: FastAPI, Pandas, LangChain Experimental Agent
- LLM Provider: Groq (OpenAI-compatible endpoint)
- Data Source: Google Sheets API (reads survey responses from a sheet tab)

## Requirements

### System Requirements

- Node.js 18+
- Python 3.10+
- npm

### Runtime Requirements

- Groq API key
- Google Sheets API key
- Google Sheet ID and tab name

## Project Structure

```text
.
├── backend/
│   ├── main.py
│   ├── prompts/
│   │   └── chart_system_prompt.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── api/
│   │   ├── chat.py
│   │   ├── chart.py
│   │   └── stats.py
│   ├── app/
│   ├── components/
│   │   └── SurveyChart.tsx
│   ├── lib/
│   ├── package.json
│   ├── vercel.json
│   └── .env.local.example
└── README.md
```

## Environment Variables

### Backend (`backend/.env`)

Copy `backend/.env.example` to `backend/.env` and set the values:

- `OPENROUTER_API_KEY` (required, use your Groq API key here)
- `OPENROUTER_MODEL` (example: `openai/gpt-oss-120b`)
- `OPENROUTER_BASE_URL` (default: `https://api.groq.com/openai/v1`)
- `OPENROUTER_SITE_URL` (optional, generally not required for Groq)
- `OPENROUTER_APP_NAME` (optional, generally not required for Groq)
- `GOOGLE_API_KEY` (required)
- `GOOGLE_SHEET_ID` (required)
- `GOOGLE_SHEET_TAB` (default: `Form Responses 1`)
- `CACHE_TTL_SECONDS` (default: `60`)

### Frontend (`frontend/.env.local`)

Copy `frontend/.env.local.example` to `frontend/.env.local`:

- `NEXT_PUBLIC_API_URL=http://localhost:8000`

## How to Run

Open two terminals: one for backend, one for frontend.

### 1. Start Backend

```powershell
cd backend
"C:/Program Files/Python313/python.exe" -m pip install -r requirements.txt
Copy-Item .env.example .env -Force
# Edit .env and add your Groq API key (in OPENROUTER_API_KEY) + Google Sheets values
& "C:/Program Files/Python313/python.exe" main.py
```

Backend should be available at `http://localhost:8000`.

Quick checks:

- `http://localhost:8000/health`
- `http://localhost:8000/stats`
- `http://localhost:8000/chart` (POST)

### 2. Start Frontend

```powershell
cd frontend
npm install
Copy-Item .env.local.example .env.local -Force
npm run dev
```

Frontend should be available at `http://localhost:3000` (or `http://localhost:3001` if 3000 is in use).

## How It Works

1. The frontend sends chat requests and chart requests to the backend.
2. The backend fetches survey rows from Google Sheets using `GOOGLE_API_KEY`, `GOOGLE_SHEET_ID`, and `GOOGLE_SHEET_TAB`.
3. Rows are converted into a Pandas DataFrame and cached for `CACHE_TTL_SECONDS`.
4. A LangChain Pandas DataFrame agent uses Groq as the model provider to compute answers from live data.
5. For chart mode, backend builds schema/context from pandas and returns a structured chart config JSON.
6. Frontend renders interactive charts with Recharts and supports PNG export.
7. Session-based in-memory chat history is included so follow-up questions keep context.
8. The frontend periodically calls `/stats` to show the latest response count.

## Chart Request Examples

- Show a bar chart of occupation-wise response counts
- Show a line chart of responses over timestamp
- Create a pie chart of reusable bag ownership
- Show a stacked bar chart of age group by occupation

## API Routes

### Local FastAPI

- `GET /health`
- `GET /stats`
- `POST /chat`
- `POST /chart`
- `DELETE /chat/{session_id}`

### Vercel Serverless

- `POST /api/chat`
- `POST /api/chart`
- `GET /api/stats`

Important: Ensure `frontend/vercel.json` includes rewrites for `chat`, `chart`, and `stats`.

## Notes

- Local backend routes are `/chat`, `/chart`, `/stats`, and `/health`.
- In local development, set `NEXT_PUBLIC_API_URL` so frontend calls the FastAPI backend directly.
- If `/stats` fails, verify Google Sheets values in `backend/.env`.
- If charts fail on Vercel, verify `frontend/vercel.json` rewrite for `/api/chart`.
- Theme preference is stored in localStorage and respects system mode.
- Long markdown tables now scroll horizontally on mobile for readability.
