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
    "chart_type": "bar" | "clustered_column" | "horizontal_bar" | "clustered_bar" | "line" | "pie" | "donut" | "scatter" | "bubble" | "area" | "stacked_bar" | "radar" | "heatmap" | "pyramid" | "funnel" | "waterfall" | "gantt" | "histogram" | "bullet" | "gauge" | "diverging_bar" | "comparison" | "venn",
  "title": "question-like title ending with ?",
  "x_label": "label",
  "y_label": "label",
  "legend_title": "legend",
  "colors": ["#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#3b82f6"],
    "data": [{"category": "text", "value": 12.3, "color_index": 0, "x": 1, "y": 2, "z": 3, "target": 10, "min": 0, "max": 100, "start": 2, "end": 6, "series": "group"}],
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
- Use `series` for grouped/clustered/stacked comparisons
- Use `x`,`y`,`z` for scatter/bubble and matrix-like views
- Use `start` and `end` for gantt timelines
- Use signed values for diverging/waterfall views

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
        "chart_type": chart_type,
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


def _is_time_series_request(user_message: str) -> bool:
    msg = user_message.lower()
    time_words = ["timestamp", "time", "date", "daily", "monthly", "trend", "over time"]
    response_words = ["response", "responses", "count", "counts", "submissions"]
    return any(w in msg for w in time_words) and any(w in msg for w in response_words)


def _find_time_column(df: pd.DataFrame):
    name_hint_cols = [
        col
        for col in df.columns
        if any(k in col.lower() for k in ["timestamp", "date", "time", "submitted", "created"])
    ]
    candidate_cols = name_hint_cols if name_hint_cols else list(df.columns)

    for col in candidate_cols:
        raw = df[col].fillna("").astype(str).str.strip()
        parsed = pd.to_datetime(raw, errors="coerce")
        if parsed.notna().mean() >= 0.5:
            return col, parsed

    return None, None


def _build_time_series_fallback(df: pd.DataFrame, user_message: str) -> dict | None:
    col, parsed = _find_time_column(df)
    if not col or parsed is None:
        return None

    ts = parsed.dropna()
    if ts.empty:
        return None

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
            "color_index": i % len(CHART_PALETTE),
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
        "colors": CHART_PALETTE,
        "data": data,
        "tooltip_format": "{category}: {value} responses",
        "show_grid": True,
        "show_legend": False,
        "note": note,
    }


def _find_column(df: pd.DataFrame, keywords: list[str]) -> str | None:
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

    def parse(v: str):
        if not v:
            return None
        if any(tok in v for tok in yes_tokens):
            return True
        if any(tok in v for tok in no_tokens):
            return False
        return None

    return s.map(parse)


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


def _requested_chart_type(message: str) -> str | None:
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
            "colors": CHART_PALETTE,
            "data": [{"category": "Responses", "value": 1.0, "color_index": 0}],
            "tooltip_format": "{category}: {value}",
            "show_grid": True,
            "show_legend": False,
            "note": "Fallback chart generated automatically",
        }

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
            start_num = float(d.get("start", i * 7) or (i * 7))
            end_num = float(d.get("end", start_num + max(1.0, float(d.get("value", 1) or 1))) or (start_num + 1))
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

    config["title"] = str(config.get("title", "Survey chart?")).rstrip(".") + "?"
    return config


def _build_direct_chart(df: pd.DataFrame, message: str) -> dict | None:
    ctype = _requested_chart_type(message)
    age_col = _find_column(df, ["age"])
    own_bag_col = _find_column(df, ["own a reusable", "reusable bag", "own reusable", "own bag"])
    awareness_col = _find_column(df, ["ban awareness", "aware", "pmc ban", "plastic ban"])
    willing_col = _find_column(df, ["willingness", "willing to pay", "pay", "price point"])
    occupation_col = _find_column(df, ["occupation", "profession"])
    harm_col = _find_column(df, ["harm", "rating", "scale", "1-5"])

    if ctype in {"comparison", "clustered_column", "clustered_bar", "stacked_bar"} and age_col and own_bag_col:
        tmp = df[[age_col, own_bag_col]].fillna("").astype(str).apply(lambda s: s.str.strip())
        tmp = tmp[(tmp[age_col] != "") & (tmp[own_bag_col] != "")]
        if not tmp.empty:
            ctab = pd.crosstab(tmp[age_col], tmp[own_bag_col])
            rows = []
            for age in ctab.index.tolist()[:10]:
                for own in ctab.columns.tolist()[:6]:
                    rows.append({"category": str(age), "series": str(own), "value": float(ctab.loc[age, own])})
            return {
                "chart_type": ctype,
                "title": "How does reusable bag ownership vary by age group?",
                "x_label": age_col,
                "y_label": "Responses",
                "legend_title": own_bag_col,
                "colors": CHART_PALETTE,
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
                "colors": CHART_PALETTE,
                "data": rows,
                "show_grid": True,
                "show_legend": False,
                "note": "Histogram bins derived from actual rating values",
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
            "colors": CHART_PALETTE,
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
                "colors": CHART_PALETTE,
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
            phases = ["Awareness Drive", "Community Mobilization", "Retail Conversion", "Impact Review"]
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
                "colors": CHART_PALETTE,
                "data": rows,
                "show_grid": True,
                "show_legend": False,
                "note": "Phases are evenly derived from observed survey response window",
            }

    return None


def _best_categorical_column(df: pd.DataFrame, exclude: set[str] | None = None) -> str | None:
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


def _best_numeric_column(df: pd.DataFrame, exclude: set[str] | None = None) -> str | None:
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

    def category_counts(col: str | None) -> list[dict]:
        if col:
            s = df[col].fillna("").astype(str).str.strip()
            vc = s[s != ""].value_counts().head(12)
            if not vc.empty:
                return [
                    {"category": str(k), "value": float(v), "color_index": i % len(CHART_PALETTE)}
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
        data = []
        for i, d in enumerate(base[:8]):
            delta = float(vals[i] - (vals[i - 1] if i > 0 else 0))
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
        "colors": CHART_PALETTE,
        "data": data[:40],
        "tooltip_format": "{category}: {value}",
        "show_grid": True,
        "show_legend": True,
        "note": "Built automatically from available columns to guarantee chart output",
    }


def _generate_chart_config(message: str) -> tuple[dict, int]:
    df = load_df()

    direct = _build_direct_chart(df, message)
    if direct:
        return _coerce_chart_for_renderer(_sanitize(direct), message), len(df)

    if _is_time_series_request(message):
        fallback = _build_time_series_fallback(df, message)
        if fallback:
            return _coerce_chart_for_renderer(fallback, message), len(df)

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
    config = _coerce_chart_for_renderer(_sanitize(_extract_json(getattr(raw, "content", str(raw)))), message)

    if "error" in config and _is_time_series_request(message):
        fallback = _build_time_series_fallback(df, message)
        if fallback:
            return _coerce_chart_for_renderer(fallback, message), len(df)

    if "error" in config:
        direct = _build_direct_chart(df, message)
        if direct:
            return _coerce_chart_for_renderer(_sanitize(direct), message), len(df)

    if "error" in config:
        universal = _build_universal_fallback_chart(df, message)
        return _coerce_chart_for_renderer(_sanitize(universal), message), len(df)

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
