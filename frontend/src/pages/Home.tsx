"use client";

import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { Badge } from "@/components/data-display/Badge";
import { Table } from "@/components/data-display/Table";
import { Priority } from "@/components/misc/Priority";
import { State } from "@/components/misc/State";

import { useSession } from "@/contexts/sessionContext";
import { useTheme } from "@/contexts/ThemeContext";
import { useDashboard, usePriorityItems } from "@/hooks/useDashboard";
import { DashboardCard, getAlertCountPriority } from "@/components/cards/DashboardCard";
import { Loader } from "@/components/feedback/Loader";
import { cn } from "@/utils/cn";

import { AlertTriangle, CheckSquare, Star, NotebookPen, Search, ThumbsDown, ThumbsUp } from 'lucide-react';
import { IconWrapper } from "@/utils/IconWrapper";

function TipBanner() {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";
  const kbdClass = cn(
    "p-1 font-mono border",
    isDarkTheme ? "border-brand-1000 bg-brand-1100" : "border-neutral-border bg-brand-primary"
  );

  const tips = React.useMemo<Array<{ icon: React.ReactNode; content: React.ReactNode }>>(
    () => [
      {
        icon: <Search />,
        content: (
          <>
            You can press <kbd className={kbdClass}>Ctrl</kbd>+<kbd className={kbdClass}>K</kbd> / <kbd className={kbdClass}>⌘</kbd>+<kbd className={kbdClass}>K</kbd> from anywhere in Intercept to open instant search.
          </>
        ),
      },
      {
        icon: <Star />,
        content: (
          <>
            When you use the <ThumbsUp className="text-base inline" /> and <ThumbsDown className="text-base inline" /> buttons in AI chat, that feedback goes direct to your Intercept admins - it never leaves your environment.
          </>
        ),
      },
    ],
    [kbdClass]
  );

  const [tipIndex, setTipIndex] = useState(() => 
    Math.floor(Math.random() * tips.length)
  );

  // Rotate tips every 30 seconds if there are multiple
  useEffect(() => {
    if (tips.length <= 1) return;
    const interval = setInterval(() => {
      setTipIndex((prev) => (prev + 1) % tips.length);
    }, 30000);
    return () => clearInterval(interval);
  }, [tips.length]);

  return (
    <div
      className={cn(
        "flex w-full flex-col gap-4 px-6 py-4 text-caption-bold border border-neutral-border rounded-md",
        isDarkTheme ? "text-brand-500" : "text-black"
      )}
    >
      <div className="flex w-full items-center gap-2">
        <span className="grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font">
          Did you know?
        </span>
      </div>
      <div className="flex w-full items-center gap-2 my-2">
        <IconWrapper className="text-heading-2 pr-3">{tips[tipIndex]?.icon}</IconWrapper>
        <div>{tips[tipIndex]?.content}</div>
      </div>
    </div>
  );
}

