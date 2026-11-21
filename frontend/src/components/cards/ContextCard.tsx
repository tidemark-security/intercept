"use client";

import { useId } from "react";
import { BrainCircuit, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";

import { IconButton } from "@/components/buttons/IconButton";
import { Badge } from "@/components/data-display/Badge";
import { CopyableTimestamp } from "@/components/data-display/CopyableTimestamp";
import MarkdownContent from "@/components/data-display/MarkdownContent";
import { useTheme } from "@/contexts/ThemeContext";
import { useAlertPanelExpansion } from "@/hooks/useAlertPanelExpansion";
import type { MatchedContextSection } from "@/types/generated/models/MatchedContextSection";
import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";
import styles from "./ContextCard.module.css";

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
  const [isExpanded, setIsExpanded] = useAlertPanelExpansion("analyst-context", true);
  const contentId = useId();
  const contextItems = Array.isArray(context?.items) ? context.items : [];

  if (contextItems.length === 0) return null;

  const contextTotalCount = context?.total_count ?? contextItems.length;
  const contextOmittedCount = context?.omitted_count ?? 0;
  const visibleContextItems = contextItems.slice(0, 3);

  return (
    <section
      aria-label="Analyst Context"
      className={cn(
        "flex w-full min-w-0 flex-col gap-2 border border-solid px-3 py-2",
        isExpanded ? "bg-default-background" : "bg-neutral-50",
        isDarkTheme ? "border-neutral-100" : "border-neutral-400",
      )}
    >
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <IconWrapper className="text-heading-3 text-default-font" aria-hidden="true">
            <BrainCircuit />
          </IconWrapper>
          <h2 className="text-heading-3 font-heading-3 text-default-font">Analyst Context</h2>
          <Badge variant="brand" className="h-5">{contextTotalCount} active</Badge>
          {contextOmittedCount > 0 && (
            <Badge variant="neutral" className="h-5">{contextOmittedCount} omitted</Badge>
          )}
        </div>
        <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
          <a
            href={buildContextEntriesHref(contextItems)}
            target="_blank"
            rel="noreferrer"
            className={cn(
              "inline-flex min-h-7 items-center gap-1 rounded-md border border-solid border-neutral-border px-2 text-caption-bold font-caption-bold text-default-font transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus-border",
              isDarkTheme ? "hover:border-brand-primary hover:text-brand-primary" : "hover:border-brand-800 hover:text-brand-800",
            )}
          >
            View all context
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
          <IconButton
            variant="neutral-tertiary"
            icon={isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            aria-label={isExpanded ? "Collapse analyst context" : "Expand analyst context"}
            aria-expanded={isExpanded}
            aria-controls={contentId}
            onClick={() => setIsExpanded(!isExpanded)}
          />
        </div>
      </div>

      {!isExpanded && (
        <p className="truncate text-caption font-caption text-subtext-color">
          {contextItems[0]?.body ?? "Matched analyst context entries"}
        </p>
      )}

      <div id={contentId} hidden={!isExpanded}>
        {isExpanded && (
          <div className={cn(styles.entries, "grid min-w-0 gap-2")}>
            {visibleContextItems.map((item, index) => {
              const scopes = formatContextScope(item.criteria);
              const isPrimary = index === 0;

              return (
                <article
                  key={item.id ?? `${item.body}-${index}`}
                  className={cn(
                    styles.entry,
                    "grid min-w-0 items-center gap-x-2 gap-y-1 border border-solid border-neutral-border px-2.5 py-2",
                    isPrimary && (isDarkTheme
                      ? "border-l-2 border-l-brand-primary bg-brand-1100"
                      : "border-l-2 border-l-brand-800 bg-brand-50"),
                  )}
                >
                  <MarkdownContent content={item.body} className={styles.body} />
                  <div className={cn(styles.metadata, "flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1")}>
                    {scopes.map((scope, scopeIndex) => (
                      <Badge key={`${scope}-${scopeIndex}`} variant="neutral" className="h-auto min-h-5 max-w-full [&>span]:line-clamp-none [&>span]:[overflow-wrap:anywhere]">
                        {scope}
                      </Badge>
                    ))}
                    <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-x-2 gap-y-1 text-caption font-caption text-subtext-color">
                      {item.author && (
                        <span className="min-w-0 [overflow-wrap:anywhere]">
                          Author: <span className="text-default-font">{item.author}</span>
                        </span>
                      )}
                      {item.expires_at && (
                        <CopyableTimestamp
                          value={item.expires_at}
                          label={Date.parse(item.expires_at) <= Date.now() ? "Expired" : "Expires"}
                          relativeOnly
                        />
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
            {contextItems.length > visibleContextItems.length && (
              <span className="text-caption font-caption text-subtext-color">
                Showing first {visibleContextItems.length} of {contextTotalCount} matched context entries
              </span>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
