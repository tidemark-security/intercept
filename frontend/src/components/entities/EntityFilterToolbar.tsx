"use client";

import React from "react";
import {
  Calendar,
  Check,
  CheckSquare,
  FileText,
  Minus,
  Plus,
  RotateCcw,
  Search,
  Square,
  Tag as TagIcon,
  User,
  X,
} from "lucide-react";

import { Toolbar, ToolbarButton } from "@/components/toolbar";
import { Button } from "@/components/buttons/Button";
import { TextField } from "@/components/forms/TextField";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { Accordion } from "@/components/misc/Accordion";
import type { FilterState } from "@/types/filters";
import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { app__api__routes__admin_auth__UserSummary } from "@/types/generated/models/app__api__routes__admin_auth__UserSummary";
import { cn } from "@/utils/cn";
import {
  formatForBackend,
  formatForDisplay,
  getRelativeTimeLabel,
  getUserTimezone,
  isValidDateRange,
  parseISO8601,
  parseRelativeTime,
} from "@/utils/dateFilters";
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
}

type TagMode = "include" | "exclude";

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

function compactAssigneeLabel(
  filters: FilterState | undefined,
  users: app__api__routes__admin_auth__UserSummary[],
) {
  const selected = filters?.assignee ?? [];
  if (selected.length === 0) return "Any";
  if (selected.length === 1) {
    if (selected[0] === "__unassigned__") return "Unassigned";
    return (
      users.find((user) => user.username === selected[0])?.username ??
      selected[0]
    );
  }
  return `${selected.length} assignees`;
}

function compactTimeLabel(value: FilterState["dateRange"]) {
  if (!value) return "All time";
  if (value.preset && value.preset !== "custom") {
    return getRelativeTimeLabel(value.preset);
  }
  return "Custom";
}

function compactTagLabel(includeTags: string[], excludeTags: string[]) {
  if (!includeTags.length && !excludeTags.length) return "No tags";
  return `+${includeTags.length} -${excludeTags.length}`;
}

function haveSameValues(left: readonly string[], right: readonly string[]) {
  if (left.length !== right.length) return false;
  const rightValues = new Set(right);
  return left.every((value) => rightValues.has(value));
}

