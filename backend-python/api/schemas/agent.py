# backend-python/api/schemas/agent.py
from __future__ import annotations

from pydantic import BaseModel


class AgentSessionPublic(BaseModel):
    id: str
    volumeId: str
    title: str
    modelId: str | None = None
    createdAt: str
    updatedAt: str


class CreateAgentSessionRequest(BaseModel):
    volumeId: str
    title: str | None = None
    modelId: str | None = None


class UpdateAgentSessionRequest(BaseModel):
    title: str | None = None
    modelId: str | None = None


class AgentMessagePublic(BaseModel):
    id: int
    sessionId: str
    role: str
    content: str
    createdAt: str
    meta: dict | None = None


class CreateAgentMessageRequest(BaseModel):
    role: str = "user"
    content: str


class AgentReplyRequest(BaseModel):
    maxMessages: int = 20


class AgentModelPublic(BaseModel):
    id: str
    label: str


class AgentConfigResponse(BaseModel):
    models: list[AgentModelPublic]
    defaultModel: str
    maxMessageChars: int
