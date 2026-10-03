"""
Research agent worker (GitHub Actions cron friendly).

Flow per request:
  load -> search -> [next_page -> fetch -> calibrated_decision
                     -> keep | skip | deep_check] x N -> analyze -> save -> load

CLI:
  python worker.py            run the worker
  python worker.py grade <decision_id> <relevant|irrelevant|unsure>
  python worker.py report     print the calibration report
"""
import os
import sys
import time
from typing import Literal, TypedDict
from urllib import robotparser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from supabase import create_client
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

# ---------------------------------------------------------------- config
MAX_PAGES = int(os.getenv("MAX_PAGES", "6"))             # pages read per request
MAX_REQUESTS = int(os.getenv("MAX_REQUESTS", "5"))       # requests per run
THRESHOLD = float(os.getenv("THRESHOLD", "0.80"))        # calibrated conf gate
MIN_BUCKET_N = int(os.getenv("MIN_BUCKET_N", "20"))      # min graded rows/bucket
SLEEP = float(os.getenv("LLM_SLEEP", "1.5"))             # free-tier friendliness
UA = {"User-Agent": "ResearchBot/1.0 (+personal research)"}

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY",
             os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/",
               "GEMINI_API_KEY", os.getenv("GEMINI_MODEL", "gemini-2.0-flash")),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
                   os.getenv("OPENROUTER_MODEL",
                             "meta-llama/llama-3.3-70b-instruct:free")),
}


def make_llm(provider: str) -> ChatOpenAI:
    base, key_env, model = PROVIDERS[provider]
    api_key = os.environ.get(key_env)
    if not api_key:
        raise ValueError(f"Missing API key env var: {key_env}")
    return ChatOpenAI(
        base_url=base,
        api_key=api_key,
        model=model,
        temperature=0,
        max_retries=3,
        timeout=60,
    )


def structured(schema, primary: str, fallback: str | None = None):
    """Structured-output chain with optional provider fallback (e.g. on 429)."""
    chain = make_llm(primary).with_structured_output(schema, method="function_calling")
    if fallback and fallback != primary and os.getenv(PROVIDERS[fallback][1]):
        alt = make_llm(fallback).with_structured_output(schema, method="function_calling")
        chain = chain.with_fallbacks([alt])
    return chain


# ---------------------------------------------------------------- schemas
class Verdict(BaseModel):
    relevant: float = Field(ge=0, le=1)
    irrelevant: float = Field(ge=0, le=1)
    unsure: float = Field(ge=0, le=1)


class TicketOut(BaseModel):
    symbol: str = Field(description="Ticker or topic, e.g. NVDA, or GENERAL")
    stance: Literal["bullish", "bearish", "neutral"]
    confidence: int = Field(ge=0, le=100)
    summary: str
    key_points: list[str]
    risks: list[str]


JUDGE_PROVIDER = os.getenv("JUDGE_PROVIDER", "groq")
ANALYST_PROVIDER = os.getenv("ANALYST_PROVIDER", "gemini")
FALLBACK_PROVIDER = os.getenv("FALLBACK_PROVIDER", "openrouter")

judge = structured(Verdict, JUDGE_PROVIDER, FALLBACK_PROVIDER)
deep_judge = structured(Verdict, ANALYST_PROVIDER, FALLBACK_PROVIDER)
analyst = structured(TicketOut, ANALYST_PROVIDER, FALLBACK_PROVIDER)


# ---------------------------------------------------------------- tools
_robots: dict[str, robotparser.RobotFileParser | None] = {}


def allowed(url: str) -> bool:
    p = urlparse(url)
    host = f"{p.scheme}://{p.netloc}"
    if host not in _robots:
        rp = robotparser.RobotFileParser()
        try:
            r = requests.get(host + "/robots.txt", headers=UA, timeout=10)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            _robots[host] = rp
        except Exception:
            _robots[host] = None          # unreachable robots.txt -> allow
    rp = _robots[host]
    return True if rp is None else rp.can_fetch(UA["User-Agent"], url)


def web_search(query: str, n: int = 10) -> list[str]:
    key = os.getenv("TAVILY_API_KEY")
    try:
        if key:
            r = requests.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {key}"},
                json={"query": query, "max_results": n},
                timeout=20,
            )
            r.raise_for_status()
            return [x["url"] for x in r.json().get("results", [])]
        from ddgs import DDGS
        with DDGS() as d:
            return [x["href"] for x in d.text(query, max_results=n)]
    except Exception as e:
        print("search failed:", e)
        return []


def fetch_text(url: str) -> str:
    if not allowed(url):
        return ""
    try:
        r = requests.get(url, headers=UA, timeout=15)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            t.decompose()
        return soup.get_text(" ", strip=True)[:6000]
    except Exception:
        return ""


