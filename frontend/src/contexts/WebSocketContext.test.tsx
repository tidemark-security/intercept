import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { mockSession, showToast } = vi.hoisted(() => ({
  mockSession: {
    status: 'authenticated',
    user: { username: 'glenn' },
  },
  showToast: vi.fn(),
}));

vi.mock('./sessionContext', () => ({
  useSession: () => mockSession,
}));

vi.mock('./ToastContext', () => ({
  useToast: () => ({ showToast }),
}));

vi.mock('@/types/generated/core/OpenAPI', () => ({
  OpenAPI: { BASE: 'http://localhost:8000' },
}));

import { queryKeys } from '@/hooks/queryKeys';
import { usePresence, useWebSocket, WebSocketProvider } from './WebSocketContext';

type MockMessage = { data: string };

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CONNECTING = 0;

  readyState = MockWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: MockMessage) => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }

  send(message: string) {
    this.sent.push(message);
  }

  close() {
    this.readyState = 3;
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  receive(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

function createWrappedUi(children: React.ReactNode, queryClient?: QueryClient) {
  const client = queryClient ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <WebSocketProvider>
        {children}
      </WebSocketProvider>
    </QueryClientProvider>
  );
}

function CaseSubscription() {
  const { subscribe, unsubscribe } = useWebSocket();

  React.useEffect(() => {
    subscribe('case', 12);
    return () => unsubscribe('case', 12);
  }, [subscribe, unsubscribe]);

  return <div />;
}

function PresenceProbe() {
  const viewers = usePresence('case', 12);
  return <div data-testid="presence">{viewers.join(',')}</div>;
}

describe('WebSocketProvider', () => {
  const originalWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    MockWebSocket.instances = [];
    (globalThis as any).WebSocket = MockWebSocket;
    mockSession.status = 'authenticated';
    mockSession.user = { username: 'glenn' };
    showToast.mockClear();
  });

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket;
    vi.restoreAllMocks();
  });

  it('invalidates only graph query for timeline_graph_updated events', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    render(createWrappedUi(<div />, queryClient));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    act(() => {
      MockWebSocket.instances[0].open();
      MockWebSocket.instances[0].receive({
        type: 'event',
        payload: {
          entity_type: 'case',
          entity_id: 12,
          event_type: 'timeline_graph_updated',
        },
      });
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: queryKeys.case.graphBase(12),
        exact: false,
      });
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: queryKeys.case.detailBase(12),
      exact: false,
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: queryKeys.case.listBase(),
      exact: false,
    });
  });

  it('shows a toast for subscribed timeline events from another user', async () => {
    render(createWrappedUi(<CaseSubscription />));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    act(() => {
      MockWebSocket.instances[0].open();
      MockWebSocket.instances[0].receive({
        type: 'event',
        payload: {
          entity_type: 'case',
          entity_id: 12,
          event_type: 'timeline_item_added',
          performed_by: 'Alex',
          item_type: 'note',
        },
      });
    });

    expect(showToast).toHaveBeenCalledWith('Alex added a note', undefined, 'neutral');
  });

  it('does not show a toast for the current user events', async () => {
    render(createWrappedUi(<CaseSubscription />));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    act(() => {
      MockWebSocket.instances[0].open();
      MockWebSocket.instances[0].receive({
        type: 'event',
        payload: {
          entity_type: 'case',
          entity_id: 12,
          event_type: 'timeline_item_added',
          performed_by: 'Glenn',
          item_type: 'note',
        },
      });
    });

    expect(showToast).not.toHaveBeenCalled();
  });

  it('stores presence viewers by subscribed entity', async () => {
    render(createWrappedUi(<PresenceProbe />));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    act(() => {
      MockWebSocket.instances[0].open();
      MockWebSocket.instances[0].receive({
        type: 'presence',
        payload: {
          entity_type: 'case',
          entity_id: 12,
          viewers: ['Alex', 'Glenn'],
        },
      });
    });

    expect(screen.getByTestId('presence')).toHaveTextContent('Alex,Glenn');
  });
});