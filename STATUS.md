# IPSA Status — Phase 6 (RAG integration gap closed)

Last updated after Phase 6 of the salvage plan. This document replaces the
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
- **`POST /api/recommendations/{id}/approve` pushes to the platform.**
  Resolves the `Arm` via `arm_id` or `arm_key`, computes the new daily
  budget, and calls `push_budget_to_platform(arm, new_budget,
  dry_run=...)` when `budget_push.enabled` is `true`. Both flags
  (`enabled` + `dry_run` flipped to `false`) must be set for a real
  Google Ads mutation. On failure: `status="failed"`, `push_error`
  stored in `details`, HTTP `502`.
- **MMM insights** — rule-based channel summaries, saturation curves, and
  optimal allocations via `mmm_insights.MMMInsightsEngine`.
- **Vector store / RAG memory is wired end-to-end.** Every explained
  allocation change is indexed into the vector store
  (`ExplanationGenerator._index_decision` →
  `VectorStore.add_decision_explanation`), and the Ask page retrieves and
  formats that history for `EXPLANATION` / `ANALYSIS` queries
  (`orchestrator.process_query` → `_format_rag_context`). Degrades
  gracefully to no-RAG when ChromaDB or the LLM is unavailable: indexing is
  a best-effort no-op and retrieval is skipped. Covered by
  `tests/test_rag_indexing.py`.
- **The spine is now covered by an end-to-end test.**
  `tests/test_e2e_spine.py` runs three real optimization cycles against an
  in-memory DB and asserts `allocation_changes` rows exist, each with a
  real integer arm FK and a generated `explanation`, then reads the latest
  decision back through the API. `tests/test_api_smoke.py` GETs every route
  and asserts no 5xx. Full suite: `pytest -q` → **68 passed, 4 skipped**.

## Works only in simulation

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
- **Scheduler auto-start and data-upload persistence remain deferred.**
  `scheduler.py` (APScheduler jobs) is not auto-started on API boot, and
  the data-upload path does not persist beyond the request. Both are parked
  by decision — see ROADMAP "Deferred / parked".

## Recently changed

- **Phase 6:** closed the RAG integration gap — the memory loop looked
  built but had never stored or surfaced a single decision.
  - **`add_decision_explanation` had zero callers**, so the vector store was
    always empty. `ExplanationGenerator.explain_allocation_change` now
    captures `campaign_id` into `change_data` and, after generating the
    explanation (LLM or template), calls a new `_index_decision` helper that
    writes to the store. `explain_allocation_change` has exactly one caller
    (`optimization_service._schedule_explanation`), so every logged change
    is indexed once — no double-indexing. Indexing is best-effort: a no-op
    when no store is configured and try/except-guarded otherwise, so a
    ChromaDB hiccup never breaks explanation generation.
  - **Fixed the dead-code bug in `orchestrator.process_query`:** the
    `if rag_results: rag_context = self._format_rag_context(...)` block was
    nested inside the `else:` branch where `rag_results` had just been set
    to `None`, so retrieved history was never formatted or used. Retrieval
    and formatting are now independent of the `if/else`.
  - Added `tests/test_rag_indexing.py`: asserts a generated explanation
    pushes exactly one document with the right `campaign_id` / `arm_id`,
    that indexing is a silent no-op with no store, and that
    `_format_rag_context` surfaces retrieved history.
- **Phase 4:** added the test harness and let it find the bugs the earlier
  "COMPLETE" docs hid.
  - Pinned `pytest` / `pytest-asyncio` / `httpx` in `requirements.txt`;
    added `pytest.ini` (`asyncio_mode = auto`, `testpaths = tests`).
  - `tests/test_e2e_spine.py` (the canary) and `tests/test_api_smoke.py`
    (no-5xx GET smoke over 33 routes). The two PDF tests now
    `importorskip("fpdf")`.
  - **Fixed `_arm_key_to_db_id`:** it resolved arms via detached ORM
    instances, raising `DetachedInstanceError` (swallowed by
    `_handle_allocation_changes`) so `allocation_changes` never got a row.
    Now reads arm primitives inside an active session. The Phase 1
    "linchpin fix" was real but had never actually run end-to-end — the
    canary is what proved it.
  - **Set `expire_on_commit=False`** on the sessionmaker. The codebase
    routinely returns ORM rows out of `with get_session()` blocks and reads
    them afterward; the default expire-on-commit broke ~6 campaign GET
    routes with `Instance ... is not bound to a Session`.
  - **Fixed `/api/campaigns/{id}/time-series`** to handle SQLite's `date()`
    text result (was calling `.isoformat()` on a `str`).
- **Phase 3:** wired the Google Ads write path behind the existing
  feature flags.
  - `api/routes/recommendations.py::approve_recommendation` now parses
    `rec.details`, resolves the `Arm` (via `arm_id` or `arm_key`),
    computes `new_budget = suggested_allocation * campaign.budget` (or
    uses `new_budget` directly for `BUDGET_ADJUSTMENT`), and calls
    `push_budget_to_platform(arm, new_budget, dry_run=...)`.
    Failures mark the row `status="failed"`, store `push_error` in
    `details`, and respond `502`. Disabled push still applies locally
    and returns the resolved push metadata on the response.
  - Added a `budget_push:` block to `config.example.yaml`
    (`enabled: false`, `dry_run: true`) so the safe defaults are
    explicit.
  - Added `tests/integration/__init__.py` and
    `tests/integration/test_google_ads_push.py`. The full round-trip is
    skipped unless `GOOGLE_ADS_TEST_CUSTOMER_ID` is set; the dry-run
    smoke runs whenever the env var is present and asserts
    `push_budget_to_platform(arm, 50, dry_run=True)` returns `True`
    without authenticating.
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
