"""
MMM Insights API endpoints.

Backed by the rule-based MMMInsightsEngine (channel summaries, saturation
curves, optimal allocations). The Bayesian Meridian backend has been archived;
see src/bandit_ads/_archive/ for the previous implementation.
"""

from fastapi import APIRouter, Query
from typing import Optional

from src.bandit_ads.utils import get_logger

logger = get_logger("api.mmm")
router = APIRouter()


def _get_engine():
    from src.bandit_ads.mmm_insights import MMMInsightsEngine
    return MMMInsightsEngine()


@router.get("/cross-platform")
async def get_cross_platform_summary(days: int = Query(30)):
    """Holistic MMM view across all campaigns and channels."""
    try:
        return _get_engine().get_cross_platform_summary(days=days)
    except Exception as e:
        logger.error(f"Error getting cross-platform summary: {e}")
        return {}


@router.get("/{campaign_id}/channel-summary")
async def get_channel_summary(
    campaign_id: int,
    days: int = Query(30),
):
    """Per-channel spend/ROAS/saturation summary for a campaign."""
    try:
        return _get_engine().get_channel_summary(campaign_id=campaign_id, days=days)
    except Exception as e:
        logger.error(f"Error getting channel summary: {e}")
        return []


@router.get("/{campaign_id}/saturation-curves")
async def get_saturation_curves(
    campaign_id: int,
    days: int = Query(30),
    points: int = Query(20),
):
    """Diminishing-returns saturation curves per channel."""
    try:
        return _get_engine().get_saturation_curves(campaign_id=campaign_id, days=days, points=points)
    except Exception as e:
        logger.error(f"Error getting saturation curves: {e}")
        return {}


@router.get("/{campaign_id}/budget-recommendations")
async def get_budget_recommendations(
    campaign_id: int,
    total_budget: Optional[float] = Query(None),
    days: int = Query(30),
):
    """Optimal budget allocation recommendations."""
    try:
        return _get_engine().get_budget_recommendations(
            campaign_id=campaign_id,
            total_budget=total_budget,
            days=days,
        )
    except Exception as e:
        logger.error(f"Error getting budget recommendations: {e}")
        return {}
