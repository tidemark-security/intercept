import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Pencil, Pin, Trash2 } from "lucide-react";
import { Button, Dialog } from "@tidemark-security/ux";

import { SavedFilterDialog } from "@/components/entities/SavedQueueFilters";
import { SharedIconPicker } from "@/components/forms/SharedIconPicker";
import { AdminPageLayout } from "@/components/layout/AdminPageLayout";
import { useSession } from "@/contexts/sessionContext";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { invalidateSavedQueueFilters, useSavedQueueFilters } from "@/hooks/useSavedQueueFilters";
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
  const savedFilters = useSavedQueueFilters("alerts", userId);
  const [action, setAction] = useState<FilterAction | null>(null);
  const filters = savedFilters.data?.filter(({ scope }) => scope === "organization") ?? [];

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
        <ul aria-label="Organization alert filters" className="w-full divide-y divide-neutral-border rounded-md border border-neutral-border bg-default-background">
          {filters.map((filter) => (
            <li key={filter.id} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 p-4">
              <div className="flex min-w-0 flex-col gap-1">
                <Link className="break-words text-body-bold font-body-bold text-default-font hover:underline" to={alertFilterHref(filter)}>
                  {filter.name}
                </Link>
                {filter.navigation_icon && (
                  <span className="flex items-center gap-2 text-caption font-caption text-subtext-color">
                    <span aria-hidden="true">{getIconComponent(filter.navigation_icon)}</span>
                    Pinned to navigation
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-1">
                <Button
                  aria-label={filter.navigation_icon ? `Edit pin for ${filter.name}` : `Pin ${filter.name}`}
                  variant="neutral-secondary"
                  size="small"
                  icon={<Pin />}
                  onClick={() => setAction({ kind: "navigation", filter })}
                >
                  {filter.navigation_icon ? "Edit pin" : "Pin"}
                </Button>
                <Button aria-label={`Rename ${filter.name}`} size="small" variant="neutral-tertiary" icon={<Pencil />} onClick={() => setAction({ kind: "rename", filter })} />
                <Button aria-label={`Delete ${filter.name}`} size="small" variant="neutral-tertiary" icon={<Trash2 />} onClick={() => setAction({ kind: "delete", filter })} />
              </div>
            </li>
          ))}
        </ul>
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
