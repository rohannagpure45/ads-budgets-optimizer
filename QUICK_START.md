# Quick Start

Three commands to get IPSA running locally.

## 1. Install

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python scripts/migrate_database.py
python scripts/create_sample_data.py   # optional seed
```

## 2. Start the API

```bash
python scripts/run_api.py --reload
```

API: http://localhost:8000 · Docs: http://localhost:8000/docs · Health:
http://localhost:8000/api/health

By default the continuous optimization loop is **off** so tests don't
trigger it. To enable:

```bash
IPSA_OPTIMIZER_ENABLED=1 python scripts/run_api.py --reload
```

## 3. Start the dashboard (separate terminal)

```bash
python scripts/start_frontend.py
```

Dashboard: http://localhost:8501

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill in:

- `database.url` — defaults to SQLite at `data/bandit_ads.db`
- `api_credentials.google_ads.*` — required only if you want the Google Ads
  write path
- `budget_push.enabled` — must be `true` to push real budget changes
- `budget_push.dry_run` — defaults `true`; **both flags must flip** for an
  actual budget mutation to fire
- `ANTHROPIC_API_KEY` — optional; falls back to template-only explanations

## Common issues

| Symptom | Likely cause |
|---|---|
| Dashboard shows an error banner instead of numbers | API isn't running. Restart `scripts/run_api.py`. |
| `IPSA_OPTIMIZER_ENABLED=1` but `allocation_changes` table stays empty | See `STATUS.md` — wiring of the optimizer service is tracked under Phase 1 of `ROADMAP.md`. |
| `ModuleNotFoundError: google.ads` | Google Ads SDK is heavy; install on demand: `pip install google-ads==24.1.0`. |
