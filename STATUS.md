# IPSA Status — Phase 1 (optimization spine wired)

Last updated after Phase 1 of the salvage plan. This document replaces the
eight conflicting "COMPLETE" declarations in `docs/archive/`. If anything
in this file disagrees with code, the code is the source of truth — file
an issue and update this doc.

## What works today (verified)

- **Thompson Sampling bandit** (`ThompsonSamplingAgent`) and
  **`IncrementalityAwareBandit`** — covered by `tests/test_agent.py`.
- **SQLAlchemy schema** — `Campaign`, `Arm`, `Metric`, `AgentState`,
  `APILog`, `IncrementalityExperiment`, `IncrementalityMetric`,
  `AllocationChange` (now with an `explanation` column).
- **FastAPI app boots** with 12 routers registered: `campaigns`,
  `dashboard`, `recommendations`, `optimizer`, `incrementality`, `ask`,
  `data`, `forecasting`, `scenarios`, `export`, `attribution`, `mmm`.
- **Continuous optimizer wires into API startup** behind
  `IPSA_OPTIMIZER_ENABLED=1`. Startup/shutdown hooks call
  `get_optimization_service().start()` / `.stop()`.
- **Allocation-change logging persists real rows.** The string-vs-int FK
  mismatch in `optimization_service._handle_allocation_changes` is fixed
  via `_arm_key_to_db_id`. `ChangeTracker.log_allocation_change` now
  raises `TypeError` on bad FKs instead of silently dropping the row.
- **Explanations are generated on every logged change.** The optimization
  thread schedules `ExplanationGenerator.explain_allocation_change` on a
  dedicated `asyncio` event loop via `run_coroutine_threadsafe`, and the
  result is persisted onto `AllocationChange.explanation`.
- **Streamlit dashboard** renders against the API (still relies on mock
  fallbacks today — see "Works only in simulation").
- **Google Ads connector** `api_connectors.py` — `set_campaign_budget` /
  `mutate_campaign_budgets` are real code, not stubs. Behind
  `budget_push.enabled` (default `false`) and `budget_push.dry_run`
  (default `true`).
- **MMM insights** — rule-based channel summaries, saturation curves, and
  optimal allocations via `mmm_insights.MMMInsightsEngine`.

## Works only in simulation

- **Dashboard / Ask page fall back to ~36 `_mock_*` methods** when the API
  is down or returns nothing, masking real failures. Phase 2.1.
- The **Google Ads write path is not yet invoked from
  `approve_recommendation`** — it currently only updates row status.
  Phase 3.
- **MMM factors (seasonality / carryover)** are configured per-campaign,
  not learned.
- **Global params** (ctr / cvr / cpc / revenue-per-conversion) are
  aggregated from the `metrics` table when history exists; brand-new
  campaigns still fall back to documented defaults and log a warning.

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
  is hand-rolled. Phase 1 added an `explanation` column migration step;
  existing dev DBs need `python scripts/migrate_database.py` once.
- **Optimizer runs in-process with FastAPI** — there is no horizontal
  scaling story. A second uvicorn worker would mean two competing loops.
- **Explanation generator falls back to a template** when
  `ANTHROPIC_API_KEY` is missing. The async-in-sync wiring uses a
  dedicated `asyncio` event loop on the service object — see `CLAUDE.md`.
- **CORS `allow_origins=["*"]`** in `api/main.py` — dev-only; tighten
  before any public deploy.
- **No authentication.** `auth.py` exists; it is not enforced on the
  routers.
- **`pytest` is not yet pinned in `requirements.txt`** — added in Phase 4.

## Recently changed

- **Phase 1:** wired the optimization spine end-to-end.
  - Added `@app.on_event("startup")` / `@app.on_event("shutdown")` hooks
    in `api/main.py`, gated by `IPSA_OPTIMIZER_ENABLED=1`.
  - Replaced hard-coded `ctr=0.03, cvr=0.08` in
    `_build_campaign_config_from_db` with aggregated reads from the
    `metrics` table per campaign. Loud ERROR when N active campaigns
    produce 0 runners.
  - **Linchpin fix:** added `_arm_key_to_db_id(campaign_id, arm_key)` to
    resolve `str(arm)` keys to integer `Arm.id` FKs in both
    `_handle_allocation_changes` and `_save_agent_state`.
    `ChangeTracker.log_allocation_change` now raises `TypeError` on
    non-int FKs instead of silently swallowing the error.
  - Added `explanation` column to `AllocationChange` plus a migration
    step in `scripts/migrate_database.py`. New
    `ChangeTracker.update_explanation` method persists LLM output.
  - Added a dedicated `asyncio.new_event_loop()` in a daemon thread on
    `ContinuousOptimizationService`, with
    `_schedule_explanation(change_id)` dispatching via
    `run_coroutine_threadsafe`. No more `asyncio.run()` per call.
  - Hydrated `previous_allocations[campaign_id]` from the restored agent
    in `add_campaign`, so the first cycle after restart does not flag
    every arm as "changed."
  - Stripped the leftover `runner.use_contextual` references from
    `_optimize_campaign`, `_save_agent_state`, and `_restore_agent_state`
    that Phase 0 had missed.
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
