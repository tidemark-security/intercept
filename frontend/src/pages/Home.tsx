"use client";

import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { Badge } from "@/components/data-display/Badge";
import { RelativeTime } from "@/components/data-display/RelativeTime";
import { Table } from "@/components/data-display/Table";
import { Priority } from "@/components/misc/Priority";
import { State } from "@/components/misc/State";
import { CarouselControl } from "@/components/navigation/CarouselControl";

import { useSession } from "@/contexts/sessionContext";
import { useTheme } from "@/contexts/ThemeContext";
import { useDashboard, usePriorityItems, useRecentItems } from "@/hooks/useDashboard";
import {
  formatOpenItemAge,
  type MyOpenItemsSortKey,
  useMyOpenItemsSort,
  useMyOpenItemsWithCreatedAt,
} from "@/hooks/useMyOpenItemsSort";
import { DashboardCard, getAlertCountPriority } from "@/components/cards/DashboardCard";
import { Loader } from "@/components/feedback/Loader";
import { cn } from "@/utils/cn";

import { ArrowDown, ArrowUp, ArrowUpDown, Bell, CheckSquare, Star, NotebookPen, Search, ThumbsDown, ThumbsUp } from 'lucide-react';
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

  // Rotate tips every 30 seconds if there are multiple. Manual navigation
  // resets the timer since tipIndex is a dependency.
  useEffect(() => {
    if (tips.length <= 1) return;
    const interval = setInterval(() => {
      setTipIndex((prev) => (prev + 1) % tips.length);
    }, 30000);
    return () => clearInterval(interval);
  }, [tips.length, tipIndex]);

  const showPreviousTip = () => setTipIndex((prev) => (prev - 1 + tips.length) % tips.length);
  const showNextTip = () => setTipIndex((prev) => (prev + 1) % tips.length);

  return (
    <div
      className={cn(
        "group flex w-full flex-col gap-4 px-6 py-4 text-caption-bold border border-neutral-border rounded-md",
        isDarkTheme ? "text-brand-500" : "text-black"
      )}
    >
      <div className="flex w-full items-center gap-2">
        <span className="grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font">
          Did you know?
        </span>
      </div>
      <div className="grid w-full my-2">
        {tips.map((tip, index) => (
          <div
            key={index}
            aria-hidden={index !== tipIndex}
            className={cn(
              "col-start-1 row-start-1 flex w-full items-center gap-2 transition-opacity duration-500",
              index === tipIndex ? "opacity-100" : "pointer-events-none opacity-0"
            )}
          >
            <IconWrapper className="text-heading-2 pr-3">{tip.icon}</IconWrapper>
            <div>{tip.content}</div>
          </div>
        ))}
      </div>
      <CarouselControl
        count={tips.length}
        index={tipIndex}
        onPrevious={showPreviousTip}
        onNext={showNextTip}
        onSelect={setTipIndex}
        itemLabel="tip"
        className="opacity-60 transition-opacity group-hover:opacity-100"
      />
    </div>
  );
}

