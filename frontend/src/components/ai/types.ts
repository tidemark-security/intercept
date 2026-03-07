/**
 * AI Chat Component Types
 * 
 * Type definitions for the reusable AI Chat sidebar component.
 */

export type AiChatMessageRole = "user" | "assistant";

export interface AiChatMessage {
  /** Unique identifier for the message */
  id: string;
  /** Role of the message sender */
  role: AiChatMessageRole;
  /** Message content */
  content: string;
  /** Timestamp of the message */
  timestamp: Date;
  /** Optional tool approval request */
  toolApproval?: ToolApproval;
  /** Feedback given by user (if any) */
  feedback?: "positive" | "negative";
  /** Whether message is currently streaming */
  isStreaming?: boolean;
}

export interface ToolApproval {
  /** Unique identifier for the tool approval request */
  id: string;
  /** Name of the tool requesting approval */
  toolName: string;
  /** Description of what the tool wants to do */
  description: string;
  /** Current status of the approval */
  status: "pending" | "approved" | "denied";
}

export interface SuggestedPrompt {
  /** Unique identifier for the prompt */
  id: string;
  /** Display text for the prompt */
  label: string;
}

export interface AiChatProps {
  /** Title displayed in the header */
  title?: string;
  /** 
   * Messages to display in the chat (controlled mode).
   * If not provided, component manages its own internal message state.
   */
  messages?: AiChatMessage[];
  /** Whether the AI is currently thinking/loading (controlled mode) */
  isLoading?: boolean;
  /** Error message to display (controlled mode) */
  error?: string | null;
  /** Suggested prompts to show at the bottom */
  suggestedPrompts?: SuggestedPrompt[];
  /** Placeholder text for the input field */
  inputPlaceholder?: string;
  /** 
   * Callback when a message is sent (controlled mode).
   * If not provided, component sends messages via internal SSE streaming.
   */
  onSendMessage?: (message: string) => void;
  /** Callback when a suggested prompt is clicked */
  onSuggestedPromptClick?: (prompt: SuggestedPrompt) => void;
  /** Callback when the close button is clicked */
  onClose?: () => void;
  /** Callback when a tool is approved */
  onToolApprove?: (messageId: string, approvalId: string) => void;
  /** Callback when a tool is denied */
  onToolDeny?: (messageId: string, approvalId: string) => void;
  /** Callback when positive feedback is given */
  onFeedbackPositive?: (messageId: string) => void;
  /** Callback when negative feedback is given */
  onFeedbackNegative?: (messageId: string) => void;
  /** Callback when copy button is clicked */
  onCopyMessage?: (messageId: string, content: string) => void;
  /** Context type - changes suggested prompts if not provided */
  contextType?: "case" | "task" | "alert" | "general";
  /** Entity ID for context-aware suggestions and session persistence */
  entityId?: number | string;
  /** 
   * Human-readable entity ID (e.g., "CAS-0000001", "TSK-0000001") for LangFlow context.
   * When provided, this is sent to LangFlow as the entity_id tweak.
   */
  entityHumanId?: string;
  /**
   * Current user's username for LangFlow context.
   * When provided, this is sent to LangFlow as the username tweak.
   */
  username?: string;
  /**
   * Optional username used for read-only session loading in admin mode.
   * When provided, session/message fetches are scoped to this username.
   */
  sessionOwnerUsername?: string;
  /** 
   * Whether to persist session ID in localStorage.
   * When true, returning to the same entity will resume the previous conversation.
   * Default: true for case/task/alert contexts, false for general.
   */
  persistSession?: boolean;
  /**
   * Pre-existing session ID to load.
   * When provided, the component will load this session instead of creating a new one.
   * Useful for resuming a conversation from a chat history list.
   */
  initialSessionId?: string;
  /**
   * Callback when the session changes (new session created or loaded).
   * Useful for syncing with parent component state.
   */
  onSessionChange?: (sessionId: string | null) => void;
  /**
   * Whether to use lazy session creation (defer until first message is sent).
   * When true (default), sessions are only created when the user sends their first message.
   * When false, sessions are created immediately on mount.
   * This prevents session bloat from page reloads and "New Chat" clicks.
   */
  isLazy?: boolean;
  /** Whether to show the history button in the input area */
  showHistoryButton?: boolean;
  /** Callback when history button is clicked */
  onHistoryClick?: () => void;
  /** Additional class names */
  className?: string;
}

export interface UserMessageProps {
  message: AiChatMessage;
}

export interface AssistantMessageProps {
  message: AiChatMessage;
  onToolApprove?: (messageId: string, approvalId: string) => void;
  onToolDeny?: (messageId: string, approvalId: string) => void;
  onFeedbackPositive?: (messageId: string) => void;
  onFeedbackNegative?: (messageId: string) => void;
  onCopyMessage?: (messageId: string, content: string) => void;
}

export interface ToolApprovalCardProps {
  messageId: string;
  approval: ToolApproval;
  onApprove?: (messageId: string, approvalId: string) => void;
  onDeny?: (messageId: string, approvalId: string) => void;
}

export interface SuggestedPromptsProps {
  prompts: SuggestedPrompt[];
  onPromptClick?: (prompt: SuggestedPrompt) => void;
}

export interface ChatInputProps {
  placeholder?: string;
  isLoading?: boolean;
  disabled?: boolean;
  onSendMessage: (message: string) => void;
  /** Whether to show the history button */
  showHistoryButton?: boolean;
  /** Callback when history button is clicked */
  onHistoryClick?: () => void;
}
