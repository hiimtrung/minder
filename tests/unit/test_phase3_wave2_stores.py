"""
P3-Wave2 unit tests — Knowledge Graph Store, Rule Store, Feedback Store.

All tests use an in-memory SQLite database so no external services are needed.
"""

from __future__ import annotations

import uuid

import pytest

from minder.store.feedback import FeedbackStore
from minder.store.graph import KnowledgeGraphStore
from minder.store.rule import RuleStore

_IN_MEM = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def graph_store() -> KnowledgeGraphStore:
    store = KnowledgeGraphStore(_IN_MEM)
    await store.init_db()
    yield store
    await store.dispose()


@pytest.fixture
async def rule_store() -> RuleStore:
    store = RuleStore(_IN_MEM)
    await store.init_db()
    yield store
    await store.dispose()


@pytest.fixture
async def feedback_store() -> FeedbackStore:
    store = FeedbackStore(_IN_MEM)
    await store.init_db()
    yield store
    await store.dispose()


# ---------------------------------------------------------------------------
# TestKnowledgeGraphStore
# ---------------------------------------------------------------------------


class TestKnowledgeGraphStore:
    async def test_add_and_get_node(self, graph_store: KnowledgeGraphStore) -> None:
        node = await graph_store.add_node("module", "auth.service")
        fetched = await graph_store.get_node(node.id)
        assert fetched is not None
        assert fetched.name == "auth.service"
        assert fetched.node_type == "module"

    async def test_add_node_with_metadata(self, graph_store: KnowledgeGraphStore) -> None:
        node = await graph_store.add_node("file", "src/main.py", metadata={"lines": 120})
        fetched = await graph_store.get_node(node.id)
        assert fetched is not None
        assert fetched.node_metadata["lines"] == 120

    async def test_get_nonexistent_node_returns_none(self, graph_store: KnowledgeGraphStore) -> None:
        result = await graph_store.get_node(uuid.uuid4())
        assert result is None

    async def test_upsert_node_creates_when_absent(self, graph_store: KnowledgeGraphStore) -> None:
        node = await graph_store.upsert_node("service", "user-service")
        assert node.id is not None
        assert node.name == "user-service"

    async def test_upsert_node_updates_metadata_when_present(
        self, graph_store: KnowledgeGraphStore
    ) -> None:
        await graph_store.upsert_node("service", "order-service", metadata={"version": 1})
        updated = await graph_store.upsert_node("service", "order-service", metadata={"version": 2})
        assert updated.node_metadata.get("version") == 2

    async def test_upsert_node_idempotent_same_id(self, graph_store: KnowledgeGraphStore) -> None:
        n1 = await graph_store.upsert_node("module", "payments")
        n2 = await graph_store.upsert_node("module", "payments")
        assert n1.id == n2.id

    async def test_query_by_type(self, graph_store: KnowledgeGraphStore) -> None:
        await graph_store.add_node("module", "auth")
        await graph_store.add_node("module", "billing")
        await graph_store.add_node("file", "main.py")
        modules = await graph_store.query_by_type("module")
        assert len(modules) == 2
        names = {n.name for n in modules}
        assert names == {"auth", "billing"}

    async def test_add_and_get_neighbors_outgoing(self, graph_store: KnowledgeGraphStore) -> None:
        src = await graph_store.add_node("module", "order")
        tgt = await graph_store.add_node("module", "payment")
        await graph_store.add_edge(src.id, tgt.id, "depends_on")
        neighbors = await graph_store.get_neighbors(src.id, direction="out")
        assert len(neighbors) == 1
        assert neighbors[0].id == tgt.id

    async def test_get_neighbors_incoming(self, graph_store: KnowledgeGraphStore) -> None:
        src = await graph_store.add_node("module", "api")
        tgt = await graph_store.add_node("module", "db")
        await graph_store.add_edge(src.id, tgt.id, "calls")
        neighbors = await graph_store.get_neighbors(tgt.id, direction="in")
        assert len(neighbors) == 1
        assert neighbors[0].id == src.id

    async def test_get_neighbors_filter_by_relation(
        self, graph_store: KnowledgeGraphStore
    ) -> None:
        src = await graph_store.add_node("module", "controller")
        a = await graph_store.add_node("module", "service-a")
        b = await graph_store.add_node("module", "service-b")
        await graph_store.add_edge(src.id, a.id, "calls")
        await graph_store.add_edge(src.id, b.id, "imports")
        calls = await graph_store.get_neighbors(src.id, direction="out", relation="calls")
        assert len(calls) == 1
        assert calls[0].id == a.id

    async def test_get_neighbors_both_directions(
        self, graph_store: KnowledgeGraphStore
    ) -> None:
        a = await graph_store.add_node("module", "a")
        b = await graph_store.add_node("module", "b")
        c = await graph_store.add_node("module", "c")
        await graph_store.add_edge(a.id, b.id, "depends_on")
        await graph_store.add_edge(c.id, b.id, "depends_on")
        both = await graph_store.get_neighbors(b.id, direction="both")
        ids = {n.id for n in both}
        assert a.id in ids
        assert c.id in ids

    async def test_get_path_direct(self, graph_store: KnowledgeGraphStore) -> None:
        src = await graph_store.add_node("module", "start")
        tgt = await graph_store.add_node("module", "end")
        await graph_store.add_edge(src.id, tgt.id, "imports")
        path = await graph_store.get_path(src.id, tgt.id)
        assert len(path) == 2
        assert path[0].id == src.id
        assert path[1].id == tgt.id

    async def test_get_path_multi_hop(self, graph_store: KnowledgeGraphStore) -> None:
        a = await graph_store.add_node("module", "A")
        b = await graph_store.add_node("module", "B")
        c = await graph_store.add_node("module", "C")
        await graph_store.add_edge(a.id, b.id, "depends_on")
        await graph_store.add_edge(b.id, c.id, "depends_on")
        path = await graph_store.get_path(a.id, c.id)
        assert [n.id for n in path] == [a.id, b.id, c.id]

    async def test_get_path_no_path_returns_empty(
        self, graph_store: KnowledgeGraphStore
    ) -> None:
        a = await graph_store.add_node("module", "isolated-a")
        b = await graph_store.add_node("module", "isolated-b")
        path = await graph_store.get_path(a.id, b.id)
        assert path == []

    async def test_get_path_same_node(self, graph_store: KnowledgeGraphStore) -> None:
        n = await graph_store.add_node("module", "self-ref")
        path = await graph_store.get_path(n.id, n.id)
        assert len(path) == 1
        assert path[0].id == n.id

    async def test_upsert_edge_idempotent(self, graph_store: KnowledgeGraphStore) -> None:
        src = await graph_store.add_node("module", "x")
        tgt = await graph_store.add_node("module", "y")
        e1 = await graph_store.upsert_edge(src.id, tgt.id, "depends_on", weight=1.0)
        e2 = await graph_store.upsert_edge(src.id, tgt.id, "depends_on", weight=2.0)
        assert e1.id == e2.id

    async def test_delete_node_cascades_edges(self, graph_store: KnowledgeGraphStore) -> None:
        src = await graph_store.add_node("module", "to-delete")
        tgt = await graph_store.add_node("module", "stays")
        await graph_store.add_edge(src.id, tgt.id, "calls")
        await graph_store.delete_node(src.id)
        # Deleting src should also remove the edge
        neighbors = await graph_store.get_neighbors(tgt.id, direction="in")
        assert neighbors == []

    async def test_get_node_by_name(self, graph_store: KnowledgeGraphStore) -> None:
        await graph_store.add_node("owner", "team-alpha")
        found = await graph_store.get_node_by_name("owner", "team-alpha")
        assert found is not None
        assert found.name == "team-alpha"


