import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { QUERY_STALE_TIMES } from '@/config/queryConfig';
import type { AttachmentLimitsRead } from '@/types/generated/models/AttachmentLimitsRead';
import { SettingsService } from '@/types/generated/services/SettingsService';

const DEFAULT_ATTACHMENT_LIMITS: AttachmentLimitsRead = {
  max_upload_size_mb: 50,
  max_upload_size_bytes: 50 * 1024 * 1024,
  max_image_preview_size_mb: 5,
  max_image_preview_size_bytes: 5 * 1024 * 1024,
  max_text_preview_size_mb: 1,
  max_text_preview_size_bytes: 1 * 1024 * 1024,
};

const ATTACHMENT_LIMITS_QUERY_KEY = ['settings', 'attachment-limits'] as const;

export function useAttachmentLimits(): UseQueryResult<AttachmentLimitsRead, Error> & {
  limits: AttachmentLimitsRead;
} {
  const query = useQuery({
    queryKey: ATTACHMENT_LIMITS_QUERY_KEY,
    queryFn: () => SettingsService.getAttachmentLimitsSettingsApiV1SettingsAttachmentLimitsGet(),
    staleTime: QUERY_STALE_TIMES.STATIC,
  });

  return {
    ...query,
    limits: query.data ?? DEFAULT_ATTACHMENT_LIMITS,
  };
}