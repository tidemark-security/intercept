import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { bulkEntityLabels, entityBulkActions, getApiErrorMessage, type BulkEntityStatus, type BulkUpdateFields } from "@/utils/entityBulkActions";
import type { EntityType } from "@/utils/statusLabels";
import type { Priority } from "@/types/generated/models/Priority";
import type { VisibleColumns } from "@/components/layout/ThreeColumnLayout.types";
import { queryKeys } from "./queryKeys";

export interface BulkSelectionItem {
  id: number;
  human_id: string;
  title: string;
  status: BulkEntityStatus[EntityType];
  priority?: Priority | null;
  assignee?: string | null;
  case_id?: number | null;
}

export function useEntityBulkActions<K extends EntityType>(
  entityType: K,
  visibleItems: readonly BulkSelectionItem[] | undefined,
  options: {
    enabled: boolean;
    users: readonly { username: string }[];
    currentUser: string | null;
    usersLoading: boolean;
    showSplitCenter: boolean;
    selectionScope?: string;
  },
) {
  const [selection, setSelection] = useState<ReadonlyMap<number, BulkSelectionItem>>(() => new Map());
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [selectionScope, setSelectionScope] = useState(options.selectionScope);
  const queryClient = useQueryClient();
  const config = entityBulkActions[entityType];
  const visibleById = useMemo(() => new Map(visibleItems?.map((item) => [item.id, item])), [visibleItems]);
  const items = useMemo(
    () => Array.from(selection, ([id, snapshot]) => visibleById.get(id) ?? snapshot),
    [selection, visibleById],
  );
  const ids = useMemo(() => items.map(({ id }) => id), [items]);
  const clear = () => {
    setSelection(new Map());
    setReviewing(false);
    setDialogOpen(false);
  };
  // Reset before rendering the next result set; paging and regular filter
  // changes leave the committed search scope unchanged.
  if (selectionScope !== options.selectionScope) {
    setSelectionScope(options.selectionScope);
    clear();
  }

  const mutation = useMutation({
    mutationFn: ({ targets, fields }: { targets: BulkSelectionItem[]; fields: BulkUpdateFields<BulkEntityStatus[K]> }) =>
      config.apply(targets.map(({ id }) => id), fields),
    onSuccess: (_result, { targets, fields }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys[entityType].listBase() });
      if (entityType === "case" && fields.status === "CLOSED") {
        for (const key of [queryKeys.alert.listBase(), queryKeys.task.listBase(), ["alert-detail"], ["task"]]) {
          void queryClient.invalidateQueries({ queryKey: key });
        }
      }
      for (const { id, human_id } of targets) {
        void queryClient.invalidateQueries({ queryKey: queryKeys[entityType].detailBase(id) });
        if (entityType === "task") {
          void queryClient.invalidateQueries({ queryKey: queryKeys.task.detailBase(human_id) });
        }
      }
      if (entityType !== "case") {
        const caseIds = new Set(targets.flatMap(({ case_id }) => case_id != null ? [case_id] : []));
        if (caseIds.size) {
          void queryClient.invalidateQueries({ queryKey: queryKeys.case.listBase() });
          for (const id of caseIds) void queryClient.invalidateQueries({ queryKey: queryKeys.case.detailBase(id) });
        }
      }
      clear();
    },
  });

  const changeSelection = (checked: boolean, targetIds: number[]) => {
    setSelection((previous) => {
      const next = new Map(previous);
      for (const id of targetIds) {
        if (!checked) next.delete(id);
        else {
          const item = visibleById.get(id);
          if (item) next.set(id, item);
        }
      }
      return next;
    });
    if (!checked && ids.length - targetIds.filter((id) => selection.has(id)).length < 2) {
      setReviewing(false);
    }
  };
  const start = () => {
    mutation.reset();
    setDialogOpen(true);
  };
  const hasMultiple = options.enabled && ids.length > 1;
  const selectionColumns: VisibleColumns | undefined = hasMultiple
    ? options.showSplitCenter ? "left+center" : reviewing ? "center" : "left"
    : undefined;
  const controls = { onBulk: start, onClear: clear, disabled: mutation.isPending };

  return {
    ids,
    clear,
    hasMultiple,
    isPending: mutation.isPending,
    selectionColumns,
    toolbarProps: {
      ...controls,
      count: ids.length,
      onReview: options.showSplitCenter ? undefined : () => setReviewing(true),
    },
    summaryProps: {
      ...controls,
      entityType,
      items,
      onRemove: (id: number) => changeSelection(false, [id]),
      onBack: options.showSplitCenter ? undefined : () => setReviewing(false),
      focusOnOpen: !options.showSplitCenter && reviewing,
    },
    listProps: {
      selectable: options.enabled,
      selectedIds: selection,
      onSelectionChange: (id: number, checked: boolean) => changeSelection(checked, [id]),
      onSelectVisible: changeSelection,
      selectVisibleLabel: `Select visible ${bulkEntityLabels[entityType].plural}`,
    },
    dialogProps: dialogOpen && hasMultiple ? {
      entityType,
      count: ids.length,
      statusOptions: config.statuses,
      users: options.users,
      currentUser: options.currentUser,
      usersLoading: options.usersLoading,
      isSubmitting: mutation.isPending,
      error: mutation.error ? getApiErrorMessage(mutation.error, "Failed to apply bulk action") : undefined,
      onClose: () => setDialogOpen(false),
      onApply: (fields: BulkUpdateFields<BulkEntityStatus[K]>) => mutation.mutate({ targets: items, fields }),
    } : null,
  };
}
