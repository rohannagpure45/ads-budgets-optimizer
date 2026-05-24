"""Route smoke test — GET every router and assert no 500s.

Boots the FastAPI app against an isolated in-memory SQLite DB seeded with a
single campaign/arm/metric so data-dependent handlers have something to read.
A handled 404/422 is fine; a 5xx means a router blew up.
"""

from __future__ import annotations

import importlib.util
import os
from datetime import datetime

import pytest


def _fpdf_available() -> bool:
    return importlib.util.find_spec("fpdf") is not None


@pytest.fixture
def client(monkeypatch):
    # Never let the TestClient boot the background optimizer.
    monkeypatch.setenv("IPSA_OPTIMIZER_ENABLED", "0")

    import src.bandit_ads.database as database_mod
    import src.bandit_ads.change_tracker as change_tracker_mod
    import src.bandit_ads.explanation_generator as expl_mod
    import src.bandit_ads.optimization_service as opt_mod
    import src.bandit_ads.auth  # noqa: F401 — registers User
    import src.bandit_ads.recommendations  # noqa: F401 — registers Recommendation
    from src.bandit_ads.database import Arm, Campaign, DatabaseManager, Metric

    dbm = DatabaseManager("sqlite:///:memory:")
    dbm.create_tables()
    monkeypatch.setattr(database_mod, "_db_manager", dbm, raising=False)
    monkeypatch.setattr(change_tracker_mod, "_change_tracker_instance", None, raising=False)
    monkeypatch.setattr(expl_mod, "_explanation_generator_instance", None, raising=False)
    monkeypatch.setattr(opt_mod, "_service_instance", None, raising=False)

    with dbm.get_session() as session:
        campaign = Campaign(
            name="smoke", budget=1000.0, start_date=datetime.utcnow(), status="active"
        )
        session.add(campaign)
        session.flush()
        cid = campaign.id
        arm = Arm(
            campaign_id=cid, platform="Google", channel="Search", creative="A", bid=1.0
        )
        session.add(arm)
        session.flush()
        session.add(
            Metric(
                campaign_id=cid,
                arm_id=arm.id,
                timestamp=datetime.utcnow(),
                impressions=100,
                clicks=10,
                conversions=2,
                revenue=50.0,
                cost=10.0,
                roas=5.0,
            )
        )
        session.commit()

    from fastapi.testclient import TestClient
    from src.bandit_ads.api.main import app

    with TestClient(app) as test_client:
        yield test_client


# Framework-provided routes we don't care to smoke.
_SKIP_PATHS = {"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}


def _get_paths():
    """Enumerate GET routes from the app, with path params filled in as '1'."""
    from src.bandit_ads.api.main import app

    paths = []
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        if "GET" not in methods:
            continue
        path = route.path
        if path in _SKIP_PATHS:
            continue
        # PDF export needs the optional `fpdf` package; skip when absent so the
        # smoke test reflects environment capability rather than a missing dep.
        if path.endswith("/pdf") and not _fpdf_available():
            continue
        concrete = path
        for part in path.split("/"):
            if part.startswith("{") and part.endswith("}"):
                concrete = concrete.replace(part, "1")
        paths.append(concrete)
    return sorted(set(paths))


@pytest.mark.parametrize("path", _get_paths())
def test_get_route_no_server_error(client, path):
    resp = client.get(path)
    assert resp.status_code < 500, f"{path} returned {resp.status_code}: {resp.text[:300]}"
