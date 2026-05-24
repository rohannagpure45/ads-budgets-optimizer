# IPSA Status — Phase 2 (dashboard + Ask on real data)

Last updated after Phase 2 of the salvage plan. This document replaces the
eight conflicting "COMPLETE" declarations in `docs/archive/`. If anything
in this file disagrees with code, the code is the source of truth — file
an issue and update this doc.

## What works today (verified)

- **Thompson Sampling bandit** (`ThompsonSamplingAgent`) and
  **`IncrementalityAwareBandit`** — covered by `tests/test_agent.py`.
- **SQLAlchemy schema** — `Campaign`, `Arm`, `Metric`, `AgentState`,
  `APILog`, `IncrementalityExperiment`, `IncrementalityMetric`,
  `AllocationChange` (with `explanation` column from Phase 1).
- **FastAPI app boots** with 12 routers registered: `campaigns`,
  `dashboard`, `recommendations`, `optimizer`, `incrementality`, `ask`,
  `data`, `forecasting`, `scenarios`, `export`, `attribution`, `mmm`.
- **Continuous optimizer wires into API startup** behind
  `IPSA_OPTIMIZER_ENABLED=1`. Startup/shutdown hooks call
  `get_optimization_service().start()` / `.stop()`.
- **Allocation-change logging persists real rows.** The string-vs-int FK
  mismatch in `optimization_service._handle_allocation_changes` is fixed
  via `_arm_key_to_db_id`. `ChangeTracker.log_allocation_change` raises
  `TypeError` on bad FKs instead of silently dropping the row.
- **Explanations are generated on every logged change.** The optimization
  thread schedules `ExplanationGenerator.explain_allocation_change` on a
  dedicated `asyncio` event loop via `run_coroutine_threadsafe`, and the
  result is persisted onto `AllocationChange.explanation`.
- **Streamlit dashboard renders against real API data only.** Phase 2
  deleted the ~36 `_mock_*` fallbacks in `frontend/services/data_service.py`.
  Failures raise `DataServiceUnavailable`; pages render the existing error
  banner instead of fabricated numbers.
- **Ask page hits `/api/ask` for real** — `_mock_query_response` is gone.
  The page surfaces backend errors via its existing try/except rather
  than synthesising fake answers.
- **`GET /api/campaigns/{id}/latest_decision`** returns the most recent
  `AllocationChange` plus its stored explanation. Plus
  `POST /api/optimizer/{pause|resume|run}` and
  `POST /api/campaigns/{id}/{pause|resume}` so all data-service button
  paths have real endpoints to call.
- **Dashboard `roas_trend` and campaign `change`** are now real
  period-over-period deltas (channel-splits vs prior equal-length window;
  allocation vs prior 7-day window).
- **Recommendation impact math is real.**
  `RecommendationEngine.generate_allocation_recommendation` reads
  `current_allocation` from the live runner (falling back to 30-day spend
  share) and computes `additional_spend`, `expected_revenue`, and
  `roas_impact` against historical ROAS from the `metrics` table.
- **Google Ads connector** `api_connectors.py` — `set_campaign_budget` /
  `mutate_campaign_budgets` are real code, not stubs. Behind
  `budget_push.enabled` (default `false`) and `budget_push.dry_run`
  (default `true`).
- **MMM insights** — rule-based channel summaries, saturation curves, and
  optimal allocations via `mmm_insights.MMMInsightsEngine`.

## Works only in simulation

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

- **Phase 2:** put the dashboard and Ask page on real data.
  - Rewrote `frontend/services/data_service.py` from ~2,360 lines of
    `_mock_*` branches down to a thin real-only HTTP client. New
    `DataServiceUnavailable` exception is raised on backend failure;
    pages render the existing error banner instead of inventing numbers.
  - Removed every `use_mock` reference from `frontend/app.py` and
    `frontend/pages/home.py`. The demo banner now keys off
    `data_service.health()`.
  - Deleted `_mock_query_response`. The Ask page already had a
    `try/except` around `query_orchestrator`; the rewrite makes that
    branch fire on real failures instead of synthesised answers.
  - Added `GET /api/campaigns/{id}/latest_decision` — returns the most
    recent `AllocationChange` row plus its stored explanation.
  - Added `POST /api/optimizer/{pause|resume|run}` and
    `POST /api/campaigns/{id}/{pause|resume}` so every data-service
    button path has a corresponding endpoint (previously the data
    service called `self.optimization_service`, an attribute that didn't
    exist — silent crash territory).
  - Filled the `roas_trend` TODO in
    `api/routes/dashboard.py::get_channel_splits` with a real
    period-over-period delta against the prior window of equal length.
  - Filled the `change` TODO in
    `api/routes/campaigns.py::get_campaign_allocation` with a real
    7-day spend-share delta vs the prior 7-day window.
  - Replaced the placeholder math in
    `recommendations.RecommendationEngine.generate_allocation_recommendation`.
    `current_allocation` is read from the live runner agent (falling back
    to 30-day spend share); `additional_spend`, `expected_revenue`, and
    `roas_impact` come from real `Metric` history. Added
    `self.db_manager` to the engine and a `_current_allocation` helper.
  - Drive-bys: `/api/optimizer/decisions` and
    `/api/optimizer/explanation/{id}` were reading
    `change.explanation_text` (never existed); both now read the real
    `AllocationChange.explanation` column. `get_recent_decisions` also
    respects `limit` and the no-campaign-filter case.
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
