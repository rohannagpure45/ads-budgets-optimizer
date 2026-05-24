# IPSA Salvage Plan — Wire the Spine, Cut the Scope

## Context

The IPSA repo at `/home/user/ads-budgets-optimizer/` is ~26k LOC of advertising-budget-optimizer code (FastAPI + Streamlit + Thompson Sampling bandit + MMM + LLM interpretability). It has accumulated **31 markdown files in the project root** from 10+ AI coding sessions, with eight separate "COMPLETE" declarations that contradict each other. Three parallel research agents (docs reader, code auditor, holistic assessor) converged on the same diagnosis:

> **Every feature class is implemented, but the runtime orchestration that wires them together is broken.** The bones are real; the integration is fake. Classic AI-session pattern: each session built a new feature class, wrote a new `*_COMPLETE.md`, and moved on without closing the loop.

Verified concrete failures (read directly from source):
- `optimization_service.py:659–668` calls `change_tracker.log_allocation_change(arm_id=arm_key)` where `arm_key` is a *string* (`str(arm)`), but `change_tracker.py:32` declares `arm_id` as `Integer ForeignKey('arms.id')`. The `except` at line 669 swallows the type error with a `logger.debug`. **The allocation-change history is silently empty no matter how many cycles run.**
- `api/main.py` (107 lines, full file read) has no `@app.on_event("startup")` — the `ContinuousOptimizationService` class exists but is never instantiated by the API.
- `_handle_allocation_changes` (lines 609–678) logs changes to DB but never calls `self.explanation_generator.explain_allocation_change()`. Even if Bug #1 is fixed, explanations are never generated.
- `frontend/services/data_service.py` has 36 `_mock_*` methods that hide the API being broken — the UI looks fine while the backend is dead.
- 26 of the 31 root-level docs are stale completion summaries / duplicate roadmaps / orphaned blueprints (e.g. `DASHBOARD_BLUEPRINT.md` is a 38KB React spec while the actual frontend is Streamlit).

**User-confirmed direction:**
- **Salvage** (not restart) — keep ~26k LOC.
- **Aggressive scope cut** — archive Meridian Bayesian MMM (~800 LOC across 4 files), contextual bandits (~400 LOC), incrementality auto-apply. Ship one platform (Google Ads), Thompson Sampling, MMM seasonality/carryover factors, explanations, Streamlit.
- **Docs to 5** — keep README, CLAUDE.md, STATUS.md, ROADMAP.md, QUICK_START.md; move other 26 to `docs/archive/`.

**Intended outcome:** A working end-to-end spine in ~3 weeks — campaigns load from DB, runners optimize, changes get logged with real integer FKs, explanations get generated, dashboard/Ask page show real data (not mocks), Google Ads budget push is wired behind a dry-run flag. The project becomes an honest pre-alpha you can iterate on, not a documentation-theater shell.

---

## Phase 0 — Cleanup (Day 1)

**Delete:**
- `campaign_results_comprehensive_mmm_optimization_20260124_123126.json` (152KB data litter in root)
- `gitignore` (duplicate of `.gitignore`)
- `src/bandit_ads/Untitled` (stray)
- One of `frontend/pages/campaign_detail.py` / `campaign_detail_enhanced.py` (keep the live one)

**Archive to `src/bandit_ads/_archive/`:**
- `meridian_bridge.py`, `meridian_data.py`, `meridian_insights.py`, `meridian_trainer.py`
- `contextual_agent.py`, `context_features.py`
- `frontend/pages/meridian_model.py` → `frontend/pages/_archive/`

**Remove dangling references** (these will compile-break otherwise):
- `runner.py` lines 21, 63, 139–178, 277–296 — gut the `use_contextual` branch
- `optimization_service.py` lines 511–526 — delete the Meridian posterior-refresh block; strip Meridian paragraph from docstring (53–57)
- `agent.py` lines 582–610 — delete `incorporate_meridian_posteriors()`
- `__init__.py` line 33–34 — remove `ContextualBanditAgent` from factory
- `requirements.txt` lines 33–38 — drop `google-meridian`, `jax`, `jaxlib`, `numpyro`, `arviz`, `xarray`

