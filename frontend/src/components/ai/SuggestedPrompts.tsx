"use client";

import React from "react";
import { useTheme } from "@/contexts/ThemeContext";

import type { SuggestedPromptsProps } from "./types";

import { MessageCircle, MessageCircleCode, MessageCirclePlus, Sparkles } from 'lucide-react';
/**
 * SuggestedPrompts - Displays suggested prompt buttons
 * 
 * Features:
 * - Wrapping layout for multiple prompts
 * - Sparkle icon for each prompt
 * - Clickable to send prompt as message
 */
export function SuggestedPrompts({ prompts, onPromptClick }: SuggestedPromptsProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  if (prompts.length === 0) return null;

  return (
    <div className="flex w-full flex-col items-start gap-3">
      <span className="text-caption-bold font-caption-bold text-subtext-color">
        Suggested prompts
      </span>
      <div className="flex w-full items-start gap-2 flex-wrap">
        {prompts.map((prompt) => (
          <button
            key={prompt.id}
            type="button"
            className="flex items-center gap-2 rounded-md border border-solid border-neutral-border bg-neutral-50 px-3 py-2 hover:bg-neutral-100 transition-colors cursor-pointer"
            onClick={() => onPromptClick?.(prompt)}
          >
            <MessageCircle className={`text-body font-body ${isDarkTheme ? 'text-brand-primary' : 'text-default-font'}`} />
            <span className="text-caption font-caption text-default-font">
              {prompt.label}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default SuggestedPrompts;