# ---------------------------------------------------------------------------
# TestRuleStore
# ---------------------------------------------------------------------------


class TestRuleStore:
    async def test_create_and_get_rule(self, rule_store: RuleStore) -> None:
        rule = await rule_store.create_rule(
            title="No bare except",
            description="Avoid bare except clauses",
            pattern="except:",
            content="Use specific exception types.",
            scope="global",
        )
        fetched = await rule_store.get_rule_by_id(rule.id)
        assert fetched is not None
        assert fetched.title == "No bare except"

    async def test_get_nonexistent_rule_returns_none(self, rule_store: RuleStore) -> None:
        result = await rule_store.get_rule_by_id(uuid.uuid4())
        assert result is None

    async def test_list_rules(self, rule_store: RuleStore) -> None:
        await rule_store.create_rule(
            title="R1", description="", pattern="", content="", scope="global"
        )
        await rule_store.create_rule(
            title="R2", description="", pattern="", content="", scope="project"
        )
        all_rules = await rule_store.list_rules()
        assert len(all_rules) == 2

    async def test_list_by_scope(self, rule_store: RuleStore) -> None:
        await rule_store.create_rule(
            title="G1", description="", pattern="", content="", scope="global"
        )
        await rule_store.create_rule(
            title="P1", description="", pattern="", content="", scope="project"
        )
        await rule_store.create_rule(
            title="G2", description="", pattern="", content="", scope="global"
        )
        global_rules = await rule_store.list_by_scope("global")
        assert len(global_rules) == 2
        assert all(r.scope == "global" for r in global_rules)

    async def test_list_active(self, rule_store: RuleStore) -> None:
        await rule_store.create_rule(
            title="Active", description="", pattern="", content="", scope="global", active=True
        )
        inactive = await rule_store.create_rule(
            title="Inactive", description="", pattern="", content="", scope="global", active=False
        )
        active_rules = await rule_store.list_active()
        ids = {r.id for r in active_rules}
        assert inactive.id not in ids

    async def test_update_rule(self, rule_store: RuleStore) -> None:
        rule = await rule_store.create_rule(
            title="Old title", description="", pattern="", content="", scope="global"
        )
        await rule_store.update_rule(rule.id, title="New title")
        updated = await rule_store.get_rule_by_id(rule.id)
        assert updated is not None
        assert updated.title == "New title"

    async def test_delete_rule(self, rule_store: RuleStore) -> None:
        rule = await rule_store.create_rule(
            title="To delete", description="", pattern="", content="", scope="global"
        )
        await rule_store.delete_rule(rule.id)
        assert await rule_store.get_rule_by_id(rule.id) is None

    async def test_list_by_scope_returns_empty_for_unknown_scope(
        self, rule_store: RuleStore
    ) -> None:
        result = await rule_store.list_by_scope("nonexistent")
        assert result == []


