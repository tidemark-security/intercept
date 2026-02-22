"use client";

import React, { useState, useCallback, useRef } from "react";
import { IconButton } from "@/components/buttons/IconButton";
import { useTheme } from "@/contexts/ThemeContext";

import type { ChatInputProps } from "./types";
import { CommandInput, type CommandInputRef } from "@/components/forms/CommandInput";

import { History, Send, Sparkles } from 'lucide-react';
/**
 * ChatInput - Message input field with send button
 * 
 * Features:
 * - Multi-line textarea with floating expansion (matches QuickTerminal design)
 * - Send button with brand primary style
 * - Enter key to send, Shift+Enter for new line
 * - Disabled state while loading
 * - Clears input after sending
 * - Consistent styling with QuickTerminal (unified CommandInput component)
 * - Slash commands disabled (for now - can be enabled later for pre-canned prompts)
 */
export function ChatInput({
  placeholder = "Ask me anything...",
  isLoading = false,
  disabled = false,
  onSendMessage,
  showHistoryButton = false,
  onHistoryClick,
}: ChatInputProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';
  const commandInputRef = useRef<CommandInputRef>(null);

  const [inputValue, setInputValue] = useState("");

  const handleSend = useCallback(
    (value: string) => {
      if (isLoading || disabled) {
        return false;
      }

      onSendMessage(value);
      requestAnimationFrame(() => {
        commandInputRef.current?.focus();
      });
      return true;
    },
    [isLoading, disabled, onSendMessage]
  );

  return (
    <CommandInput
      ref={commandInputRef}
      value={inputValue}
      onChange={setInputValue}
      onSubmit={handleSend}
      placeholder={placeholder}
      disabled={disabled}
      isLoading={false}
      multiline={true}
      minLines={1}
      maxLines={5}
      floatOnExpand={true}
      enableSlashCommands={false} // Disabled for now - can enable later for AI prompts
      leftIcon={<Sparkles className={isDarkTheme ? 'text-brand-primary' : 'text-default-font'} />}
      rightActions={
        <div className="flex items-center gap-1 flex-shrink-0" style={{ height: '40px' }}>
          <IconButton
            variant="brand-primary"
            size="large"
            icon={<Send />}
            onClick={() => inputValue.trim() && handleSend(inputValue)}
            disabled={isLoading || disabled || !inputValue.trim()}
          />
          {showHistoryButton && onHistoryClick && (
            <IconButton
              size="large"
              variant="brand-tertiary"
              icon={<History />}
              onClick={onHistoryClick}
              disabled={isLoading || disabled}
              aria-label="Show chat history"
            />
          )}
        </div>
      }
    />
  );
}

export default ChatInput;