**Docs to `docs/archive/`** (use `git mv` to preserve history):
The 26 files (all `*_COMPLETE.md`, `*_SUMMARY.md`, `*_IMPLEMENTATION.md`, `PHASE3_*.md`, `DASHBOARD_BLUEPRINT.md`, `IPSA_CORE_DIFFERENTIATORS_AUDIT.md`, `EVALUATION_AND_ROADMAP.md`, `NEXT_STEPS*.md`, `FUTURE_ENHANCEMENTS_PLAN.md`, `FRONTEND_IMPROVEMENTS.md`, `CAMPAIGN_*.md`, `INTERPRETABILITY_*.md`, `ERROR_HANDLING_*.md`, `CONTEXTUAL_BANDITS.md`, `TESTING_*.md`, `TEST_FIXES.md`, `INSTALL_FASTAPI.md`, `API_*.md`, `SETUP_INSTRUCTIONS.md`).

**Kept in root, rewritten:**
- `README.md` — what works today, status: pre-alpha, link to QUICK_START
- `CLAUDE.md` — coding conventions, "no Meridian", "Google Ads only"
- `STATUS.md` — honest "what works / what doesn't" (see Phase 5 outline)
- `ROADMAP.md` — this plan's phases plus deferred items (Meta, contextual, Meridian re-add)
- `QUICK_START.md` — 3 commands to run locally

**Verify:** `find . -name "meridian_*" -not -path "*/_archive/*" -not -path "*/.git/*"` returns nothing; `pip install -r requirements.txt` no longer pulls JAX.

---

## Phase 1 — Close the optimization spine (Days 2–5)

This is the heart of the salvage. Five surgical fixes to make the loop actually run end-to-end.

### 1.1 Start the optimization service on API boot
**`src/bandit_ads/api/main.py`** — add `@app.on_event("startup")` calling `get_optimization_service().start()` and `@app.on_event("shutdown")` calling `.stop()`. Gate behind `IPSA_OPTIMIZER_ENABLED=1` env so tests don't trigger the loop.

### 1.2 Make `_load_active_campaigns` actually instantiate runners
**`src/bandit_ads/optimization_service.py:156–245`** — `_build_campaign_config_from_db` currently fills in hard-coded `ctr=0.03, cvr=0.08` and empty `mmm_factors={}` (lines 230–235), then `add_campaign()` calls `AdOptimizationRunner.setup_campaign()` which silently succeeds with bogus data. Replace the hard-coded constants with aggregated reads from the `metrics` table per `(platform, channel, creative)`. Populate `mmm_factors` from `campaign.campaign_config` JSON if present. After the loop, if `len(campaigns) > 0 and len(self.campaign_runners) == 0`, log `ERROR` with the first failure reason — currently this fails silently.

### 1.3 Fix the silent FK type-mismatch bug (THE critical fix)
**`src/bandit_ads/optimization_service.py:659–668`** — `arm_key` is `str(arm)` but `AllocationChange.arm_id` is `Integer ForeignKey('arms.id')`. Resolve the string to the integer DB id before calling. Factor out `_arm_key_to_db_id(campaign_id, arm_key)` that uses the existing `get_arms_by_campaign()` pattern from line 690. Same helper fixes `_save_agent_state` at line 691.

**Without this fix, every other Phase 1 step is decorative — the allocation_changes table stays empty.**

### 1.4 Trigger explanation generation on every logged change
**`src/bandit_ads/optimization_service.py:_handle_allocation_changes`** — after `log_allocation_change` returns the persisted `change` row, call `explanation_generator.explain_allocation_change(change.id)` and store the resulting text. Two sub-tasks:

1. Add a `Column(Text, nullable=True)` `explanation` field on `AllocationChange` in `change_tracker.py:55`.
2. The optimization loop is a `threading.Thread`; `explain_allocation_change` is `async`. Use a dedicated event loop on the service object (`self._loop = asyncio.new_event_loop()` in `__init__`) and `run_coroutine_threadsafe`. Do **not** `asyncio.run()` per-call — it tears down the LLM client's connection pool. A pure-template synchronous fallback (skip the LLM when no `ANTHROPIC_API_KEY`) is also acceptable for v1.

### 1.5 Hydrate `previous_allocations` on restart
**`optimization_service.py:619`** + `add_campaign` (~line 281) — `previous_allocations` is empty after restart, so the first cycle flags every arm as "changed" and creates an explanation-generation storm. After `_restore_agent_state` returns, seed `self.previous_allocations[campaign_id] = dict(runner.agent.current_allocation)`.

**Verify Phase 1 end-to-end:**
```bash
IPSA_OPTIMIZER_ENABLED=1 uvicorn src.bandit_ads.api.main:app
# Wait 60s, then:
sqlite3 data/bandit_ads.db "SELECT COUNT(*), COUNT(explanation) FROM allocation_changes;"
# Both columns must be > 0 and equal.
```

