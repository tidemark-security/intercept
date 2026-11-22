"use client";

import { useId } from "react";
import { BrainCircuit, ChevronDown, ChevronUp } from "lucide-react";

import { IconButton } from "@/components/buttons/IconButton";
import { Badge } from "@/components/data-display/Badge";
import { CopyableTimestamp } from "@/components/data-display/CopyableTimestamp";
import MarkdownContent from "@/components/data-display/MarkdownContent";
import { useAlertPanelExpansion } from "@/hooks/useAlertPanelExpansion";
import type { MatchedContextSection } from "@/types/generated/models/MatchedContextSection";
import { IconWrapper } from "@/utils/IconWrapper";

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

export function ContextCard({ context }: ContextCardProps) {
  const [isExpanded, setIsExpanded] = useAlertPanelExpansion("analyst-context", false);
  const contentId = useId();
  const contextItems = Array.isArray(context?.items) ? context.items : [];

  if (contextItems.length === 0) return null;

  const contextTotalCount = context?.total_count ?? contextItems.length;
  const contextOmittedCount = context?.omitted_count ?? 0;
  const visibleContextItems = contextItems.slice(0, 3);

  return (
    <section
      aria-label="Analyst Context"
      className="mt-2 flex w-full min-w-0 flex-col gap-2 border-t border-solid border-neutral-border pt-4"
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
        <IconButton
          className="ml-auto shrink-0"
          variant="neutral-tertiary"
          icon={isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          aria-label={isExpanded ? "Collapse analyst context" : "Expand analyst context"}
          aria-expanded={isExpanded}
          aria-controls={contentId}
          onClick={() => setIsExpanded(!isExpanded)}
        />
      </div>

      {!isExpanded && (
        <p className="truncate text-caption font-caption text-subtext-color">
          {contextItems[0]?.body ?? "Matched analyst context entries"}
        </p>
      )}

      <div id={contentId} hidden={!isExpanded}>
        {isExpanded && (
          <div className="flex min-w-0 flex-col gap-2">
            {visibleContextItems.map((item, index) => {
              const scopes = formatContextScope(item.criteria);

              return (
                <article
                  key={item.id ?? `${item.body}-${index}`}
                  className="flex min-w-0 flex-col gap-1 border border-solid border-neutral-border px-2.5 py-2"
                >
                  <MarkdownContent content={item.body} className="[&>:first-child]:mt-0 [&>:last-child]:mb-0" />
                  <div className="flex min-w-0 flex-wrap items-end gap-x-2 gap-y-1">
                    <div className="flex min-w-0 grow basis-28 flex-wrap items-center gap-1">
                      {scopes.map((scope, scopeIndex) => (
                        <Badge key={`${scope}-${scopeIndex}`} variant="neutral" className="h-auto min-h-5 max-w-full [&>span]:line-clamp-none [&>span]:[overflow-wrap:anywhere]">
                          {scope}
                        </Badge>
                      ))}
                    </div>
                    {(item.author || item.expires_at) && (
                      <div className="ml-auto grid w-full min-w-0 max-w-[26rem] grid-cols-[minmax(0,1fr)_9rem] items-end gap-x-3 text-caption font-caption text-subtext-color">
                        {item.author && (
                          <span className="col-start-1 row-start-1 min-w-0 [overflow-wrap:anywhere]">
                            Author: <span className="text-default-font">{item.author}</span>
                          </span>
                        )}
                        {item.expires_at && (
                          <CopyableTimestamp
                            value={item.expires_at}
                            label={Date.parse(item.expires_at) <= Date.now() ? "Expired" : "Expires"}
                            relativeOnly
                            className="col-start-2 row-start-1 min-w-0"
                          />
                        )}
                      </div>
                    )}
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
