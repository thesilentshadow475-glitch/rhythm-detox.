"""Digital Rhythm Detox: a hosted AI agent (FastAPI + Claude tool use) that also serves the web app."""
import json, os, time
from collections import defaultdict

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from logic import extract_json, rhythm_score, validate_plan

MODEL = os.getenv("MODEL", "claude-sonnet-5-5")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_HOUR", "30"))
app = FastAPI(title="Digital Rhythm Detox Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_client = None
_hits = defaultdict(list)


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _client


class Profile(BaseModel):
    wake: str
    sleep: str
    ws: str
    we: str
    hrs: float = Field(ge=0, le=18)
    prob: str = Field(max_length=60)
    goal: str = Field(default="", max_length=140)


class PlanReq(BaseModel):
    profile: Profile


class AdaptReq(BaseModel):
    profile: Profile
    plan: dict
    feedback: str = Field(max_length=500)


SYSTEM = """You are the agent behind Digital Rhythm Detox, a digital-wellbeing coach.
Goal: reboot the person's daily rhythm and reduce problematic screen time without hard bans.
Block types: focus (notifications silenced, inside work/study hours), offline (phone-free), winddown (screens away, must end exactly at bedtime), free.
Use 4 to 8 blocks, 24h HH:MM, no overlaps, all between wake-up and bedtime.
Process: 1) draft a plan, 2) call validate_plan, 3) fix every issue and validate again until it returns ok, 4) call rhythm_score, 5) reply with JSON ONLY:
{"summary": string, "bedtime_target": "HH:MM", "blocks": [{"start","end","type","label","why" (under 18 words)}], "tips": [3 short strings]}"""

TOOLS = [
    {"name": "validate_plan", "description": "Check a draft plan against the person's schedule. Returns ok and a list of issues.",
     "input_schema": {"type": "object", "properties": {"plan": {"type": "object"}}, "required": ["plan"]}},
    {"name": "rhythm_score", "description": "Compute the projected rhythm score (0-100) for a valid plan.",
     "input_schema": {"type": "object", "properties": {"plan": {"type": "object"}}, "required": ["plan"]}},
]


def run_tool(name, args, profile):
    plan = args.get("plan", {})
    if name == "validate_plan":
        issues = validate_plan(profile, plan)
        return {"ok": not issues, "issues": issues}
    if name == "rhythm_score":
        return {"score": rhythm_score(profile, plan)}
    return {"error": "unknown tool"}


def run_agent(profile, user_msg):
    messages, trace = [{"role": "user", "content": user_msg}], []
    for _ in range(8):
        r = client().messages.create(model=MODEL, max_tokens=2000, system=SYSTEM, tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": r.content})
        if r.stop_reason == "tool_use":
            results = []
            for b in r.content:
                if b.type == "tool_use":
                    out = run_tool(b.name, b.input, profile)
                    trace.append(b.name + (" ✓" if out.get("ok") else " ✗" if "ok" in out else ""))
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out)})
            messages.append({"role": "user", "content": results})
            continue
        plan = extract_json("".join(b.text for b in r.content if b.type == "text"))
        plan["score"] = rhythm_score(profile, plan)  # never trust a model-written number
        plan["warnings"] = validate_plan(profile, plan)
        plan["trace"] = trace
        return plan
    raise HTTPException(502, "The agent did not finish in time.")


def limit(request: Request):
    ip = (request.headers.get("x-forwarded-for") or request.client.host).split(",")[0].strip()
    now = time.time()
    _hits[ip] = [t for t in _hits[ip] if now - t < 3600]
    if len(_hits[ip]) >= RATE_LIMIT:
        raise HTTPException(429, "Too many requests. Try again later.")
    _hits[ip].append(now)


def call(profile, msg):
    try:
        return run_agent(profile, msg)
    except anthropic.APIError as e:
        raise HTTPException(502, f"AI service error: {getattr(e, 'message', e)}")
    except (ValueError, KeyError) as e:
        raise HTTPException(502, f"Agent returned an unusable plan: {e}")


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL, "key_configured": bool(os.getenv("ANTHROPIC_API_KEY"))}


@app.post("/api/plan")
def plan(req: PlanReq, request: Request):
    limit(request)
    p = req.profile.model_dump()
    return call(p, "Build today's plan for this person:\n" + json.dumps(p))


@app.post("/api/adapt")
def adapt(req: AdaptReq, request: Request):
    limit(request)
    p = req.profile.model_dump()
    msg = ("Person: " + json.dumps(p) + "\nCurrent plan: " + json.dumps(req.plan) +
           "\nCheck-in: " + json.dumps(req.feedback) +
           "\nAdapt the plan for tomorrow. In 'summary' say what you changed and why.")
    return call(p, msg)


app.mount("/", StaticFiles(directory="static", html=True), name="static")
