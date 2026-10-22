# Digital Rhythm Detox (hosted AI agent + web app)

The agent runs on a server, not on your computer. One FastAPI service hosts both the
Claude-powered agent (`/api/plan`, `/api/adapt`) and the web app (`static/index.html`).

## How the agent works
Claude drafts a day plan, then calls its tools in a loop: `validate_plan` (checks overlaps,
work hours, bedtime) until the plan is valid, then `rhythm_score` (a deterministic score).
The page shows these steps as "Agent steps".

## Deploy (about 5 minutes, free tier works)
1. Create an API key at https://console.anthropic.com
2. Push this folder to a GitHub repo.
3. On https://render.com: New > Blueprint (uses `render.yaml`) or New > Web Service.
   Build: `pip install -r requirements.txt`  Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add the environment variable `ANTHROPIC_API_KEY`.
5. Open your Render URL. Check `/health` shows `"key_configured": true`.

Any host that runs Python works the same way (Railway, Fly.io, Google Cloud Run).

## Notes
- Requests are limited per IP (`RATE_LIMIT_PER_HOUR`, default 30) to protect your API budget.
- The page falls back to a simple built-in planner if the server is unreachable, and says so.
- Change the model with the `MODEL` environment variable.
