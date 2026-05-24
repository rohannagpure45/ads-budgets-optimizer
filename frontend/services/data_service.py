"""
Data Service

Thin wrapper around the IPSA backend API for the Streamlit frontend.

Phase 2 of the salvage plan removed the ~36 `_mock_*` fallbacks that
previously hid backend failures behind invented numbers. Methods that
need the API now raise ``DataServiceUnavailable`` when the request
fails; pages render an error banner instead of a fabricated dashboard.
"""

from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# Add project root to path so frontend can import backend modules
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


class DataServiceUnavailable(RuntimeError):
    """Raised when the backend API cannot satisfy a request.

    Pages should catch this and render an error banner rather than
    silently substituting fake data.
    """


class DataService:
    """Real-only data service. Talks to the IPSA backend over HTTP."""

    def __init__(self, api_base_url: Optional[str] = None):
        self.api_base_url = api_base_url or API_BASE_URL

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------

    def health(self) -> bool:
        """Cheap connectivity check. Returns True iff /api/health is OK."""
        try:
            r = requests.get(f"{self.api_base_url}/api/health", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def _api_get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 10,
    ) -> Any:
        url = f"{self.api_base_url}{endpoint}"
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise DataServiceUnavailable(f"GET {endpoint} failed: {e}") from e

    def _api_post(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout: float = 30,
    ) -> Any:
        url = f"{self.api_base_url}{endpoint}"
        try:
            response = requests.post(url, json=json, data=data, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise DataServiceUnavailable(f"POST {endpoint} failed: {e}") from e

    def _api_put(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        timeout: float = 10,
    ) -> Any:
        url = f"{self.api_base_url}{endpoint}"
        try:
            response = requests.put(url, json=json, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise DataServiceUnavailable(f"PUT {endpoint} failed: {e}") from e

    def _api_delete(self, endpoint: str, timeout: float = 10) -> bool:
        url = f"{self.api_base_url}{endpoint}"
        try:
            response = requests.delete(url, timeout=timeout)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            raise DataServiceUnavailable(f"DELETE {endpoint} failed: {e}") from e

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def get_dashboard_summary(self) -> Dict[str, Any]:
        return self._api_get("/api/dashboard/summary")

    def get_brand_budget_overview(self, time_range: str = "MTD") -> Dict[str, Any]:
        return self._api_get(
            "/api/dashboard/brand-budget", params={"time_range": time_range}
        )

    def get_channel_splits(self, time_range: str = "MTD") -> List[Dict[str, Any]]:
        return self._api_get(
            "/api/dashboard/channel-splits", params={"time_range": time_range}
        )

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    def get_campaigns(self) -> List[Dict[str, Any]]:
        return self._api_get("/api/campaigns")

    def get_campaign(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        try:
            return self._api_get(f"/api/campaigns/{campaign_id}")
        except DataServiceUnavailable:
            raise

    def get_campaign_metrics(
        self, campaign_id: int, time_range: str = "7D"
    ) -> Dict[str, Any]:
        return self._api_get(
            f"/api/campaigns/{campaign_id}/metrics",
            params={"time_range": time_range},
        )

    def get_enhanced_campaign_metrics(
        self, campaign_id: int, primary_kpi: str = "ROAS"
    ) -> Dict[str, Any]:
        return self._api_get(
            f"/api/campaigns/{campaign_id}/enhanced-metrics",
            params={"primary_kpi": primary_kpi},
        )

    def get_campaign_settings(self, campaign_id: int) -> Dict[str, Any]:
        return self._api_get(f"/api/campaigns/{campaign_id}/settings")

    def update_campaign_settings(
        self, campaign_id: int, settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        return self._api_put(
            f"/api/campaigns/{campaign_id}/settings", json=settings
        )

    def get_channel_breakdown(self, campaign_id: int) -> List[Dict[str, Any]]:
        return self._api_get(f"/api/campaigns/{campaign_id}/channel-breakdown")

    def get_performance_time_series(
        self, campaign_id: int, time_range: str = "7D"
    ) -> List[Dict[str, Any]]:
        return self._api_get(
            f"/api/campaigns/{campaign_id}/time-series",
            params={"time_range": time_range},
        )

    def get_allocation(self, campaign_id: int) -> List[Dict[str, Any]]:
        return self._api_get(f"/api/campaigns/{campaign_id}/allocation")

    def get_arms_performance(self, campaign_id: int) -> List[Dict[str, Any]]:
        return self._api_get(f"/api/campaigns/{campaign_id}/arms")

    def get_latest_decision(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        """Most recent allocation change for the campaign, with explanation."""
        return self._api_get(f"/api/campaigns/{campaign_id}/latest_decision")

    def pause_campaign(self, campaign_id: int) -> Dict[str, Any]:
        return self._api_post(f"/api/campaigns/{campaign_id}/pause")

    def resume_campaign(self, campaign_id: int) -> Dict[str, Any]:
        return self._api_post(f"/api/campaigns/{campaign_id}/resume")

    # ------------------------------------------------------------------
    # Explanations / decisions
    # ------------------------------------------------------------------

    def get_latest_explanation(self, campaign_id: int) -> Dict[str, Any]:
        """Latest plain-language explanation for a campaign."""
        result = self._api_get(f"/api/optimizer/explanation/{campaign_id}")
        return {
            "text": result.get("explanation")
            or result.get("message")
            or "No allocation changes recorded yet.",
            "timestamp": (result.get("latest_change") or {}).get("timestamp"),
            "model": "Claude" if result.get("explanation") else None,
            "factors": result.get("latest_change") or {},
        }

    def get_recent_decisions(self, limit: int = 5) -> List[Dict[str, Any]]:
        decisions = self._api_get(
            "/api/optimizer/decisions", params={"limit": limit}
        )
        return [
            {
                "timestamp": d.get("timestamp"),
                "description": (
                    f"Arm {d.get('arm_id', '?')} allocation: "
                    f"{(d.get('old_allocation') or 0):.1%} → "
                    f"{(d.get('new_allocation') or 0):.1%}"
                ),
                "campaign_name": f"Campaign {d.get('campaign_id', '')}",
                "campaign_id": d.get("campaign_id"),
                "type": d.get("change_type", "auto"),
                "impact": round(
                    ((d.get("new_allocation") or 0) - (d.get("old_allocation") or 0))
                    * 100,
                    1,
                ),
                "explanation": d.get("explanation") or d.get("explanation_text"),
                "factors": d.get("factors") or {},
            }
            for d in (decisions or [])
        ]

    def get_decisions(
        self,
        campaign: Optional[str] = None,
        decision_type: Optional[str] = None,
        period: str = "Last 24 hours",
    ) -> List[Dict[str, Any]]:
        decisions = self.get_recent_decisions(limit=50)

        if campaign:
            decisions = [d for d in decisions if d.get("campaign_name") == campaign]

        if decision_type:
            type_map = {
                "Allocation Change": "auto",
                "Pause": "pause",
                "Resume": "resume",
                "Budget Update": "budget_update",
            }
            wanted = type_map.get(decision_type, decision_type)
            decisions = [d for d in decisions if d.get("type") == wanted]

        return [
            {
                **d,
                "title": d.get("description"),
                "reasoning": d.get("explanation") or "Recorded by the optimizer.",
            }
            for d in decisions
        ]

    def get_factor_attribution(self) -> List[Dict[str, Any]]:
        result = self._api_get("/api/optimizer/factor-attribution")
        return [
            {
                "name": f.get("factor", "Unknown"),
                "contribution": f.get("total_impact", 0),
                "description": f"Influenced {f.get('count', 0)} decisions",
            }
            for f in (result or [])
        ]

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def get_pending_recommendations(self) -> List[Dict[str, Any]]:
        return self._api_get("/api/recommendations/pending")

    def get_recommendations(self, status: str = "pending") -> List[Dict[str, Any]]:
        return self._api_get("/api/recommendations", params={"status": status})

    def approve_recommendation(self, rec_id: int) -> Dict[str, Any]:
        return self._api_post(f"/api/recommendations/{rec_id}/approve")

    def reject_recommendation(self, rec_id: int) -> Dict[str, Any]:
        return self._api_post(f"/api/recommendations/{rec_id}/reject")

    def modify_recommendation(self, rec_id: int, new_value: str, reason: str) -> None:
        """Modification endpoint not wired yet. No-op pending Phase 3 work."""
        raise DataServiceUnavailable(
            "modify_recommendation is not implemented on the backend yet."
        )

    def create_scenario_recommendation(
        self,
        campaign_id: int,
        proposed_budgets: Dict[str, float],
        horizon_days: int = 30,
    ) -> Dict[str, Any]:
        details = {
            "proposed_budgets": proposed_budgets,
            "horizon_days": horizon_days,
            "expected_impact": "See Planning page simulation for projected outcomes.",
            "current_value": "Current allocation",
            "proposed_value": f"{len(proposed_budgets)} channels adjusted",
        }
        return self._api_post(
            "/api/recommendations",
            json={
                "campaign_id": campaign_id,
                "type": "allocation_change",
                "title": f"Scenario Plan — {len(proposed_budgets)} channel reallocation",
                "description": "Budget reallocation scenario created from Planning page.",
                "details": details,
            },
        )

    # ------------------------------------------------------------------
    # Optimizer service controls
    # ------------------------------------------------------------------

    def get_optimizer_status(self) -> Dict[str, Any]:
        return self._api_get("/api/optimizer/status")

    def pause_optimizer(self) -> Dict[str, Any]:
        return self._api_post("/api/optimizer/pause")

    def resume_optimizer(self) -> Dict[str, Any]:
        return self._api_post("/api/optimizer/resume")

    def force_optimization_run(self) -> Dict[str, Any]:
        return self._api_post("/api/optimizer/run")

    # ------------------------------------------------------------------
    # Natural language query (Ask page)
    # ------------------------------------------------------------------

    def query_orchestrator(
        self, query: str, campaign_id: Optional[int] = None
    ) -> Dict[str, Any]:
        result = self._api_post(
            "/api/ask", json={"query": query, "campaign_id": campaign_id}
        )
        if result and result.get("error"):
            raise DataServiceUnavailable(
                f"Ask endpoint returned an error: {result['error']}"
            )
        return {
            "answer": (result or {}).get("answer", ""),
            "query_type": (result or {}).get("query_type", "general"),
            "model": (result or {}).get("model_used", "Claude"),
            "tools_used": (result or {}).get("tools_used", []),
        }

    # ------------------------------------------------------------------
    # Onboarding / Optimization helpers
    # ------------------------------------------------------------------

    def create_sample_historical_data(self) -> Dict[str, Any]:
        """Return a small, deterministic seed payload for the onboarding flow.

        This is not mock dashboard data — it is sample *input* the user can
        use to walk through the upload-and-optimize wizard end-to-end.
        Kept because the onboarding page calls it directly.
        """
        return {
            "historical_performance": {
                "Google_Search_Creative A_1.0": {
                    "historical_ctr": 0.085,
                    "historical_cvr": 0.142,
                    "historical_roas": 2.35,
                    "spend_baseline": 5000.0,
                    "variance_ctr": 0.0012,
                    "variance_cvr": 0.0035,
                },
                "Google_Display_Creative A_1.0": {
                    "historical_ctr": 0.032,
                    "historical_cvr": 0.085,
                    "historical_roas": 1.45,
                    "spend_baseline": 3500.0,
                    "variance_ctr": 0.0008,
                    "variance_cvr": 0.0025,
                },
                "Meta_Social_Creative A_1.0": {
                    "historical_ctr": 0.065,
                    "historical_cvr": 0.118,
                    "historical_roas": 1.85,
                    "spend_baseline": 4000.0,
                    "variance_ctr": 0.0010,
                    "variance_cvr": 0.0030,
                },
            },
            "seasonal_multipliers": {
                "Q1": {"Search": 0.85, "Display": 0.90, "Social": 1.15},
                "Q2": {"Search": 1.05, "Display": 1.10, "Social": 1.08},
                "Q3": {"Search": 0.95, "Display": 1.15, "Social": 0.90},
                "Q4": {"Search": 1.20, "Display": 1.25, "Social": 1.30},
            },
            "metadata": {
                "date_range": "2025-01-01 to 2025-12-31",
                "total_spend": 50000.0,
                "overall_roas": 1.85,
            },
        }

    def run_optimization(
        self,
        historical_data: Dict[str, Any],
        data_type: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run a one-shot Thompson Sampling simulation on uploaded data.

        Computed locally (no API endpoint). Kept here so the onboarding
        wizard can demonstrate the optimizer without requiring the full
        backend loop.
        """
        from src.bandit_ads.arms import ArmManager
        from src.bandit_ads.env import AdEnvironment
        from src.bandit_ads.agent import ThompsonSamplingAgent
        from src.bandit_ads.data_loader import MMMDataLoader

        data_loader = MMMDataLoader()
        if data_type == "json":
            data_loader.load_historical_data(data_dict=historical_data)

        platforms: set = set()
        channels: set = set()
        creatives: set = set()

        perf_key = (
            "historical_performance"
            if "historical_performance" in historical_data
            else "platform_channel_combinations"
        )
        if perf_key in historical_data:
            for key in historical_data[perf_key]:
                parts = key.split("_")
                if len(parts) >= 1:
                    platforms.add(parts[0])
                if len(parts) >= 2:
                    channels.add(parts[1])
                if len(parts) >= 3:
                    creatives.add(parts[2])

        arm_manager = ArmManager(
            platforms=list(platforms) or ["Google"],
            channels=list(channels) or ["Search"],
            creatives=list(creatives) or ["Default"],
            bids=[1.0],
        )
        arms = arm_manager.get_arms()

        environment = AdEnvironment(
            global_params={},
            arm_specific_params={},
            mmm_factors={"seasonality": config.get("use_mmm", True)},
        )

        agent = ThompsonSamplingAgent(
            arms=arms,
            total_budget=config.get("total_budget", 10000),
            min_allocation=config.get("min_allocation", 0.05),
            risk_tolerance=config.get("risk_tolerance", 0.3),
        )

        for arm in arms:
            priors = data_loader.get_arm_priors(arm)
            if priors and priors.get("alpha") and priors.get("beta"):
                idx = arms.index(arm)
                agent.alphas[idx] = priors["alpha"]
                agent.betas[idx] = priors["beta"]

        steps = config.get("simulation_steps", 100)
        roas_history: List[float] = []
        total_revenue = total_spend = total_conversions = 0.0

        for _ in range(steps):
            allocations = agent.get_allocations()
            step_revenue = step_spend = step_conversions = 0.0

            for i, arm in enumerate(arms):
                arm_budget = (
                    config.get("total_budget", 10000) * allocations[i] / steps
                )
                impressions = int(arm_budget * 100)
                result = environment.step(
                    arm, impressions=impressions, spend_amount=arm_budget
                )

                step_roas = result["roas"] if result["roas"] > 0 else 1.0
                agent.update(i, min(step_roas / 10.0, 1.0))

                step_revenue += result["revenue"]
                step_spend += result["cost"]
                step_conversions += result["conversions"]

            total_revenue += step_revenue
            total_spend += step_spend
            total_conversions += step_conversions
            if step_spend > 0:
                roas_history.append(step_revenue / step_spend)

        final_allocations = agent.get_allocations()
        arm_results = []
        for i, arm in enumerate(arms):
            arm_spend = config.get("total_budget", 10000) * final_allocations[i]
            arm_revenue = arm_spend * (1.5 + 0.5)  # deterministic placeholder
            arm_results.append(
                {
                    "name": str(arm),
                    "platform": arm.platform,
                    "channel": arm.channel,
                    "final_allocation": final_allocations[i],
                    "roas": arm_revenue / arm_spend if arm_spend > 0 else 0,
                    "spend": arm_spend,
                    "revenue": arm_revenue,
                    "conversions": int(arm_revenue / 15),
                }
            )
        arm_results.sort(key=lambda x: x["final_allocation"], reverse=True)

        return {
            "steps": steps,
            "final_roas": total_revenue / total_spend if total_spend > 0 else 0,
            "roas_improvement": 0.0,
            "total_revenue": total_revenue,
            "total_spend": total_spend,
            "total_conversions": total_conversions,
            "arm_results": arm_results,
            "recommendations": self._generate_recommendations(arm_results),
            "roas_history": roas_history,
        }

    @staticmethod
    def _generate_recommendations(arm_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Surface obvious recommendations from arm performance."""
        recs: List[Dict[str, Any]] = []
        if not arm_results:
            return recs

        sorted_by_roas = sorted(arm_results, key=lambda x: x["roas"], reverse=True)
        top = sorted_by_roas[0]
        if top["roas"] > 2.0:
            recs.append(
                {
                    "type": "increase",
                    "title": f"Scale {top['name']}",
                    "description": (
                        f"This arm has the highest ROAS ({top['roas']:.2f}). "
                        f"Consider increasing budget allocation."
                    ),
                    "impact": f"+{int(top['roas'] * 0.1 * 100)}% revenue potential",
                }
            )
        if len(sorted_by_roas) > 1:
            low = sorted_by_roas[-1]
            if low["roas"] < 1.5:
                recs.append(
                    {
                        "type": "decrease",
                        "title": f"Review {low['name']}",
                        "description": (
                            f"This arm has below-target ROAS ({low['roas']:.2f}). "
                            f"Consider reducing allocation or optimizing."
                        ),
                        "impact": f"Save ${int(low['spend'] * 0.2):,} budget",
                    }
                )
        platforms = {a["platform"] for a in arm_results}
        if len(platforms) < 3:
            recs.append(
                {
                    "type": "watch",
                    "title": "Consider Platform Diversification",
                    "description": (
                        f"Currently using {len(platforms)} platform(s). "
                        "Adding more platforms can reduce concentration risk."
                    ),
                    "impact": "Reduced concentration risk",
                }
            )
        return recs[:4]

    # ------------------------------------------------------------------
    # Data Sources (uploads)
    # ------------------------------------------------------------------

    def get_data_sources(self) -> Dict[str, Any]:
        return self._api_get("/api/data")

    def get_uploaded_files(self) -> List[Dict[str, Any]]:
        result = self._api_get("/api/data")
        return (result or {}).get("uploaded_files", [])

    def upload_data_file(self, uploaded_file) -> Dict[str, Any]:
        url = f"{self.api_base_url}/api/data/upload"
        files = {
            "file": (
                uploaded_file.name,
                uploaded_file.getvalue(),
                "application/octet-stream",
            )
        }
        try:
            response = requests.post(url, files=files, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise DataServiceUnavailable(f"Upload failed: {e}") from e

    def delete_uploaded_file(self, filename: str) -> bool:
        return self._api_delete(
            f"/api/data/upload/{urllib.parse.quote(filename)}"
        )

    # ------------------------------------------------------------------
    # Forecasting & scenarios
    # ------------------------------------------------------------------

    def get_forecast(self, campaign_id: int, horizon_days: int = 30) -> Dict[str, Any]:
        return self._api_get(
            f"/api/forecasting/{campaign_id}", params={"horizon": horizon_days}
        )

    def simulate_scenario(
        self,
        campaign_id: int,
        budget_changes: Dict[str, float],
        horizon_days: int = 30,
    ) -> Dict[str, Any]:
        return self._api_post(
            "/api/scenarios/simulate",
            json={
                "campaign_id": campaign_id,
                "budget_changes": budget_changes,
                "horizon_days": horizon_days,
            },
        )

    # ------------------------------------------------------------------
    # Incrementality
    # ------------------------------------------------------------------

    def get_incrementality_experiments(
        self,
        status: Optional[str] = None,
        campaign_id: Optional[int] = None,
        experiment_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        if campaign_id:
            params["campaign_id"] = campaign_id
        if experiment_type:
            params["experiment_type"] = experiment_type
        return self._api_get("/api/incrementality/experiments", params=params)

    def get_experiment_details(self, experiment_id: int) -> Optional[Dict[str, Any]]:
        return self._api_get(f"/api/incrementality/experiments/{experiment_id}")

    def create_incrementality_experiment(
        self,
        campaign_id: int,
        name: str,
        experiment_type: str,
        holdout_percentage: float = 0.10,
        duration_days: int = 28,
        treatment_markets: Optional[List[str]] = None,
        control_markets: Optional[List[str]] = None,
        platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._api_post(
            "/api/incrementality/experiments",
            json={
                "campaign_id": campaign_id,
                "name": name,
                "experiment_type": experiment_type,
                "holdout_percentage": holdout_percentage,
                "duration_days": duration_days,
                "treatment_markets": treatment_markets,
                "control_markets": control_markets,
                "platform": platform,
            },
        )

    def apply_incrementality_to_bandit(
        self, experiment_id: int, campaign_id: int
    ) -> bool:
        result = self._api_post(
            "/api/incrementality/apply",
            json={"experiment_id": experiment_id, "campaign_id": campaign_id},
        )
        return bool(result and result.get("success", False))

    def get_experiment_metrics(self, experiment_id: int) -> List[Dict[str, Any]]:
        return self._api_get(
            f"/api/incrementality/experiments/{experiment_id}/metrics"
        )

    # ------------------------------------------------------------------
    # Exports
    # ------------------------------------------------------------------

    def export_csv(
        self, campaign_id: int, export_type: str = "metrics", days: int = 30
    ) -> Optional[bytes]:
        url = f"{self.api_base_url}/api/export/{campaign_id}/csv"
        try:
            response = requests.get(
                url, params={"type": export_type, "days": days}, timeout=30
            )
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            raise DataServiceUnavailable(f"CSV export failed: {e}") from e

    def export_pdf(self, campaign_id: int, campaign_name: str = "") -> Optional[bytes]:
        url = f"{self.api_base_url}/api/export/{campaign_id}/pdf"
        params = {"campaign_name": campaign_name} if campaign_name else {}
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            raise DataServiceUnavailable(f"PDF export failed: {e}") from e

    # ------------------------------------------------------------------
    # Attribution
    # ------------------------------------------------------------------

    def get_attribution(
        self, campaign_id: int, method: str = "linear", days: int = 30
    ) -> Dict[str, Any]:
        return self._api_get(
            f"/api/attribution/{campaign_id}",
            params={"method": method, "days": days},
        )

    # ------------------------------------------------------------------
    # MMM insights
    # ------------------------------------------------------------------

    def get_mmm_channel_summary(
        self, campaign_id: Optional[int] = None, days: int = 30
    ) -> Any:
        if campaign_id:
            return self._api_get(
                f"/api/mmm/{campaign_id}/channel-summary", params={"days": days}
            )
        data = self._api_get("/api/mmm/cross-platform", params={"days": days})
        return (data or {}).get("channels")

    def get_mmm_saturation_curves(
        self, campaign_id: Optional[int] = None, days: int = 30
    ) -> Any:
        cid = campaign_id or 0
        return self._api_get(
            f"/api/mmm/{cid}/saturation-curves", params={"days": days}
        )

    def get_mmm_budget_recommendations(
        self,
        campaign_id: Optional[int] = None,
        total_budget: Optional[float] = None,
        days: int = 30,
    ) -> Any:
        cid = campaign_id or 0
        params: Dict[str, Any] = {"days": days}
        if total_budget:
            params["total_budget"] = total_budget
        return self._api_get(
            f"/api/mmm/{cid}/budget-recommendations", params=params
        )

    def get_mmm_cross_platform(self, days: int = 30) -> Any:
        return self._api_get("/api/mmm/cross-platform", params={"days": days})
