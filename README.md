# IPSA — Intelligent Platform for Strategic Advertising

**Status: pre-alpha.** A salvage of an earlier prototype. The bones are real
(Thompson Sampling bandit, SQLAlchemy schema, FastAPI + Streamlit surface,
Google Ads connector), but several integration points are being wired up in
the current restructure. See [STATUS.md](STATUS.md) for an honest "what
works / what doesn't" matrix and [ROADMAP.md](ROADMAP.md) for the salvage
plan.

## What it does

IPSA optimizes advertising budget allocation across arms (combinations of
platform / channel / creative / bid) using a multi-armed bandit. A
rule-based MMM layer adjusts for seasonality and carryover effects, and an
LLM layer generates human-readable explanations for each reallocation
decision.

- **Optimizer:** Thompson Sampling with incrementality-aware updates from
  holdout experiments.
- **Write path:** Google Ads `CampaignBudgetService.mutate_campaign_budgets`
  (behind a `budget_push.enabled` flag, dry-run by default).
- **Dashboard:** Streamlit, served separately from the FastAPI backend.
- **Explanations:** Anthropic Claude API; falls back to a template-only
  generator when no API key is configured.

## Scope (today)

In scope: Google Ads, Thompson Sampling, rule-based MMM factors,
explanation generation, Streamlit dashboard, SQLite persistence.

Archived (kept in `src/bandit_ads/_archive/`, may return later): Bayesian
Meridian MMM, contextual bandits (LinUCB), Meta / Trade Desk write paths,
incrementality auto-apply.

## Getting started

See [QUICK_START.md](QUICK_START.md) for the three commands.

## Project layout

```
src/bandit_ads/          # core optimizer, agents, DB, API, integrations
src/bandit_ads/api/      # FastAPI app + routes (12 routers)
src/bandit_ads/_archive/ # parked modules (Meridian, contextual bandits)
frontend/                # Streamlit app
frontend/pages/          # page-routed Streamlit pages
scripts/                 # CLI entrypoints (run_api, run_simulation, ...)
tests/                   # pytest test suite
docs/archive/            # historical design + status docs (do not trust)
```

## License

Proprietary / not yet specified.
