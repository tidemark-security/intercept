"use client";

import React from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  CheckSquare,
  FileText,
  Minus,
  Plus,
  RotateCcw,
  Search,
  Square,
  Tag as TagIcon,
  X,
} from "lucide-react";

import { Toolbar, ToolbarButton } from "@/components/toolbar";
import { AssigneeSelector } from "@/components/forms/AssigneeSelector";
import { DateRangePicker } from "@/components/forms/DateRangePicker";
import { TextField } from "@/components/forms/TextField";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { SessionContext } from "@/contexts/sessionContext";
import type { FilterState, SortOrder } from "@/types/filters";
import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { app__api__routes__admin_auth__UserSummary } from "@/types/generated/models/app__api__routes__admin_auth__UserSummary";
import { cn } from "@/utils/cn";
import { ALERT_STATUS_OPTIONS, formatAlertStatusLabel, type StatusOption } from "@/utils/statusLabels";

export interface EntityFilterToolbarProps
  extends React.HTMLAttributes<HTMLDivElement> {
  filters?: FilterState;
  onFilterChange?: (filters: FilterState) => void;
  assignees?: app__api__routes__admin_auth__UserSummary[];
  assigneesLoading?: boolean;
  statusOptions?: StatusOption[];
  showTagFilters?: boolean;
  availableTags?: Array<{ tag: string; count: number }>;
  actions?: React.ReactNode;
  sortOptions?: SortOption[];
}

type TagMode = "include" | "exclude";

export interface SortOption {
  value: string;
  label: string;
  directionLabel?: {
    asc: string;
    desc: string;
  };
}

function emptyFilters(): FilterState {
  return {
    search: "",
    assignee: null,
    status: null,
    includeTags: null,
    excludeTags: null,
    dateRange: null,
  };
}

function normalizeTags(tags: string[] | null | undefined) {
  return tags ?? [];
}

function addTag(tags: string[], tag: string) {
  const trimmed = tag.trim();
  if (!trimmed || tags.includes(trimmed)) return tags;
  return [...tags, trimmed];
}

function removeTag(tags: string[], tag: string) {
  return tags.filter((candidate) => candidate !== tag);
}

function statusButtonLabel(
  filters: FilterState | undefined,
  statusOptions: StatusOption[],
) {
  const selected = filters?.status ?? [];
  if (selected.length === 0) return "Status";

  const labelFor = (status: string) =>
    statusOptions.find((option) => option.value === status)?.label ??
    formatAlertStatusLabel(status as AlertStatus);

  if (selected.length === 1) return labelFor(selected[0]);
  if (selected.length === 2) return selected.map(labelFor).join(", ");
  return `${selected.length} statuses`;
}

function compactStatusLabel(
  filters: FilterState | undefined,
  statusOptions: StatusOption[],
) {
  const selected = filters?.status ?? [];
  if (selected.length === 0) return "Any";
  if (selected.length === 1) return statusButtonLabel(filters, statusOptions);
  return `${selected.length} statuses`;
}

function compactTagLabel(includeTags: string[], excludeTags: string[]) {
  if (!includeTags.length && !excludeTags.length) return "No tags";
  return `+${includeTags.length} -${excludeTags.length}`;
}

function compactSortLabel(
  filters: FilterState | undefined,
  sortOptions: SortOption[],
) {
  const selectedSortBy = filters?.sortBy ?? sortOptions[0]?.value;
  const selectedOption = sortOptions.find(
    (option) => option.value === selectedSortBy,
  );
  const sortOrder = filters?.sortOrder ?? "desc";

  if (!selectedOption) return "Default";

  return selectedOption.directionLabel?.[sortOrder] ?? selectedOption.label;
}

function sortFilterDiffersFromDefault(
  filters: FilterState | undefined,
  sortOptions: SortOption[],
) {
  const defaultSortBy = sortOptions[0]?.value;
  if (!defaultSortBy) return false;

  const selectedSortBy = filters?.sortBy ?? defaultSortBy;
  const selectedSortOrder = filters?.sortOrder ?? "desc";

  return selectedSortBy !== defaultSortBy || selectedSortOrder !== "desc";
}

function haveSameValues(left: readonly string[], right: readonly string[]) {
  if (left.length !== right.length) return false;
  const rightValues = new Set(right);
  return left.every((value) => rightValues.has(value));
}

function isClosedStatus(status: string) {
  return status === "DONE" || status.startsWith("CLOSED");
}

function getStatusGroups(statusOptions: StatusOption[]) {
  return {
    all: statusOptions.map((option) => option.value),
    defaultOpen: statusOptions
      .slice(0, 2)
      .filter((option) => !isClosedStatus(option.value))
      .map((option) => option.value),
    open: statusOptions
      .filter((option) => !isClosedStatus(option.value))
      .map((option) => option.value),
    closed: statusOptions
      .filter((option) => isClosedStatus(option.value))
      .map((option) => option.value),
  };
}