function HomeDashboard() {
  const navigate = useNavigate();
  const { user } = useSession();
  const { data: stats, isLoading: statsLoading, error: statsError } = useDashboard({ myItems: true });
  const { data: recentData, isLoading: recentLoading, error: recentError } = useRecentItems({ myItems: false, limit: 10 });
  const { data: priorityData, isLoading: priorityLoading } = usePriorityItems({ limit: 100 });
  const openItemsWithCreatedAt = useMyOpenItemsWithCreatedAt(priorityData?.items ?? []);
  const { sort, sortedItems, requestSort } = useMyOpenItemsSort(openItemsWithCreatedAt);

  // Counts of my open items by type, derived from the priority items feed
  const myOpenItems = priorityData?.items ?? [];
  const myOpenAlerts = myOpenItems.filter((item) => item.item_type === "alert").length;
  const myOpenCases = myOpenItems.filter((item) => item.item_type === "case").length;
  const myOpenTasks = myOpenItems.filter((item) => item.item_type === "task").length;

  // Build links to the filtered list pages for the current user's open work
  const assigneeParam = user?.username ? `&assignee=${encodeURIComponent(user.username)}` : "";
  const myOpenAlertsLink = `/alerts?status=NEW,IN_PROGRESS${assigneeParam}`;
  const myOpenCasesLink = `/cases?status=NEW,IN_PROGRESS${assigneeParam}`;
  const myOpenTasksLink = `/tasks?status=TODO,IN_PROGRESS${assigneeParam}`;

  const formatItemType = (type: string) => {
    switch (type) {
      case "alert": return { label: "Alert", icon: <Bell />, variant: "neutral" as const };
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
    const path = getItemPath(type, humanId);
    if (path) {
      navigate(path);
    }
  };

  const getItemPath = (type: string, humanId: string) => {
    switch (type) {
      case "alert": return `/alerts/${humanId}`;
      case "case": return `/cases/${humanId}`;
      case "task": return `/tasks/${humanId}`;
      default: return null;
    }
  };

  const renderSortableHeader = (key: MyOpenItemsSortKey, label: string) => {
    const isActive = sort.key === key;
    const SortIcon = !isActive ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;

    return (
      <button
        type="button"
        onClick={() => requestSort(key)}
        className="inline-flex items-center gap-1 text-left text-caption-bold font-caption-bold text-subtext-color hover:text-default-font"
        aria-label={`${label}: ${isActive ? `sorted ${sort.direction === "asc" ? "ascending" : "descending"}` : "not sorted"
          }`}
      >
        <span>{label}</span>
        <SortIcon className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    );
  };

  return (
    <DefaultPageLayout withContainer>
      <div className="mx-auto flex w-full max-w-[1536px] flex-col items-start gap-4 px-6 py-8 mobile:px-4">
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
          <div className="grid w-full grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <DashboardCard
              icon={<Bell />}
              title="New Alerts"
              description={`${stats?.unacknowledged_alerts ?? 0} alerts awaiting triage`}
              link="/alerts?status=NEW"
              variant="stat"
              priority={getAlertCountPriority(stats?.unacknowledged_alerts ?? 0)}
            />
            <DashboardCard
              icon={<Bell />}
              title="My Open Alerts"
              description={`${myOpenAlerts} alerts assigned to you`}
              link={myOpenAlertsLink}
              variant="stat"
              priority={getAlertCountPriority(myOpenAlerts)}
            />
            <DashboardCard
              icon={<NotebookPen />}
              title="My Open Cases"
              description={`${myOpenCases} cases assigned to you`}
              link={myOpenCasesLink}
              variant="stat"
              priority={getAlertCountPriority(myOpenCases)}
            />
            <DashboardCard
              icon={<CheckSquare />}
              title="My Open Tasks"
              description={`${myOpenTasks} tasks assigned to you`}
              link={myOpenTasksLink}
              variant="stat"
              priority={getAlertCountPriority(myOpenTasks)}
            />
          </div>
        )}

        {/* Live Activity Feed + My Open Items (side by side on wide screens) */}
        <div className="grid w-full grid-cols-1 gap-4 xl:grid-cols-2">
          {/* Live Activity Feed */}
          <div className="flex w-full flex-col items-start gap-5 rounded-md border border-solid border-neutral-border bg-default-background px-6 py-6">
            <div className="flex w-full flex-col gap-1 sm:flex-row sm:items-end">
              <span className="grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font">
                Live Activity Feed
              </span>
            </div>
            {recentLoading ? (
              <div className="flex w-full items-center justify-center py-8">
                <Loader />
              </div>
            ) : recentError ? (
              <div className="flex w-full items-center justify-center py-8">
                <span className="text-body font-body text-error-600">
                  Failed to load recent activity
                </span>
              </div>
            ) : recentData?.items && recentData.items.length > 0 ? (
              <>
                {/* Mobile: card list */}
                <div className="flex w-full flex-col divide-y divide-neutral-border md:hidden">
                  {recentData.items.map((item) => {
                    const typeInfo = formatItemType(item.item_type);
                    const path = getItemPath(item.item_type, item.human_id);
                    const content = (
                      <>
                        <div className="flex min-w-0 grow flex-col gap-2">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <Badge variant={typeInfo.variant} icon={typeInfo.icon}>
                              {typeInfo.label}
                            </Badge>
                            <span className="text-caption font-caption text-subtext-color">
                              {item.human_id}
                            </span>
                            <span className="text-caption font-caption text-subtext-color">
                              <RelativeTime value={item.updated_at} />
                            </span>
                          </div>
                          <span className="line-clamp-2 text-body-bold font-body-bold text-default-font">
                            {item.title}
                          </span>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-2 sm:flex-row sm:items-center">
                          <State state={mapStatus(item.status, item.item_type)} variant="small" />
                          <Priority priority={mapPriority(item.priority)} size="mini" />
                        </div>
                      </>
                    );

                    return path ? (
                      <Link
                        key={`activity-${item.item_type}-${item.id}`}
                        to={path}
                        className="flex w-full items-start gap-4 px-0 py-4 transition-colors hover:bg-neutral-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary sm:items-center"
                      >
                        {content}
                      </Link>
                    ) : (
                      <div
                        key={`activity-${item.item_type}-${item.id}`}
                        className="flex w-full items-start gap-4 px-0 py-4 sm:items-center"
                      >
                        {content}
                      </div>
                    );
                  })}
                </div>

                {/* Tablet/Desktop: table */}
                <div className="hidden w-full md:block">
                  <Table
                    header={
                      <Table.HeaderRow>
                        <Table.HeaderCell>Title</Table.HeaderCell>
                        <Table.HeaderCell>Type</Table.HeaderCell>
                        <Table.HeaderCell>Status</Table.HeaderCell>
                        <Table.HeaderCell>Priority</Table.HeaderCell>
                        <Table.HeaderCell>Updated</Table.HeaderCell>
                      </Table.HeaderRow>
                    }
                  >
                    {recentData.items.map((item) => {
                      const typeInfo = formatItemType(item.item_type);
                      const path = getItemPath(item.item_type, item.human_id);
                      return (
                        <Table.Row
                          key={`activity-${item.item_type}-${item.id}`}
                          onClick={() => navigateToItem(item.item_type, item.human_id)}
                          className={path ? "cursor-pointer hover:bg-neutral-50" : undefined}
                        >
                          <Table.Cell>
                            <div className="flex flex-col gap-0.5">
                              <span className="text-caption font-caption text-subtext-color">
                                {item.human_id}
                              </span>
                              <span className="text-body-bold font-body-bold text-neutral-700 line-clamp-1">
                                {item.title}
                              </span>
                            </div>
                          </Table.Cell>
                          <Table.Cell>
                            <Badge variant={typeInfo.variant} icon={typeInfo.icon}>
                              {typeInfo.label}
                            </Badge>
                          </Table.Cell>
                          <Table.Cell>
                            <State state={mapStatus(item.status, item.item_type)} variant="mini" />
                          </Table.Cell>
                          <Table.Cell>
                            <Priority priority={mapPriority(item.priority)} size="mini" />
                          </Table.Cell>
                          <Table.Cell>
                            <span className="text-caption font-caption text-subtext-color whitespace-nowrap">
                              <RelativeTime value={item.updated_at} />
                            </span>
                          </Table.Cell>
                        </Table.Row>
                      );
                    })}
                  </Table>
                </div>
              </>
            ) : (
              <div className="flex w-full items-center justify-center py-8">
                <span className="text-body font-body text-subtext-color">
                  No recent activity
                </span>
              </div>
            )}
          </div>

          {/* My Open Items */}
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
                {/* Mobile: card list */}
                <div className="flex w-full flex-col divide-y divide-neutral-border md:hidden">
                  {sortedItems.map((item) => {
                    const typeInfo = formatItemType(item.item_type);
                    return (
                      <button
                        key={`priority-card-${item.item_type}-${item.id}`}
                        type="button"
                        onClick={() => navigateToItem(item.item_type, item.human_id)}
                        className="flex w-full items-start gap-4 px-0 py-4 text-left transition-colors hover:bg-neutral-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary sm:items-center"
                      >
                        <div className="flex min-w-0 grow flex-col gap-2">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <Badge variant={typeInfo.variant} icon={typeInfo.icon}>
                              {typeInfo.label}
                            </Badge>
                            <span className="text-caption font-caption text-subtext-color">
                              {item.human_id}
                            </span>
                            <span
                              className="text-caption font-caption text-subtext-color"
                              title={item.created_at ? `Created ${new Date(item.created_at).toLocaleString()}` : undefined}
                            >
                              {formatOpenItemAge(item.created_at)}
                            </span>
                          </div>
                          <span className="line-clamp-2 text-body-bold font-body-bold text-default-font">
                            {item.title}
                          </span>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-2 sm:flex-row sm:items-center">
                          <State state={mapStatus(item.status, item.item_type)} variant="small" />
                          <Priority priority={mapPriority(item.priority)} size="mini" />
                        </div>
                      </button>
                    );
                  })}
                </div>

                {/* Tablet/Desktop: table */}
                <div className="hidden w-full md:block">
                  <Table
                    header={
                      <Table.HeaderRow>
                        <Table.HeaderCell>{renderSortableHeader("title", "Title")}</Table.HeaderCell>
                        <Table.HeaderCell>{renderSortableHeader("item_type", "Type")}</Table.HeaderCell>
                        <Table.HeaderCell>{renderSortableHeader("status", "Status")}</Table.HeaderCell>
                        <Table.HeaderCell>{renderSortableHeader("priority", "Priority")}</Table.HeaderCell>
                        <Table.HeaderCell>{renderSortableHeader("age", "Age")}</Table.HeaderCell>
                      </Table.HeaderRow>
                    }
                  >
                    {sortedItems.map((item) => {
                      const typeInfo = formatItemType(item.item_type);
                      return (
                        <Table.Row
                          key={`priority-${item.item_type}-${item.id}`}
                          onClick={() => navigateToItem(item.item_type, item.human_id)}
                          className="cursor-pointer hover:bg-neutral-50"
                        >
                          <Table.Cell>
                            <div className="flex flex-col gap-0.5">
                              <span className="text-caption font-caption text-subtext-color">
                                {item.human_id}
                              </span>
                              <span className="text-body-bold font-body-bold text-neutral-700 line-clamp-1">
                                {item.title}
                              </span>
                            </div>
                          </Table.Cell>
                          <Table.Cell>
                            <Badge variant={typeInfo.variant} icon={typeInfo.icon}>
                              {typeInfo.label}
                            </Badge>
                          </Table.Cell>
                          <Table.Cell>
                            <State state={mapStatus(item.status, item.item_type)} variant="mini" />
                          </Table.Cell>
                          <Table.Cell>
                            <Priority priority={mapPriority(item.priority)} size="mini" />
                          </Table.Cell>
                          <Table.Cell>
                            <span
                              className="text-caption font-caption text-subtext-color"
                              title={item.created_at ? `Created ${new Date(item.created_at).toLocaleString()}` : undefined}
                            >
                              {formatOpenItemAge(item.created_at)}
                            </span>
                          </Table.Cell>
                        </Table.Row>
                      );
                    })}
                  </Table>
                </div>
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
      </div>
    </DefaultPageLayout>
  );
}

export default HomeDashboard;
