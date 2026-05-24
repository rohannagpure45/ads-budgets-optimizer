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

## Phase 2 — Wire dashboard + Ask to real data

1. Delete ~36 `_mock_*` methods in `frontend/services/data_service.py`;
   raise a clear `DataServiceUnavailable` instead of silently lying.
2. Make the Ask page hit `/api/ask` for real and stop falling back to
   `_mock_query_response`.
3. Add `GET /api/campaigns/{id}/latest_decision`.
4. Fill TODO stubs: `dashboard.roas_trend`, `campaigns.change` 7-day
   delta.
5. Replace placeholder math in `recommendations.py` (current allocation,
   additional spend, expected revenue, ROAS impact) with real reads.

## Phase 3 — Google Ads write path

1. Wire `approve_recommendation` to call
   `push_budget_to_platform(arm, new_budget, dry_run=...)`.
2. Feature-flag in `config.example.yaml` — `budget_push.enabled: false`,
   `dry_run: true` by default; both must flip for a real mutation.
3. Add a sandbox integration test gated by
   `GOOGLE_ADS_TEST_CUSTOMER_ID`.

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
