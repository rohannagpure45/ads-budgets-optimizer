# IPSA Roadmap

The salvage plan, condensed. Full plan with code-level references is at
`docs/archive/SALVAGE_PLAN.md` (after Phase 0 commits) or in the
plan file used by the active session.

## Phase 0 — Cleanup ✅

Archive Meridian (4 files) and contextual bandits (2 files). Strip
dangling imports. Move 28 legacy `*_COMPLETE.md` / `*_SUMMARY.md` /
`*_IMPLEMENTATION.md` files to `docs/archive/`. Delete the 152KB JSON
litter, duplicate `gitignore`, empty `Untitled`. Remove
`google-meridian`, `jax`, `jaxlib`, `numpyro`, `arviz`, `xarray` from
`requirements.txt`.

## Phase 1 — Close the optimization spine ✅

Five surgical fixes, all landed:

1. **Optimization service starts on API boot.** `api/main.py` has
   `@app.on_event("startup")` / `shutdown` hooks, gated by
   `IPSA_OPTIMIZER_ENABLED=1`.
2. **`_load_active_campaigns` populates runners from real metrics.**
   `_aggregate_global_params` reads ctr / cvr / cpc / revenue-per-conversion
   from the `metrics` table; falls back to documented defaults with a
   warning when there is no history. Loud ERROR when N active campaigns
   produce 0 runners.
3. **Silent FK type mismatch is fixed.** New `_arm_key_to_db_id` resolves
   `str(arm)` to the integer `Arm.id` FK in both
   `_handle_allocation_changes` and `_save_agent_state`.
   `ChangeTracker.log_allocation_change` now raises `TypeError` on bad
   FKs instead of swallowing them.
4. **Explanations generated on every logged change.** Added
   `AllocationChange.explanation` column + migration step. The service
   runs a dedicated `asyncio` loop in a daemon thread;
   `_schedule_explanation(change_id)` uses `run_coroutine_threadsafe` so
   the Anthropic client's connection pool survives across calls.
5. **`previous_allocations` is hydrated on restart** from
   `runner.agent.current_allocation` after `_restore_agent_state`, so the
   first cycle doesn't flag every arm as "changed."

## Phase 2 — Wire dashboard + Ask to real data ✅

All five sub-tasks landed:

1. **Mock fallback deleted.** `frontend/services/data_service.py` was
   rewritten from ~2,360 lines of `_mock_*` branches down to a thin
   real-only client. Failures raise `DataServiceUnavailable`; pages
   render the existing error banner instead of inventing numbers. The
   `use_mock` flag is gone; `frontend/app.py` and `frontend/pages/home.py`
   key the demo banner off `data_service.health()` instead.
2. **Ask page calls `/api/ask` for real.** `_mock_query_response` is
   gone. `query_orchestrator` raises on backend error so
   `frontend/pages/ask.py`'s existing `try/except` shows the error
   instead of fake answers.
3. **`GET /api/campaigns/{id}/latest_decision`** added — returns the
   most recent `AllocationChange` row plus its stored explanation.
4. **`dashboard.roas_trend` and `campaigns.change`** are real.
   `channel-splits` computes period-over-period ROAS delta against the
   prior window of equal length; `/campaigns/{id}/allocation` computes
   7-day spend-share delta vs. the prior 7-day window.
5. **`recommendations.generate_allocation_recommendation`** now reads
   `current_allocation` from the live runner agent (falling back to the
   30-day spend share) and computes `additional_spend`,
   `expected_revenue`, and `roas_impact` from real `Metric` history.

Drive-bys done while we were in the area:
- Fixed `/api/optimizer/decisions` and `/api/optimizer/explanation/{id}`
  to read the real `AllocationChange.explanation` column (Phase 1's new
  column) instead of the non-existent `explanation_text`. The decisions
  route also now respects `limit` and the no-campaign-filter case.
- Added `POST /api/optimizer/pause|resume|run` and
  `POST /api/campaigns/{id}/pause|resume` so the data service's button
  paths actually have endpoints to call.

## Phase 3 — Google Ads write path ✅

1. **`approve_recommendation` pushes to the platform.**
   `api/routes/recommendations.py::approve_recommendation` now parses
   `rec.details`, resolves the `Arm` via `arm_id` or `arm_key`, computes
   `new_budget = suggested_allocation * campaign.budget` (or
   `new_budget` directly for `BUDGET_ADJUSTMENT`), and calls
   `push_budget_to_platform(arm, new_budget, dry_run=...)`. On push
   failure the row is marked `status="failed"`, `push_error` is stored in
   `details`, and the response is `502`.