# ---------------------------------------------------------------------------
# TestFeedbackStore
# ---------------------------------------------------------------------------


class TestFeedbackStore:
    async def test_create_and_get_feedback(self, feedback_store: FeedbackStore) -> None:
        eid = uuid.uuid4()
        fb = await feedback_store.create_feedback(
            entity_type="skill",
            entity_id=eid,
            rating=4,
            feedback_text="Very helpful",
        )
        fetched = await feedback_store.get_feedback_by_id(fb.id)
        assert fetched is not None
        assert fetched.rating == 4
        assert fetched.entity_type == "skill"

    async def test_get_nonexistent_feedback_returns_none(
        self, feedback_store: FeedbackStore
    ) -> None:
        result = await feedback_store.get_feedback_by_id(uuid.uuid4())
        assert result is None

    async def test_list_feedback(self, feedback_store: FeedbackStore) -> None:
        eid = uuid.uuid4()
        await feedback_store.create_feedback(entity_type="response", entity_id=eid, rating=3)
        await feedback_store.create_feedback(entity_type="response", entity_id=eid, rating=5)
        all_fb = await feedback_store.list_feedback()
        assert len(all_fb) == 2

    async def test_list_by_entity(self, feedback_store: FeedbackStore) -> None:
        eid_a = uuid.uuid4()
        eid_b = uuid.uuid4()
        await feedback_store.create_feedback(entity_type="skill", entity_id=eid_a, rating=5)
        await feedback_store.create_feedback(entity_type="skill", entity_id=eid_b, rating=2)
        await feedback_store.create_feedback(entity_type="skill", entity_id=eid_a, rating=4)

        for_a = await feedback_store.list_by_entity("skill", eid_a)
        assert len(for_a) == 2
        assert all(fb.entity_id == eid_a for fb in for_a)

    async def test_list_by_entity_filters_entity_type(
        self, feedback_store: FeedbackStore
    ) -> None:
        eid = uuid.uuid4()
        await feedback_store.create_feedback(entity_type="skill", entity_id=eid, rating=5)
        await feedback_store.create_feedback(entity_type="response", entity_id=eid, rating=3)

        skill_fb = await feedback_store.list_by_entity("skill", eid)
        assert len(skill_fb) == 1
        assert skill_fb[0].entity_type == "skill"

    async def test_average_rating(self, feedback_store: FeedbackStore) -> None:
        eid = uuid.uuid4()
        await feedback_store.create_feedback(entity_type="skill", entity_id=eid, rating=3)
        await feedback_store.create_feedback(entity_type="skill", entity_id=eid, rating=5)
        avg = await feedback_store.average_rating(eid)
        assert avg == pytest.approx(4.0)

    async def test_average_rating_returns_none_when_no_feedback(
        self, feedback_store: FeedbackStore
    ) -> None:
        result = await feedback_store.average_rating(uuid.uuid4())
        assert result is None

    async def test_average_rating_single_entry(self, feedback_store: FeedbackStore) -> None:
        eid = uuid.uuid4()
        await feedback_store.create_feedback(entity_type="retrieval", entity_id=eid, rating=2)
        avg = await feedback_store.average_rating(eid)
        assert avg == pytest.approx(2.0)

    async def test_update_feedback(self, feedback_store: FeedbackStore) -> None:
        eid = uuid.uuid4()
        fb = await feedback_store.create_feedback(
            entity_type="workflow", entity_id=eid, rating=2
        )
        await feedback_store.update_feedback(fb.id, rating=5)
        updated = await feedback_store.get_feedback_by_id(fb.id)
        assert updated is not None
        assert updated.rating == 5

    async def test_delete_feedback(self, feedback_store: FeedbackStore) -> None:
        eid = uuid.uuid4()
        fb = await feedback_store.create_feedback(entity_type="skill", entity_id=eid, rating=1)
        await feedback_store.delete_feedback(fb.id)
        assert await feedback_store.get_feedback_by_id(fb.id) is None
