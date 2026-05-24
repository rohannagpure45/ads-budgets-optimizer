"""
Recommendations API endpoints.
"""

import json
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from src.bandit_ads.database import get_db_manager, Arm, Campaign
from src.bandit_ads.utils import ConfigManager, get_logger

logger = get_logger('api.recommendations')
router = APIRouter()

_config_manager = ConfigManager()


def _budget_push_settings() -> Tuple[bool, bool]:
    """Return ``(enabled, dry_run)`` for the Google Ads write path.

    Falls back to enabled=False, dry_run=True so we never mutate a real
    account by accident.
    """
    enabled = bool(_config_manager.get('budget_push.enabled', False))
    dry_run = bool(_config_manager.get('budget_push.dry_run', True))
    return enabled, dry_run


def _resolve_arm(session, campaign_id: int, details: Dict[str, Any]) -> Optional[Arm]:
    """Resolve an Arm row from recommendation details.

    Accepts either ``arm_id`` (integer DB id) or ``arm_key`` in the form
    ``"<platform>_<channel>_<creative>_<bid>"`` (matches ``str(Arm)`` from
    ``src/bandit_ads/arms.py``).
    """
    arm_id = details.get('arm_id')
    if isinstance(arm_id, int):
        arm = session.query(Arm).filter(Arm.id == arm_id).first()
        if arm:
            return arm

    arm_key = details.get('arm_key')
    if isinstance(arm_key, str) and arm_key:
        # ``arm_key`` is ``str(agent_arm)`` from src/bandit_ads/arms.py:11 —
        # ``"Arm(platform=..., channel=..., creative=..., bid=...)"``. The DB
        # Arm repr includes ``id``, so match on the rebuilt agent-style key.
        for arm in session.query(Arm).filter(Arm.campaign_id == campaign_id).all():
            rebuilt = (
                f"Arm(platform={arm.platform}, channel={arm.channel}, "
                f"creative={arm.creative}, bid={arm.bid})"
            )
            if rebuilt == arm_key:
                return arm
    return None


def _rec_to_dict(rec) -> Dict[str, Any]:
    """Convert a Recommendation ORM object to an API-friendly dict."""
    try:
        details = json.loads(rec.details) if rec.details else {}
    except Exception:
        details = {}

    return {
        "id": rec.id,
        "title": rec.title,
        "description": rec.description,
        "type": rec.recommendation_type,
        "campaign_id": rec.campaign_id,
        "campaign_name": f"Campaign {rec.campaign_id}",
        "status": rec.status,
        "confidence": details.get("confidence", 0.7),
        "current_value": details.get("current_value"),
        "proposed_value": details.get("proposed_value"),
        "expected_impact": details.get("expected_impact", ""),
        "explanation": details.get("explanation", rec.description),
        "created_at": rec.created_at.strftime("%b %d, %Y") if rec.created_at else "",
    }


@router.get("")
async def get_recommendations(
    status: str = Query("pending", description="Status: pending, approved, applied, rejected")
):
    """Get recommendations by status."""
    try:
        from src.bandit_ads.recommendations import Recommendation
        db_manager = get_db_manager()
        with db_manager.get_session() as session:
            recs = session.query(Recommendation).filter(
                Recommendation.status == status
            ).order_by(Recommendation.created_at.desc()).all()
            return [_rec_to_dict(r) for r in recs]
    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        return []


@router.get("/pending")
async def get_pending_recommendations():
    """Get pending recommendations."""
    try:
        from src.bandit_ads.recommendations import Recommendation
        db_manager = get_db_manager()
        with db_manager.get_session() as session:
            recs = session.query(Recommendation).filter(
                Recommendation.status == "pending"
            ).order_by(Recommendation.created_at.desc()).all()
            return [_rec_to_dict(r) for r in recs]
    except Exception as e:
        logger.error(f"Error getting pending recommendations: {str(e)}")
        return []


@router.post("")
async def create_recommendation(body: dict):
    """Create a new recommendation (e.g. from a scenario plan)."""
    try:
        from src.bandit_ads.recommendations import Recommendation
        db_manager = get_db_manager()
        with db_manager.get_session() as session:
            rec = Recommendation(
                campaign_id=body.get("campaign_id", 0),
                recommendation_type=body.get("type", "allocation_change"),
                title=body.get("title", "Scenario Plan"),
                description=body.get("description", ""),
                details=json.dumps(body.get("details", {})),
                status="pending",
            )
            session.add(rec)
            session.commit()
            session.refresh(rec)
            return {"id": rec.id, "success": True}
    except Exception as e:
        logger.error(f"Error creating recommendation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{recommendation_id}/approve")