---

## Phase 2 — Wire dashboard + Ask to real data (Days 6–8)

### 2.1 Kill the mock fallback
**`frontend/services/data_service.py`** — delete every `_mock_*` method (~36 of them) and the `self.use_mock = True` branch (lines 39–51). Replace silent fallbacks with a raised `DataServiceUnavailable`; render an error banner in pages instead of fake numbers. Keep one helper, `_seed_demo_data()`, that writes **real** rows to the SQLite DB — call from `scripts/create_sample_data.py`. This is the single biggest credibility fix: stop the UI from lying.

### 2.2 Real Ask page
**`frontend/services/data_service.py:1330–1349`** + **`frontend/pages/ask.py:134`** — delete the `_mock_query_response` fallback. The `/api/ask` route exists at `api/routes/ask.py:31` and already calls `OrchestratorAgent().process_query()`. On non-200, raise — the page's existing `try/except` at `ask.py:148–158` already shows an error message.

### 2.3 Latest-decision endpoint
**`src/bandit_ads/api/routes/campaigns.py`** — add `GET /{campaign_id}/latest_decision` returning the most recent `AllocationChange` for the campaign with `{change, explanation, timestamp}`. Reuse the session pattern from `campaigns.py:680`.

### 2.4 Fill the dashboard TODO stubs with real math
- **`api/routes/dashboard.py:220`** `roas_trend` — period-over-period delta using the same query pattern already at lines 56–57.
- **`api/routes/campaigns.py:701`** `change` field — 7-day spend-share delta.

### 2.5 Recommendations scoring
**`src/bandit_ads/recommendations.py:111, 124–126`** — replace TODOs with real math:
- `current_allocation`: read from `optimization_service.campaign_runners[campaign_id].agent.current_allocation[str(arm)]`
- `additional_spend = (suggested - current) * total_budget`
- `expected_revenue = additional_spend * historical_roas` (from last-30-day `Metric` rows)
- `roas_impact`: campaign-level ROAS shift formula

---

## Phase 3 — Google Ads write path (Days 9–12)

`api_connectors.py:356–423` already has real Google Ads API code (`CampaignBudgetService.mutate_campaign_budgets`). It's not stubbed — only the call sites are missing.

### 3.1 Wire `approve_recommendation`
**`src/bandit_ads/api/routes/recommendations.py:99–119`** — currently only flips `rec.status = "applied"` in DB. Before commit, parse `rec.details` JSON, look up the `Arm`, compute `new_budget = suggested_allocation * campaign.budget`, call `push_budget_to_platform(arm, new_budget, dry_run=settings.budget_push_dry_run)` (`api_connectors.py:1255`). On push failure: 502 + `rec.status = "failed"` + error stored in details.

### 3.2 Feature flag
**`config.example.yaml`** — default `budget_push.enabled: false` and `dry_run: true`. Document in `QUICK_START.md` that BOTH must flip for real pushes.

### 3.3 Sandbox integration test
**`tests/integration/test_google_ads_push.py`** (new) — skip unless `GOOGLE_ADS_TEST_CUSTOMER_ID` is set; calls `set_campaign_budget(arm, 50.0, dry_run=False)` and asserts `amount_micros == 50_000_000` on read-back.

---

## Phase 4 — Tests + verification (Days 13–15)

### 4.1 pytest setup
Add `pytest==8.0`, `pytest-asyncio==0.23`, `httpx==0.27` to `requirements.txt`. Create `pytest.ini` with `asyncio_mode = auto` and `testpaths = tests`.

### 4.2 Prune dead tests
- Delete `tests/test_meridian_pipeline.py` (Meridian archived).
- Audit `test_comprehensive_mmm.py`, `test_env_enhanced.py`, `test_new_features.py` — `@pytest.mark.skip` with TODO if they fail.
- Keep `test_agent.py`, `test_env.py`, `test_runner.py`.

### 4.3 End-to-end spine test (the canary)
**`tests/test_e2e_spine.py`** (new) — pattern:
1. In-memory SQLite, insert Campaign + 3 Arms.
2. `ContinuousOptimizationService(interval=0.01)`.
3. Run `_run_optimization_cycle()` 3×.
4. Assert `len(AllocationChange query) > 0`.
5. Assert every row has non-null `explanation`.
6. `TestClient.get("/api/campaigns/1/latest_decision")` returns 200 + non-empty explanation.

If this test passes, the salvage is real. If it doesn't, you're still in documentation theater.

