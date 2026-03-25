import React, { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/buttons/Button";
import { CopyableTimestamp } from "@/components/data-display/CopyableTimestamp";
import { Table } from "@/components/data-display/Table";
import {
  DateRangePicker,
  type DateRangeValue,
} from "@/components/forms/DateRangePicker";
import { Select } from "@/components/forms/Select";
import { Badge } from "@/components/data-display/Badge";
import { AdminPageLayout } from "@/components/layout/AdminPageLayout";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { PaginationFooter } from "@/components/navigation/PaginationFooter";
import { useQueueJobs } from "@/hooks/useQueueJobs";
import { AdminService } from "@/types/generated/services/AdminService";
import type { QueueJobRead } from "@/types/generated/models/QueueJobRead";
import type { QueueStatsRead } from "@/types/generated/models/QueueStatsRead";

import { useSession } from "../contexts/sessionContext";

import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  RotateCcw,
} from "lucide-react";

const STATUS_OPTIONS = [
  { label: "All statuses", value: "__all__" },
  { label: "Queued", value: "queued" },
  { label: "Picked", value: "picked" },
  { label: "Successful", value: "successful" },
  { label: "Exception", value: "exception" },
  { label: "Canceled", value: "canceled" },
];

function statusBadgeVariant(status: string): "success" | "error" | "warning" | "brand" | "neutral" {
  switch (status) {
    case "successful":
      return "success";
    case "exception":
      return "error";
    case "queued":
      return "warning";
    case "picked":
      return "brand";
    default:
      return "neutral";
  }
}

