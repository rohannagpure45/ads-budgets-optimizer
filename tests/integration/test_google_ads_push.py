"""Sandbox integration test for the Google Ads budget-push path.

Skipped unless ``GOOGLE_ADS_TEST_CUSTOMER_ID`` is set. This test is
intentionally read-then-write-then-read against a real (test) customer —
do not point it at a production account.

Required environment:

* ``GOOGLE_ADS_TEST_CUSTOMER_ID`` — test account ID (also enables the test).
* ``GOOGLE_ADS_TEST_CAMPAIGN_ID`` — the campaign on that account to mutate.
* Standard Google Ads credentials (``GOOGLE_ADS_CLIENT_ID``,
  ``GOOGLE_ADS_CLIENT_SECRET``, ``GOOGLE_ADS_REFRESH_TOKEN``,
  ``GOOGLE_ADS_DEVELOPER_TOKEN``) — picked up via ConfigManager.
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("GOOGLE_ADS_TEST_CUSTOMER_ID"),
    reason="GOOGLE_ADS_TEST_CUSTOMER_ID not set — skipping Google Ads sandbox test",
)


def _make_arm(platform_campaign_id: str):
    """Build an in-memory Arm carrying the Google Ads campaign id."""
    import json

    from src.bandit_ads.database import Arm

    arm = Arm(
        campaign_id=1,
        platform="google",
        channel="search",
        creative="sandbox",
        bid=2.5,
        platform_entity_ids=json.dumps({"campaign_id": platform_campaign_id}),
    )
    arm.id = 1
    return arm


def test_dry_run_push_returns_true_without_calling_api():
    """``dry_run=True`` short-circuits before any network call. Always safe."""
    from src.bandit_ads.api_connectors import push_budget_to_platform

    arm = _make_arm(os.environ.get("GOOGLE_ADS_TEST_CAMPAIGN_ID", "0"))
    assert push_budget_to_platform(arm, 50.0, dry_run=True) is True


def test_set_campaign_budget_round_trip():
    """End-to-end: write a $50.00 daily budget and read it back as 50_000_000 micros.

    Requires ``GOOGLE_ADS_TEST_CAMPAIGN_ID`` in addition to the customer id.
    """
    campaign_id = os.environ.get("GOOGLE_ADS_TEST_CAMPAIGN_ID")
    if not campaign_id:
        pytest.skip("GOOGLE_ADS_TEST_CAMPAIGN_ID not set")

    from src.bandit_ads.api_connectors import GoogleAdsConnector

    connector = GoogleAdsConnector(credentials=None)
    if not connector.authenticate():
        pytest.skip("Google Ads credentials missing — cannot authenticate")

    arm = _make_arm(campaign_id)

    target_dollars = 50.0
    assert connector.set_campaign_budget(arm, target_dollars, dry_run=False) is True

    ga_service = connector.client.get_service("GoogleAdsService")
    query = (
        f"SELECT campaign.campaign_budget, campaign_budget.amount_micros "
        f"FROM campaign "
        f"WHERE campaign.id = {campaign_id}"
    )
    response = ga_service.search(customer_id=connector.customer_id, query=query)
    amount_micros = None
    for row in response:
        amount_micros = row.campaign_budget.amount_micros
        break

    assert amount_micros == int(target_dollars * 1_000_000), (
        f"Expected amount_micros={int(target_dollars * 1_000_000)}, got {amount_micros}"
    )
