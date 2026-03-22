import { useQuery, useMutation, useQueryClient, type UseQueryResult, type UseMutationResult } from '@tanstack/react-query';
import { AdminService } from '@/types/generated/services/AdminService';
import type { AppSettingRead } from '@/types/generated/models/AppSettingRead';
import type { AppSettingCreate } from '@/types/generated/models/AppSettingCreate';
import type { AppSettingUpdate } from '@/types/generated/models/AppSettingUpdate';
import { QUERY_STALE_TIMES } from '@/config/queryConfig';

const SETTINGS_QUERY_KEY = ['admin', 'settings'] as const;

/**
 * Hook to fetch all application settings.
 */
export function useSettings(
  category?: string | null
): UseQueryResult<AppSettingRead[], Error> {
  return useQuery({
    queryKey: category ? [...SETTINGS_QUERY_KEY, { category }] : [...SETTINGS_QUERY_KEY],
    queryFn: () =>
      AdminService.getAllSettingsApiV1AdminSettingsGet({
        category: category ?? undefined,
      }),
    staleTime: QUERY_STALE_TIMES.STATIC,
  });
}

/**
 * Hook to update an existing setting.
 */
export function useUpdateSetting(): UseMutationResult<
  AppSettingRead,
  Error,
  { key: string; value: string; description?: string | null }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value, description }) =>
      AdminService.updateSettingApiV1AdminSettingsKeyPut({
        key,
        requestBody: { value, description: description ?? null } as AppSettingUpdate,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY });
    },
  });
}

/**
 * Hook to create a new setting.
 */
export function useCreateSetting(): UseMutationResult<
  AppSettingRead,
  Error,
  AppSettingCreate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data) =>
      AdminService.createSettingApiV1AdminSettingsPost({ requestBody: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY });
    },
  });
}
