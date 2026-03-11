// src/api/agent.ts
import type { AgentMessage, AgentModel, AgentSession } from '../types';
import { API_BASE, apiFetch } from './client';

export interface CreateAgentSessionRequest {
  volumeId: string;
  title?: string;
  modelId?: string;
}

export interface CreateAgentMessageRequest {
  role?: string;
  content: string;
}

export interface UpdateAgentSessionRequest {
  title?: string;
  modelId?: string;
}

export interface AgentReplyRequest {
  maxMessages?: number;
  currentFilename?: string;
}

export interface AgentConfigResponse {
  models: AgentModel[];
  defaultModel: string;
  maxMessageChars: number;
}

export async function fetchAgentConfig(): Promise<AgentConfigResponse> {
  const res = await apiFetch(`${API_BASE}/api/agent/config`, {
    headers: { Accept: 'application/json' },
  });

  return res.json() as Promise<AgentConfigResponse>;
}

export async function fetchAgentSessions(volumeId: string): Promise<AgentSession[]> {
  const res = await apiFetch(
    `${API_BASE}/api/agent/sessions?volumeId=${encodeURIComponent(volumeId)}`,
    {
      headers: { Accept: 'application/json' },
    },
  );

  return res.json() as Promise<AgentSession[]>;
}

export async function createAgentSession(
  payload: CreateAgentSessionRequest,
): Promise<AgentSession> {
  const res = await apiFetch(`${API_BASE}/api/agent/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  return res.json() as Promise<AgentSession>;
}

export async function updateAgentSession(
  sessionId: string,
  payload: UpdateAgentSessionRequest,
): Promise<AgentSession> {
  const res = await apiFetch(`${API_BASE}/api/agent/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  return res.json() as Promise<AgentSession>;
}

export async function deleteAgentSession(sessionId: string): Promise<void> {
  await apiFetch(`${API_BASE}/api/agent/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
}

export async function fetchAgentMessages(sessionId: string): Promise<AgentMessage[]> {
  const res = await apiFetch(
    `${API_BASE}/api/agent/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      headers: { Accept: 'application/json' },
    },
  );

  return res.json() as Promise<AgentMessage[]>;
}

export async function createAgentMessage(
  sessionId: string,
  payload: CreateAgentMessageRequest,
): Promise<AgentMessage> {
  const res = await apiFetch(
    `${API_BASE}/api/agent/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
    },
  );

  return res.json() as Promise<AgentMessage>;
}

export async function requestAgentReply(
  sessionId: string,
  payload: AgentReplyRequest = {},
): Promise<AgentMessage> {
  const res = await apiFetch(
    `${API_BASE}/api/agent/sessions/${encodeURIComponent(sessionId)}/reply`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
    },
  );

  return res.json() as Promise<AgentMessage>;
}
