"use client";

import React from "react";
import { IconButton } from "@/components/buttons/IconButton";
import { Tooltip } from "@/components/overlays/Tooltip";
import MarkdownContent from "@/components/data-display/MarkdownContent";
import { useTheme } from "@/contexts/ThemeContext";

import type { AssistantMessageProps } from "./types";
import { ToolApprovalCard } from "./ToolApprovalCard";

import { Check, Copy, Sparkle, ThumbsDown, ThumbsUp } from 'lucide-react';
/**
 * Format timestamp to display time
 */
function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/**
 * AssistantMessage - Displays an AI assistant message in the chat
 * 
 * Features:
 * - AI avatar with sparkle icon
 * - Message bubble with neutral background
 * - Optional tool approval card
 * - Feedback buttons (thumbs up/down)
 * - Copy button
 * - Timestamp display
 */
export function AssistantMessage({
  message,
  onToolApprove,
  onToolDeny,
  onFeedbackPositive,
  onFeedbackNegative,
  onCopyMessage,
}: AssistantMessageProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';
  const [copied, setCopied] = React.useState(false);

  const handleCopy = () => {
    if (onCopyMessage) {
      onCopyMessage(message.id, message.content);
    } else {
      // Default copy behavior
      navigator.clipboard.writeText(message.content);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex w-full items-start gap-3 pr-8">

      <div className="flex min-w-0 grow shrink-0 basis-0 flex-col items-start gap-2">
        {/* Message Content */}
        <div className="flex w-full min-w-0 flex-col items-start gap-2 rounded-md bg-neutral-100 px-3 py-3">
          <div className="w-full min-w-0 text-body font-body text-default-font [overflow-wrap:anywhere]">
            <MarkdownContent content={message.content} />
            {message.isStreaming && (
              <div className="mt-2 flex w-full flex-col gap-1">
                <div className="flex items-center gap-2 text-caption font-caption text-subtext-color">
                  <span>Generating response</span>
                  <span className={`ai-caret inline-block h-4 w-[2px] ${isDarkTheme ? 'bg-brand-primary' : 'bg-default-font'}`} />
                </div>
                <div className="ai-scanline-track">
                  <span className={`ai-scanline ${isDarkTheme ? 'bg-brand-primary' : 'bg-default-font'}`} />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Tool Approval Card */}
        {message.toolApproval && message.toolApproval.status === "pending" && (
          <ToolApprovalCard
            messageId={message.id}
            approval={message.toolApproval}
            onApprove={onToolApprove}
            onDeny={onToolDeny}
          />
        )}

        {/* Action Buttons */}
        <div className="flex items-center gap-1">
          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger asChild={true}>
                <IconButton
                  size="small"
                  icon={message.feedback === 'positive' ? <Check className="text-success-600" /> : <ThumbsUp />}
                  onClick={() => onFeedbackPositive?.(message.id)}
                  disabled={message.feedback === 'positive'}
                />
              </Tooltip.Trigger>
              <Tooltip.Content
                  side="bottom"
                  align="center"
                  sideOffset={4}
                >
                  {message.feedback === 'positive' ? 'Feedback sent!' : 'Good response'}
                </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>

          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger asChild={true}>
                <IconButton
                  size="small"
                  icon={message.feedback === 'negative' ? <Check className="text-success-600" /> : <ThumbsDown />}
                  onClick={() => onFeedbackNegative?.(message.id)}
                  disabled={message.feedback === 'negative'}
                />
              </Tooltip.Trigger>
              <Tooltip.Content
                  side="bottom"
                  align="center"
                  sideOffset={4}
                >
                  {message.feedback === 'negative' ? 'Feedback sent!' : 'Bad response'}
                </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>

          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger asChild={true}>
                <IconButton
                  size="small"
                  icon={copied ? <Check /> : <Copy />}
                  onClick={handleCopy}
                />
              </Tooltip.Trigger>
              <Tooltip.Content
                  side="bottom"
                  align="center"
                  sideOffset={4}
                >
                  {copied ? "Copied!" : "Copy"}
                </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>
        </div>

        {/* Timestamp */}
        <span className="text-caption font-caption text-subtext-color">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  );
}

export default AssistantMessage;