def notify(t: dict) -> None:
    tok, chat = os.getenv("TG_TOKEN"), os.getenv("TG_CHAT_ID")
    if not (tok and chat):
        return
    text = (
        f"📊 {t['symbol']}: {t['stance']} ({t['confidence']}%)\n"
        f"{t['summary']}\n\nResearch only, not financial advice."
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id": chat, "text": text[:4000]},
            timeout=15,
        )
    except Exception:
        pass


# ---------------------------------------------------------------- calibration
_cal_cache: dict[str, list[dict]] = {}


def calibrate(conf: float, dtype: str) -> float:
    """Map raw confidence to observed accuracy from graded history."""
    if dtype not in _cal_cache:
        try:
            _cal_cache[dtype] = (
                sb.table("calibration_report")
                .select("*")
                .eq("decision_type", dtype)
                .execute()
                .data
            )
        except Exception:
            _cal_cache[dtype] = []
    rows = [r for r in _cal_cache[dtype] if r["n"] >= MIN_BUCKET_N]
    if not rows:
        return conf                        # not enough data -> no correction
    nearest = min(rows, key=lambda r: abs(float(r["bucket"]) - conf))
    return float(nearest["actual_accuracy"])


def log_decision(req_id, dtype, summary, probs, pred, raw, cal, action, model):
    row = (
        sb.table("decision_log")
        .insert({
            "request_id": req_id,
            "decision_type": dtype,
            "input_summary": summary[:300],
            "probs": probs,
            "predicted": pred,
            "confidence": raw,
            "calibrated_confidence": cal,
            "action": action,
            "model": model,
        })
        .execute()
        .data[0]
    )
    return row["id"]


def normalize(v: Verdict) -> dict:
    probs = v.model_dump()
    total = sum(probs.values()) or 1.0
    return {k: p / total for k, p in probs.items()}


# ---------------------------------------------------------------- graph state
class S(TypedDict, total=False):
    req: dict | None
    queue: list
    current_url: str | None
    page_text: str
    evidence: list
    decision: str
    steps: int
    done: int
    ticket: dict