function statusFilterDiffersFromDefault(
  filters: FilterState | undefined,
  statusOptions: StatusOption[],
) {
  const defaultStatuses = getStatusGroups(statusOptions).defaultOpen;
  const selectedStatuses = (filters?.status ?? []) as string[];

  return !haveSameValues(selectedStatuses, defaultStatuses);
}

function FilterValueChip({
  tone,
  children,
  onRemove,
}: {
  tone: "include" | "exclude";
  children: React.ReactNode;
  onRemove: () => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        "flex h-6 max-w-full items-center gap-1 rounded-md border px-2 text-caption font-caption transition-colors",
        tone === "include"
          ? "border-brand-primary/60 bg-brand-primary/10 text-default-font hover:bg-brand-primary/15"
          : "border-error-600/60 bg-error-600/10 text-default-font hover:bg-error-600/15",
      )}
      onClick={onRemove}
    >
      <span className="min-w-0 truncate">{children}</span>
      <X className="shrink-0 text-[12px]" />
    </button>
  );
}

function SortDropdown({
  filters,
  options,
  onChange,
}: {
  filters?: FilterState;
  options: SortOption[];
  onChange: (sortBy: string, sortOrder: SortOrder) => void;
}) {
  const selectedSortBy = filters?.sortBy ?? options[0]?.value;
  const selectedSortOrder = filters?.sortOrder ?? "desc";

  if (!options.length) return null;

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <ToolbarButton
          icon={<ArrowUpDown />}
          label="Sort"
          value={compactSortLabel(filters, options)}
          chevron
          active={sortFilterDiffersFromDefault(filters, options)}
        />
      </DropdownMenu.Trigger>
      <DropdownMenu.Content side="bottom" align="start" sideOffset={6}>
        {options.map((option) => (
          <React.Fragment key={option.value}>
            <DropdownMenu.DropdownItem
              icon={
                selectedSortBy === option.value && selectedSortOrder === "desc" ? (
                  <Check />
                ) : (
                  <ArrowDown />
                )
              }
              label={option.directionLabel?.desc ?? `${option.label}, descending`}
              onClick={() => onChange(option.value, "desc")}
            />
            <DropdownMenu.DropdownItem
              icon={
                selectedSortBy === option.value && selectedSortOrder === "asc" ? (
                  <Check />
                ) : (
                  <ArrowUp />
                )
              }
              label={option.directionLabel?.asc ?? `${option.label}, ascending`}
              onClick={() => onChange(option.value, "asc")}
            />
          </React.Fragment>
        ))}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}