function formatPayload(payload?: Record<string, any> | null): string {
  if (!payload) return "No payload";
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

function formatDuration(ms?: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

function hasExpandableDetails(job: QueueJobRead): boolean {
  const hasPayload =
    job.payload != null && Object.keys(job.payload).length > 0;
  const hasTraceback = !!job.traceback;
  return hasPayload || hasTraceback;
}

export default function AdminQueueStatus() {
  const { user: currentUser } = useSession();
  const isAdmin = currentUser?.role === "ADMIN";

  const [entrypoint, setEntrypoint] = useState("__all__");
  const [status, setStatus] = useState("__all__");
  const [dateRange, setDateRange] = useState<DateRangeValue | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [expandedRows, setExpandedRows] = useState<number[]>([]);

  const queueJobsQuery = useQueueJobs({
    page: currentPage,
    size: 25,
    entrypoint: entrypoint !== "__all__" ? entrypoint : null,
    status: status !== "__all__" ? status : null,
    startDate: dateRange?.start || null,
    endDate: dateRange?.end || null,
  });

  const entrypointsQuery = useQuery<string[], Error>({
    queryKey: ["queue-entrypoints"],
    queryFn: () =>
      AdminService.listQueueEntrypointsApiV1AdminQueueEntrypointsGet(),
    staleTime: 5 * 60 * 1000,
  });

  const statsQuery = useQuery<QueueStatsRead[], Error>({
    queryKey: ["queue-stats"],
    queryFn: () => AdminService.getQueueStatsApiV1AdminQueueStatsGet(),
    staleTime: 30 * 1000,
    refetchInterval: 30 * 1000,
  });

  const entrypointOptions = [
    { label: "All entrypoints", value: "__all__" },
    ...(entrypointsQuery.data || []).map((ep) => ({
      label: ep,
      value: ep,
    })),
  ];

  useEffect(() => {
    setCurrentPage(1);
  }, [entrypoint, status, dateRange]);

  useEffect(() => {
    setExpandedRows([]);
  }, [queueJobsQuery.data?.page, queueJobsQuery.data?.items]);

  if (!isAdmin) {
    return (
      <DefaultPageLayout>
        <div className="container max-w-none flex h-full w-full flex-col items-center justify-center gap-4 bg-default-background">
          <AlertCircle className="text-[48px] text-error text-error-500" />
          <span className="text-heading-2 font-heading-2 text-default-font">
            Access Denied
          </span>
          <span className="text-body font-body text-subtext-color">
            Admin privileges required to access worker queue status
          </span>
        </div>
      </DefaultPageLayout>
    );
  }

  // Aggregate stats into summary numbers
  const totalQueued =
    statsQuery.data
      ?.filter((s) => s.status === "queued")
      .reduce((sum, s) => sum + s.count, 0) ?? 0;
  const totalPicked =
    statsQuery.data
      ?.filter((s) => s.status === "picked")
      .reduce((sum, s) => sum + s.count, 0) ?? 0;

  return (
    <AdminPageLayout
      title="Worker Queue"
      subtitle="Monitor background task status and queue health"
      actionButton={
        <Button
          variant="neutral-secondary"
          icon={<RotateCcw />}
          onClick={() => {
            setEntrypoint("__all__");
            setStatus("__all__");
            setDateRange(null);
            setCurrentPage(1);
          }}
        >
          Reset Filters
        </Button>
      }
    >
      {/* Stats summary */}
      {(totalQueued > 0 || totalPicked > 0) && (
        <div className="flex w-full gap-4">
          <div className="flex items-center gap-2 rounded-lg border border-neutral-border bg-default-background px-4 py-2">
            <span className="text-caption font-caption text-subtext-color">
              Queued
            </span>
            <span className="text-body-bold font-body-bold text-warning-700">
              {totalQueued}
            </span>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-neutral-border bg-default-background px-4 py-2">
            <span className="text-caption font-caption text-subtext-color">
              In Progress
            </span>
            <span className="text-body-bold font-body-bold text-brand-700">
              {totalPicked}
            </span>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex w-full flex-col gap-3 rounded-lg border border-neutral-border bg-default-background p-4">
        <div className="grid w-full grid-cols-1 gap-3 lg:grid-cols-3">
          <DateRangePicker
            className="h-8 w-full justify-between px-3"
            value={dateRange}
            onChange={setDateRange}
            showAllTime={true}
            size="small"
            variant="neutral-secondary"
          />
          <Select
            value={entrypoint}
            onValueChange={setEntrypoint}
            placeholder="All entrypoints"
          >
            {entrypointOptions.map((option) => (
              <Select.Item key={option.value} value={option.value}>
                {option.label}
              </Select.Item>
            ))}
          </Select>
          <Select
            value={status}
            onValueChange={setStatus}
            placeholder="All statuses"
          >
            {STATUS_OPTIONS.map((option) => (
              <Select.Item key={option.value} value={option.value}>
                {option.label}
              </Select.Item>
            ))}
          </Select>
        </div>
      </div>

      {/* Table */}
      <div className="w-full overflow-hidden rounded-lg border border-neutral-border bg-default-background">
        {queueJobsQuery.isLoading ? (
          <div className="flex min-h-[240px] w-full items-center justify-center px-6 py-10 text-body font-body text-subtext-color">
            Loading queue jobs...
          </div>
        ) : queueJobsQuery.isError ? (
          <div className="flex min-h-[240px] w-full flex-col items-center justify-center gap-4 px-6 py-10 text-center">
            <AlertCircle className="text-[40px] text-error-500" />
            <div className="flex flex-col gap-1">
              <span className="text-body-bold font-body-bold text-default-font">
                Unable to load queue jobs
              </span>
              <span className="text-body font-body text-subtext-color">
                {queueJobsQuery.error.message}
              </span>
            </div>
            <Button
              variant="neutral-secondary"
              onClick={() => queueJobsQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        ) : (
          <>
            <Table
              header={
                <Table.HeaderRow>
                  <Table.HeaderCell className="w-[52px]" />
                  <Table.HeaderCell>Created</Table.HeaderCell>
                  <Table.HeaderCell>Entrypoint</Table.HeaderCell>
                  <Table.HeaderCell>Status</Table.HeaderCell>
                  <Table.HeaderCell>Priority</Table.HeaderCell>
                  <Table.HeaderCell>Duration</Table.HeaderCell>
                </Table.HeaderRow>
              }
            >
              {(queueJobsQuery.data?.items || []).map((job: QueueJobRead) => {
                const isExpanded = expandedRows.includes(job.id);
                const expandable = hasExpandableDetails(job);

                return (
                  <React.Fragment key={`${job.id}-${job.status}`}>
                    <Table.Row>
                      <Table.Cell className="justify-center">
                        {expandable ? (
                          <button
                            type="button"
                            className="flex h-8 w-8 items-center justify-center rounded-md text-subtext-color hover:bg-neutral-50 hover:text-default-font"
                            onClick={() => {
                              setExpandedRows((current) =>
                                current.includes(job.id)
                                  ? current.filter((v) => v !== job.id)
                                  : [...current, job.id],
                              );
                            }}
                          >
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                          </button>
                        ) : null}
                      </Table.Cell>
                      <Table.Cell>
                        {job.created ? (
                          <CopyableTimestamp
                            value={job.created}
                            showFull={false}
                            variant="default-right"
                            className="whitespace-nowrap"
                          />
                        ) : (
                          <span className="text-body font-body text-subtext-color">
                            N/A
                          </span>
                        )}
                      </Table.Cell>
                      <Table.Cell className="text-body font-body text-default-font">
                        <span className="font-mono text-caption">
                          {job.entrypoint}
                        </span>
                      </Table.Cell>
                      <Table.Cell>
                        <Badge variant={statusBadgeVariant(job.status)}>
                          {job.status}
                        </Badge>
                      </Table.Cell>
                      <Table.Cell className="text-body font-body text-default-font">
                        {job.priority}
                      </Table.Cell>
                      <Table.Cell className="text-body font-body text-subtext-color whitespace-nowrap">
                        {formatDuration(job.duration_ms)}
                      </Table.Cell>
                    </Table.Row>
                    {isExpanded && expandable ? (
                      <tr className="border-t border-neutral-border bg-neutral-25">
                        <td colSpan={6}>
                          <div className="grid gap-4 px-4 py-4 lg:grid-cols-2">
                            {job.payload != null &&
                            Object.keys(job.payload).length > 0 ? (
                              <div className="flex flex-col gap-2 rounded-md border border-neutral-border bg-default-background p-4">
                                <span className="text-caption-bold font-caption-bold text-subtext-color">
                                  Payload
                                </span>
                                <pre className="overflow-x-auto whitespace-pre-wrap break-words text-caption font-caption text-default-font">
                                  {formatPayload(job.payload)}
                                </pre>
                              </div>
                            ) : null}
                            {job.traceback ? (
                              <div className="flex flex-col gap-2 rounded-md border border-error-200 bg-error-50 p-4">
                                <span className="text-caption-bold font-caption-bold text-error-700">
                                  Traceback
                                </span>
                                <pre className="overflow-x-auto whitespace-pre-wrap break-words text-caption font-caption text-error-600">
                                  {job.traceback}
                                </pre>
                              </div>
                            ) : null}
                            {(job.picked_at || job.finished_at) ? (
                              <div className="flex flex-col gap-2 rounded-md border border-neutral-border bg-default-background p-4 lg:col-span-2">
                                <span className="text-caption-bold font-caption-bold text-subtext-color">
                                  Timeline
                                </span>
                                <div className="flex gap-6 text-caption font-caption text-default-font">
                                  {job.picked_at ? (
                                    <span>
                                      <span className="text-subtext-color">Picked: </span>
                                      <CopyableTimestamp
                                        value={job.picked_at}
                                        showFull={false}
                                        variant="default-right"
                                      />
                                    </span>
                                  ) : null}
                                  {job.finished_at ? (
                                    <span>
                                      <span className="text-subtext-color">Finished: </span>
                                      <CopyableTimestamp
                                        value={job.finished_at}
                                        showFull={false}
                                        variant="default-right"
                                      />
                                    </span>
                                  ) : null}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </React.Fragment>
                );
              })}
            </Table>

            {(queueJobsQuery.data?.items?.length || 0) === 0 ? (
              <div className="flex min-h-[160px] w-full items-center justify-center px-6 py-10 text-body font-body text-subtext-color">
                No queue jobs matched the current filters.
              </div>
            ) : null}

            <PaginationFooter
              currentPage={queueJobsQuery.data?.page || 1}
              totalPages={queueJobsQuery.data?.pages || 1}
              totalResults={queueJobsQuery.data?.total || 0}
              onPageChange={setCurrentPage}
              className="border-t-0"
            />
          </>
        )}
      </div>
    </AdminPageLayout>
  );
}
