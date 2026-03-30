@echo off
REM =============================================================================
REM Survey Chatbot — One-command startup (Windows)
REM =============================================================================

echo.
echo ==================================================
echo   Survey Chatbot - Starting up
echo ==================================================
echo.

echo [1/3] Building frontend...
cd frontend
call npm install
call npm run build
cd ..

echo [2/3] Installing backend dependencies...
cd backend
pip install -r requirements.txt
cd ..

echo [3/3] Starting server on http://localhost:8000
echo.
cd backend
python main.py
