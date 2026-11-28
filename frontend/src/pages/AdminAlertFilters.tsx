import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, Pencil, Pin, Trash2 } from "lucide-react";
import { Button, Dialog } from "@tidemark-security/ux";

import { SavedFilterDialog } from "@/components/entities/SavedQueueFilters";
import { SharedIconPicker } from "@/components/forms/SharedIconPicker";
import { AdminPageLayout } from "@/components/layout/AdminPageLayout";
import { useSession } from "@/contexts/sessionContext";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { invalidateSavedQueueFilters, useSavedQueueFilters } from "@/hooks/useSavedQueueFilters";
import { ApiError } from "@/types/generated/core/ApiError";
import type { SavedFilterRead } from "@/types/generated/models/SavedFilterRead";
import { SavedFiltersService } from "@/types/generated/services/SavedFiltersService";
import { getIconComponent, normalizeLinkTemplateIconName } from "@/utils/iconMapping";
import { alertFilterHref } from "@/utils/savedQueueFilters";

type FilterAction = { kind: "rename" | "delete" | "navigation"; filter: SavedFilterRead };

function NavigationDialog({ filter, userId, onClose }: {
  filter: SavedFilterRead;
  userId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [iconName, setIconName] = useState(() => normalizeLinkTemplateIconName(filter.navigation_icon ?? "Bell"));
  const pinned = Boolean(filter.navigation_icon);
  const mutation = useMutation({
    mutationFn: (icon: string | null) => SavedFiltersService.setSavedFilterNavigation({
      filterId: filter.id,
      requestBody: { icon_name: icon },
    }),
    onSuccess: () => {
      invalidateSavedQueueFilters(queryClient, "alerts", userId);
      onClose();
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!mutation.isPending) mutation.mutate(iconName);
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !mutation.isPending) onClose(); }}>
      <Dialog.Content className="w-[min(28rem,calc(100vw-2rem))] min-w-0 bg-neutral-100 p-5">
        <form onSubmit={submit} className="flex w-full flex-col gap-4">
          <div className="flex flex-col gap-1">
            <Dialog.Title className="text-heading-3 font-heading-3 text-default-font">
              {pinned ? "Edit navigation pin" : "Pin to navigation"}
            </Dialog.Title>
            <Dialog.Description className="break-words text-body font-body text-subtext-color">
              Choose the icon for {filter.name} in your organization’s navigation.
            </Dialog.Description>
          </div>
          <SharedIconPicker value={iconName} onChange={setIconName} />
          {mutation.isError && (
            <p role="alert" className="text-error-color">Couldn’t update the navigation pin. Try again.</p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            {pinned && (
              <Button type="button" variant="neutral-tertiary" disabled={mutation.isPending} onClick={() => mutation.mutate(null)}>
                Unpin
              </Button>
            )}
            <Button type="button" variant="neutral-secondary" disabled={mutation.isPending} onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={mutation.isPending} loading={mutation.isPending}>
              {pinned ? "Save icon" : "Pin to navigation"}
            </Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog>
  );
}

function OrganizationAlertFilters({ userId }: { userId: string }) {
  const queryClient = useQueryClient();
  const savedFilters = useSavedQueueFilters("alerts", userId);
  const [action, setAction] = useState<FilterAction | null>(null);
  const filters = savedFilters.data?.filter(({ scope }) => scope === "organization") ?? [];
  const pinnedFilters = filters
    .filter(({ navigation_icon }) => navigation_icon)
    .sort((left, right) => (left.navigation_position ?? 0) - (right.navigation_position ?? 0));
  const sections = [
    { title: "Pinned filters", filters: pinnedFilters, pinned: true },
    { title: "Unpinned filters", filters: filters.filter(({ navigation_icon }) => !navigation_icon), pinned: false },
  ];
  const reorder = useMutation({
    mutationFn: (filterIds: string[]) => SavedFiltersService.setSavedFilterNavigationOrder({
      requestBody: { filter_ids: filterIds },
    }),
    onSettled: () => invalidateSavedQueueFilters(queryClient, "alerts", userId),
  });

  function movePinnedFilter(index: number, direction: -1 | 1) {
    const nextIndex = index + direction;
    const filterIds = pinnedFilters.map(({ id }) => id);
    [filterIds[index], filterIds[nextIndex]] = [filterIds[nextIndex], filterIds[index]];
    reorder.mutate(filterIds);
  }

  return (
    <>
      {savedFilters.isPending ? (
        <p role="status" className="text-subtext-color">Loading organization alert filters…</p>
      ) : savedFilters.isError ? (
        <div className="flex flex-wrap items-center gap-2">
          <p role="alert" className="text-error-color">Couldn’t load organization alert filters.</p>
          <Button type="button" variant="neutral-secondary" onClick={() => void savedFilters.refetch()}>Try again</Button>
        </div>
      ) : filters.length === 0 ? (
        <p className="text-subtext-color">No organization alert filters yet. Open <Link className="underline" to="/alerts">Alerts</Link> and save a filter with Org-wide visibility.</p>
      ) : (
        <div className="flex w-full flex-col gap-4">
          {reorder.isError && (
            <p role="alert" className="text-error-color">
              {reorder.error instanceof ApiError && reorder.error.status === 409
                ? "The pinned filters changed. Try moving the filter again."
                : "Couldn’t reorder pinned filters. Try again."}
            </p>
          )}
          {sections.filter((section) => section.filters.length > 0).map((section) => (
            <section key={section.title} className="flex w-full flex-col gap-2">
              <h2 className="text-heading-3 font-heading-3 text-default-font">{section.title}</h2>
              <ul aria-label={section.title} className="w-full divide-y divide-neutral-border rounded-md border border-neutral-border bg-default-background">
                {section.filters.map((filter, index) => (
                  <li key={filter.id} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 p-4">
                    <Link className="flex min-w-0 items-center gap-2 break-words text-body-bold font-body-bold text-default-font hover:underline" to={alertFilterHref(filter)}>
                      {filter.navigation_icon && (
                        <span aria-hidden="true" className="shrink-0 text-subtext-color">{getIconComponent(filter.navigation_icon)}</span>
                      )}
                      <span className="min-w-0">{filter.name}</span>
                    </Link>
                    <div className="flex flex-wrap gap-1">
                      {section.pinned && (
                        <>
                          <Button
                            aria-label={`Move ${filter.name} up`}
                            title="Move up"
                            size="small"
                            variant="neutral-tertiary"
                            icon={<ArrowUp />}
                            disabled={reorder.isPending || index === 0}
                            onClick={() => movePinnedFilter(index, -1)}
                          />
                          <Button
                            aria-label={`Move ${filter.name} down`}
                            title="Move down"
                            size="small"
                            variant="neutral-tertiary"
                            icon={<ArrowDown />}
                            disabled={reorder.isPending || index === section.filters.length - 1}
                            onClick={() => movePinnedFilter(index, 1)}
                          />
                        </>
                      )}
                      <Button
                        aria-label={section.pinned ? `Edit pin for ${filter.name}` : `Pin ${filter.name}`}
                        variant="neutral-secondary"
                        size="small"
                        icon={<Pin />}
                        onClick={() => setAction({ kind: "navigation", filter })}
                      >
                        {section.pinned ? "Edit pin" : "Pin"}
                      </Button>
                      <Button aria-label={`Rename ${filter.name}`} size="small" variant="neutral-tertiary" icon={<Pencil />} onClick={() => setAction({ kind: "rename", filter })} />
                      <Button aria-label={`Delete ${filter.name}`} size="small" variant="neutral-tertiary" icon={<Trash2 />} onClick={() => setAction({ kind: "delete", filter })} />
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      {action?.kind === "navigation" && (
        <NavigationDialog filter={action.filter} userId={userId} onClose={() => setAction(null)} />
      )}
      {action && (action.kind === "rename" || action.kind === "delete") && (
        <SavedFilterDialog action={{ kind: action.kind, filter: action.filter }} queue="alerts" userId={userId} isAdmin onClose={() => setAction(null)} />
      )}
    </>
  );
}

export default function AdminAlertFilters() {
  useDocumentTitle("Organization alert filters");
  const { user } = useSession();

  return (
    <AdminPageLayout title="Organization alert filters" subtitle="Manage shared filters and choose which appear in navigation.">
      {user?.role === "ADMIN" && <OrganizationAlertFilters userId={user.id} />}
    </AdminPageLayout>
  );
}
