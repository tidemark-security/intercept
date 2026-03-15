import React, { useDeferredValue, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/buttons/Button";
import { CopyableTimestamp } from "@/components/data-display/CopyableTimestamp";
import { Table } from "@/components/data-display/Table";
import {
  DateRangePicker,
  type DateRangeValue,
} from "@/components/forms/DateRangePicker";
import { EventTypeSelector } from "@/components/forms/EventTypeSelector";
import { Select } from "@/components/forms/Select";
import { TextField } from "@/components/forms/TextField";
import { AdminPageLayout } from "@/components/layout/AdminPageLayout";
import { PaginationFooter } from "@/components/navigation/PaginationFooter";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { useAuditLogs } from "@/hooks/useAuditLogs";
import { useSearchCore } from "@/hooks/useSearchCore";
import { AdminService } from "@/types/generated/services/AdminService";
import type { AuditLogRead } from "@/types/generated/models/AuditLogRead";

import { useSession } from "../contexts/sessionContext";

import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  RotateCcw,
  Search,
  ShieldCheck,
} from "lucide-react";

const ENTITY_TYPE_OPTIONS = [
  { label: "All entities", value: "__all__" },
  { label: "User", value: "user" },
  { label: "Case", value: "case" },
  { label: "Alert", value: "alert" },
  { label: "Task", value: "task" },
  { label: "Setting", value: "setting" },
  { label: "API Key", value: "api_key" },
];

