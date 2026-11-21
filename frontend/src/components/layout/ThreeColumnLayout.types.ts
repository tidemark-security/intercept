import type { ThreeColumnLayoutProps as UxThreeColumnLayoutProps } from '@tidemark-security/ux';

export type { VisibleColumns, Breakpoint, ColumnConfig } from '@tidemark-security/ux';

export interface ThreeColumnLayoutProps extends UxThreeColumnLayoutProps {
  leftRailLabel?: string;
  leftColumnWidthStorageKey?: string;
}
