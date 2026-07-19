"use client";

import React, { useState } from "react";

import { IconButton } from "@/components/buttons/IconButton";
import { Badge } from "@/components/data-display/Badge";
import { CopyableTimestamp } from "@/components/data-display/CopyableTimestamp";
import MarkdownContent from "@/components/data-display/MarkdownContent";
import { useTheme } from "@/contexts/ThemeContext";
import type { MatchedContextSection } from "@/types/generated/models/MatchedContextSection";
import { cn } from "@/utils/cn";

import { BrainCircuit, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";

interface ContextCardProps {
  context?: MatchedContextSection | null;
}

type ContextCriterion = Record<string, string> & {
  type?: string | null;
  value?: string | null;
};

function formatCriterionType(value: string | null | undefined) {
  if (!value) return "Scope";
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatContextScope(criteria: ContextCriterion[] | null | undefined) {
  if (!criteria || criteria.length === 0) return ["Global"];
  return criteria.map((criterion) => {
    const type = formatCriterionType(criterion.type);
    return criterion.value ? `${type}: ${criterion.value}` : type;
  });
}

function buildContextEntriesHref(contextItems: MatchedContextSection["items"]) {
  const items = contextItems ?? [];
  const ids = items
    .map((item) => item.id)
    .filter((id): id is number => id !== null && id !== undefined)
    .map((id) => String(id).trim())
    .filter(Boolean);
  const params = new URLSearchParams();
  params.set("include_expired", "true");

  if (ids.length > 0) {
    params.set("ids", ids.join(","));
  } else {
    const fallbackTerms = items.flatMap((item) => {
      const criteria = item.criteria ?? [];
      const criteriaTerms = criteria.flatMap((criterion) => [
        criterion.type ?? "",
        criterion.value ?? "",
      ]);
      return [...criteriaTerms, item.body ?? ""];
    }).map((term) => term.trim()).filter(Boolean);

    if (fallbackTerms.length > 0) {
      params.set("q", fallbackTerms[0]);
    }
  }

  const query = params.toString();
  return query ? `/context-entries?${query}` : "/context-entries";
}

export function ContextCard({ context }: ContextCardProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";
  const [isExpanded, setIsExpanded] = useState(true);
  const contextItems = Array.isArray(context?.items) ? context.items : [];

  if (contextItems.length === 0) {
    return null;
  }

  const contextTotalCount = context?.total_count ?? contextItems.length;
  const contextOmittedCount = context?.omitted_count ?? 0;
  const visibleContextItems = contextItems.slice(0, 3);
  const contextEntriesHref = buildContextEntriesHref(contextItems);

  if (!isExpanded) {
    return (
      <div
        className={cn(
          "flex w-full flex-wrap items-center gap-4 rounded-md border border-solid bg-neutral-50 px-4 py-3 shadow-sm",
          isDarkTheme ? "border-neutral-100" : "border-neutral-600",
        )}
      >
        <div className="flex items-center gap-3">
          <BrainCircuit className="h-5 w-5 text-subtext-color" />
          <span className="text-heading-3 font-heading-3 text-subtext-color">
            Analyst Context
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="brand">{contextTotalCount} active</Badge>
          {contextOmittedCount > 0 ? (
            <Badge variant="neutral">{contextOmittedCount} omitted</Badge>
          ) : null}
        </div>
        <div className="hidden h-4 w-px flex-none flex-col items-center gap-2 bg-neutral-border sm:flex" />
        <span className="min-w-[200px] grow shrink basis-0 truncate text-body font-body text-subtext-color">
          {contextItems[0]?.body ?? "Matched analyst context entries"}
        </span>
        <div className="flex grow shrink-0 basis-0 items-center justify-end gap-2">
          <a
            href={contextEntriesHref}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-7 flex-none items-center gap-1 rounded-md border border-solid border-neutral-border px-2 text-caption-bold font-caption-bold text-default-font transition-colors hover:border-brand-primary hover:text-brand-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus-border"
          >
            <span>View all context</span>
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
          <IconButton
            variant="neutral-tertiary"
            icon={<ChevronDown className="h-4 w-4" />}
            aria-label="Expand analyst context"
            onClick={() => setIsExpanded(true)}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex w-full flex-col items-start gap-6 border border-solid bg-default-background px-6 py-6",
        isDarkTheme ? "border-neutral-100" : "border-neutral-400",
      )}
    >
      <div className="flex w-full flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <BrainCircuit className="h-5 w-5 text-default-font" />
          <span className="text-heading-3 font-heading-3 text-default-font">
            Analyst Context
          </span>
        </div>
        <Badge variant="brand">{contextTotalCount} active</Badge>
        {contextOmittedCount > 0 ? (
          <Badge variant="neutral">{contextOmittedCount} omitted</Badge>
        ) : null}
        <div className="flex grow shrink-0 basis-0 items-center justify-end gap-2">
          <a
            href={contextEntriesHref}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-7 flex-none items-center gap-1 rounded-md border border-solid border-neutral-border px-2 text-caption-bold font-caption-bold text-default-font transition-colors hover:border-brand-primary hover:text-brand-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus-border"
          >
            <span>View all context</span>
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
          <IconButton
            variant="neutral-tertiary"
            icon={<ChevronUp className="h-4 w-4" />}
            aria-label="Collapse analyst context"
            onClick={() => setIsExpanded(false)}
          />
        </div>
      </div>

      <div className="flex h-px w-full flex-none bg-neutral-border" />

      <div className="flex w-full flex-col items-start gap-4">
        <span className="text-heading-3 font-heading-3 text-default-font">
          Matched Context
        </span>
        <div className="grid w-full min-w-0 gap-3">
          {visibleContextItems.map((item, index) => {
            const scopes = formatContextScope(item.criteria as ContextCriterion[] | null | undefined);
            const key = item.id ?? `${item.body ?? "context"}-${index}`;
            const isPrimary = index === 0;

            return (
              <article
                key={key}
                className={cn(
                  "flex min-w-0 flex-col gap-2 rounded-md border border-solid px-3 py-2",
                  isPrimary
                    ? cn(
                      "border-brand-primary",
                      isDarkTheme ? "bg-brand-1100" : "bg-brand-50",
                    )
                    : "border-neutral-border bg-default-background",
                )}
              >
                {item.body ? (
                  <MarkdownContent
                    content={item.body}
                    className={cn(
                      "[overflow-wrap:anywhere] [&_*]:text-inherit [&_p]:!my-0",
                      isPrimary
                        ? "text-body-bold font-body-bold text-default-font"
                        : "text-body font-body text-default-font",
                    )}
                  />
                ) : null}

                <div className="flex min-w-0 flex-wrap gap-1.5">
                  {scopes.map((scope, scopeIndex) => (
                    <Badge key={`${scope}-${scopeIndex}`} variant="neutral">
                      {scope}
                    </Badge>
                  ))}
                </div>

                <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-caption font-caption text-subtext-color">
                  {item.author ? (
                    <span className="min-w-0 truncate">
                      Author: <span className="text-default-font">{item.author}</span>
                    </span>
                  ) : null}
                  {item.expires_at ? (
                    <div className="flex min-w-0 items-center gap-1">
                      <span>Expires:</span>
                      <CopyableTimestamp
                        value={item.expires_at}
                        showFull
                        variant="default-right"
                        className="min-w-0 max-w-full flex-wrap"
                        textClassName="text-default-font"
                      />
                    </div>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      </div>

      {contextItems.length > visibleContextItems.length ? (
        <span className="text-caption font-caption text-subtext-color">
          Showing first {visibleContextItems.length} of {contextTotalCount} matched context entries
        </span>
      ) : null}
    </div>
  );
}