### 4.4 Route smoke tests
**`tests/test_api_smoke.py`** — enumerate routers from `api/main.py:41–52`, hit GET on each with `TestClient`, assert `status < 500`.

---

## Phase 5 — STATUS.md (the honest doc)

The replacement for 8 conflicting "COMPLETE" declarations. Structure:

```
# IPSA Status — <date>

## What works today (verified by tests)
- Thompson Sampling bandit + IncrementalityAwareBandit
- SQLAlchemy schema, DB persistence, agent state restore
- FastAPI: 12 routers, smoke-tested
- Streamlit dashboard rendering real data
- Allocation-change tracking + explanation generation wired end-to-end
- Google Ads set_campaign_budget (behind budget_push.enabled flag)

## Works only in simulation
- Optimization driven by synthetic AdEnvironment
- MMM factors (seasonality/carryover) configured per-campaign, not learned

## Archived (rebuild later)
- Meridian Bayesian MMM
- Contextual bandits (LinUCB)
- Meta Ads / TradeDesk write paths (read-only today)
- Incrementality auto-apply
- Vector store / RAG

## Known fragility
- DB migrations manual (no Alembic)
- Optimizer in-process with FastAPI (no horizontal scaling)
- LLM template-only fallback when no ANTHROPIC_API_KEY
- CORS allow_origins=["*"] — tighten before deploy
- Authentication bypassed in dev
```

---

## Critical files (the ones that actually move the needle)

- `src/bandit_ads/optimization_service.py` — Phase 1.1–1.5 all converge here
- `src/bandit_ads/change_tracker.py` — schema add for `explanation` column
- `src/bandit_ads/api/main.py` — startup/shutdown hooks
- `src/bandit_ads/api/routes/recommendations.py` — Phase 2.5 + Phase 3.1
- `src/bandit_ads/api/routes/campaigns.py` — Phase 2.3 + 2.4
- `frontend/services/data_service.py` — Phase 2.1 (delete mocks)
- `src/bandit_ads/recommendations.py` — Phase 2.5 scoring math

## Risks & gotchas

1. **Bug 1.3 (FK type mismatch) is the linchpin.** Until it's fixed, every later step is decorative — the `allocation_changes` table stays empty regardless of how many cycles run. Fix this first.
2. **Async-in-sync trap (1.4).** `explanation_generator.*` is async; the optimization loop is a `threading.Thread`. Do *not* `asyncio.run()` per call — use a dedicated event loop on the service object with `run_coroutine_threadsafe`. The template-only synchronous path is the safer v1.
3. **`campaign_config` column may not exist** on the `Campaign` model. Verify in `database.py` before Phase 1.2; add a migration if missing.
4. **First-cycle uniform exploration is not a bug.** New campaigns with no historical metrics get `alpha=beta=1` for every arm — log it visibly so it's not mistaken for failure.
5. **`_save_agent_state` silently skips arms missing from DB** (`optimization_service.py:694`). Replace the silent `continue` with an explicit error log; otherwise config-DB drift goes invisible.
6. **CORS `allow_origins=["*"]`** (`api/main.py:34`) is dev-only — tighten before any deploy.
7. **Removing mock fallbacks (2.1) will visibly break the UI** if the API isn't running. That's the point — but add a `frontend/app.py` health-check splash so failures are explicable, not crash-screens on every page.

## Verification checklist (per phase)

- **Phase 0:** `find . -name "meridian_*" -not -path "*/_archive/*"` empty; `python -c "import src.bandit_ads"` succeeds; `pip install -r requirements.txt` no JAX/Meridian.
- **Phase 1:** `IPSA_OPTIMIZER_ENABLED=1 uvicorn src.bandit_ads.api.main:app` logs `"Loaded N active campaigns, N runners created"` with matching Ns. After 60s: `sqlite3 data/bandit_ads.db "SELECT COUNT(*), COUNT(explanation) FROM allocation_changes;"` — both > 0 and equal.
- **Phase 2:** Stop API → dashboard shows explicit error banner, no fake ROAS numbers. Restart → `curl /api/campaigns/1/latest_decision` returns real explanation text.
- **Phase 3:** With `budget_push.enabled: true, dry_run: true` + Google Ads test account, approve a recommendation → logs `[DRY RUN] Would set Google Ads budget $X`, `rec.status='applied'`. Flip `dry_run: false` → budget actually changes on the test account.
- **Phase 4:** `pytest -q` green. `pytest tests/test_e2e_spine.py -v` — the canary passes. **This test passing is the definition of "salvage succeeded."**