export function EntityFilterToolbar({
  className,
  filters,
  onFilterChange,
  assignees = [],
  assigneesLoading = false,
  statusOptions,
  showTagFilters = false,
  availableTags = [],
  actions,
  sortOptions = [],
  ...otherProps
}: EntityFilterToolbarProps) {
  const [tagMode, setTagMode] = React.useState<TagMode>("include");
  const [tagSearch, setTagSearch] = React.useState("");
  const [customTag, setCustomTag] = React.useState("");

  const sessionContext = React.useContext(SessionContext);
  const currentUsername = sessionContext?.user?.username ?? null;

  const effectiveStatusOptions = statusOptions ?? ALERT_STATUS_OPTIONS;
  const includeTags = normalizeTags(filters?.includeTags);
  const excludeTags = normalizeTags(filters?.excludeTags);
  const statusFilterModified = statusFilterDiffersFromDefault(
    filters,
    effectiveStatusOptions,
  );

  const updateFilter = <K extends keyof FilterState>(
    key: K,
    value: FilterState[K],
  ) => {
    onFilterChange?.({
      ...emptyFilters(),
      ...filters,
      [key]: value,
    } as FilterState);
  };

  const updateTags = (mode: TagMode, tags: string[]) => {
    updateFilter(
      mode === "include" ? "includeTags" : "excludeTags",
      tags.length ? tags : null,
    );
  };

  const handleTagAdd = (mode: TagMode, tag: string) => {
    const current = mode === "include" ? includeTags : excludeTags;
    const other = mode === "include" ? excludeTags : includeTags;
    const nextCurrent = addTag(current, tag);
    const nextOther = removeTag(other, tag);

    onFilterChange?.({
      ...emptyFilters(),
      ...filters,
      includeTags:
        mode === "include"
          ? nextCurrent.length
            ? nextCurrent
            : null
          : nextOther.length
            ? nextOther
            : null,
      excludeTags:
        mode === "exclude"
          ? nextCurrent.length
            ? nextCurrent
            : null
          : nextOther.length
            ? nextOther
            : null,
    } as FilterState);
  };

  const handleCustomTagSubmit = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter" && event.key !== "," && event.key !== ";") return;
    event.preventDefault();
    customTag
      .split(/[;,]/)
      .map((tag) => tag.trim())
      .filter(Boolean)
      .forEach((tag) => handleTagAdd(tagMode, tag));
    setCustomTag("");
  };

  const handleStatusToggle = (status: string) => {
    const current = (filters?.status ?? []) as string[];
    const next = current.includes(status)
      ? current.filter((candidate) => candidate !== status)
      : [...current, status];

    updateFilter("status", next.length ? (next as FilterState["status"]) : null);
  };

  const handleStatusGroupSelect = (statuses: string[]) => {
    updateFilter("status", statuses as FilterState["status"]);
  };

  const handleSortChange = (sortBy: string, sortOrder: SortOrder) => {
    onFilterChange?.({
      ...emptyFilters(),
      ...filters,
      sortBy,
      sortOrder,
    } as FilterState);
  };

  const filteredSuggestions = availableTags.filter((tag) => {
    if (!tagSearch.trim()) return true;
    return tag.tag.toLowerCase().includes(tagSearch.toLowerCase());
  });
  const selectedStatuses = (filters?.status ?? []) as string[];
  const statusGroups = getStatusGroups(effectiveStatusOptions);
  const statusGroupItems = [
    { label: "All", statuses: statusGroups.all },
    { label: "All Open", statuses: statusGroups.open },
    { label: "All Closed", statuses: statusGroups.closed },
  ].filter((item) => item.statuses.length > 0);

  return (
    <div className={cn("flex w-full flex-col gap-3", className)} {...otherProps}>
      <Toolbar>
        <AssigneeSelector
          presentation="toolbar"
          mode="filter"
          currentUser={currentUsername}
          selectedAssignees={filters?.assignee ?? null}
          users={assignees}
          isLoadingUsers={assigneesLoading}
          onSelectionChange={(nextAssignees) =>
            updateFilter("assignee", nextAssignees)
          }
        />

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <ToolbarButton
              icon={<FileText />}
              label="Status"
              value={compactStatusLabel(filters, effectiveStatusOptions)}
              chevron
              active={statusFilterModified}
            />
          </DropdownMenu.Trigger>
          <DropdownMenu.Content side="bottom" align="start" sideOffset={6}>
            {statusGroupItems.map((item) => (
              <DropdownMenu.DropdownItem
                key={item.label}
                icon={
                  haveSameValues(selectedStatuses, item.statuses) ? (
                    <CheckSquare />
                  ) : (
                    <Square />
                  )
                }
                label={item.label}
                onClick={() => handleStatusGroupSelect(item.statuses)}
                onSelect={(event) => event.preventDefault()}
              />
            ))}
            <DropdownMenu.DropdownDivider />
            {effectiveStatusOptions.map((option) => (
              <DropdownMenu.DropdownItem
                key={option.value}
                icon={selectedStatuses.includes(option.value as AlertStatus) ? <CheckSquare /> : <Square />}
                label={option.label}
                onClick={() => handleStatusToggle(option.value)}
                onSelect={(event) => event.preventDefault()}
              />
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Root>

        <DateRangePicker
          presentation="toolbar"
          value={filters?.dateRange ?? null}
          onChange={(value) => updateFilter("dateRange", value)}
        />

        <SortDropdown
          filters={filters}
          options={sortOptions}
          onChange={handleSortChange}
        />

        {showTagFilters ? (
          <DropdownMenu.Root modal={false}>
          <DropdownMenu.Trigger asChild>
            <ToolbarButton
              icon={<TagIcon />}
              label="Tags"
              value={compactTagLabel(includeTags, excludeTags)}
              chevron
              active={!!includeTags.length || !!excludeTags.length}
            />
          </DropdownMenu.Trigger>
          <DropdownMenu.Content
            side="bottom"
            align="end"
            sideOffset={8}
            className="w-[min(520px,calc(100vw-32px))] gap-3 p-3"
          >
            <div className="flex w-full items-center gap-2">
              <button
                type="button"
                className={cn(
                  "flex h-8 flex-1 items-center justify-center gap-1 rounded-md border text-caption-bold font-caption-bold",
                  tagMode === "include"
                    ? "border-brand-primary bg-brand-primary/15 text-default-font"
                    : "border-neutral-border bg-default-background text-subtext-color hover:text-default-font",
                )}
                onClick={() => setTagMode("include")}
              >
                <Plus /> Include
              </button>
              <button
                type="button"
                className={cn(
                  "flex h-8 flex-1 items-center justify-center gap-1 rounded-md border text-caption-bold font-caption-bold",
                  tagMode === "exclude"
                    ? "border-error-600 bg-error-600/15 text-default-font"
                    : "border-neutral-border bg-default-background text-subtext-color hover:text-default-font",
                )}
                onClick={() => setTagMode("exclude")}
              >
                <Minus /> Exclude
              </button>
            </div>

            <div className="grid w-full gap-2 md:grid-cols-[1fr_1fr]">
              <TextField className="h-8 w-full" variant="filled" label="" helpText="" icon={<Search />}>
                <TextField.Input
                  placeholder="Find tags"
                  value={tagSearch}
                  onChange={(event) => setTagSearch(event.target.value)}
                  onKeyDown={(event) => event.stopPropagation()}
                />
              </TextField>
              <TextField
                className="h-8 w-full"
                variant="filled"
                label=""
                helpText=""
                icon={tagMode === "include" ? <Plus /> : <Minus />}
              >
                <TextField.Input
                  placeholder={tagMode === "include" ? "Add include tag" : "Add exclude tag"}
                  value={customTag}
                  onChange={(event) => setCustomTag(event.target.value)}
                  onKeyDown={(event) => {
                    event.stopPropagation();
                    handleCustomTagSubmit(event);
                  }}
                />
              </TextField>
            </div>

            <div className="flex w-full flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-caption-bold font-caption-bold uppercase text-subtext-color">
                  Tags in current results
                </span>
                <span className="text-caption font-caption text-subtext-color">
                  {tagMode === "include" ? "Must have" : "Must not have"}
                </span>
              </div>
              <div className="grid max-h-48 w-full gap-1 overflow-y-auto pr-1 md:grid-cols-2">
                {filteredSuggestions.length ? (
                  filteredSuggestions.map((tag) => {
                    const selectedInMode = (tagMode === "include" ? includeTags : excludeTags).includes(tag.tag);

                    return (
                      <button
                        type="button"
                        key={tag.tag}
                        aria-label={`${tag.tag} ${tag.count}`}
                        className="flex h-9 w-full items-center gap-2 rounded-md border border-neutral-border bg-default-background px-2 text-left hover:border-neutral-300 hover:bg-neutral-100"
                        onClick={() => handleTagAdd(tagMode, tag.tag)}
                      >
                        <span
                          className={cn(
                            "flex h-4 w-4 items-center justify-center rounded-sm border",
                            selectedInMode
                              ? tagMode === "include"
                                ? "border-brand-primary bg-brand-primary text-black"
                                : "border-error-600 bg-error-600 text-black"
                              : "border-neutral-border text-transparent",
                          )}
                        >
                          <Check className="text-[12px]" />
                        </span>
                        <span className="min-w-0 flex-1 truncate text-body font-body text-default-font">
                          {tag.tag}
                        </span>
                        <span className="font-['Kode_Mono'] text-caption font-caption text-accent-1-primary">
                          {tag.count}
                        </span>
                      </button>
                    );
                  })
                ) : (
                  <span className="px-1 py-2 text-caption font-caption text-subtext-color">
                    No tags in current results
                  </span>
                )}
              </div>
            </div>

            <div className="grid w-full gap-3 border-t border-neutral-border pt-3 md:grid-cols-2">
              <div className="flex min-w-0 flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-caption-bold font-caption-bold text-default-font">Include</span>
                  <span className="text-caption font-caption text-subtext-color">{includeTags.length}</span>
                </div>
                <div className="flex min-h-8 flex-wrap items-center gap-1.5">
                  {includeTags.length ? (
                    includeTags.map((tag) => (
                      <FilterValueChip
                        key={tag}
                        tone="include"
                        onRemove={() => updateTags("include", removeTag(includeTags, tag))}
                      >
                        {tag}
                      </FilterValueChip>
                    ))
                  ) : (
                    <span className="text-caption font-caption text-subtext-color">
                      No include tags
                    </span>
                  )}
                </div>
              </div>
              <div className="flex min-w-0 flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-caption-bold font-caption-bold text-default-font">Exclude</span>
                  <span className="text-caption font-caption text-subtext-color">{excludeTags.length}</span>
                </div>
                <div className="flex min-h-8 flex-wrap items-center gap-1.5">
                  {excludeTags.length ? (
                    excludeTags.map((tag) => (
                      <FilterValueChip
                        key={tag}
                        tone="exclude"
                        onRemove={() => updateTags("exclude", removeTag(excludeTags, tag))}
                      >
                        {tag}
                      </FilterValueChip>
                    ))
                  ) : (
                    <span className="text-caption font-caption text-subtext-color">
                      No exclude tags
                    </span>
                  )}
                </div>
              </div>
            </div>
          </DropdownMenu.Content>
          </DropdownMenu.Root>
        ) : null}

        <ToolbarButton
          icon={<RotateCcw />}
          label="Reset"
          value="Clear all"
          onClick={() => onFilterChange?.(emptyFilters())}
        />
      </Toolbar>
      {actions ? <div className="w-full">{actions}</div> : null}
    </div>
  );
}
