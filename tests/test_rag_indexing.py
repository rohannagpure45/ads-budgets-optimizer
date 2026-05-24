"""RAG-indexing tests — prove the vector-store loop is actually wired.

Before Phase 6 the RAG memory looked built but had never stored or surfaced a
single decision: ``VectorStore.add_decision_explanation`` had zero callers, and
the Ask path's ``_format_rag_context`` was dead code nested inside an ``else``.
These tests are the canary for that loop:

1. Every explained allocation change is handed to the vector store.
2. ``Orchestrator._format_rag_context`` produces non-empty context from a
   retrieved decision (the bug fix that lets the Ask page use that history).

No ChromaDB or network is required — the store is faked.
"""

from __future__ import annotations

from datetime import datetime

import pytest


@pytest.fixture
def in_memory_db(monkeypatch):
    """Point the relevant global singletons at a fresh in-memory SQLite DB.

    The change tracker and explanation generator capture ``get_db_manager()``
    at construction, so the DB global must be swapped *before* those singletons
    are built. monkeypatch reverts everything after the test.
    """
    import src.bandit_ads.database as database_mod
    import src.bandit_ads.change_tracker as change_tracker_mod
    import src.bandit_ads.explanation_generator as expl_mod

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

    yield dbm


class FakeStore:
    """Records what gets indexed; returns a canned hit on search."""

    def __init__(self):
        self.documents = []

    def add_decision_explanation(self, **kwargs):
        self.documents.append(kwargs)
        return True

    def search_similar_decisions(self, query, campaign_id=None, top_k=5):
        return [{"text": "Campaign 1, Arm 1 — shifted budget toward Search on rising ROAS."}]


def _seed_change(dbm) -> tuple[int, int, int]:
    """Insert one campaign + arm + one AllocationChange row.

    Returns (campaign_id, arm_id, change_id).
    """
    from src.bandit_ads.database import Arm, Campaign
    from src.bandit_ads.change_tracker import get_change_tracker

    with dbm.get_session() as session:
        campaign = Campaign(
            name="rag-canary",
            budget=5000.0,
            start_date=datetime.utcnow(),
            status="active",
        )
        session.add(campaign)
        session.flush()
        campaign_id = campaign.id

        arm = Arm(
            campaign_id=campaign_id,
            platform="Google",
            channel="Search",
            creative="Creative A",
            bid=1.0,
        )
        session.add(arm)
        session.commit()
        session.refresh(arm)
        arm_id = arm.id

    change_id = get_change_tracker().log_allocation_change(
        campaign_id=campaign_id,
        arm_id=arm_id,
        old_allocation=0.30,
        new_allocation=0.45,
        change_type="allocation_increase",
        change_reason="Rising ROAS on Search",
        factors={"roas_trend": "increasing", "saturation": 0.4},
    )
    assert isinstance(change_id, int), "seed change must produce an integer id"
    return campaign_id, arm_id, change_id


async def test_explanation_is_indexed(in_memory_db):
    """Generating an explanation must push exactly one document to the store."""
    from src.bandit_ads.explanation_generator import ExplanationGenerator

    campaign_id, arm_id, change_id = _seed_change(in_memory_db)

    gen = ExplanationGenerator()
    # Force the template path so the test never touches the network.
    gen.claude_client = None
    store = FakeStore()
    gen.vector_store = store

    explanation = await gen.explain_allocation_change(change_id)

    assert explanation, "explanation must be non-empty"
    assert len(store.documents) == 1, "exactly one decision should be indexed"

    doc = store.documents[0]
    assert doc["campaign_id"] == campaign_id
    assert doc["arm_id"] == arm_id
    assert doc["change_type"] == "allocation_increase"
    assert doc["explanation"], "indexed explanation must be non-empty"
    assert doc["factors"] == {"roas_trend": "increasing", "saturation": 0.4}


def test_indexing_is_noop_without_store(in_memory_db):
    """No vector store → indexing degrades to a silent no-op, no raise."""
    from src.bandit_ads.explanation_generator import ExplanationGenerator

    gen = ExplanationGenerator()
    gen.vector_store = None
    # Must not raise even though there is nowhere to index.
    gen._index_decision({"campaign_id": 1, "arm_id": 1}, "some explanation")


def test_format_rag_context_surfaces_history():
    """The Ask-path formatter must turn a retrieved decision into context.

    Exercises the orchestrator bug fix: pre-Phase-6 this formatting lived in a
    dead ``else`` branch and never ran. We call it directly (no LLM needed).
    """
    from src.bandit_ads.orchestrator import OrchestratorAgent

    orch = object.__new__(OrchestratorAgent)  # skip __init__; we only need the method
    rag_results = FakeStore().search_similar_decisions("why did Search go up?")
    context = OrchestratorAgent._format_rag_context(orch, rag_results)

    assert context, "formatted RAG context must be non-empty"
    assert "Past Decisions" in context
    assert "Search" in context
