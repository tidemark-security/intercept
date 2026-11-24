import { useId, useState, type FormEvent } from "react";
import * as Popover from "@radix-ui/react-popover";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, Pencil, Trash2 } from "lucide-react";
import { Button, Dialog, TextField } from "@tidemark-security/ux";

import { MIN_SEARCH_QUERY_LENGTH } from "@/components/search/searchUtils";
import type { FilterState } from "@/types/filters";
import type { SavedFilterQueue } from "@/types/generated/models/SavedFilterQueue";
import type { SavedFilterRead } from "@/types/generated/models/SavedFilterRead";
import type { SavedFilterScope } from "@/types/generated/models/SavedFilterScope";
import type { SavedFilterSnapshot } from "@/types/generated/models/SavedFilterSnapshot";
import { SavedFiltersService } from "@/types/generated/services/SavedFiltersService";
import { MAX_QUEUE_SEARCH_LENGTH, normalizeQueueSearch } from "@/utils/queueSearch";

const MAX_FILTER_NAME_LENGTH = 100;

type FilterAction =
  | { kind: "save"; snapshot: SavedFilterSnapshot; invalidSearch: boolean }
  | { kind: "rename" | "delete"; filter: SavedFilterRead };

interface SavedQueueFiltersProps {
  queue: SavedFilterQueue;
  userId: string;
  isAdmin: boolean;
  filters: FilterState;
  readSearchInput: () => string;
  onApply: (snapshot: SavedFilterSnapshot) => void;
}

const scopes = [
  { value: "personal", label: "Personal" },
  { value: "organization", label: "Org-wide" },
] as const;

const titles = {
  save: "Save current filter",
  rename: "Rename saved filter",
  delete: "Delete saved filter",
};

const descriptions = {
  save: "Save these queue filters for later.",
  rename: "Change the name shown in the saved filters list.",
  delete: "Remove this filter from the saved filters list.",
};

const submitLabels = {
  save: "Save filter",
  rename: "Rename filter",
  delete: "Delete filter",
};

function savedFilterKey(queue: SavedFilterQueue, userId: string) {
  return ["saved-filters", userId, queue] as const;
}

function createSnapshot(filters: FilterState, search: string): SavedFilterSnapshot {
  return {
    search,
    status: filters.status,
    assignee: filters.assignee,
    include_tags: filters.includeTags ?? null,
    exclude_tags: filters.excludeTags ?? null,
    date_range: filters.dateRange,
    sort_by: (filters.sortBy ?? null) as SavedFilterSnapshot["sort_by"],
    sort_order: filters.sortOrder ?? null,
  };
}