function statusFilterDiffersFromDefault(
  filters: FilterState | undefined,
  statusOptions: StatusOption[],
) {
  const defaultStatuses = statusOptions.slice(0, 2).map((option) => option.value);
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

function AssigneeFilterDropdown({
  filters,
  users,
  isLoadingUsers,
  onChange,
}: {
  filters?: FilterState;
  users: app__api__routes__admin_auth__UserSummary[];
  isLoadingUsers: boolean;
  onChange: (assignees: string[] | null) => void;
}) {
  const [searchQuery, setSearchQuery] = React.useState("");
  const selected = filters?.assignee ?? [];
  const filteredUsers = React.useMemo(() => {
    const query = searchQuery.toLowerCase();
    if (!query) return users;
    return users.filter(
      (user) =>
        user.username.toLowerCase().includes(query) ||
        user.email?.toLowerCase().includes(query),
    );
  }, [searchQuery, users]);

  const toggleAssignee = (username: string) => {
    const next = selected.includes(username)
      ? selected.filter((assignee) => assignee !== username)
      : [...selected, username];
    onChange(next.length ? next : null);
  };

  return (
    <DropdownMenu.Root
      modal={false}
      onOpenChange={(open) => !open && setSearchQuery("")}
    >
      <DropdownMenu.Trigger asChild>
        <ToolbarButton
          icon={<User />}
          label="Assignee"
          value={compactAssigneeLabel(filters, users)}
          chevron
          active={selected.length > 0}
        />
      </DropdownMenu.Trigger>
      <DropdownMenu.Content
        side="bottom"
        align="start"
        sideOffset={6}
        className="max-h-[400px] min-w-[260px] overflow-y-auto"
      >
        {users.length > 0 ? (
          <div className="w-full border-b border-neutral-border px-2 py-2">
            <TextField
              className="h-8 w-full"
              variant="filled"
              label=""
              helpText=""
              icon={<Search />}
            >
              <TextField.Input
                placeholder="Search users..."
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onKeyDown={(event) => event.stopPropagation()}
              />
            </TextField>
          </div>
        ) : null}
        <DropdownMenu.DropdownItem
          icon={selected.includes("__unassigned__") ? <CheckSquare /> : <Square />}
          label="Unassigned"
          onClick={() => toggleAssignee("__unassigned__")}
          onSelect={(event) => event.preventDefault()}
        />
        {users.length > 0 ? <DropdownMenu.DropdownDivider /> : null}
        {isLoadingUsers ? (
          <DropdownMenu.DropdownItem icon={null} label="Loading users..." />
        ) : filteredUsers.length ? (
          filteredUsers.map((user) => (
            <DropdownMenu.DropdownItem
              key={user.userId}
              icon={selected.includes(user.username) ? <CheckSquare /> : <Square />}
              label={user.username}
              hint={user.email}
              onClick={() => toggleAssignee(user.username)}
              onSelect={(event) => event.preventDefault()}
            />
          ))
        ) : (
          <DropdownMenu.DropdownItem
            icon={null}
            label={searchQuery ? "No users found" : "No users available"}
          />
        )}
        {users.length > 0 ? (
          <>
            <DropdownMenu.DropdownDivider />
            <DropdownMenu.DropdownItem
              icon={null}
              label="Clear selection"
              onClick={() => onChange(null)}
            />
          </>
        ) : null}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}

function TimeFilterDropdown({
  value,
  onChange,
}: {
  value: FilterState["dateRange"];
  onChange: (value: FilterState["dateRange"]) => void;
}) {
  const [customStart, setCustomStart] = React.useState("");
  const [customEnd, setCustomEnd] = React.useState("");
  const [dateError, setDateError] = React.useState<string | null>(null);
  const [isOpen, setIsOpen] = React.useState(false);
  const userTimezone = React.useMemo(() => getUserTimezone(), []);
  const presets = ["-15m", "-1h", "-24h", "-7d", "-30d", "-90d"];

  const resetCustomState = () => {
    setCustomStart("");
    setCustomEnd("");
    setDateError(null);
  };

  const handlePresetClick = (relativeExpression: string | null) => {
    if (relativeExpression === null) {
      onChange(null);
      setIsOpen(false);
      resetCustomState();
      return;
    }

    const range = parseRelativeTime(relativeExpression);
    if (!range) return;

    onChange({
      start: formatForBackend(range.start),
      end: formatForBackend(range.end),
      preset: relativeExpression,
    });
    setIsOpen(false);
    resetCustomState();
  };

  const handleCustomApply = () => {
    setDateError(null);
    if (!customStart || !customEnd) {
      setDateError("Please enter both start and end dates");
      return;
    }

    const relativeStart = parseRelativeTime(customStart);
    const startDate = relativeStart ? relativeStart.start : parseISO8601(customStart);
    const relativeEnd = parseRelativeTime(customEnd);
    const endDate = relativeEnd ? relativeEnd.end : parseISO8601(customEnd);

    if (!startDate) {
      setDateError("Invalid start date format. Use YYYY-MM-DD HH:mm:ss or -7d");
      return;
    }
    if (!endDate) {
      setDateError("Invalid end date format. Use YYYY-MM-DD HH:mm:ss or now");
      return;
    }
    if (!isValidDateRange(startDate, endDate)) {
      setDateError("End date must be after start date");
      return;
    }

    onChange({
      start: formatForBackend(startDate),
      end: formatForBackend(endDate),
      preset: "custom",
    });
    setIsOpen(false);
    resetCustomState();
  };

  const customRangeLabel = React.useMemo(() => {
    if (!value || value.preset !== "custom") return "";
    const start = parseISO8601(value.start);
    const end = parseISO8601(value.end);
    if (!start || !end) return "Custom range";
    return `${formatForDisplay(start)} - ${formatForDisplay(end)}`;
  }, [value]);

  return (
    <DropdownMenu.Root open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenu.Trigger asChild>
        <ToolbarButton
          icon={<Calendar />}
          label="Time"
          value={compactTimeLabel(value)}
          chevron
          active={!!value}
          title={customRangeLabel || undefined}
        />
      </DropdownMenu.Trigger>
      <DropdownMenu.Content
        className="w-[320px] items-stretch p-0"
        side="bottom"
        align="start"
        sideOffset={6}
      >
        <Accordion
          trigger={
            <div className="flex w-full items-center justify-start gap-2 px-3 py-3">
              <span className="grow text-left text-body-bold font-body-bold text-default-font">
                Presets
              </span>
              <Accordion.Chevron />
            </div>
          }
          defaultOpen
        >
          <div className="flex w-full flex-col border-t border-neutral-border">
            {presets.map((expr) => (
              <button
                type="button"
                key={expr}
                className="flex w-full cursor-pointer items-center gap-2 bg-neutral-50 px-3 py-2 text-left hover:bg-neutral-100"
                onClick={() => handlePresetClick(expr)}
              >
                <span className="grow text-body font-body text-default-font">
                  {getRelativeTimeLabel(expr)}
                </span>
              </button>
            ))}
            <button
              type="button"
              className="flex w-full cursor-pointer items-center gap-2 bg-neutral-50 px-3 py-2 text-left hover:bg-neutral-100"
              onClick={() => handlePresetClick(null)}
            >
              <span className="grow text-body font-body text-default-font">
                All time
              </span>
            </button>
          </div>
        </Accordion>
        <div className="h-px w-full bg-neutral-border" />
        <Accordion
          trigger={
            <div className="flex w-full items-center justify-start gap-2 px-3 py-3">
              <span className="grow text-left text-body-bold font-body-bold text-default-font">
                Custom Range
              </span>
              <Accordion.Chevron />
            </div>
          }
        >
          <div className="flex w-full flex-col gap-3 border-t border-neutral-border bg-neutral-50 px-3 py-3">
            <span className="text-caption font-caption text-subtext-color">
              Times shown in your local timezone ({userTimezone})
            </span>
            <TextField
              className="h-auto w-full"
              label="Start date"
              helpText={dateError || ""}
              error={!!dateError}
            >
              <TextField.Input
                className="h-8 w-full"
                type="text"
                value={customStart}
                onChange={(event) => {
                  setCustomStart(event.target.value);
                  setDateError(null);
                }}
                onKeyDown={(event) => event.stopPropagation()}
                placeholder="YYYY-MM-DD HH:mm or -7d"
              />
            </TextField>
            <TextField className="h-auto w-full" label="End date" helpText="">
              <TextField.Input
                className="h-8 w-full"
                type="text"
                value={customEnd}
                onChange={(event) => {
                  setCustomEnd(event.target.value);
                  setDateError(null);
                }}
                onKeyDown={(event) => event.stopPropagation()}
                placeholder="YYYY-MM-DD HH:mm or now"
              />
            </TextField>
            <Button
              className="h-6 w-full"
              size="small"
              onClick={handleCustomApply}
              disabled={!customStart || !customEnd}
            >
              Apply
            </Button>
          </div>
        </Accordion>
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
  ...otherProps
}: EntityFilterToolbarProps) {
  const [tagMode, setTagMode] = React.useState<TagMode>("include");
  const [tagSearch, setTagSearch] = React.useState("");
  const [customTag, setCustomTag] = React.useState("");

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

  const filteredSuggestions = availableTags.filter((tag) => {
    if (!tagSearch.trim()) return true;
    return tag.tag.toLowerCase().includes(tagSearch.toLowerCase());
  });

  return (
    <Toolbar className={className} {...otherProps}>
      <AssigneeFilterDropdown
        filters={filters}
        users={assignees}
        isLoadingUsers={assigneesLoading}
        onChange={(assignees) => updateFilter("assignee", assignees)}
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
          {effectiveStatusOptions.map((option) => (
            <DropdownMenu.DropdownItem
              key={option.value}
              icon={(filters?.status ?? []).includes(option.value as AlertStatus) ? <CheckSquare /> : <Square />}
              label={option.label}
              onClick={() => handleStatusToggle(option.value)}
              onSelect={(event) => event.preventDefault()}
            />
          ))}
          <DropdownMenu.DropdownDivider />
          <DropdownMenu.DropdownItem
            icon={null}
            label="Clear selection"
            onClick={() => updateFilter("status", null)}
          />
        </DropdownMenu.Content>
      </DropdownMenu.Root>

      <TimeFilterDropdown
        value={filters?.dateRange ?? null}
        onChange={(value) => updateFilter("dateRange", value)}
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
  );
}
