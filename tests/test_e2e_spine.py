"""End-to-end spine test — the canary for the IPSA salvage.

If this passes, the optimization loop is actually wired: campaigns load,
the agent reallocates, allocation changes are logged with real integer FKs,
and an explanation is generated and persisted for every change. If it fails,
we're back in documentation theater.

The test drives the loop synchronously (no background thread) against an
in-memory SQLite DB, then waits for the dedicated explanation loop to flush.
"""

from __future__ import annotations

import time
from datetime import datetime

import pytest


@pytest.fixture
def in_memory_db(monkeypatch):
    """Point every relevant global singleton at a fresh in-memory SQLite DB.

    The change tracker, explanation generator, and optimization service all
    capture ``get_db_manager()`` at construction, so the DB global must be
    swapped *before* those singletons are built. monkeypatch reverts all of
    this after the test so the suite stays hermetic.
    """
    import src.bandit_ads.database as database_mod
    import src.bandit_ads.change_tracker as change_tracker_mod
    import src.bandit_ads.explanation_generator as expl_mod
    import src.bandit_ads.optimization_service as opt_mod

    # Import every module that defines a Base-mapped model so create_all() sees
    # the full schema (allocation_changes FKs reference arms/campaigns/users).
    import src.bandit_ads.auth  # noqa: F401 — registers User
    import src.bandit_ads.recommendations  # noqa: F401 — registers Recommendation
    from src.bandit_ads.database import DatabaseManager

    dbm = DatabaseManager("sqlite:///:memory:")
    dbm.create_tables()

    monkeypatch.setattr(database_mod, "_db_manager", dbm, raising=False)
    monkeypatch.setattr(change_tracker_mod, "_change_tracker_instance", None, raising=False)
    monkeypatch.setattr(expl_mod, "_explanation_generator_instance", None, raising=False)
    monkeypatch.setattr(opt_mod, "_service_instance", None, raising=False)

    yield dbm


def _seed_campaign_with_arms(dbm) -> int:
    """Insert one active campaign with 3 arms; return the campaign id."""
    from src.bandit_ads.database import Arm, Campaign

    with dbm.get_session() as session:
        campaign = Campaign(
            name="canary",
            budget=5000.0,
            start_date=datetime.utcnow(),
            status="active",
        )
        session.add(campaign)
        session.flush()
        campaign_id = campaign.id
        for creative in ("Creative A", "Creative B", "Creative C"):
            session.add(
                Arm(
                    campaign_id=campaign_id,
                    platform="Google",
                    channel="Search",
                    creative=creative,
                    bid=1.0,
                )
            )
        session.commit()
    return campaign_id


def _canary_config() -> dict:
    return {
        "name": "canary",
        "arms": {
            "platforms": ["Google"],
            "channels": ["Search"],
            "creatives": ["Creative A", "Creative B", "Creative C"],
            "bids": [1.0],
        },
        "environment": {
            "global_params": {"ctr": 0.05, "cvr": 0.10, "revenue": 12.0, "cpc": 1.0},
        },
        "agent": {
            "total_budget": 5000.0,
            "min_allocation": 0.05,
            "risk_tolerance": 0.3,
            "variance_limit": 0.1,
        },
        # Plain Thompson Sampling — incrementality holdout machinery is not
        # under test here.
        "incrementality": {"enabled": False},
        "impressions_per_round": 200,
    }


def test_e2e_spine(in_memory_db):
    from src.bandit_ads.change_tracker import AllocationChange
    from src.bandit_ads.optimization_service import ContinuousOptimizationService

    campaign_id = _seed_campaign_with_arms(in_memory_db)

    service = ContinuousOptimizationService(optimization_interval_minutes=1)
    # Force the template explanation path so the test never touches the network,
    # regardless of whether ANTHROPIC_API_KEY / chromadb happen to be present.
    if service.explanation_generator is not None:
        service.explanation_generator.claude_client = None
        service.explanation_generator.vector_store = None

    service._start_event_loop()
    try:
        assert service.add_campaign(campaign_id, _canary_config()) is True

        # Simulate a fresh start: an empty previous-allocation map means the
        # first cycle records a change for every funded arm.
        service.previous_allocations[campaign_id] = {}

        for _ in range(3):
            service._run_optimization_cycle()

        # Explanations are generated on the dedicated asyncio loop; poll until
        # every logged change has one (template generation is near-instant).
        deadline = time.time() + 10.0
        while time.time() < deadline:
            with in_memory_db.get_session() as session:
                rows = (
                    session.query(AllocationChange)
                    .filter(AllocationChange.campaign_id == campaign_id)
                    .all()
                )
                if rows and all(r.explanation for r in rows):
                    break
            time.sleep(0.1)

        with in_memory_db.get_session() as session:
            rows = (
                session.query(AllocationChange)
                .filter(AllocationChange.campaign_id == campaign_id)
                .all()
            )
            assert len(rows) > 0, "allocation_changes is empty — the spine is not wired"
            assert all(r.arm_id for r in rows), "every change must carry a real integer arm FK"
            assert all(r.explanation for r in rows), (
                "every logged change must carry a generated explanation"
            )
    finally:
        service._stop_event_loop()

    # The dashboard's latest-decision endpoint must read the same rows back.
    from fastapi.testclient import TestClient
    from src.bandit_ads.api.main import app

    with TestClient(app) as client:
        resp = client.get(f"/api/campaigns/{campaign_id}/latest_decision")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["change"] is not None
        assert body["explanation"], "latest_decision must surface a non-empty explanation"
