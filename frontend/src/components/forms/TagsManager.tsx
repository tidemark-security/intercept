/**
 * Tags Manager Component
 * 
 * Shared component for managing tags in forms.
 * Handles tag input, display, and removal.
 */

import React, { useState, KeyboardEvent } from "react";

import { TextField } from "@/components/forms/TextField";
import { Tag } from "@/components/data-display/Tag";
import { Tooltip } from "@/components/overlays/Tooltip";

import { Tags } from 'lucide-react';
export interface TagsManagerProps {
  tags: string[];
  onTagsChange: (tags: string[]) => void;
  label?: string;
  placeholder?: string;
  className?: string;
  inline?: boolean;
  readonly?: boolean;
}

export function TagsManager({ 
  tags, 
  onTagsChange, 
  label = "Tags",
  placeholder,
  className,
  inline = false,
  readonly = false
}: TagsManagerProps) {
  const [inputValue, setInputValue] = useState("");
  const effectivePlaceholder = placeholder || (inline ? "+ Add tags..." : "Enter tags and press Enter");

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && inputValue.trim()) {
      e.preventDefault();
      
      // Split by semicolon or comma for multiple tags
      const newTags = inputValue
        .split(/[;,]/)
        .map(tag => tag.trim())
        .filter(tag => tag && !tags.includes(tag));
      
      if (newTags.length > 0) {
        onTagsChange([...tags, ...newTags]);
        setInputValue("");
      }
    }
  };

  const handleRemoveTag = (tagToRemove: string) => {
    onTagsChange(tags.filter(tag => tag !== tagToRemove));
  };

  if (inline) {
    return (
      <div className={`flex w-full flex-wrap items-center gap-1.5 ${className || ""}`}>
        {tags.map((tag) => (
          <div key={tag} onClick={() => !readonly && handleRemoveTag(tag)} style={{ cursor: readonly ? 'default' : 'pointer' }}>
            <Tag tagText={tag} showDelete={!readonly} p="0" />
          </div>
        ))}
        {!readonly && (
          <div className="relative grid items-center justify-start group/input">
            <span className="invisible col-start-1 row-start-1 whitespace-pre text-body font-body px-0.5 opacity-0 pointer-events-none">
              {inputValue || effectivePlaceholder}
            </span>
            <input
              className="col-start-1 row-start-1 w-full min-w-[4ch] bg-transparent border-b border-transparent focus:border-brand-primary outline-none text-body font-body text-default-font placeholder:text-subtext-color h-6 px-0.5 transition-all hover:placeholder:text-neutral-300 focus:placeholder:text-neutral-200"
              placeholder={effectivePlaceholder}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={`flex w-full flex-col items-start gap-4 ${className || ""}`}>
      {!readonly && (
        <TextField
          className="h-auto w-full flex-none"
          label={label}
          helpText=""
          icon={<Tags />}
        >
          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger asChild>
                <TextField.Input 
                  placeholder={effectivePlaceholder}
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                />
              </Tooltip.Trigger>
              <Tooltip.Content
                side="bottom"
                align="center"
                sideOffset={4}
              >
                Separate multiple tags with a semicolon or comma. e.g. tag1; tag2
              </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>
        </TextField>
      )}
      {tags.length > 0 && (
        <div className="flex w-full flex-wrap items-center gap-2">
          {tags.map((tag) => (
            <div key={tag} onClick={() => !readonly && handleRemoveTag(tag)} style={{ cursor: readonly ? 'default' : 'pointer' }}>
              <Tag tagText={tag} showDelete={!readonly} p="0" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
