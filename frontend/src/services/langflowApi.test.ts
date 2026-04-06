import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OpenAPI } from '@/types/generated/core/OpenAPI';

import { streamMessage } from './langflowApi';


function createSseResponse(events: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) {
        controller.enqueue(encoder.encode(event));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}


describe('langflowApi.streamMessage', () => {
  beforeEach(() => {
    OpenAPI.BASE = 'http://localhost:8000';
    document.cookie = 'XSRF-TOKEN=test-csrf-token; path=/';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = 'XSRF-TOKEN=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  });

  it('posts the stream request with CSRF headers and parses SSE events', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      createSseResponse([
        'event: connected\ndata: {"session_id":"session-1"}\n\n',
        'event: message\ndata: {"content":"Hello","partial":true}\n\n',
        'event: complete\ndata: {"message_id":"msg-1","content":"Hello world"}\n\n',
        'event: complete\ndata: {"session_id":"session-1","status":"completed"}\n\n',
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    const onConnected = vi.fn();
    const onMessage = vi.fn();
    const onComplete = vi.fn();

    await streamMessage(
      'session-1',
      { message: 'hello stream' },
      { onConnected, onMessage, onComplete },
    );

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/langflow/stream/session-1',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-XSRF-TOKEN': 'test-csrf-token',
        }),
      }),
    );
    expect(onConnected).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledWith({ content: 'Hello', partial: true });
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith({ message_id: 'msg-1', content: 'Hello world' });
  });
});