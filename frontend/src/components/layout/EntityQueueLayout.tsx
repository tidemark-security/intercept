import { useEffect, useRef, useState, type ComponentProps, type ReactNode } from "react";
import { BulkSelectionSummary, BulkSelectionToolbar } from "@/components/entities/BulkSelection";
import { QueueSearchHighlightScope } from "@/components/search/QueueSearchHighlight";
import { getColumnConfig } from "@/utils/columnConfig";
import type { EntityType } from "@/utils/statusLabels";
import { ThreeColumnLayout } from "./ThreeColumnLayout";
import type { VisibleColumns } from "./ThreeColumnLayout.types";

interface EntityQueueLayoutProps {
  entityType: EntityType;
  searchQuery?: string;
  isMobile: boolean;
  showSplitCenter: boolean;
  listWidth: number;
  onListWidthChange: (width: number) => void;
  selectedId: number | null;
  onSelect: (id: number, humanId: string, options: { floating: boolean }) => void;
  renderList: (props: {
    onSelect: (id: number, humanId: string) => void;
    toolbarActions?: ReactNode;
    deferPointerSelection: boolean;
  }) => ReactNode;
  detail: ReactNode;
  selection?: {
    columns: VisibleColumns;
    toolbar: ComponentProps<typeof BulkSelectionToolbar>;
    summary: ComponentProps<typeof BulkSelectionSummary>;
  };
  mobileColumns?: VisibleColumns;
  dock?: { open: boolean; content: ReactNode };
}

/** Shared queue/detail layout, including the floating preview and selection summary. */
export function EntityQueueLayout({
  entityType, searchQuery = "", isMobile, showSplitCenter, listWidth, onListWidthChange,
  selectedId, onSelect, renderList, detail, selection, mobileColumns, dock,
}: EntityQueueLayoutProps) {
  const [listInFront, setListInFront] = useState(false);
  const listPane = useRef<HTMLDivElement>(null);
  const detailPane = useRef<HTMLDivElement>(null);
  const focusDetailOnOpen = useRef(false);
  const hasSelection = !!selection;
  const dockOpen = !!dock?.open && !hasSelection;
  // Reserve the floating pane geometry before the first entity is selected.
  const overlap = !isMobile && !showSplitCenter;
  const hasDetail = selectedId !== null;
  const hasPreview = hasDetail || hasSelection;
  const floating = overlap && !dockOpen;
  const showListInFront = !hasPreview || listInFront;
  const entityLabel = entityType[0].toUpperCase() + entityType.slice(1);

  useEffect(() => {
    setListInFront(hasSelection);
    if (hasDetail && !hasSelection && floating && (
      focusDetailOnOpen.current || listPane.current?.contains(document.activeElement)
    )) {
      detailPane.current?.focus({ preventScroll: true });
      focusDetailOnOpen.current = false;
    }
  }, [selectedId, hasDetail, floating, hasSelection]);

  const select = (id: number, humanId: string) => {
    if (overlap) {
      setListInFront(false);
      if (floating && hasPreview) detailPane.current?.focus({ preventScroll: true });
      else focusDetailOnOpen.current = true;
    }
    onSelect(id, humanId, { floating: overlap });
  };

  const focusList = () => {
    setListInFront(true);
    listPane.current?.focus({ preventScroll: true });
  };

  const focusDetail = () => {
    setListInFront(false);
    detailPane.current?.focus({ preventScroll: true });
  };

  // With the dock open, hide rather than unmount the narrow queue to retain its scroll position.
  let columns: VisibleColumns;
  if (overlap) columns = dockOpen ? "all" : "left+center";
  else if (selection) columns = selection.columns;
  else if (isMobile) columns = mobileColumns ?? (hasDetail ? "center" : "left");
  else columns = dockOpen && hasDetail ? "all" : "left+center";

  return (
    <ThreeColumnLayout
      floatingPanes={{
        mode: overlap ? "on" : "off",
        labels: { left: `${entityLabel} list`, center: `${entityLabel} detail` },
        frontPane: showListInFront ? "left" : "center",
        onFrontPaneChange: (pane) => setListInFront(pane === "left"),
        refs: { left: listPane, center: detailPane },
        centerPlaceholder: !hasPreview,
      }}
      showLeftRail={showSplitCenter}
      leftRailLabel={`Resize ${entityType} list`}
      leftColumnWidth={listWidth}
      onLeftColumnWidthChange={onListWidthChange}
      leftColumn={renderList({
        onSelect: select,
        deferPointerSelection: overlap,
        toolbarActions: selection && (
          <BulkSelectionToolbar
            {...selection.toolbar}
            onReview={floating ? focusDetail : selection.toolbar.onReview}
          />
        ),
      })}
      centerColumn={selection ? (
        <QueueSearchHighlightScope query={searchQuery}>
          <BulkSelectionSummary
            {...selection.summary}
            onBack={floating ? focusList : selection.summary.onBack}
          />
        </QueueSearchHighlightScope>
      ) : detail}
      rightColumn={dock?.content}
      visibleColumns={columns}
      columnConfig={getColumnConfig(selectedId, listWidth, columns === "left")}
      dimLeftColumn={!hasSelection && hasDetail && !overlap}
    />
  );
}