# ---------------------------------------------------------------- nodes
def load(s: S):
    done = s.get("done", 0)
    if done >= MAX_REQUESTS:
        return {"req": None}
    rows = (
        sb.table("research_requests")
        .select("*")
        .eq("status", "pending")
        .order("created_at")
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return {"req": None}
    req = rows[0]
    sb.table("research_requests").update({"status": "running"}).eq("id", req["id"]).execute()
    return {
        "req": req,
        "queue": [],
        "evidence": [],
        "steps": 0,
        "current_url": None,
        "page_text": "",
        "done": done,
        "ticket": None,
    }


def search_node(s: S):
    urls, seen = [], set()
    for u in web_search(s["req"]["question"], n=MAX_PAGES * 2):
        host = urlparse(u).netloc
        if host not in seen:               # one page per domain for variety
            seen.add(host)
            urls.append(u)
    return {"queue": urls}


def next_page(s: S):
    q = list(s["queue"])
    if not q or s["steps"] >= MAX_PAGES:
        return {"current_url": None}
    return {"current_url": q.pop(0), "queue": q, "steps": s["steps"] + 1}


def fetch_page(s: S):
    return {"page_text": fetch_text(s["current_url"])}


def calibrated_decision(s: S):
    goal, text = s["req"]["question"], s["page_text"][:3000]
    time.sleep(SLEEP)
    v = judge.invoke(
        "You judge whether a web page helps answer a research goal. "
        "Return probabilities (summing to 1) that the page is relevant, "
        "irrelevant, or unsure. Be honest about uncertainty.\n\n"
        f"GOAL: {goal}\n\nPAGE ({s['current_url']}):\n{text}"
    )
    probs = normalize(v)
    pred = max(probs, key=probs.get)
    raw = probs[pred]
    cal = calibrate(raw, "page_relevance")
    if pred == "relevant" and cal >= THRESHOLD:
        action = "proceed"
    elif pred == "irrelevant" and cal >= THRESHOLD:
        action = "skip"
    else:
        action = "escalate"
    log_decision(
        s["req"]["id"], "page_relevance", text, probs, pred, raw, cal,
        action, PROVIDERS[JUDGE_PROVIDER][2],
    )
    return {"decision": action}


def deep_check(s: S):
    """Second opinion from the stronger model when the fast judge is unsure."""
    goal, text = s["req"]["question"], s["page_text"]
    time.sleep(SLEEP)
    v = deep_judge.invoke(
        "Think carefully. Does this page contain information that materially "
        "helps answer the goal? Return probabilities (summing to 1) for "
        "relevant, irrelevant, unsure.\n\n"
        f"GOAL: {goal}\n\nPAGE ({s['current_url']}):\n{text}"
    )
    probs = normalize(v)
    pred = max(probs, key=probs.get)
    raw = probs[pred]
    cal = calibrate(raw, "page_relevance_deep")
    action = "proceed" if pred == "relevant" else "skip"
    log_decision(
        s["req"]["id"], "page_relevance_deep", text, probs, pred, raw,
        cal, action, PROVIDERS[ANALYST_PROVIDER][2],
    )
    return {"decision": action}


def keep(s: S):
    ev = s["evidence"] + [{"url": s["current_url"], "text": s["page_text"][:2500]}]
    return {"evidence": ev}


def analyze(s: S):
    req, ev = s["req"], s["evidence"]
    if not ev:
        return {
            "ticket": {
                "symbol": "GENERAL",
                "stance": "neutral",
                "confidence": 0,
                "summary": "No relevant sources found for this question.",
                "key_points": [],
                "risks": [],
                "sources": [],
            }
        }
    sources = "\n\n".join(f"[{i+1}] {e['url']}\n{e['text']}" for i, e in enumerate(ev))
    time.sleep(SLEEP)
    out = analyst.invoke(
        "You are a cautious investment research analyst. Using ONLY the sources "
        "below, answer the question. If evidence is thin, conflicting, or "
        "stale, choose 'neutral' and a LOW confidence. List real risks. Do not "
        "give buy/sell commands.\n\n"
        f"QUESTION: {req['question']}\n\nSOURCES:\n{sources[:14000]}"
    )
    return {"ticket": {**out.model_dump(), "sources": [e["url"] for e in ev]}}


def save(s: S):
    req, t = s["req"], s["ticket"]
    # Copy user_id from the request into the ticket (required by RLS + frontend)
    row = {
        "request_id": req["id"],
        "user_id": req.get("user_id"),
        "symbol": t["symbol"],
        "stance": t["stance"],
        "confidence": t["confidence"],
        "summary": t["summary"],
        "sources": {
            "urls": t.get("sources", []),
            "key_points": t.get("key_points", []),
            "risks": t.get("risks", []),
        },
    }
    sb.table("tickets").insert(row).execute()
    sb.table("research_requests").update({"status": "done"}).eq("id", req["id"]).execute()
    notify(t)
    return {"done": s.get("done", 0) + 1}


# ---------------------------------------------------------------- routing
def r_load(s: S):
    return "search" if s.get("req") else END


def r_next(s: S):
    return "fetch" if s.get("current_url") else "analyze"


def r_fetch(s: S):
    return "decide" if s.get("page_text") else "next_page"


def r_decide(s: S):
    return {"proceed": "keep", "skip": "next_page", "escalate": "deep_check"}[s["decision"]]


def r_deep(s: S):
    return "keep" if s["decision"] == "proceed" else "next_page"


def build():
    g = StateGraph(S)
    for name, fn in [
        ("load", load),
        ("search", search_node),
        ("next_page", next_page),
        ("fetch", fetch_page),
        ("decide", calibrated_decision),
        ("deep_check", deep_check),
        ("keep", keep),
        ("analyze", analyze),
        ("save", save),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "load")
    g.add_conditional_edges("load", r_load)
    g.add_edge("search", "next_page")
    g.add_conditional_edges("next_page", r_next)
    g.add_conditional_edges("fetch", r_fetch)
    g.add_conditional_edges("decide", r_decide)
    g.add_conditional_edges("deep_check", r_deep)
    g.add_edge("keep", "next_page")
    g.add_edge("analyze", "save")
    g.add_edge("save", "load")
    return g.compile()


# ---------------------------------------------------------------- CLI
def grade(decision_id: str, outcome: str):
    row = (
        sb.table("decision_log")
        .select("predicted")
        .eq("id", decision_id)
        .single()
        .execute()
        .data
    )
    sb.table("decision_log").update(
        {"outcome": outcome, "correct": row["predicted"] == outcome}
    ).eq("id", decision_id).execute()
    print("graded", decision_id, "->", outcome)


def report():
    rows = sb.table("calibration_report").select("*").execute().data
    if not rows:
        print("No graded decisions yet.")
    for r in rows:
        print(
            f"{r['decision_type']:<22} bucket {r['bucket']}  n={r['n']:<4} "
            f"stated={r['avg_confidence']}  actual={r['actual_accuracy']}"
        )


def mark_failed(req_id: str, error_message: str = "Worker error"):
    """Mark a request as failed with an error message."""
    sb.table("research_requests").update({
        "status": "error",
        "error_message": str(error_message)[:500],
    }).eq("id", req_id).execute()


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "grade":
        grade(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 2 and sys.argv[1] == "report":
        report()
    else:
        app = build()
        try:
            app.invoke({}, {"recursion_limit": 500})
        except Exception as e:
            # release any request stuck in 'running' so it can be retried
            print("run failed:", e)
            stuck = (
                sb.table("research_requests")
                .select("id")
                .eq("status", "running")
                .execute()
                .data
            )
            for r in stuck:
                mark_failed(r["id"], str(e))
            raise