2. **Feature flag in `config.example.yaml`** — added `budget_push.enabled:
   false` and `budget_push.dry_run: true`. Both must flip for a real
   Google Ads mutation to fire. Read via `ConfigManager` in the route.
3. **Sandbox integration test** `tests/integration/test_google_ads_push.py`
   gated by `GOOGLE_ADS_TEST_CUSTOMER_ID`. Includes a dry-run smoke
   (no creds required) and an end-to-end round-trip that asserts
   `amount_micros == 50_000_000` after a $50 mutation.

## Phase 4 — Tests + verification ✅

1. **Test deps pinned + `pytest.ini`.** `pytest`, `pytest-asyncio`, and
   `httpx` added to `requirements.txt` (pinned to the versions verified in
   this environment: 9.0.3 / 1.3.0 / 0.28.1). `pytest.ini` sets
   `asyncio_mode = auto` and `testpaths = tests`.
2. **Unstable tests marked.** The two PDF-export tests now
   `pytest.importorskip("fpdf")` — they skip cleanly when the optional
   `fpdf` dep is absent and run when it's present (TODO: pin `fpdf2`).
3. **`tests/test_e2e_spine.py`** — the canary. In-memory SQLite, one
   campaign + 3 arms, 3× `_run_optimization_cycle()`, asserts
   `allocation_changes` is non-empty, every row has a real integer arm FK
   and a non-null `explanation`, then `GET /api/campaigns/{id}/latest_decision`
   returns 200 with that explanation.
4. **`tests/test_api_smoke.py`** — enumerates every GET route from the app
   and asserts no 5xx. 33 routes covered (PDF route skipped when `fpdf`
   absent).

Two real wiring bugs the new tests surfaced and fixed (the canary's whole
reason to exist):
- **`_arm_key_to_db_id` resolved arms via detached ORM instances.**
  `get_arms_by_campaign` returns rows from a closed session; with the
  default `expire_on_commit=True` every attribute access raised
  `DetachedInstanceError`, which `_handle_allocation_changes`' broad
  `except` swallowed — so `allocation_changes` stayed empty no matter how
  many cycles ran. Now reads arm primitives inside an active session.
- **`expire_on_commit=False` on the sessionmaker.** The same detached-read
  pattern broke ~6 GET routes (`/api/campaigns/{id}`, `/arms`,
  `/settings`, …) with `Instance ... is not bound to a Session`. Disabling
  expire-on-commit fixes the whole class at the root.
- Drive-by: `/api/campaigns/{id}/time-series` called `.isoformat()` on
  SQLite's `date()` text result; now tolerates str (SQLite) and date
  (Postgres).

Result: `pytest -q` → **65 passed, 4 skipped** (2 Google Ads sandbox
without creds, 2 PDF without `fpdf`).

## Phase 5 — STATUS.md

Replace the eight conflicting "COMPLETE" declarations with a single
honest "what works / what doesn't" doc. (Done as part of Phase 0
already, will be re-tightened as each later phase lands.)

## Phase 6 — Close the RAG integration gap ✅

The interpretability layer's RAG memory looked built but had never stored
or surfaced a single decision. Closed the loop:

1. **`add_decision_explanation` had zero callers.** Added
   `ExplanationGenerator._index_decision` and call it from
   `explain_allocation_change` (the single chokepoint — one caller via
   `optimization_service._schedule_explanation`) so every explained change
   is indexed exactly once. `change_data` now carries `campaign_id`.
   Indexing is best-effort: a no-op without a store, try/except-guarded
   against an optional ChromaDB.
2. **Fixed the dead-code bug in `orchestrator.process_query`.** The
   `if rag_results: rag_context = self._format_rag_context(...)` block was
   nested inside the `else:` branch where `rag_results` had just been set
   to `None`. Retrieval and formatting are now independent of the
   `if/else`, so the Ask page actually uses retrieved history.
3. **`tests/test_rag_indexing.py`** proves the write happens (one document,
   correct FKs), that indexing degrades to a no-op without a store, and
   that `_format_rag_context` surfaces history. Full suite: `pytest -q` →
   **68 passed, 4 skipped**.

## Deferred / parked

- Bayesian Meridian MMM (re-add when the rule-based MMM bottlenecks
  decision quality).
- Contextual bandits (re-add if per-context performance matters more
  than budget-allocation accuracy).
- Meta Ads / Trade Desk write paths.
- Incrementality auto-apply.
- Scheduler auto-start on API boot (`scheduler.py` APScheduler jobs are
  not started by the FastAPI lifespan hooks).
- Data-upload persistence (the upload path does not persist beyond the
  request).
- Alembic migrations.
- Authentication enforcement on routers.
