/**
 * LangFlow API Client
 * 
 * Provides type-safe interface to LangFlow backend endpoints using
 * the generated OpenAPI client.
 */

import { LangflowService } from '../types/generated/services/LangflowService';
import { OpenAPI } from '../types/generated/core/OpenAPI';
import type { 
  LangFlowSessionRead, 
  LangFlowMessageRead,
  LangFlowSessionCreate,
  LangFlowSessionUpdate,
  ChatRequest as GeneratedChatRequest,
  ChatResponse as GeneratedChatResponse,
} from '../types/generated';

// Re-export types for backwards compatibility
export type LangFlowSession = LangFlowSessionRead;
export type LangFlowMessage = LangFlowMessageRead;
export type CreateSessionRequest = LangFlowSessionCreate;
export type UpdateSessionRequest = LangFlowSessionUpdate;
export type ChatRequest = GeneratedChatRequest;
export type ChatResponse = GeneratedChatResponse;

interface StreamMessagePayload {
  message: string;
  context?: Record<string, unknown>;
}

interface StreamMessageHandlers {
  onConnected?: () => void;
  onMessage?: (data: { content: string; partial?: boolean; timestamp?: string }) => void;
  onComplete?: (data: { message_id?: string; content?: string; partial?: boolean }) => void;
  signal?: AbortSignal;
}

function getCookieValue(name: string): string | null {
  if (typeof document === 'undefined') {
    return null;
  }

  const cookie = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${name}=`));

  return cookie ? decodeURIComponent(cookie.slice(name.length + 1)) : null;
}

async function getErrorMessage(response: Response): Promise<string> {
  const text = await response.text();

  try {
    const payload = JSON.parse(text);
    if (payload && typeof payload === 'object') {
      const detail = 'detail' in payload ? payload.detail : undefined;
      if (detail && typeof detail === 'object' && detail && 'message' in detail && typeof detail.message === 'string') {
        return detail.message;
      }
      if ('message' in payload && typeof payload.message === 'string') {
        return payload.message;
      }
    }
  } catch {
    // Ignore JSON parsing failures and fall back to the response text.
  }

  return text || `Request failed with status ${response.status}`;
}

function dispatchStreamEvent(rawEvent: string, handlers: StreamMessageHandlers): void {
  let eventName = 'message';
  const dataLines: string[] = [];

  for (const line of rawEvent.split('\n')) {
    if (!line || line.startsWith(':')) {
      continue;
    }
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim();
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return;
  }

  const rawData = dataLines.join('\n');
  let parsedData: unknown = rawData;
  try {
    parsedData = JSON.parse(rawData);
  } catch {
    parsedData = rawData;
  }

  if (eventName === 'connected') {
    handlers.onConnected?.();
    return;
  }

  if (eventName === 'message') {
    handlers.onMessage?.((parsedData ?? {}) as { content: string; partial?: boolean; timestamp?: string });
    return;
  }

  if (eventName === 'error') {
    const errorMessage =
      typeof parsedData === 'object' && parsedData && 'error' in parsedData && typeof parsedData.error === 'string'
        ? parsedData.error
        : 'An error occurred while processing your message';
    throw new Error(errorMessage);
  }

  if (eventName === 'complete') {
    if (
      typeof parsedData === 'object' &&
      parsedData &&
      !('message_id' in parsedData) &&
      !('content' in parsedData)
    ) {
      return;
    }
    handlers.onComplete?.((parsedData ?? {}) as { message_id?: string; content?: string; partial?: boolean });
  }
}

/**
 * List all chat sessions for the current user
 */
export async function listSessions(
  skip?: number,
  limit?: number,
  username?: string,
): Promise<LangFlowSession[]> {
  return LangflowService.listSessionsApiV1LangflowSessionsGet({
    skip,
    limit,
    username,
  });
}

/**
 * Create a new LangFlow chat session
 */
export async function createSession(data: CreateSessionRequest): Promise<LangFlowSession> {
  return LangflowService.createSessionApiV1LangflowSessionsPost({
    requestBody: data,
  });
}

/**
 * Get session details
 */
export async function getSession(sessionId: string, username?: string): Promise<LangFlowSession> {
  return LangflowService.getSessionApiV1LangflowSessionsSessionIdGet({
    sessionId,
    username,
  });
}

/**
 * Update a session (title, context, or status)
 */
export async function updateSession(sessionId: string, data: UpdateSessionRequest): Promise<LangFlowSession> {
  return LangflowService.updateSessionApiV1LangflowSessionsSessionIdPatch({
    sessionId,
    requestBody: data,
  });
}

/**
 * Delete a chat session and all its messages
 */
export async function deleteSession(sessionId: string): Promise<void> {
  return LangflowService.deleteSessionApiV1LangflowSessionsSessionIdDelete({
    sessionId,
  });
}

/**
 * Get message history for a session
 */
export async function getMessages(sessionId: string, username?: string): Promise<LangFlowMessage[]> {
  return LangflowService.getSessionMessagesApiV1LangflowSessionsSessionIdMessagesGet({
    sessionId,
    username,
  });
}

/**
 * Send a chat message (non-streaming)
 */
export async function sendMessage(data: ChatRequest): Promise<ChatResponse> {
  return LangflowService.sendChatMessageApiV1LangflowChatPost({
    requestBody: data,
  });
}

/**
 * Stream a LangFlow response via POST + SSE over fetch.
 */
export async function streamMessage(
  sessionId: string,
  payload: StreamMessagePayload,
  handlers: StreamMessageHandlers = {},
): Promise<void> {
  const baseUrl = OpenAPI.BASE || '';
  const url = `${baseUrl}/api/v1/langflow/stream/${sessionId}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  const csrfToken = getCookieValue('XSRF-TOKEN');
  if (csrfToken) {
    headers['X-XSRF-TOKEN'] = csrfToken;
  }

  const response = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers,
    body: JSON.stringify(payload),
    signal: handlers.signal,
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  if (!response.body) {
    throw new Error('Streaming response body is unavailable');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

    let separatorIndex = buffer.indexOf('\n\n');
    while (separatorIndex !== -1) {
      const rawEvent = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      dispatchStreamEvent(rawEvent, handlers);
      separatorIndex = buffer.indexOf('\n\n');
    }

    if (done) {
      break;
    }
  }
}