function formatJsonSnapshot(value?: string | null): string {
  if (!value) {
    return "No snapshot recorded";
  }

  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

function getEntityLabel(entry: AuditLogRead): string {
  if (!entry.entity_type && !entry.entity_id) {
    return "System";
  }

  if (!entry.entity_type) {
    return entry.entity_id || "Unknown";
  }

  if (!entry.entity_id) {
    return entry.entity_type;
  }

  return `${entry.entity_type}:${entry.entity_id}`;
}

function hasSnapshotDetails(entry: AuditLogRead): boolean {
  return Boolean(
    entry.old_value ||
    entry.new_value ||
    entry.correlation_id ||
    entry.user_agent,
  );
}

export default function AdminAuditTrail() {
  const { user: currentUser } = useSession();
  const isAdmin = currentUser?.role === "ADMIN";

  const {
    query: searchQuery,
    setQuery: setSearchQuery,
    debouncedQuery: debouncedSearchQuery,
    clearSearch,
  } = useSearchCore({ debounceMs: 350 });

  const [selectedEventTypes, setSelectedEventTypes] = useState<string[]>([]);
  const [entityType, setEntityType] = useState("__all__");
  const [entityId, setEntityId] = useState("");
  const [performedBy, setPerformedBy] = useState("");
  const [dateRange, setDateRange] = useState<DateRangeValue | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [expandedRows, setExpandedRows] = useState<number[]>([]);

  const deferredEntityId = useDeferredValue(entityId);
  const deferredPerformedBy = useDeferredValue(performedBy);

  const auditLogsQuery = useAuditLogs({
    page: currentPage,
    size: 25,
    eventType: selectedEventTypes.length > 0 ? selectedEventTypes : null,
    entityType: entityType !== "__all__" ? entityType : null,
    entityId: deferredEntityId.trim() || null,
    performedBy: deferredPerformedBy.trim() || null,
    search: debouncedSearchQuery.trim() || null,
    startDate: dateRange?.start || null,
    endDate: dateRange?.end || null,
  });

  const auditEventTypesQuery = useQuery<string[], Error>({
    queryKey: ["audit-event-types"],
    queryFn: () =>
      AdminService.listAuditEventTypesApiV1AdminAuditEventTypesGet(),
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    setCurrentPage(1);
  }, [
    debouncedSearchQuery,
    selectedEventTypes,
    entityType,
    deferredEntityId,
    deferredPerformedBy,
    dateRange,
  ]);

  useEffect(() => {
    setExpandedRows([]);
  }, [auditLogsQuery.data?.page, auditLogsQuery.data?.items]);

  if (!isAdmin) {
    return (
      <DefaultPageLayout>
        <div className="container max-w-none flex h-full w-full flex-col items-center justify-center gap-4 bg-default-background">
          <AlertCircle className="text-[48px] text-error text-error-500" />
          <span className="text-heading-2 font-heading-2 text-default-font">
            Access Denied
          </span>
          <span className="text-body font-body text-subtext-color">
            Admin privileges required to access the audit trail
          </span>
        </div>
      </DefaultPageLayout>
    );
  }

  return (
    <AdminPageLayout
      title="Audit Trail"
      subtitle="Review security-sensitive activity with filtering and pagination"
      actionButton={
        <Button
          variant="neutral-secondary"
          icon={<RotateCcw />}
          onClick={() => {
            clearSearch();
            setSelectedEventTypes([]);
            setEntityType("__all__");
            setEntityId("");
            setPerformedBy("");
            setDateRange(null);
            setCurrentPage(1);
          }}
        >
          Reset Filters
        </Button>
      }
    >
      <div className="flex w-full flex-col gap-3 rounded-lg border border-neutral-border bg-default-background p-4">
        <div className="w-full">
          <TextField className="w-full" icon={<Search />}>
            <TextField.Input
              placeholder="Search event, description, actor..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </TextField>
        </div>

        <div className="grid w-full grid-cols-1 gap-3 lg:grid-cols-3">
          <DateRangePicker
            className="h-8 w-full justify-between px-3"
            value={dateRange}
            onChange={setDateRange}
            showAllTime={true}
            size="small"
            variant="neutral-secondary"
          />
          <EventTypeSelector
            selectedEventTypes={selectedEventTypes}
            eventTypes={auditEventTypesQuery.data || []}
            isLoading={auditEventTypesQuery.isLoading}
            onSelectionChange={(eventTypes) =>
              setSelectedEventTypes(eventTypes || [])
            }
            className="h-8 w-full justify-between px-3"
            dropdownClassName="w-[320px]"
          />
          <Select
            value={entityType}
            onValueChange={setEntityType}
            placeholder="All entities"
          >
            {ENTITY_TYPE_OPTIONS.map((option) => (
              <Select.Item key={option.value || "all"} value={option.value}>
                {option.label}
              </Select.Item>
            ))}
          </Select>
        </div>

        <div className="grid w-full grid-cols-1 gap-3 md:grid-cols-2">
          <TextField className="w-full" icon={<ShieldCheck />}>
            <TextField.Input
              placeholder="Actor"
              value={performedBy}
              onChange={(event) => setPerformedBy(event.target.value)}
            />
          </TextField>

          <TextField className="w-full">
            <TextField.Input
              placeholder="Filter by entity ID"
              value={entityId}
              onChange={(event) => setEntityId(event.target.value)}
            />
          </TextField>
        </div>
      </div>

      <div className="w-full overflow-hidden rounded-lg border border-neutral-border bg-default-background">
        {auditLogsQuery.isLoading ? (
          <div className="flex min-h-[240px] w-full items-center justify-center px-6 py-10 text-body font-body text-subtext-color">
            Loading audit trail...
          </div>
        ) : auditLogsQuery.isError ? (
          <div className="flex min-h-[240px] w-full flex-col items-center justify-center gap-4 px-6 py-10 text-center">
            <AlertCircle className="text-[40px] text-error-500" />
            <div className="flex flex-col gap-1">
              <span className="text-body-bold font-body-bold text-default-font">
                Unable to load audit trail
              </span>
              <span className="text-body font-body text-subtext-color">
                {auditLogsQuery.error.message}
              </span>
            </div>
            <Button
              variant="neutral-secondary"
              onClick={() => auditLogsQuery.refetch()}
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
                  <Table.HeaderCell>Timestamp</Table.HeaderCell>
                  <Table.HeaderCell>Event Type</Table.HeaderCell>
                  <Table.HeaderCell>Entity</Table.HeaderCell>
                  <Table.HeaderCell>Description</Table.HeaderCell>
                  <Table.HeaderCell>Performed By</Table.HeaderCell>
                  <Table.HeaderCell>IP Address</Table.HeaderCell>
                </Table.HeaderRow>
              }
            >
              {(auditLogsQuery.data?.items || []).map((entry) => {
                const isExpanded = expandedRows.includes(entry.id);

                return (
                  <React.Fragment key={entry.id}>
                    <Table.Row>
                      <Table.Cell className="justify-center">
                        {hasSnapshotDetails(entry) ? (
                          <button
                            type="button"
                            className="flex h-8 w-8 items-center justify-center rounded-md text-subtext-color hover:bg-neutral-50 hover:text-default-font"
                            onClick={() => {
                              setExpandedRows((current) =>
                                current.includes(entry.id)
                                  ? current.filter(
                                      (value) => value !== entry.id,
                                    )
                                  : [...current, entry.id],
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
                        <CopyableTimestamp
                          value={entry.performed_at}
                          showFull={false}
                          variant="default-right"
                          className="whitespace-nowrap"
                        />
                      </Table.Cell>
                      <Table.Cell>
                        <span className="bg-neutral-200 px-2 py-1 text-caption-bold font-caption-bold text-default-font">
                          {entry.event_type}
                        </span>
                      </Table.Cell>
                      <Table.Cell className="text-body font-body text-default-font">
                        {getEntityLabel(entry)}
                      </Table.Cell>
                      <Table.Cell className="text-body font-body text-default-font">
                        {entry.description || "No description"}
                      </Table.Cell>
                      <Table.Cell className="text-body font-body text-default-font">
                        {entry.performed_by || "System"}
                      </Table.Cell>
                      <Table.Cell className="text-body font-body text-subtext-color">
                        {entry.ip_address || "N/A"}
                      </Table.Cell>
                    </Table.Row>
                    {isExpanded ? (
                      <tr className="border-t border-neutral-border bg-neutral-25">
                        <td colSpan={7}>
                          <div className="grid gap-4 px-4 py-4 lg:grid-cols-2">
                            {entry.old_value != null ? (
                              <div className="flex flex-col gap-2 rounded-md border border-neutral-border bg-default-background p-4">
                                <span className="text-caption-bold font-caption-bold text-subtext-color">
                                  Before
                                </span>
                                <pre className="overflow-x-auto whitespace-pre-wrap break-words text-caption font-caption text-default-font">
                                  {formatJsonSnapshot(entry.old_value)}
                                </pre>
                              </div>
                            ) : null}
                            <div
                              className={`flex flex-col gap-2 rounded-md border border-neutral-border bg-default-background p-4 ${entry.old_value == null ? "lg:col-span-2" : ""}`}
                            >
                              <span className="text-caption-bold font-caption-bold text-subtext-color">
                                After
                              </span>
                              <pre className="overflow-x-auto whitespace-pre-wrap break-words text-caption font-caption text-default-font">
                                {formatJsonSnapshot(entry.new_value)}
                              </pre>
                            </div>
                            {entry.correlation_id != null ? (
                              <div className="flex flex-col gap-1 rounded-md border border-neutral-border bg-default-background p-4 lg:col-span-2">
                                <span className="text-caption-bold font-caption-bold text-subtext-color">
                                  Correlation ID
                                </span>
                                <span className="text-body font-body text-default-font">
                                  {entry.correlation_id}
                                </span>
                              </div>
                            ) : null}
                            <div className="flex flex-col gap-1 rounded-md border border-neutral-border bg-default-background p-4 lg:col-span-2">
                              <span className="text-caption-bold font-caption-bold text-subtext-color">
                                User Agent
                              </span>
                              <span className="text-body font-body text-default-font break-all">
                                {entry.user_agent || "N/A"}
                              </span>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </React.Fragment>
                );
              })}
            </Table>

            {(auditLogsQuery.data?.items.length || 0) === 0 ? (
              <div className="flex min-h-[160px] w-full items-center justify-center px-6 py-10 text-body font-body text-subtext-color">
                No audit events matched the current filters.
              </div>
            ) : null}

            <PaginationFooter
              currentPage={auditLogsQuery.data?.page || 1}
              totalPages={auditLogsQuery.data?.pages || 1}
              totalResults={auditLogsQuery.data?.total || 0}
              onPageChange={setCurrentPage}
              className="border-t-0"
            />
          </>
        )}
      </div>
    </AdminPageLayout>
  );
}
