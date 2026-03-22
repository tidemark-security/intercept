/**
 * Column visibility state - which columns are visible at current breakpoint
 */
export type VisibleColumns = 'left' | 'center' | 'right' | 'left+center' | 'center+right' | 'all';

/**
 * Breakpoint names
 */
export type Breakpoint = 'mobile' | 'tablet' | 'desktop' | 'ultrawide';

/**
 * Configuration for column widths at different breakpoints
 */
export interface ColumnConfig {
  /** Ultrawide (≥1920px) layout configuration */
  ultrawide?: {
    /** Tailwind width class for left column */
    leftWidth?: string;
    /** Tailwind width class for center column */
    centerWidth?: string;
    /** Tailwind width class for right column */
    rightWidth?: string;
  };

  /** Desktop (1024px-1919px) layout configuration */
  desktop?: {
    /** Tailwind width class for left column */
    leftWidth?: string;
    /** Tailwind width class for center column */
    centerWidth?: string;
    /** Tailwind width class for right column */
    rightWidth?: string;
  };
  
  /** Tablet (768px-1023px) layout configuration */
  tablet?: {
    /** Tailwind width class for left column */
    leftWidth?: string;
    /** Tailwind width class for center column */
    centerWidth?: string;
    /** Tailwind width class for right column */
    rightWidth?: string;
  };

  /** Mobile (<768px) layout configuration */
  mobile?: {
    /** Tailwind width class for left column */
    leftWidth?: string;
    /** Tailwind width class for center column */
    centerWidth?: string;
    /** Tailwind width class for right column */
    rightWidth?: string;
  };
}

/**
 * Props for the ThreeColumnLayout component
 */
export interface ThreeColumnLayoutProps {
  /** Content for the left column (typically a list view) */
  leftColumn: React.ReactNode;
  
  /** Content for the center column (typically a detail view) */
  centerColumn: React.ReactNode;
  
  /** Content for the right column (typically a dock/panel). Optional - not all layouts need a third column. */
  rightColumn?: React.ReactNode;
  
  /** 
   * Current column visibility state
   * Controls which column(s) are visible
   * - 'left', 'center', 'right': Single column (typically for mobile)
   * - 'left+center', 'center+right': Two columns (typically for tablet/desktop)
   * - 'all': All three columns (typically for ultrawide)
   */
  visibleColumns: VisibleColumns;
  
  /** 
   * Callback when visible columns change
   * Used for navigation between column views
   */
  onVisibleColumnsChange: (columns: VisibleColumns) => void;
  
  /** 
   * Additional CSS classes for the container
   */
  className?: string;
  
  /** 
   * Optional configuration for column widths at different breakpoints
   * If not provided, uses sensible defaults
   */
  columnConfig?: ColumnConfig;

  /**
   * Whether to dim the left column when the center column is visible.
   * Defaults to true.
   */
  dimLeftColumn?: boolean;

  /**
   * Whether to show the rail between left and center columns.
   * The rail provides a toggle control and optional resize handle.
   */
  showLeftRail?: boolean;

  /**
   * Whether the left column is collapsed (controlled by the rail).
   * Only relevant when showLeftRail is true.
   */
  leftRailCollapsed?: boolean;

  /**
   * Callback when the left rail is toggled.
   * Only relevant when showLeftRail is true.
   */
  onLeftRailToggle?: () => void;

  /**
   * Current width of the left column for resizing (in pixels).
   * Only used when showLeftRail is true.
   */
  leftColumnWidth?: number;

  /**
   * Callback when the left column width changes via drag resize.
   * Only used when showLeftRail is true.
   */
  onLeftColumnWidthChange?: (width: number) => void;
}
