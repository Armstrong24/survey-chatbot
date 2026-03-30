#!/bin/bash
# =============================================================================
# Survey Chatbot — One-command startup
# Builds the frontend and starts everything on http://localhost:8000
# =============================================================================

set -e  # Exit on any error

echo ""
echo "=================================================="
echo "  Survey Chatbot — Starting up"
echo "=================================================="
echo ""

# Step 1: Build the Next.js frontend into static files
echo "[1/3] Building frontend (Next.js static export)..."
cd "$(dirname "$0")/frontend"
npm install --silent
npm run build
echo "      Frontend built ✓"

# Step 2: Install Python backend dependencies
echo ""
echo "[2/3] Installing backend dependencies..."
cd "$(dirname "$0")/backend"
pip install -r requirements.txt -q
echo "      Backend deps installed ✓"

# Step 3: Start FastAPI (serves both API + frontend on :8000)
echo ""
echo "[3/3] Starting server..."
echo ""
echo "  Open in browser: http://localhost:8000"
echo ""
python main.py
