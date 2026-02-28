# backend-python/infra/db/db.py
"""Database engine initialization and schema bootstrap utilities."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from config import DATABASE_URL
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Volume(Base):
    __tablename__ = "volumes"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    next_index = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("name", name="uq_volumes_name"),
    )

    pages = relationship(
        "Page",
        back_populates="volume",
        cascade="all, delete-orphan",
    )
    agent_sessions = relationship(
        "AgentSession",
        back_populates="volume",
        cascade="all, delete-orphan",
    )
    context = relationship(
        "VolumeContext",
        back_populates="volume",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Page(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True)
    volume_id = Column(
        String,
        ForeignKey("volumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename = Column(String, nullable=False)
    context = Column(Text, default="", nullable=False)
    page_index = Column(Float, nullable=False)

    volume = relationship("Volume", back_populates="pages")
    boxes = relationship(
        "Box",
        back_populates="page",
        cascade="all, delete-orphan",
    )
    box_detection_runs = relationship(
        "BoxDetectionRun",
        back_populates="page",
        cascade="all, delete-orphan",
    )
    context_snapshot = relationship(
        "PageContext",
        back_populates="page",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("volume_id", "filename", name="uq_pages_volume_filename"),
        Index("ix_pages_volume_page_index", "volume_id", "page_index"),
    )


class VolumeContext(Base):
    __tablename__ = "volume_context"

    volume_id = Column(
        String,
        ForeignKey("volumes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rolling_summary = Column(Text, default="", nullable=False)
    active_characters = Column(JSONB, nullable=True)
    open_threads = Column(JSONB, nullable=True)
    glossary = Column(JSONB, nullable=True)
    last_page_index = Column(Float, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    volume = relationship("Volume", back_populates="context")


class PageContext(Base):
    __tablename__ = "page_context"

    page_id = Column(
        Integer,
        ForeignKey("pages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    volume_id = Column(
        String,
        ForeignKey("volumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_summary = Column(Text, default="", nullable=False)
    image_summary = Column(Text, default="", nullable=False)
    characters_snapshot = Column(JSONB, nullable=True)
    open_threads_snapshot = Column(JSONB, nullable=True)
    glossary_snapshot = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    page = relationship("Page", back_populates="context_snapshot")

    __table_args__ = (
        Index("ix_page_context_volume_created", "volume_id", "created_at"),
    )


class Box(Base):
    __tablename__ = "boxes"

    id = Column(Integer, primary_key=True)
    page_id = Column(Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    box_id = Column(Integer, nullable=False)
    order_index = Column(Integer, nullable=False, default=0)
    type = Column(String, nullable=False, default="text")
    source = Column(String, nullable=False, default="manual")
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("box_detection_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)

    page = relationship("Page", back_populates="boxes")
    detection_run = relationship("BoxDetectionRun", back_populates="boxes")
    text_content = relationship(
        "TextBoxContent",
        back_populates="box",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("page_id", "box_id", name="uq_boxes_page_box"),
        Index("ix_boxes_page_type", "page_id", "type"),
        Index("ix_boxes_page_type_order", "page_id", "type", "order_index"),
        Index("ix_boxes_page_source", "page_id", "source"),
        Index("ix_boxes_run_id", "run_id"),
        CheckConstraint(
            "type IN ('text', 'panel', 'face', 'body')",
            name="ck_boxes_type",
        ),
        CheckConstraint(
            "source IN ('manual', 'detect')",
            name="ck_boxes_source",
        ),
    )


class BoxDetectionRun(Base):
    __tablename__ = "box_detection_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    page_id = Column(Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    task = Column(String, nullable=False)
    model_id = Column(String, nullable=True)
    model_label = Column(String, nullable=True)
    model_version = Column(String, nullable=True)
    model_path = Column(Text, nullable=True)
    model_hash = Column(String, nullable=True)
    params = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    page = relationship("Page", back_populates="box_detection_runs")
    boxes = relationship("Box", back_populates="detection_run")

    __table_args__ = (
        Index("ix_box_detection_runs_page_task", "page_id", "task"),
        CheckConstraint(
            "task IN ('text', 'panel', 'face', 'body')",
            name="ck_box_detection_runs_task",
        ),
    )


class TextBoxContent(Base):
    __tablename__ = "text_box_contents"

    box_id = Column(
        Integer,
        ForeignKey("boxes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ocr_text = Column(Text, default="", nullable=False)
    translation = Column(Text, default="", nullable=False)
    ocr_language = Column(String, nullable=True)
    translation_language = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)

    box = relationship("Box", back_populates="text_content")


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    volume_id = Column(
        String,
        ForeignKey("volumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String, nullable=False, default="Session")
    model_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    volume = relationship("Volume", back_populates="agent_sessions")
    messages = relationship(
        "AgentMessage",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_agent_sessions_volume_created", "volume_id", "created_at"),
    )


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    session = relationship("AgentSession", back_populates="messages")

    __table_args__ = (
        Index("ix_agent_messages_session_created", "session_id", "created_at"),
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="ck_agent_messages_role",
        ),
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True)
    scope = Column(String, nullable=False, default="global")
    key = Column(String, nullable=False)
    value = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("scope", "key", name="uq_app_settings_scope_key"),
        Index("ix_app_settings_scope", "scope"),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id = Column(Integer, primary_key=True)
    job_type = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    request_hash = Column(String, nullable=False)
    resource_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "job_type",
            "idempotency_key",
            name="uq_idempotency_keys_job_type_key",
        ),
        Index("ix_idempotency_keys_created", "created_at"),
    )


class OcrProfileSetting(Base):
    __tablename__ = "ocr_profile_settings"

    profile_id = Column(String, primary_key=True)
    agent_enabled = Column(Boolean, nullable=False, default=True)
    model_id = Column(String, nullable=True)
    max_output_tokens = Column(Integer, nullable=True)
    reasoning_effort = Column(String, nullable=True)
    temperature = Column(Float, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "reasoning_effort IN ('low', 'medium', 'high') OR reasoning_effort IS NULL",
            name="ck_ocr_profile_settings_reasoning_effort",
        ),
        CheckConstraint(
            "max_output_tokens IS NULL OR max_output_tokens >= 1",
            name="ck_ocr_profile_settings_max_output",
        ),
        CheckConstraint(
            "temperature IS NULL OR (temperature >= 0 AND temperature <= 2)",
            name="ck_ocr_profile_settings_temperature",
        ),
    )


class TranslationProfileSetting(Base):
    __tablename__ = "translation_profile_settings"

    profile_id = Column(String, primary_key=True)
    single_box_enabled = Column(Boolean, nullable=False, default=True)
    model_id = Column(String, nullable=True)
    max_output_tokens = Column(Integer, nullable=True)
    reasoning_effort = Column(String, nullable=True)
    temperature = Column(Float, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "reasoning_effort IN ('low', 'medium', 'high') OR reasoning_effort IS NULL",
            name="ck_translation_profile_settings_reasoning_effort",
        ),
        CheckConstraint(
            "max_output_tokens IS NULL OR max_output_tokens >= 1",
            name="ck_translation_profile_settings_max_output",
        ),
        CheckConstraint(
            "temperature IS NULL OR (temperature >= 0 AND temperature <= 2)",
            name="ck_translation_profile_settings_temperature",
        ),
    )


class AgentTranslateSetting(Base):
    __tablename__ = "agent_translate_settings"

    id = Column(Integer, primary_key=True, default=1)
    model_id = Column(String, nullable=False)
    max_output_tokens = Column(Integer, nullable=True)
    reasoning_effort = Column(String, nullable=True)
    temperature = Column(Float, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "reasoning_effort IN ('low', 'medium', 'high') OR reasoning_effort IS NULL",
            name="ck_agent_translate_settings_reasoning_effort",
        ),
        CheckConstraint(
            "max_output_tokens IS NULL OR max_output_tokens >= 1",
            name="ck_agent_translate_settings_max_output",
        ),
        CheckConstraint(
            "temperature IS NULL OR (temperature >= 0 AND temperature <= 2)",
            name="ck_agent_translate_settings_temperature",
        ),
        CheckConstraint("id = 1", name="ck_agent_translate_settings_singleton"),
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_type = Column(String, nullable=False)
    volume_id = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=False, index=True)
    page_revision = Column(String, nullable=True)
    state = Column(String, nullable=False)
    status = Column(String, nullable=False)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    error_message = Column(Text, nullable=True)
    result_json = Column(JSONB, nullable=True)
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    tasks = relationship(
        "TaskRun",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_workflow_runs_type_created", "workflow_type", "created_at"),
        Index("ix_workflow_runs_status_updated", "status", "updated_at"),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'canceled')",
            name="ck_workflow_runs_status",
        ),
    )


class TaskRun(Base):
    __tablename__ = "task_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage = Column(String, nullable=False)
    box_id = Column(Integer, nullable=True)
    profile_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="queued")
    attempt = Column(Integer, nullable=False, default=0)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String, nullable=True)
    error_detail = Column(Text, nullable=True)
    input_json = Column(JSONB, nullable=True)
    result_json = Column(JSONB, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    workflow = relationship("WorkflowRun", back_populates="tasks")
    attempt_events = relationship(
        "TaskAttemptEvent",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_task_runs_workflow_stage", "workflow_id", "stage"),
        Index("ix_task_runs_status_stage", "status", "stage"),
        Index("ix_task_runs_retry", "next_retry_at", "status"),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'timed_out', 'canceled')",
            name="ck_task_runs_status",
        ),
        CheckConstraint("attempt >= 0", name="ck_task_runs_attempt_nonnegative"),
    )


class TaskAttemptEvent(Base):
    __tablename__ = "task_attempt_events"

    id = Column(Integer, primary_key=True)
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("task_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt = Column(Integer, nullable=False)
    tool_name = Column(String, nullable=False)
    model_id = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    params_snapshot = Column(JSONB, nullable=True)
    token_usage = Column(JSONB, nullable=True)
    finish_reason = Column(String, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    task = relationship("TaskRun", back_populates="attempt_events")

    __table_args__ = (
        Index("ix_task_attempt_events_task_attempt", "task_id", "attempt"),
        CheckConstraint("attempt >= 1", name="ck_task_attempt_events_attempt_positive"),
    )


class LlmCallLog(Base):
    __tablename__ = "llm_call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider = Column(String, nullable=False, default="openai")
    api = Column(String, nullable=False)
    component = Column(String, nullable=False, default="unknown")
    status = Column(String, nullable=False, default="success")
    model_id = Column(String, nullable=True)
    job_id = Column(String, nullable=True)
    workflow_run_id = Column(String, nullable=True)
    task_run_id = Column(String, nullable=True)
    attempt = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    finish_reason = Column(String, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    error_detail = Column(Text, nullable=True)
    params_snapshot = Column(JSONB, nullable=True)
    request_excerpt = Column(Text, nullable=True)
    response_excerpt = Column(Text, nullable=True)
    payload_path = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_llm_call_logs_created", "created_at"),
        Index("ix_llm_call_logs_component_created", "component", "created_at"),
        Index("ix_llm_call_logs_status_created", "status", "created_at"),
        Index("ix_llm_call_logs_job_created", "job_id", "created_at"),
        CheckConstraint(
            "status IN ('success', 'error')",
            name="ck_llm_call_logs_status",
        ),
        CheckConstraint(
            "attempt IS NULL OR attempt >= 1",
            name="ck_llm_call_logs_attempt_positive",
        ),
    )


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)


def check_db() -> tuple[bool, str | None]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, str(exc)


@contextmanager
def get_session() -> Iterator:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
