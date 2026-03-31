"""
Vercel Serverless Function — GET /api/stats
Returns live response count from Google Sheet.
"""

import os
import json
import time
import requests
import pandas as pd
from http.server import BaseHTTPRequestHandler

GOOGLE_API_KEY   = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_SHEET_ID  = os.environ.get("GOOGLE_SHEET_ID", "1ABWgQgUzBKHr1Gd9mGUJ4TgeYj-M8KFrE1cP9gjyl4s")
GOOGLE_SHEET_TAB = os.environ.get("GOOGLE_SHEET_TAB", "Form Responses 1")

_cached_df  = None
_cache_time = 0.0
CACHE_TTL   = 60


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
    rows    = resp.json().get("values", [])
    headers = rows[0]
    records = [
        dict(zip(headers, row + [""] * (len(headers) - len(row))))
        for row in rows[1:]
    ]
    _cached_df  = pd.DataFrame(records)
    _cache_time = time.time()
    return _cached_df


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not GOOGLE_API_KEY:
            self._json({"total_responses": 0, "columns": [], "error": "GOOGLE_API_KEY not set"})
            return
        try:
            df = load_df()
            self._json({
                "total_responses": len(df),
                "columns": df.columns.tolist(),
                "cache_age_seconds": int(time.time() - _cache_time),
            })
        except Exception as e:
            self._json({"total_responses": 0, "columns": [], "error": str(e)})

    def _json(self, data: dict):
        payload = json.dumps(data).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *args):
        pass