function SavedFilterDialog({
  action,
  queue,
  userId,
  isAdmin,
  onClose,
}: Pick<SavedQueueFiltersProps, "queue" | "userId" | "isAdmin"> & {
  action: FilterAction;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const scopeName = useId();
  const [name, setName] = useState(action.kind === "save" ? "" : action.filter.name);
  const [scope, setScope] = useState<SavedFilterScope>("personal");
  const mutation = useMutation({
    mutationFn: async () => {
      if (action.kind === "save") {
        return await SavedFiltersService.createSavedFilter({
          requestBody: { name: name.trim(), scope, queue, filters: action.snapshot },
        });
      }
      if (action.kind === "rename") {
        return await SavedFiltersService.renameSavedFilter({
          filterId: action.filter.id,
          requestBody: { name: name.trim() },
        });
      }
      return await SavedFiltersService.deleteSavedFilter({ filterId: action.filter.id });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: savedFilterKey(queue, userId) });
      onClose();
    },
  });
  const deleting = action.kind === "delete";
  const invalidSearch = action.kind === "save" && action.invalidSearch;
  const canSubmit = !mutation.isPending && (deleting || !!name.trim()) && !invalidSearch;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (canSubmit) mutation.mutate();
  }

  const search = action.kind === "save" ? action.snapshot.search : "";
  return (
    <Dialog
      open
      className="z-[calc(var(--z-popover)_+_1)]"
      onOpenChange={(open) => { if (!open && !mutation.isPending) onClose(); }}
    >
      <Dialog.Content className="w-[min(28rem,calc(100vw-2rem))] min-w-0 bg-neutral-100 p-5">
        <form className="flex w-full min-w-0 flex-col gap-4" onSubmit={submit}>
          <div className="flex flex-col gap-1">
            <Dialog.Title className="text-heading-3 font-heading-3 text-default-font">
              {titles[action.kind]}
            </Dialog.Title>
            <Dialog.Description className="text-body font-body text-subtext-color">
              {descriptions[action.kind]}
            </Dialog.Description>
          </div>
          {deleting ? (
            <p className="break-words text-body font-body text-default-font">
              Delete <strong>{action.filter.name}</strong>{action.filter.scope === "organization" ? " for your organization" : ""}?
            </p>
          ) : (
            <TextField label="Filter name">
              <TextField.Input
                aria-label="Filter name"
                value={name}
                maxLength={MAX_FILTER_NAME_LENGTH}
                onChange={(event) => setName(event.currentTarget.value)}
              />
            </TextField>
          )}
          {action.kind === "save" && isAdmin && (
            <fieldset className="flex flex-col gap-2 text-body font-body text-default-font">
              <legend className="mb-2 text-caption-bold font-caption-bold">Visibility</legend>
              {scopes.map((option) => (
                <label key={option.value} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name={scopeName}
                    checked={scope === option.value}
                    className="accent-brand-primary"
                    onChange={() => setScope(option.value)}
                  />
                  {option.label}
                </label>
              ))}
            </fieldset>
          )}
          {search && (
            <div className="flex flex-col gap-1 rounded-md border border-neutral-border bg-neutral-50 p-3 text-body font-body text-default-font">
              <p>{scope === "organization"
                ? "This search text will be visible to everyone in your organization."
                : "This search will be included in the saved filter."}</p>
              <p className="break-words font-body-bold">{search}</p>
            </div>
          )}
          {invalidSearch && (
            <p role="alert" className="text-body font-body text-error-color">
              Enter {MIN_SEARCH_QUERY_LENGTH} to {MAX_QUEUE_SEARCH_LENGTH} characters in the search box or clear it before saving.
            </p>
          )}
          {mutation.isError && (
            <p role="alert" className="text-body font-body text-error-color">Couldn’t update saved filters. Try again.</p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" aria-label="Cancel" variant="neutral-secondary" disabled={mutation.isPending} onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" aria-label={submitLabels[action.kind]} disabled={!canSubmit} loading={mutation.isPending}>
              {submitLabels[action.kind]}
            </Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog>
  );
}

export function SavedQueueFilters({
  queue,
  userId,
  isAdmin,
  filters,
  readSearchInput,
  onApply,
}: SavedQueueFiltersProps) {
  const [action, setAction] = useState<FilterAction | null>(null);
  const savedFilters = useQuery({
    queryKey: savedFilterKey(queue, userId),
    queryFn: () => SavedFiltersService.listSavedFilters({ queue }),
    staleTime: 0,
  });

  function openSaveDialog() {
    const input = readSearchInput();
    const search = normalizeQueueSearch(input);
    setAction({
      kind: "save",
      snapshot: createSnapshot(filters, search),
      invalidSearch: !!input && !search,
    });
  }

  return (
    <section aria-label="Saved filters" className="flex flex-col gap-2 border-t border-neutral-border p-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-caption-bold font-caption-bold text-default-font">Saved filters</h3>
        <Button type="button" aria-label="Save current filter" variant="neutral-secondary" size="small" icon={<Bookmark />} onClick={openSaveDialog}>
          Save current filter
        </Button>
      </div>
      {savedFilters.isPending ? (
        <p role="status" className="text-caption font-caption text-subtext-color">Loading saved filters…</p>
      ) : savedFilters.isError ? (
        <div className="flex flex-wrap items-center gap-2">
          <p role="alert" className="text-caption font-caption text-error-color">Couldn’t load saved filters.</p>
          <Button type="button" aria-label="Try again" variant="neutral-secondary" size="small" onClick={() => void savedFilters.refetch()}>
            Try again
          </Button>
        </div>
      ) : (
        scopes.map(({ value, label }) => {
          const entries = savedFilters.data.filter((filter) => filter.scope === value);
          return (
            <div key={value} className="flex flex-col gap-1">
              <h4 className="text-caption-bold font-caption-bold text-subtext-color">{label}</h4>
              {entries.length ? (
                <ul aria-label={`${label} filters`} className="flex flex-col gap-1">
                  {entries.map((filter) => (
                    <li key={filter.id} className="flex min-w-0 gap-1">
                      <Popover.Close asChild>
                        <button
                          type="button"
                          aria-label={`Apply ${filter.name}`}
                          title={filter.name}
                          className="min-w-0 flex-1 truncate rounded-md px-2 py-1 text-left text-body font-body text-default-font hover:bg-neutral-100 focus-visible:outline focus-visible:outline-1 focus-visible:outline-focus-border"
                          onClick={() => onApply(filter.filters)}
                        >
                          {filter.name}
                        </button>
                      </Popover.Close>
                      {(value === "personal" || isAdmin) && (
                        <>
                          <Button
                            type="button"
                            aria-label={`Rename ${filter.name}`}
                            title={`Rename ${filter.name}`}
                            variant="neutral-tertiary"
                            size="small"
                            icon={<Pencil />}
                            onClick={() => setAction({ kind: "rename", filter })}
                          />
                          <Button
                            type="button"
                            aria-label={`Delete ${filter.name}`}
                            title={`Delete ${filter.name}`}
                            variant="neutral-tertiary"
                            size="small"
                            icon={<Trash2 />}
                            onClick={() => setAction({ kind: "delete", filter })}
                          />
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-caption font-caption text-subtext-color">No saved filters</p>
              )}
            </div>
          );
        })
      )}
      {action && (
        <SavedFilterDialog
          action={action}
          queue={queue}
          userId={userId}
          isAdmin={isAdmin}
          onClose={() => setAction(null)}
        />
      )}
    </section>
  );
}
