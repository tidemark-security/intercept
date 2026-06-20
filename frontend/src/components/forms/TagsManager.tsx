import { useState, type KeyboardEvent } from 'react';
import { Tags } from 'lucide-react';

import { Tag } from '@/components/data-display/Tag';
import { TextField } from '@/components/forms/TextField';
import { Tooltip } from '@/components/overlays/Tooltip';

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
  label = 'Tags',
  placeholder,
  className,
  inline = false,
  readonly = false,
}: TagsManagerProps) {
  const [inputValue, setInputValue] = useState('');
  const effectivePlaceholder = placeholder || (inline ? '+ Add tags...' : 'Enter tags and press Enter');

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && inputValue.trim()) {
      event.preventDefault();

      const newTags = inputValue
        .split(/[;,]/)
        .map((tag) => tag.trim())
        .filter((tag) => tag && !tags.includes(tag));

      if (newTags.length > 0) {
        onTagsChange([...tags, ...newTags]);
        setInputValue('');
      }
    }
  };

  const handleRemoveTag = (tagToRemove: string) => {
    onTagsChange(tags.filter((tag) => tag !== tagToRemove));
  };

  const renderTag = (tag: string) => (
    <Tag
      key={tag}
      tagText={tag}
      showDelete={!readonly}
      onDelete={readonly ? undefined : () => handleRemoveTag(tag)}
      p="0"
    />
  );

  if (inline) {
    return (
      <div className={`flex w-full flex-wrap items-center gap-1.5 ${className || ''}`}>
        {tags.map(renderTag)}
        {!readonly ? (
          <div className="group/input relative grid items-center justify-start">
            <span className="invisible pointer-events-none col-start-1 row-start-1 whitespace-pre px-0.5 text-body font-body opacity-0">
              {inputValue || effectivePlaceholder}
            </span>
            <input
              className="col-start-1 row-start-1 h-6 w-full min-w-[4ch] border-b border-transparent bg-transparent px-0.5 text-body font-body text-default-font outline-none transition-all placeholder:text-subtext-color hover:placeholder:text-neutral-300 focus:border-brand-primary focus:placeholder:text-neutral-200"
              placeholder={effectivePlaceholder}
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className={`flex w-full flex-col items-start gap-4 ${className || ''}`}>
      {!readonly ? (
        <TextField className="h-auto w-full flex-none" label={label} helpText="" icon={<Tags />}>
          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger asChild>
                <TextField.Input
                  placeholder={effectivePlaceholder}
                  value={inputValue}
                  onChange={(event) => setInputValue(event.target.value)}
                  onKeyDown={handleKeyDown}
                />
              </Tooltip.Trigger>
              <Tooltip.Content side="bottom" align="center" sideOffset={4}>
                Separate multiple tags with a semicolon or comma. e.g. tag1; tag2
              </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>
        </TextField>
      ) : null}
      {tags.length > 0 ? (
        <div className="flex w-full flex-wrap items-center gap-2">
          {tags.map(renderTag)}
        </div>
      ) : null}
    </div>
  );
}
