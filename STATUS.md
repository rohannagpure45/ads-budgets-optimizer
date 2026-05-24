# IPSA Status — Phase 0 (cleanup complete)

Last updated after the Phase 0 cleanup of the salvage plan. This document
replaces the eight conflicting "COMPLETE" declarations in `docs/archive/`.
If anything in this file disagrees with code, the code is the source of
truth — file an issue and update this doc.

## What works today (verified)

- **Thompson Sampling bandit** (`ThompsonSamplingAgent`) and
  **`IncrementalityAwareBandit`** — covered by `tests/test_agent.py`.
- **SQLAlchemy schema** — `Campaign`, `Arm`, `Metric`, `AgentState`,
  `APILog`, `IncrementalityExperiment`, `IncrementalityMetric`,
  `AllocationChange`.
- **FastAPI app boots** with 12 routers registered: `campaigns`,
  `dashboard`, `recommendations`, `optimizer`, `incrementality`, `ask`,
  `data`, `forecasting`, `scenarios`, `export`, `attribution`, `mmm`.
- **Streamlit dashboard** renders against the API (still relies on mock
  fallbacks today — see "Works only in simulation").
- **Google Ads connector** `api_connectors.py` — `set_campaign_budget` /
  `mutate_campaign_budgets` are real code, not stubs. Behind
  `budget_push.enabled` (default `false`) and `budget_push.dry_run`
  (default `true`).
- **MMM insights** — rule-based channel summaries, saturation curves, and
  optimal allocations via `mmm_insights.MMMInsightsEngine`.

## Works only in simulation

- The **continuous optimization loop is not yet wired into API startup.**
  `ContinuousOptimizationService` exists; the FastAPI app does not invoke
  it. Tracked as Phase 1.1 of the roadmap.
- **Allocation-change logging silently drops rows.** A string `arm_key`
  is passed to an integer-FK column; the surrounding `except` swallows the
  type error. Phase 1.3 is the linchpin fix.
- **Explanations are never generated** for live allocation changes —
  `ExplanationGenerator` is wired into the service object but never called
  from `_handle_allocation_changes`. Phase 1.4.
- **Dashboard / Ask page fall back to ~36 `_mock_*` methods** when the API
  is down or returns nothing, masking real failures. Phase 2.1.
- MMM factors (seasonality / carryover) are **configured per-campaign,
  not learned.**

## Archived (rebuild later, not in scope today)

Now living in `src/bandit_ads/_archive/`:

- **Bayesian Meridian MMM** (`meridian_bridge.py`, `meridian_data.py`,
  `meridian_insights.py`, `meridian_trainer.py`).
- **Contextual bandits** — `contextual_agent.py` (LinUCB),
  `context_features.py`, `scripts/_archive/test_simulation.py`,
  `scripts/_archive/run_contextual_example.py`.
- **Meridian Streamlit page** (`frontend/pages/_archive/meridian_model.py`).
- **Older campaign-detail variants** (`campaign_detail_enhanced.py`,
  `campaign_detail_old.py`). The live page is `campaign_detail.py`.
- **Meta Ads / Trade Desk write paths** — connector classes exist for
  read but write paths are not wired.
- **Incrementality auto-apply** — experiments can be designed and metrics
  recorded; automated bandit-prior updates from results are not yet wired
  end-to-end.
- **Vector store / RAG** — `vector_store.py` and `chromadb` dependency
  remain, but no live retrieval path is wired into the Ask page yet.

## Known fragility

- **DB migrations are manual** — there is no Alembic. `migrate_database.py`
  is hand-rolled.
- **Optimizer runs in-process with FastAPI** — there is no horizontal
  scaling story. A second uvicorn worker would mean two competing loops.
- **Explanation generator falls back to a template** when
  `ANTHROPIC_API_KEY` is missing. The async-in-sync trap (calling an async
  generator from the optimization `threading.Thread`) must use a dedicated
  event loop — see `CLAUDE.md`.
- **CORS `allow_origins=["*"]`** in `api/main.py` — dev-only; tighten
  before any public deploy.
- **No authentication.** `auth.py` exists; it is not enforced on the
  routers.
- **`pytest` is not yet pinned in `requirements.txt`** — added in Phase 4.

## Recently changed

- **Phase 0:** archived Meridian (4 files) and contextual bandits (2
  files) to `src/bandit_ads/_archive/`. Removed `google-meridian`, `jax`,
  `jaxlib`, `numpyro`, `arviz`, `xarray` from `requirements.txt`. Moved 28
  legacy markdown files from the project root to `docs/archive/`. Deleted
  a 152KB JSON litter file, the duplicate `gitignore`, and the empty
  `src/bandit_ads/Untitled`. Stripped all dangling Meridian / contextual
  imports from `runner.py`, `optimization_service.py`, `agent.py`,
  `__init__.py`, `data_loader.py`, `etl.py`, `scheduler.py`,
  `api/routes/mmm.py`, `frontend/app.py`,
  `frontend/services/data_service.py`, `frontend/pages/mmm_insights.py`.
  Deleted `tests/test_meridian_pipeline.py`.
