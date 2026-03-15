import { AlertsService } from '@/types/generated/services/AlertsService';
import { CasesService } from '@/types/generated/services/CasesService';
import { TasksService } from '@/types/generated/services/TasksService';
import { OpenAPI } from '@/types/generated/core/OpenAPI';

export type AttachmentEntityType = 'alert' | 'case' | 'task';

export interface AttachmentDownloadDetails {
  downloadUrl: string;
  filename: string;
  mimeType: string;
  fileSize: number;
  expiresAt: string;
}

interface AttachmentDownloadOptions {
  download?: boolean;
}

const getApiBase = (): string => {
  return OpenAPI.BASE || window.location.origin;
};

const getAttachmentDownloadPath = (
  entityType: AttachmentEntityType,
  entityId: number,
  itemId: string,
  download: boolean
): string => {
  const encodedItemId = encodeURIComponent(itemId);
  const query = download ? '?download=true' : '';

  if (entityType === 'case') {
    return `/api/v1/cases/${entityId}/timeline/items/${encodedItemId}/download-url${query}`;
  }

  if (entityType === 'task') {
    return `/api/v1/tasks/${entityId}/timeline/items/${encodedItemId}/download-url${query}`;
  }

  return `/api/v1/alerts/${entityId}/timeline/items/${encodedItemId}/download-url${query}`;
};

async function fetchAttachmentDownloadDetails(
  entityType: AttachmentEntityType,
  entityId: number,
  itemId: string,
  download: boolean
): Promise<AttachmentDownloadDetails> {
  const response = await fetch(`${getApiBase()}${getAttachmentDownloadPath(entityType, entityId, itemId, download)}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to generate attachment download URL (${response.status})`);
  }

  const payload = (await response.json()) as {
    download_url: string;
    filename: string;
    mime_type: string;
    file_size: number;
    expires_at: string;
  };

  return {
    downloadUrl: payload.download_url,
    filename: payload.filename,
    mimeType: payload.mime_type,
    fileSize: payload.file_size,
    expiresAt: payload.expires_at,
  };
}

export async function getAttachmentDownloadDetails(
  entityType: AttachmentEntityType,
  entityId: number,
  itemId: string,
  options: AttachmentDownloadOptions = {}
): Promise<AttachmentDownloadDetails> {
  const { download = false } = options;

  if (download) {
    return fetchAttachmentDownloadDetails(entityType, entityId, itemId, true);
  }

  if (entityType === 'case') {
    const response = await CasesService.generateDownloadUrlApiV1CasesCaseIdTimelineItemsItemIdDownloadUrlGet({
      caseId: entityId,
      itemId,
    });

    return {
      downloadUrl: response.download_url,
      filename: response.filename,
      mimeType: response.mime_type,
      fileSize: response.file_size,
      expiresAt: response.expires_at,
    };
  }

  if (entityType === 'task') {
    const response = await TasksService.generateDownloadUrlApiV1TasksTaskIdTimelineItemsItemIdDownloadUrlGet({
      taskId: entityId,
      itemId,
    });

    return {
      downloadUrl: response.download_url,
      filename: response.filename,
      mimeType: response.mime_type,
      fileSize: response.file_size,
      expiresAt: response.expires_at,
    };
  }

  const response = await AlertsService.generateDownloadUrlApiV1AlertsAlertIdTimelineItemsItemIdDownloadUrlGet({
    alertId: entityId,
    itemId,
  });

  return {
    downloadUrl: response.download_url,
    filename: response.filename,
    mimeType: response.mime_type,
    fileSize: response.file_size,
    expiresAt: response.expires_at,
  };
}

export function triggerBrowserDownload(url: string, filename: string) {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}