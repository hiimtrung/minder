import uuid

from minder.models import (
    DocumentSchema,
    ErrorSchema,
    FeedbackSchema,
    HistorySchema,
    MetadataSchema,
    RepositorySchema, RepositoryWorkflowStateSchema,
    RuleSchema,
    SessionSchema,
    SkillSchema,
    UserSchema,
    WorkflowSchema,
)

def test_user_schema():
    user = UserSchema(
        email="test@example.com",
        username="testuser",
        display_name="Test User",
        api_key_hash="hash",
        role="admin"
    )
    assert user.email == "test@example.com"
    assert user.is_active is True
    assert isinstance(user.id, uuid.UUID)

def test_skill_schema():
    skill = SkillSchema(
        title="Test Skill",
        content="Testing",
        language="python"
    )
    assert skill.usage_count == 0
    assert skill.quality_score == 0.0

def test_session_schema():
    user_id = uuid.uuid4()
    session = SessionSchema(user_id=user_id)
    assert session.user_id == user_id
    assert session.ttl == 86400  # 24h default for multi-day work continuity

def test_workflow_schema():
    wf = WorkflowSchema(name="Test Workflow")
    assert wf.name == "Test Workflow"
    assert wf.version == 1
    assert wf.steps == []

def test_repository_schema():
    repo = RepositorySchema(
        repo_name="test-repo",
        repo_url="https://github.com/test",
        default_branch="main"
    )
    assert repo.repo_name == "test-repo"
    assert repo.state_path == ".minder"

def test_repository_workflow_state_schema():
    repo_id = uuid.uuid4()
    state = RepositoryWorkflowStateSchema(
        repo_id=repo_id,
        current_step="Step 1"
    )
    assert state.current_step == "Step 1"
    assert state.completed_steps == []

def test_history_schema():
    session_id = uuid.uuid4()
    history = HistorySchema(
        session_id=session_id,
        role="user",
        content="Hello"
    )
    assert history.role == "user"
    assert history.tokens_used == 0

def test_error_schema():
    error = ErrorSchema(
        error_code="TEST_ERROR",
        error_message="A test error"
    )
    assert error.resolved is False

def test_document_schema():
    doc = DocumentSchema(
        title="Test Doc",
        content="test content",
        doc_type="markdown",
        source_path="/test",
        project="test"
    )
    assert doc.doc_type == "markdown"

def test_rule_schema():
    rule = RuleSchema(
        title="Test Rule",
        description="A rule",
        pattern="*",
        content="test",
        scope="global"
    )
    assert rule.active is True

def test_feedback_schema():
    feedback = FeedbackSchema(
        entity_type="skill",
        entity_id=uuid.uuid4(),
        rating=5
    )
    assert feedback.rating == 5

def test_metadata_schema():
    meta = MetadataSchema(
        entity_type="document",
        entity_id=uuid.uuid4(),
        key="test_key",
        source="system"
    )
    assert meta.version == 1
