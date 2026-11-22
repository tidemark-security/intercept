import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { Button, TextField } from "@tidemark-security/ux";
import { MAX_QUEUE_SEARCH_LENGTH, normalizeQueueSearch } from "@/utils/queueSearch";
import { cn } from "@/utils/cn";

const DEBOUNCE_MS = 300;

export function QueueSearchField({ query, onCommit }: {
  query: string;
  onCommit: (query: string) => void;
}) {
  const [edit, setEdit] = useState({ source: query, text: query });
  const [composing, setComposing] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  if (edit.source !== query) {
    setEdit({ source: query, text: normalizeQueueSearch(edit.text) === query ? edit.text : query });
  }
  const normalized = normalizeQueueSearch(edit.text);

  useEffect(() => {
    if (composing || !normalized || normalized === query) return;
    const timer = window.setTimeout(() => onCommit(normalized), DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [composing, normalized, onCommit, query]);

  const editText = (text: string, isComposing: boolean) => {
    setEdit({ source: query, text });
    if (!isComposing && !normalizeQueueSearch(text) && query) onCommit("");
  };

  return (
    <div role="search" aria-label="Queue search" className="relative min-w-16 flex-1">
      <TextField className="w-full" icon={<Search />} label="">
        <TextField.Input
          ref={input}
          aria-label="Search this queue"
          placeholder="Search"
          value={edit.text}
          maxLength={MAX_QUEUE_SEARCH_LENGTH}
          className={cn(edit.text && "pr-5")}
          onChange={(event) => editText(event.currentTarget.value, composing)}
          onCompositionStart={() => setComposing(true)}
          onCompositionEnd={(event) => {
            setComposing(false);
            editText(event.currentTarget.value, false);
          }}
          onKeyDown={(event) => {
            if (event.key !== "Enter" || composing || event.nativeEvent.isComposing) return;
            event.preventDefault();
            if (normalized !== query) onCommit(normalized);
          }}
        />
      </TextField>
      {edit.text && (
        <Button
          aria-label="Clear search"
          title="Clear search"
          variant="neutral-tertiary"
          size="small"
          icon={<X />}
          className="absolute right-1 top-1 h-6 w-6 p-0"
          onClick={() => {
            editText("", false);
            input.current?.focus();
          }}
        />
      )}
    </div>
  );
}
