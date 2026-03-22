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
 * Create EventSource for streaming responses
 * Note: EventSource doesn't use the generated client since it needs a URL directly
 */
export function createStreamConnection(sessionId: string, message: string): EventSource {
  const baseUrl = OpenAPI.BASE || '';
  const url = `${baseUrl}/api/v1/langflow/stream/${sessionId}?message=${encodeURIComponent(message)}`;
  return new EventSource(url, { withCredentials: true });
}
