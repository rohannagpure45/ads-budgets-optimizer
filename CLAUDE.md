# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IPSA (Intelligent Platform for Strategic Advertising) — an advertising
budget optimization platform using Thompson Sampling bandits, a rule-based
MMM factor layer (seasonality + carryover), and LLM-powered interpretability.
FastAPI backend, Streamlit frontend, SQLite/PostgreSQL database.

**Project status is pre-alpha.** Read [STATUS.md](STATUS.md) before making
claims about what works. The earlier `*_COMPLETE.md` files in
`docs/archive/` contradict each other and should not be trusted.

## Scope rules

These are deliberate choices, not omissions. Don't reintroduce them
without explicit user approval:

- **Google Ads only.** Meta / Trade Desk write paths are not in scope.
  Read-only connectors may stay; write paths are off.
- **No Meridian / no Bayesian MMM.** Meridian code lives in
  `src/bandit_ads/_archive/`. Do not re-import or re-add `google-meridian`,
  `jax`, `numpyro`, `arviz`, or `xarray` to `requirements.txt`.
- **No contextual bandits.** `ContextualBanditAgent` and
  `context_features.py` are archived. Stick to `ThompsonSamplingAgent` and
  `IncrementalityAwareBandit`.
- **No new mock data.** The frontend used to fall back to ~36
  `_mock_*` methods that hid the API being down. Phase 2 of the restructure
  removes those — do not add them back. Surface real errors instead.

## Common Commands

### Setup
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python scripts/migrate_database.py
python scripts/create_sample_data.py  # optional sample data
```

### Run the Application
```bash
# API server (Terminal 1) - serves on http://localhost:8000
python scripts/run_api.py
python scripts/run_api.py --reload  # with auto-reload

# Frontend (Terminal 2) - serves on http://localhost:8501
python scripts/start_frontend.py
# or: streamlit run frontend/app.py
```

To start the continuous optimization loop on API boot, set
`IPSA_OPTIMIZER_ENABLED=1` (default off so tests don't trigger the loop).

### Tests
```bash
pytest tests/                          # all tests
pytest tests/test_agent.py             # single test file
pytest --cov=src/bandit_ads tests/     # with coverage
python scripts/test_api.py             # API endpoint smoke tests
```

## Architecture

### Core Package (`src/bandit_ads/`)

**Optimization Engine:**
- `agent.py` — `ThompsonSamplingAgent` + `IncrementalityAwareBandit`
- `arms.py` — Arm definitions (platform, channel, creative, bid combinations)
- `env.py` — Simulated ad environment; `realtime_env.py` — live API environment
- `runner.py` — `AdOptimizationRunner` orchestrates campaign optimization rounds
- `optimization_service.py` — `ContinuousOptimizationService` background loop

**Data Layer:**
- `database.py` — SQLAlchemy models (Campaign, Arm, Metric, AgentState, APILog,
  IncrementalityExperiment/Metric)
- `change_tracker.py` — `AllocationChange` history table
- `models.py` — Pydantic validation models
- `data_loader.py` — `MMMDataLoader` for historical data
- `etl.py` — ETL pipeline
- `data_validator.py` — Data validation

**MMM:**
- `mmm_insights.py` — `MMMInsightsEngine` (rule-based channel summaries,
  saturation curves, optimal allocations)

**API (`src/bandit_ads/api/`):**
- `main.py` — FastAPI app with CORS, global error handling
- Routes: `campaigns`, `dashboard`, `recommendations`, `optimizer`,
  `incrementality`, `ask`, `data`, `forecasting`, `scenarios`, `export`,
  `attribution`, `mmm` (12 routers)
- Health check at `/api/health`; API docs at `/docs`

**Interpretability / LLM Layer:**
- `explanation_generator.py` — Claude API for human-readable optimization
  explanations
- `llm_router.py` — Routes between LLM providers (Anthropic, OpenAI)
- `vector_store.py` — ChromaDB RAG context store

**Integrations:**
- `api_connectors.py` — Google Ads write path; Meta + Trade Desk are
  read-only / parked
- `incrementality.py` — Experiment design with holdout groups
- `scheduler.py` — APScheduler background jobs

### Frontend (`frontend/`)

- `app.py` — Main Streamlit app
- `components/` — Reusable UI components
- `pages/` — Streamlit page-based routing
- `services/data_service.py` — `DataService` class that calls the API

### Key Patterns

- **Database access:** `DatabaseManager` with context manager
  (`with db_manager.get_session() as session:`)
- **Configuration:** `config.example.yaml` (copy to `config.yaml`); supports
  `.env` via python-dotenv
- **API credentials:** Configured in `config.yaml` under the
  `api_credentials` section (Google Ads currently the only active write
  target)

### Async-in-sync warning

The optimization loop runs in a `threading.Thread`. `ExplanationGenerator`
methods are `async`. Do not call `asyncio.run()` per call — it tears down
the Anthropic client's connection pool. Use a dedicated event loop on the
service object with `run_coroutine_threadsafe`, or stick to the synchronous
template fallback.

## Database

SQLite at `data/bandit_ads.db` (dev). PostgreSQL supported for production.
Schema managed via `scripts/migrate_database.py`.

## Commit conventions

- Do not include "Claude Code" co-author trailers or signatures in commit
  messages.
- One commit per phase during the active restructure (see
  [ROADMAP.md](ROADMAP.md)).
