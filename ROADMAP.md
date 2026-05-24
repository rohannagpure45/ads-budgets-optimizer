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

## Phase 4 — Tests + verification

1. Pin `pytest`, `pytest-asyncio`, `httpx` in `requirements.txt`; add
   `pytest.ini` with `asyncio_mode = auto`.
2. Prune dead tests; mark unstable ones with `pytest.mark.skip` + TODO.
3. **`tests/test_e2e_spine.py`** — the canary. In-memory SQLite,
   3 cycles of `_run_optimization_cycle()`, assert
   `allocation_changes` is non-empty and every row has a non-null
   `explanation`. If this passes, the salvage is real.
4. `tests/test_api_smoke.py` — smoke every router.

## Phase 5 — STATUS.md

Replace the eight conflicting "COMPLETE" declarations with a single
honest "what works / what doesn't" doc. (Done as part of Phase 0
already, will be re-tightened as each later phase lands.)

## Deferred / parked

- Bayesian Meridian MMM (re-add when the rule-based MMM bottlenecks
  decision quality).
- Contextual bandits (re-add if per-context performance matters more
  than budget-allocation accuracy).
- Meta Ads / Trade Desk write paths.
- Incrementality auto-apply.
- Vector-store / RAG integration into the Ask page.
- Alembic migrations.
- Authentication enforcement on routers.
