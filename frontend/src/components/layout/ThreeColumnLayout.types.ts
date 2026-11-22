import type { ThreeColumnLayoutProps as UxThreeColumnLayoutProps } from '@tidemark-security/ux';
import type { Ref } from 'react';

export type { VisibleColumns, Breakpoint, ColumnConfig } from '@tidemark-security/ux';

export type FloatingPane = "left" | "center";

interface FloatingPanesOptions {
  mode: "narrow" | "on" | "off";
  labels: Record<FloatingPane, string>;
  frontPane?: FloatingPane;
  onFrontPaneChange?: (pane: FloatingPane) => void;
  refs?: Partial<Record<FloatingPane, Ref<HTMLDivElement>>>;
  centerPlaceholder?: boolean;
}

export interface ThreeColumnLayoutProps extends Omit<UxThreeColumnLayoutProps, "onVisibleColumnsChange"> {
  onVisibleColumnsChange?: UxThreeColumnLayoutProps["onVisibleColumnsChange"];
  leftRailLabel?: string;
  leftColumnWidthStorageKey?: string;
  floatingPanes?: FloatingPanesOptions;
}
