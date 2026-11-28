import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useSession } from "@/contexts/sessionContext";
import type { DashboardEvaluate } from "@/types/generated/models/DashboardEvaluate";
import type { CancelablePromise } from "@/types/generated/core/CancelablePromise";
import { CustomDashboardsService as api } from "@/types/generated/services/CustomDashboardsService";

async function request<T>(pending: CancelablePromise<T>, signal: AbortSignal): Promise<T> {
  const cancel = () => pending.cancel();
  if (signal.aborted) cancel();
  else signal.addEventListener("abort", cancel, { once: true });
  try {
    return await pending;
  } finally {
    signal.removeEventListener("abort", cancel);
  }
}

export function useDashboardKeys() {
  const { session } = useSession();
  const key = ["custom-dashboards", session?.sessionId];
  return { list: [...key, "list"], catalog: [...key, "catalog"], detail: (id: string) => [...key, "detail", id], key };
}

export function useDashboardList() {
  const keys = useDashboardKeys();
  return useQuery({
    queryKey: keys.list,
    queryFn: ({ signal }) => request(api.listCustomDashboards(), signal),
  });
}

export function useDashboardDetail(id: string) {
  const keys = useDashboardKeys();
  return useQuery({
    queryKey: keys.detail(id),
    queryFn: ({ signal }) => request(api.getCustomDashboard({ identifier: id }), signal),
    retry: false,
  });
}

export function useDashboardCatalog() {
  const keys = useDashboardKeys();
  return useQuery({
    queryKey: keys.catalog,
    queryFn: ({ signal }) => request(api.getDashboardCatalog(), signal),
    staleTime: 5 * 60 * 1000,
  });
}

export function useDashboardEvaluation(payload: DashboardEvaluate) {
  const [debounced, setDebounced] = useState(payload);
  const keys = useDashboardKeys();
  useEffect(() => {
    const timeout = window.setTimeout(() => setDebounced(payload), 350);
    return () => window.clearTimeout(timeout);
  }, [payload]);
  const query = useQuery({
    queryKey: [...keys.key, "evaluate", debounced],
    queryFn: async ({ signal }) => ({
      response: await request(api.evaluateCustomDashboard({ requestBody: debounced }), signal),
      request: debounced,
    }),
    enabled: (debounced.definition.widgets?.length ?? 0) > 0,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    gcTime: 30_000,
    retry: false,
  });
  return { ...query, pendingEdit: payload !== debounced };
}

export function useDashboardRecords(reference: string, page: number) {
  const keys = useDashboardKeys();
  return useQuery({
    queryKey: [...keys.key, "records", reference, page],
    queryFn: ({ signal }) => request(api.getDashboardRecords({ requestBody: { reference, page } }), signal),
    retry: false,
    gcTime: 0,
  });
}
