import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  generateTaskUploadUrl,
  updateTaskAttachmentStatus,
  generateAlertUploadUrl,
  generateCaseUploadUrl,
} = vi.hoisted(() => ({
  generateTaskUploadUrl: vi.fn(),
  updateTaskAttachmentStatus: vi.fn(),
  generateAlertUploadUrl: vi.fn(),
  generateCaseUploadUrl: vi.fn(),
}));

vi.mock('@/types/generated/services/AlertsService', () => ({
  AlertsService: {
    generateUploadUrlApiV1AlertsAlertIdTimelineAttachmentsUploadUrlPost: generateAlertUploadUrl,
    updateAttachmentStatusApiV1AlertsAlertIdTimelineItemsItemIdStatusPatch: vi.fn(),
  },
}));

vi.mock('@/types/generated/services/CasesService', () => ({
  CasesService: {
    generateUploadUrlApiV1CasesCaseIdTimelineAttachmentsUploadUrlPost: generateCaseUploadUrl,
    updateAttachmentStatusApiV1CasesCaseIdTimelineItemsItemIdStatusPatch: vi.fn(),
  },
}));

vi.mock('@/types/generated/services/TasksService', () => ({
  TasksService: {
    generateUploadUrlApiV1TasksTaskIdTimelineAttachmentsUploadUrlPost: generateTaskUploadUrl,
    updateAttachmentStatusApiV1TasksTaskIdTimelineItemsItemIdStatusPatch: updateTaskAttachmentStatus,
  },
}));

import { useFileUpload } from './useFileUpload';

class MockXMLHttpRequest {
  static lastInstance: MockXMLHttpRequest | null = null;

  public status = 200;
  public upload = {
    addEventListener: vi.fn((event: string, handler: (payload: ProgressEvent) => void) => {
      if (event === 'progress') {
        this.progressHandler = handler;
      }
    }),
  };

  private loadHandler?: () => void;
  private errorHandler?: () => void;
  private abortHandler?: () => void;
  private progressHandler?: (payload: ProgressEvent) => void;

  constructor() {
    MockXMLHttpRequest.lastInstance = this;
  }

  addEventListener(event: string, handler: () => void) {
    if (event === 'load') {
      this.loadHandler = handler;
    } else if (event === 'error') {
      this.errorHandler = handler;
    } else if (event === 'abort') {
      this.abortHandler = handler;
    }
  }

  open() {}

  setRequestHeader() {}

  send() {
    this.progressHandler?.({
      lengthComputable: true,
      loaded: 3,
      total: 3,
    } as ProgressEvent);
    this.loadHandler?.();
  }
}

describe('useFileUpload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    generateTaskUploadUrl.mockResolvedValue({
      item_id: 'attachment-1',
      upload_url: 'https://uploads.example.test/presigned',
      storage_key: 'tasks/42/attachment-1/report.txt',
      expires_at: '2026-01-01T00:00:00Z',
      max_file_size: 1024,
    });
    updateTaskAttachmentStatus.mockResolvedValue({
      id: 42,
      title: 'Task',
      description: 'Task description',
      status: 'OPEN',
      priority: 'MEDIUM',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      created_by: 'analyst',
      assignee: 'analyst',
      timeline_items: [],
      tags: [],
      audit_logs: [],
      human_id: 'TSK-0000042',
    });
    generateAlertUploadUrl.mockResolvedValue(undefined);
    generateCaseUploadUrl.mockResolvedValue(undefined);

    vi.stubGlobal('XMLHttpRequest', MockXMLHttpRequest);
    vi.stubGlobal('crypto', {
      subtle: {
        digest: vi.fn().mockResolvedValue(new Uint8Array([1, 2, 3, 4]).buffer),
      },
    });
  });

  it('uses task attachment endpoints when taskId is provided', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useFileUpload({ taskId: 42 }), { wrapper });
    const file = new File(['abc'], 'report.txt', { type: 'text/plain' });
    Object.defineProperty(file, 'arrayBuffer', {
      value: vi.fn().mockResolvedValue(new Uint8Array([97, 98, 99]).buffer),
    });

    await act(async () => {
      await result.current.uploadFile(file);
    });

    expect(generateTaskUploadUrl).toHaveBeenCalledWith({
      taskId: 42,
      requestBody: {
        filename: 'report.txt',
        file_size: 3,
        mime_type: 'text/plain',
      },
    });
    expect(updateTaskAttachmentStatus).toHaveBeenCalledWith({
      taskId: 42,
      itemId: 'attachment-1',
      requestBody: {
        status: 'COMPLETE',
        file_hash: '01020304',
      },
    });
    expect(generateAlertUploadUrl).not.toHaveBeenCalled();
    expect(generateCaseUploadUrl).not.toHaveBeenCalled();
    expect(result.current.itemId).toBe('attachment-1');
    expect(result.current.error).toBeNull();
  });
});