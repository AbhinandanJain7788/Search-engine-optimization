# Deploy guide

This app runs anywhere that supports a Docker container with ~1 GB memory.
Railway is the path of least resistance; Fly.io and Render also work.

Everything below assumes you're in `e:\seo\frontend\`.

---

## Option 1: Railway (recommended, ~5 min)

Railway builds the Dockerfile in their cloud — you do **not** need Docker
installed locally.

### One-time setup

1. Create a free account at https://railway.com
2. Install the CLI:
   ```powershell
   npm install -g @railway/cli
   ```
3. Log in:
   ```powershell
   railway login
   ```

### Deploy

From `e:\seo\frontend\`:

```powershell
railway init    # creates a new project; pick "Empty Project"
railway up      # uploads the folder + builds + deploys
```

Wait ~3-5 minutes for the first build (Playwright base image is ~2 GB,
gets pulled once, then cached). After it boots:

```powershell
railway domain  # generates a *.up.railway.app URL
```

Open the URL in your browser. Same UI, same audits, public on the internet.

### Updating later

Edit any file, then run `railway up` again. Redeploys take ~1 min after
the first build is cached.

### Notes for Railway

- **Free tier**: $5/month free credit. A small app costs ~$0.50-$2/month.
- **Memory**: default 512 MB is tight for Chromium. If audits crash with
  "Target page, context or browser has been closed", upgrade to 1 GB:
  Project Settings -> Resources -> Memory.
- **Storage**: audit outputs in `/app/runs/` survive while the service
  is running. They reset on every redeploy. If you want them durable,
  add a Railway Volume mounted at `/app/runs`.

---

## Option 2: Fly.io

Same Dockerfile, lower-level platform.

```powershell
# One-time
iwr https://fly.io/install.ps1 -useb | iex
fly auth signup
fly launch --no-deploy   # pick a region; this creates fly.toml (replaces ours)
# Edit the generated fly.toml to match the one in this repo (sets internal_port = 8080)
fly deploy
fly open
```

Fly's free allowance: 3 small shared VMs. Cold-start is ~5s if the machine
was stopped (set `auto_stop_machines = "stop"` in fly.toml to enable that).

---

## Option 3: Render.com

```text
1. Push this folder to a GitHub repo
2. Render -> New + -> Blueprint
3. Pick the repo; render.yaml is detected
4. Click "Apply"
```

First build is ~5 min. Free tier sleeps after 15 min of inactivity (first
audit after a sleep adds ~30s). Paid plans avoid the sleep.

---

## Option 4: Any Docker host (Cloud Run, ECS, your VPS)

```bash
docker build -t claude-seo .
docker run -p 7860:7860 claude-seo
# Open http://localhost:7860
```

For Google Cloud Run:
```bash
gcloud run deploy claude-seo --source . --memory 1Gi --port 7860
```

---

## Things you should know

| Concern | Reality |
|---|---|
| Public URL — can strangers spam it? | Yes. The app has no auth gate. For a hobby deploy that's fine; for a real product, add a token check in `app.py` `start_audit` before queuing jobs. |
| Will it work for sites with anti-bot WAFs? | Real Chromium handles many JS challenges, but Cloudflare/Akamai aggressive mode and Amazon's WAF still block. The audit gracefully degrades and reports `rendered_status` so you see what happened. |
| Does it call Claude or any LLM? | No. Pure Python + Chromium. Zero per-audit cost. |
| Memory budget per audit | ~400 MB peak (Chromium + page + PDF render). 1 GB platform memory is comfortable. |
| Average audit time | 15-30s for healthy sites, up to 60s for slow / WAF-challenged sites. |
| What if a site times out? | The pipeline returns `rendered_ok: false` and still produces a partial report (robots.txt / sitemap / llms.txt always work even if the homepage doesn't). |

---

## Files involved

```
Dockerfile        # Container build (Playwright base, pip install, start uvicorn)
requirements.txt  # Python deps
railway.json      # Railway-specific config (uses Dockerfile)
fly.toml          # Fly.io config
render.yaml       # Render.com config
.dockerignore     # Excludes runs/, venv, debug files from image
```

The app itself (`app.py`, `audit_runner.py`, `commands.py`, `static/`) is
unchanged from the local version. It already honors `$PORT` from the
environment, so it Just Works on any platform.
