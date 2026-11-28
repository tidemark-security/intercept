import { Tag } from '@/components/data-display/Tag';
import { TagsManager } from '@/components/forms/TagsManager';
import { useFeatureFlags } from '@/hooks/useFeatureFlags';
import { cn } from '@/utils/cn';

const DEFAULT_TAGS = ['Resolved', 'False Positive', 'True Positive', 'Escalated', 'No Action Required', 'Duplicate'];

interface SuggestedTagsFieldProps {
  tags: string[];
  onTagsChange: (tags: string[]) => void;
  placeholder: string;
}

export function SuggestedTagsField({ tags, onTagsChange, placeholder }: SuggestedTagsFieldProps) {
  const { data: featureFlags } = useFeatureFlags();
  const configuredTags = featureFlags?.case_closure_recommended_tags;
  const suggestedTags = configuredTags?.length ? configuredTags : DEFAULT_TAGS;
  const selectedTagKeys = new Set(tags.map((tag) => tag.toLowerCase()));
  const availableTags = suggestedTags.filter((tag) => !selectedTagKeys.has(tag.toLowerCase()));
  const suggestionsEmpty = availableTags.length === 0;

  return (
    <div className="flex w-full flex-col items-start gap-3 rounded-md border border-solid border-neutral-border bg-neutral-50 px-3 py-3">
      <div className={cn('flex w-full flex-col items-start gap-2', suggestionsEmpty && 'invisible')}>
        <span className="text-caption font-caption text-subtext-color">Suggested tags</span>
        <div className="grid w-full grid-cols-1">
          {/* Keep the original wrapped height as suggestions are picked. */}
          <div aria-hidden="true" className="invisible col-start-1 row-start-1 flex flex-wrap items-center gap-2">
            {suggestedTags.map((tag) => <Tag key={tag} tagText={tag} searchable={false} />)}
          </div>
          <div className="col-start-1 row-start-1 flex flex-wrap items-center self-start gap-2">
            {availableTags.map((tag) => (
              <button
                key={tag}
                type="button"
                className="cursor-pointer"
                // Tag stops clicks from bubbling to its parent.
                onClickCapture={() => onTagsChange([...tags, tag])}
              >
                <Tag tagText={tag} searchable={false} />
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className={cn('h-px w-full flex-none bg-neutral-border', suggestionsEmpty && 'invisible')} />
      <TagsManager tags={tags} onTagsChange={onTagsChange} label="Tags" placeholder={placeholder} reserveTagRow />
    </div>
  );
}
