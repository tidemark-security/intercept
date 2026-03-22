import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { AdminService } from '@/types/generated/services/AdminService';
import type { app__api__routes__admin_auth__UserSummary } from '@/types/generated/models/app__api__routes__admin_auth__UserSummary';
import type { UserStatus } from '@/types/generated/models/UserStatus';
import type { UserRole } from '@/types/generated/models/UserRole';

interface UseUsersOptions {
  userStatus?: UserStatus | null;
  role?: UserRole | null;
}

/**
 * Hook to fetch users from the API using TanStack Query
 * Provides user list for assignee dropdowns and filtering
 * Caches results for 30 minutes to minimize API calls
 */
export function useUsers(
  options: UseUsersOptions = {}
): UseQueryResult<app__api__routes__admin_auth__UserSummary[], Error> {
  const {
    userStatus = 'ACTIVE' as UserStatus,
    role = null,
  } = options;

  return useQuery({
    queryKey: ['users', { status: userStatus, role }],
    queryFn: () =>
      AdminService.getUsersSummaryApiV1AdminAuthUsersSummaryGet({
        userStatus,
        role,
      }),
    staleTime: 30 * 60 * 1000, // 30 minutes
  });
}
