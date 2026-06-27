"use client";

import React from "react";

import { Badge } from "@/components/data-display/Badge";
import { CopyableTimestamp } from "@/components/data-display/CopyableTimestamp";
import MarkdownContent from "@/components/data-display/MarkdownContent";
import { useTheme } from "@/contexts/ThemeContext";
import type { MatchedContextSection } from "@/types/generated/models/MatchedContextSection";
import { cn } from "@/utils/cn";

import { ExternalLink } from "lucide-react";

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
  const contextItems = Array.isArray(context?.items) ? context.items : [];

  if (contextItems.length === 0) {
    return null;
  }

  const contextTotalCount = context?.total_count ?? contextItems.length;
  const contextOmittedCount = context?.omitted_count ?? 0;
  const visibleContextItems = contextItems.slice(0, 3);
  const contextEntriesHref = buildContextEntriesHref(contextItems);

  return (
    <section
      className={cn(
        "flex w-full min-w-0 flex-col gap-3 rounded-md border border-solid border-neutral-border bg-default-background p-3",
        isDarkTheme ? "shadow-accent-1-shadow-sm" : "shadow-sm",
      )}
    >
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 border-l-2 border-solid border-brand-primary pl-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-heading-3 font-heading-3 uppercase text-default-font">
            Analyst Context
          </span>
          <Badge variant="brand">{contextTotalCount} active</Badge>
          {contextOmittedCount > 0 ? (
            <Badge variant="neutral">{contextOmittedCount} omitted</Badge>
          ) : null}
        </div>
        <a
          href={contextEntriesHref}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-7 flex-none items-center gap-1 rounded-md border border-solid border-neutral-border px-2 text-caption-bold font-caption-bold text-default-font transition-colors hover:border-brand-primary hover:text-brand-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus-border"
        >
          <span>View all context</span>
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      </div>

      <div className="grid w-full min-w-0 gap-2">
        {visibleContextItems.map((item, index) => {
          const scopes = formatContextScope(item.criteria as ContextCriterion[] | null | undefined);
          const key = item.id ?? `${item.body ?? "context"}-${index}`;
          const isPrimary = index === 0;

          return (
            <article
              key={key}
              className={cn(
                "flex min-w-0 flex-col gap-2 border-l-2 border-solid py-2 pl-3 pr-2",
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

      {contextItems.length > visibleContextItems.length ? (
        <span className="text-caption font-caption text-subtext-color">
          Showing first {visibleContextItems.length} of {contextTotalCount} matched context entries
        </span>
      ) : null}
    </section>
  );
}
