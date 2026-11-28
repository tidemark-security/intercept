import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/buttons/Button";
import { Table } from "@/components/data-display/Table";
import { Dialog } from "@/components/overlays/Dialog";
import { useTimezonePreference } from "@/contexts/TimezoneContext";
import { useDashboardRecords } from "@/hooks/useCustomDashboards";
import { getApiErrorMessage } from "@/services/apiRequestError";
import type { DashboardRecord } from "@/types/generated/models/DashboardRecord";
import type { DashboardRecords } from "@/types/generated/models/DashboardRecords";
import { formatAbsoluteTime } from "@/utils/dateFormatters";
import { fieldLabel, metricValue } from "./dashboardPresentation";

export type RecordSelection = { title: string; reference: string };

export function DashboardRecordTable({
  records, limit, onOpenRecord,
}: {
  records: DashboardRecords;
  limit?: number;
  onOpenRecord?: () => void;
}) {
  const { timezonePreference } = useTimezonePreference();
  function cell(item: DashboardRecord, field: string) {
    if (field === "human_id" || field === "title") {
      return (
        <Link
          to={`/${records.entity}/${item.human_id}`}
          className="font-body-bold underline-offset-4 hover:underline focus-visible:underline"
          data-dashboard-record
          onClick={onOpenRecord}
        >
          {field === "human_id" ? item.human_id : item.title}
        </Link>
      );
    }
    if (field === "case" && item.case_id != null) {
      const id = `CAS-${String(item.case_id).padStart(7, "0")}`;
      return <Link className="underline-offset-4 hover:underline" to={`/cases/${id}`} data-dashboard-record onClick={onOpenRecord}>{id}</Link>;
    }
    const value = item[field as keyof DashboardRecord];
    if (value == null) return "—";
    if (field === "elapsed_seconds" || field === "target_seconds") return metricValue(Number(value), "seconds");
    if (field.endsWith("_at") || field === "due_date") {
      return formatAbsoluteTime(String(value), "MMM d, yyyy HH:mm", timezonePreference);
    }
    return String(value);
  }

  if (!records.items.length) return <p className="py-4 text-body text-subtext-color">No matching records on this page.</p>;
  const columns = records.columns.some((field) => field === "human_id" || field === "title")
    ? records.columns
    : ["human_id", ...records.columns];
  return (
    <div className="overflow-x-auto">
      <Table header={<Table.HeaderRow>{columns.map((field) => <Table.HeaderCell key={field}>{fieldLabel(field)}</Table.HeaderCell>)}</Table.HeaderRow>}>
        {records.items.slice(0, limit ?? records.items.length).map((item) => (
          <Table.Row key={item.id}>
            {columns.map((field) => <Table.Cell key={field}>{cell(item, field)}</Table.Cell>)}
          </Table.Row>
        ))}
      </Table>
    </div>
  );
}

export function DashboardRecordDialog({ selection, onClose }: { selection: RecordSelection; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const query = useDashboardRecords(selection.reference, page);
  const records = query.data;
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[min(96vw,72rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-auto rounded-lg border border-neutral-border bg-default-background p-6 shadow-lg">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Dialog.Title className="text-heading-2 font-heading-2">{selection.title}</Dialog.Title>
            <Dialog.Description className="text-body text-subtext-color">
              {records ? `${records.total.toLocaleString()} matching ${records.entity}` : "Matching records"}
              {records?.original_count != null && records.original_count !== records.total
                ? ` · ${records.original_count.toLocaleString()} at last refresh` : ""}
            </Dialog.Description>
          </div>
          <Button variant="neutral-secondary" onClick={onClose}>Close</Button>
        </div>
        {query.isPending && <p role="status">Loading matching records…</p>}
        {query.isError && <p role="alert">{getApiErrorMessage(query.error, "Could not load records.")}</p>}
        {records && <DashboardRecordTable records={records} onOpenRecord={onClose} />}
        {records && (
          <div className="flex items-center gap-3">
            <Button disabled={page === 1} onClick={() => setPage(page - 1)} variant="neutral-secondary">Previous</Button>
            <span>Page {page}</span>
            {records.queue_statuses && (
              <Link
                to={`/${records.entity}?${new URLSearchParams({ status: records.queue_statuses.join(",") })}`}
                className="underline-offset-4 hover:underline focus-visible:underline"
                data-dashboard-record
                onClick={onClose}
              >Open in {records.entity} queue</Link>
            )}
            <Button disabled={page * records.page_size >= records.total} onClick={() => setPage(page + 1)} variant="neutral-secondary">Next</Button>
          </div>
        )}
      </Dialog.Content>
    </Dialog>
  );
}