async def approve_recommendation(recommendation_id: int):
    """Approve a recommendation and, for budget-mutating types, push the
    new budget to the underlying ad platform.

    Budget push is gated by two flags (both default safe):

    * ``budget_push.enabled`` — master switch, default ``False``.
    * ``budget_push.dry_run`` — default ``True``; logs the change without
      hitting the platform API.

    Both must be flipped for a real Google Ads mutation to fire.
    """
    try:
        from src.bandit_ads.recommendations import Recommendation, RecommendationType
        from src.bandit_ads.api_connectors import push_budget_to_platform

        db_manager = get_db_manager()
        push_enabled, dry_run = _budget_push_settings()

        with db_manager.get_session() as session:
            rec = session.query(Recommendation).filter(
                Recommendation.id == recommendation_id
            ).first()
            if not rec:
                raise HTTPException(status_code=404, detail="Recommendation not found")

            try:
                details = json.loads(rec.details) if rec.details else {}
            except Exception:
                details = {}

            rec_type = rec.recommendation_type
            push_result: Optional[Dict[str, Any]] = None

            budget_types = {
                RecommendationType.ALLOCATION_CHANGE.value,
                RecommendationType.BUDGET_ADJUSTMENT.value,
            }

            if rec_type in budget_types:
                campaign = session.query(Campaign).filter(
                    Campaign.id == rec.campaign_id
                ).first()
                if not campaign:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Campaign {rec.campaign_id} not found",
                    )

                arm = _resolve_arm(session, rec.campaign_id, details)
                if arm is None:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Recommendation details did not resolve to a known "
                            "Arm (need 'arm_id' or 'arm_key')."
                        ),
                    )

                if rec_type == RecommendationType.BUDGET_ADJUSTMENT.value:
                    raw = details.get('new_budget', details.get('suggested_budget'))
                    if raw is None:
                        raise HTTPException(
                            status_code=400,
                            detail="BUDGET_ADJUSTMENT requires 'new_budget' or 'suggested_budget'",
                        )
                    new_budget = float(raw)
                else:
                    alloc = details.get('suggested_allocation', details.get('new_allocation'))
                    if alloc is None:
                        raise HTTPException(
                            status_code=400,
                            detail="ALLOCATION_CHANGE requires 'suggested_allocation' or 'new_allocation'",
                        )
                    total = float(campaign.budget or 0)
                    new_budget = float(alloc) * total

                push_result = {
                    "enabled": push_enabled,
                    "dry_run": dry_run,
                    "arm_id": arm.id,
                    "platform": arm.platform,
                    "new_budget": new_budget,
                }

                if push_enabled:
                    ok = push_budget_to_platform(arm, new_budget, dry_run=dry_run)
                    push_result["ok"] = bool(ok)
                    if not ok:
                        rec.status = "failed"
                        details["push_error"] = (
                            f"push_budget_to_platform returned False for arm {arm.id} "
                            f"on {arm.platform} (dry_run={dry_run})"
                        )
                        rec.details = json.dumps(details)
                        session.commit()
                        raise HTTPException(
                            status_code=502,
                            detail={
                                "message": "Budget push to platform failed",
                                "push": push_result,
                            },
                        )
                else:
                    push_result["ok"] = None
                    logger.info(
                        f"budget_push.enabled is False — marking recommendation "
                        f"{recommendation_id} applied without pushing to platform"
                    )

            rec.status = "applied"
            rec.applied_at = datetime.utcnow()
            session.commit()

        response: Dict[str, Any] = {"success": True, "message": "Recommendation applied"}
        if push_result is not None:
            response["push"] = push_result
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving recommendation {recommendation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{recommendation_id}/reject")
async def reject_recommendation(recommendation_id: int):
    """Reject a recommendation."""
    try:
        from src.bandit_ads.recommendations import Recommendation
        db_manager = get_db_manager()
        with db_manager.get_session() as session:
            rec = session.query(Recommendation).filter(
                Recommendation.id == recommendation_id
            ).first()
            if not rec:
                raise HTTPException(status_code=404, detail="Recommendation not found")
            rec.status = "rejected"
            session.commit()
        return {"success": True, "message": "Recommendation rejected"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting recommendation {recommendation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
