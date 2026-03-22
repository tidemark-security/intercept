"use client";

import MarkdownContent from "@/components/data-display/MarkdownContent";
import { RelativeTime } from "@/components/data-display/RelativeTime";
import type { UserMessageProps } from "./types";

/**
 * UserMessage - Displays a user message in the AI chat
 *
 * Features:
 * - User avatar
 * - Message bubble with brand primary background
 * - Timestamp display
 */
export function UserMessage({ message }: UserMessageProps) {
  const timestampIso = message.timestamp.toISOString();

  return (
    <div className="flex w-full items-start gap-3 pl-8">
      <div className="flex grow shrink-0 basis-0 flex-col items-start gap-2">
        <div className="flex w-full flex-col items-start gap-1 rounded-md bg-brand-primary px-3 py-2">
          <div className="w-full text-body font-body text-black">
            <MarkdownContent
              content={message.content}
              className="[&_*]:text-black"
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-caption font-caption text-subtext-color w-24 text-left shrink-0">
            <RelativeTime value={timestampIso} />
          </span>
        </div>
      </div>
    </div>
  );
}

export default UserMessage;
