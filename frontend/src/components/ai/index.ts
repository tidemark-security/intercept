/**
 * AI Chat Component
 * 
 * Reusable AI chat sidebar component for case and task detail pages.
 * 
 * @example
 * ```tsx
 * import { AiChat } from "@/components/AiChat";
 * 
 * function MyComponent() {
 *   const [messages, setMessages] = useState<AiChatMessage[]>([]);
 *   
 *   const handleSendMessage = (message: string) => {
 *     // Add user message
 *     setMessages(prev => [...prev, {
 *       id: crypto.randomUUID(),
 *       role: "user",
 *       content: message,
 *       timestamp: new Date(),
 *     }]);
 *     // Call AI API...
 *   };
 *   
 *   return (
 *     <AiChat
 *       messages={messages}
 *       onSendMessage={handleSendMessage}
 *       contextType="case"
 *       entityId={caseId}
 *       onClose={handleClosePanel}
 *     />
 *   );
 * }
 * ```
 */

export { AiChat, default } from "./AiChat";
export { UserMessage } from "./UserMessage";
export { AssistantMessage } from "./AssistantMessage";
export { ToolApprovalCard } from "./ToolApprovalCard";
export { SuggestedPrompts } from "./SuggestedPrompts";
export { ChatInput } from "./ChatInput";
export type {
  AiChatProps,
  AiChatMessage,
  AiChatMessageRole,
  ToolApproval,
  SuggestedPrompt,
  UserMessageProps,
  AssistantMessageProps,
  ToolApprovalCardProps,
  SuggestedPromptsProps,
  ChatInputProps,
} from "./types";
