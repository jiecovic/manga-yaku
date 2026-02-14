# backend-python/infra/db/db.py
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
