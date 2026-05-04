import type { AlertRead } from '@/types/generated/models/AlertRead';
import type { AlertStatus } from '@/types/generated/models/AlertStatus';
import type { CaseReadWithAlerts } from '@/types/generated/models/CaseReadWithAlerts';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import type { AcceptRecommendationRequest } from '@/types/generated/models/AcceptRecommendationRequest';
import type { RejectionCategory } from '@/types/generated/models/RejectionCategory';
import type { app__api__routes__admin_auth__UserSummary } from '@/types/generated/models/app__api__routes__admin_auth__UserSummary';
import type { TimelineItemType } from '@/types/drafts';
import type { UIState } from '@/utils/statusHelpers';

// Define a compatible user type since UserAccountRead might be missing or different
export type UnifiedUser = app__api__routes__admin_auth__UserSummary | any;

export type UnifiedEntity = AlertRead | CaseReadWithAlerts | TaskRead;

export interface UnifiedTimelineProps {
  /** 
   * Entity detail data with timeline items
   * Null when no entity is selected
   */
  entityDetail: UnifiedEntity | null;
  
  /** Type of the entity */
  entityType: 'alert' | 'case' | 'task';

  /** Currently selected entity ID */
  selectedEntityId: number | null;
  
  /** Current authenticated user username */
  currentUser: string | null;
  
  /** Loading state for entity detail */
  isLoading: boolean;
  
  /** Error state (null if no error) */
  error: Error | null;
  
  /** Available users for assignment dropdown */
  users: UnifiedUser[];
  
  /** Loading state for users data */
  usersLoading: boolean;
  
  /** Whether assignment update is in progress */
  isUpdating?: boolean;

  /** Collaboration presence text for the selected entity */
  presenceText?: string | null;

  /** Whether a page-level overlay (dock/modal/dialog) is currently open */
  isOverlayOpen?: boolean;
  
  /** Display mode - 'readonly' hides all editing controls, 'editable' shows them */
  mode?: 'readonly' | 'editable';

  // Timeline item interaction handlers
  
  /** Handler for flagging/unflagging a timeline item */
  onFlagItem?: (itemId: string) => void;
  
  /** Handler for highlighting/unhighlighting a timeline item */
  onHighlightItem?: (itemId: string) => void;
  
  /** Handler for editing a timeline item */
  onEditItem?: (itemId: string) => void;
  
  /** Handler for deleting a timeline item */
  onDeleteItem?: (itemId: string) => void;
  
  /** Handler for batch deleting multiple timeline items (used for grouped items) */
  onDeleteBatch?: (itemIds: string[]) => void;
  
  // Entity assignment handlers
  
  /** Handler for assigning entity to current user */
  onAssignToMe?: () => void;
  
  /** Handler for assigning entity to a specific user */
  onAssignToUser?: (username: string) => void;
  
  /** Handler for unassigning entity */
  onUnassign?: () => void;
  
  /** Handler for closing entity with a specific status (UIState - lowercase) */
  onCloseEntity?: (status: UIState) => void;

  /** Handler for closing a case with linked alert closure updates and closure tags */
  onCloseCaseWithDetails?: (payload: {
    alert_closure_updates: Array<{ alert_id: number; status: AlertStatus }>;
    tags: string[];
  }) => void;
  
  /** Handler for reopening a closed entity */
  onReopenEntity?: () => void;
  
  /** Handler for updating entity tags (Alerts only currently) */
  onUpdateTags?: (tags: string[]) => void;

  /** Handler for escalating/opening entity (Cases only currently) */
  onOpenEntity?: () => void;

  /** Handler for linking alert to an existing case (Alerts only) */
  onLinkToCase?: () => void;

  /** Handler for unlinking alert from its associated case (Alerts only) */
  onUnlinkFromCase?: () => void;

  /** Handler for editing the entity (Case only currently) */
  onEditEntity?: () => void;
  
  // Quick terminal handlers
  
  /** 
   * Handler for submitting a note via quick terminal
   * Returns a promise that resolves when submission is complete
   * Optionally accepts a parent item ID for creating replies
   */
  onQuickTerminalSubmit?: (noteText: string, parentItemId?: string) => Promise<void>;
  
  /** Handler for slash command (opens dock with specific item type) */
  onSlashCommand?: (itemType: TimelineItemType) => void;
  
  /** Handler for add note button */
  onAddNote?: () => void;
  
  /** Handler for menu item selection (opens dock) */
  onMenuItemSelect?: (itemType: TimelineItemType) => void;

  /** Handler for files pasted from clipboard in the quick terminal */
  onPasteFiles?: (files: File[]) => void;
  
  /** Optional callback to get the current reply parent ID for RightDock */
  onReplyParentIdChange?: (parentId: string | null) => void;
  
  /** Whether quick terminal note submission is in progress */
  isSubmittingNote?: boolean;
  
  // AI Chat integration
  
  /** Optional: Show AI chat button in quick terminal (only for cases/tasks) */
  showAiChatButton?: boolean;
  
  /** Optional: Callback when AI chat button is clicked */
  onAiChatClick?: () => void;
  
  // Mobile navigation
  
  /** 
   * Optional callback for mobile back button
   * If provided, shows back button on mobile
   */
  onBackToList?: () => void;
  
  /** 
   * Optional scroll target item ID
   * If provided, component will auto-scroll to this timeline item
   */
  scrollToItemId?: string | null;
  
  // Triage Recommendation (Alerts only)
  
  /**
   * Handler for accepting a triage recommendation
   * Called when user clicks Accept on the recommendation card
   */
  onAcceptTriageRecommendation?: (options: AcceptRecommendationRequest) => void;
  
  /**
   * Handler for rejecting a triage recommendation
   * Called when user confirms rejection with a category and optional reason
   */
  onRejectTriageRecommendation?: (category: RejectionCategory, reason?: string) => void;
  
  /**
   * Handler for scrolling to a timeline item (for evidence ref clicks)
   * Called when user clicks an evidence reference in the recommendation card
   */
  onScrollToTimelineItem?: (itemId: string) => void;
  
  /**
   * Handler for navigating to a case (after escalation)
   * Called when user clicks to view the created case
   */
  onNavigateToCase?: (caseHumanId: string) => void;
  
  /** Whether accept recommendation is in progress */
  isAcceptingRecommendation?: boolean;
  
  /** Whether reject recommendation is in progress */
  isRejectingRecommendation?: boolean;
  
  /**
   * Handler for retrying a failed triage recommendation
   * Called when user clicks Retry on a failed recommendation card
   */
  onRetryTriage?: () => void;
  
  /**
   * Handler for requesting AI triage when no recommendation exists
   * Called when user clicks Request AI Triage button
   */
  onRequestTriage?: () => void;
  
  /** Whether triage enqueue/retry is in progress */
  isEnqueuingTriage?: boolean;
  
  /** Whether AI triage feature is enabled */
  isTriageEnabled?: boolean;
}