function HomeDashboard() {
  const navigate = useNavigate();
  const { user } = useSession();
  const { data: stats, isLoading: statsLoading, error: statsError } = useDashboard({ myItems: true });
  const { data: priorityData, isLoading: priorityLoading } = usePriorityItems({ limit: 100 });

  const formatItemType = (type: string) => {
    switch (type) {
      case "alert": return { label: "Alert", icon: <AlertTriangle />, variant: "neutral" as const };
      case "case": return { label: "Case", icon: <NotebookPen />, variant: "neutral" as const };
      case "task": return { label: "Task", icon: <CheckSquare />, variant: "neutral" as const };
      default: return { label: type, icon: null, variant: "neutral" as const };
    }
  };

  // Convert API priority (UPPERCASE) to Priority component format (lowercase)
  const mapPriority = (priority: string | null | undefined): "info" | "low" | "medium" | "high" | "critical" | "extreme" => {
    if (!priority) return "info";
    return priority.toLowerCase() as "info" | "low" | "medium" | "high" | "critical" | "extreme";
  };

  // Convert API status to State component format
  type StateType = "closed" | "new" | "in_progress" | "escalated" | "closed_true_positive" | "closed_benign_positive" | "closed_false_positive" | "closed_unresolved" | "closed_duplicate" | "tsk_todo" | "tsk_in_progress" | "tsk_done";
  const mapStatus = (status: string, itemType: string): StateType => {
    // Task statuses
    if (itemType === "task") {
      switch (status) {
        case "TODO": return "tsk_todo";
        case "IN_PROGRESS": return "tsk_in_progress";
        case "DONE": return "tsk_done";
        default: return "tsk_todo";
      }
    }
    // Alert/Case statuses
    switch (status) {
      case "NEW": return "new";
      case "IN_PROGRESS": return "in_progress";
      case "ESCALATED": return "escalated";
      case "CLOSED_TP": return "closed_true_positive";
      case "CLOSED_BP": return "closed_benign_positive";
      case "CLOSED_FP": return "closed_false_positive";
      case "CLOSED_UNRESOLVED": return "closed_unresolved";
      case "CLOSED_DUPLICATE": return "closed_duplicate";
      case "CLOSED": return "closed";
      default: return "new";
    }
  };

  const navigateToItem = (type: string, humanId: string) => {
    switch (type) {
      case "alert": navigate(`/alerts/${humanId}`); break;
      case "case": navigate(`/cases/${humanId}`); break;
      case "task": navigate(`/tasks/${humanId}`); break;
    }
  };

  return (
    <DefaultPageLayout withContainer>
      <div className="container max-w-none flex w-full flex-col items-start gap-8 py-12">
        <div className="flex w-full items-center gap-4">
          <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
            <span className="text-heading-1 font-heading-1 text-default-font">
              Welcome back{user?.username ? `, ${user.username}` : ""}
            </span>
            <span className="text-body font-body text-subtext-color">
              Here&#39;s your personal overview
            </span>
          </div>
        </div>

        {/* Tip Banner */}
        <TipBanner />

        {/* Stats Cards */}
        {statsLoading ? (
          <div className="flex w-full items-center justify-center py-12">
            <Loader />
          </div>
        ) : statsError ? (
          <div className="flex w-full items-center justify-center py-12">
            <span className="text-body font-body text-error-600">
              Failed to load dashboard stats
            </span>
          </div>
        ) : (
          <div className="w-full">
            <DashboardCard
              icon={<AlertTriangle />}
              title="New Alerts"
              description={`${stats?.unacknowledged_alerts ?? 0} alerts awaiting triage`}
              link="/alerts?status=NEW"
              variant="stat"
              priority={getAlertCountPriority(stats?.unacknowledged_alerts ?? 0)}
            />
          </div>
        )}

        {/* My Open Items - sorted by priority */}
        <div className="flex w-full flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-default-background px-6 py-6">
          <div className="flex w-full items-center gap-2">
            <span className="grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font">
              My Open Items
            </span>
          </div>
          {priorityLoading ? (
            <div className="flex w-full items-center justify-center py-8">
              <Loader />
            </div>
          ) : priorityData?.items && priorityData.items.length > 0 ? (
            <>
              <Table
                header={
                  <Table.HeaderRow>
                    <Table.HeaderCell>ID</Table.HeaderCell>
                    <Table.HeaderCell>Title</Table.HeaderCell>
                    <Table.HeaderCell>Type</Table.HeaderCell>
                    <Table.HeaderCell>Status</Table.HeaderCell>
                    <Table.HeaderCell>Priority</Table.HeaderCell>
                  </Table.HeaderRow>
                }
              >
                {priorityData.items.map((item) => {
                  const typeInfo = formatItemType(item.item_type);
                  return (
                    <Table.Row 
                      key={`priority-${item.item_type}-${item.id}`}
                      onClick={() => navigateToItem(item.item_type, item.human_id)}
                      className="cursor-pointer hover:bg-neutral-50"
                    >
                      <Table.Cell>
                        <span className="text-caption font-caption text-subtext-color">
                          {item.human_id}
                        </span>
                      </Table.Cell>
                      <Table.Cell>
                        <span className="text-body-bold font-body-bold text-neutral-700 line-clamp-1">
                          {item.title}
                        </span>
                      </Table.Cell>
                      <Table.Cell>
                        <Badge variant={typeInfo.variant} icon={typeInfo.icon}>
                          {typeInfo.label}
                        </Badge>
                      </Table.Cell>
                      <Table.Cell>
                        <State state={mapStatus(item.status, item.item_type)} variant="small" />
                      </Table.Cell>
                      <Table.Cell>
                        <Priority priority={mapPriority(item.priority)} size="mini" />
                      </Table.Cell>
                    </Table.Row>
                  );
                })}
              </Table>
              {priorityData.truncated && (
                <div className="flex w-full items-center justify-center py-2">
                  <span className="text-caption font-caption text-subtext-color">
                    Showing first 100 items. Use filters on each page to see more.
                  </span>
                </div>
              )}
            </>
          ) : (
            <div className="flex w-full items-center justify-center py-8">
              <span className="text-body font-body text-subtext-color">
                No open items assigned to you
              </span>
            </div>
          )}
        </div>
      </div>
    </DefaultPageLayout>
  );
}

export default HomeDashboard;