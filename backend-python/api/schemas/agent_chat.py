# backend-python/api/schemas/agent_chat.py
"""Request/response schemas for chat-style agent session endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class AgentModelCapabilityPublic(BaseModel):
    """Effective tuning controls for one chat model option."""

    appliesTemperature: bool
    appliesReasoningEffort: bool
    temperatureSupport: str
    notes: list[str] = []


class AgentSessionPublic(BaseModel):
    """Public session metadata returned by agent session endpoints."""

    id: str
    volumeId: str
    title: str
    modelId: str | None = None
    createdAt: str
    updatedAt: str


class CreateAgentSessionRequest(BaseModel):
    """Payload to create a new chat agent session for a volume."""

    volumeId: str
    title: str | None = None
    modelId: str | None = None


class UpdateAgentSessionRequest(BaseModel):
    """Patch payload for editable session metadata."""

    title: str | None = None
    modelId: str | None = None


class AgentMessagePublic(BaseModel):
    """Public message record associated with an agent session."""

    id: int
    sessionId: str
    role: str
    content: str
    createdAt: str
    meta: dict | None = None


class CreateAgentMessageRequest(BaseModel):
    """Payload to append a user/tool/system message to a session."""

    role: str = "user"
    content: str


class AgentReplyRequest(BaseModel):
    """Request options for generating one assistant reply."""

    maxMessages: int = 20
    currentFilename: str | None = None


class AgentModelPublic(BaseModel):
    """Agent model option exposed to the frontend."""

    id: str
    label: str
    capability: AgentModelCapabilityPublic


class AgentConfigResponse(BaseModel):
    """Config payload used to initialize the chat agent UI."""

    models: list[AgentModelPublic]
    defaultModel: str
    maxMessageChars: int
