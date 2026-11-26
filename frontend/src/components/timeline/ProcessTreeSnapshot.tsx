import { useMemo, useState } from 'react';
import { Accordion, Button, IconButton, Table } from '@tidemark-security/ux';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { ProcessTreeNode } from '@/types/generated/models/ProcessTreeNode';
import { formatAbsoluteTime } from '@/utils/dateFormatters';

const STATUS_LABELS = { running: 'Running', exited: 'Exited' };
const UTC_FORMAT = "MMM d, yyyy HH:mm:ss 'UTC'";

function indexProcesses(processes: ProcessTreeNode[]) {
  const byId = new Map(processes.map((process) => [process.id, process]));
  const byParent = new Map<string | null, ProcessTreeNode[]>();
  for (const process of processes) {
    const parent = process.parent_id ?? null;
    const siblings = byParent.get(parent);
    if (siblings) siblings.push(process);
    else byParent.set(parent, [process]);
  }
  return { byId, byParent };
}

function ProcessTreeDetails({ processes }: { processes: ProcessTreeNode[] }) {
  const { byId, byParent } = useMemo(() => indexProcesses(processes), [processes]);
  const roots = byParent.get(null) ?? [];
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [selectedId, setSelectedId] = useState<string>();
  const selected = (selectedId ? byId.get(selectedId) : undefined) ?? roots[0];
  const selectedParent = selected?.parent_id ? byId.get(selected.parent_id) : undefined;

  const visible: { process: ProcessTreeNode; depth: number }[] = [];
  const pending = roots.map((process) => ({ process, depth: 0 })).reverse();
  while (pending.length) {
    const row = pending.pop()!;
    visible.push(row);
    if (expanded.has(row.process.id)) {
      const children = byParent.get(row.process.id) ?? [];
      for (let index = children.length - 1; index >= 0; index--) {
        pending.push({ process: children[index], depth: row.depth + 1 });
      }
    }
  }

  function toggleBranch(id: string) {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  return (
    <div className="flex w-full flex-wrap items-start gap-4">
      <div className="min-w-0 flex-[2_1_20rem] overflow-x-auto">
        <Table
          aria-label="Processes in snapshot"
          className="table-fixed"
          header={
            <Table.HeaderRow>
              <Table.HeaderCell scope="col">Process</Table.HeaderCell>
              <Table.HeaderCell scope="col" style={{ width: 'clamp(3.5rem, 12vw, 5rem)' }}>PID</Table.HeaderCell>
              <Table.HeaderCell scope="col" style={{ width: 'clamp(3.75rem, 12vw, 4.625rem)' }}>Status</Table.HeaderCell>
            </Table.HeaderRow>
          }
        >
          {visible.map(({ process, depth }) => {
            const isExpanded = expanded.has(process.id);
            const hasChildren = byParent.has(process.id);
            return (
              <Table.Row key={process.id}>
                <Table.Cell className="h-9 min-w-0 gap-1 px-2">
                  <div className="flex min-w-0 items-center" style={{ paddingInlineStart: Math.min(depth, 6) * 10 }}>
                    {hasChildren ? (
                      <IconButton
                        type="button"
                        size="small"
                        variant="neutral-tertiary"
                        aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${process.process_name} (PID ${process.process_id})`}
                        aria-expanded={isExpanded}
                        className="shrink-0"
                        icon={isExpanded ? <ChevronDown /> : <ChevronRight />}
                        onClick={() => toggleBranch(process.id)}
                      />
                    ) : <span className="w-6 shrink-0" aria-hidden="true" />}
                    <Button
                      type="button"
                      size="small"
                      variant={selected?.id === process.id ? 'brand-tertiary' : 'neutral-tertiary'}
                      aria-pressed={selected?.id === process.id}
                      aria-label={`Inspect ${process.process_name} (PID ${process.process_id})`}
                      title={process.process_name}
                      className="min-w-0 justify-start overflow-hidden px-1"
                      onClick={() => setSelectedId(process.id)}
                    >
                      <span className="block truncate">{process.process_name}</span>
                    </Button>
                  </div>
                </Table.Cell>
                <Table.Cell className="h-9 px-2 text-caption font-caption tabular-nums">{process.process_id}</Table.Cell>
                <Table.Cell className="h-9 px-2 text-caption font-caption">
                  {process.status ? STATUS_LABELS[process.status] : '—'}
                </Table.Cell>
              </Table.Row>
            );
          })}
        </Table>
      </div>

      {selected && (
        <section aria-label="Process details" aria-live="polite" className="min-w-0 flex-[1_1_12rem] border-l border-neutral-border pl-4">
          <h3 className="break-words text-heading-3 font-heading-3">{selected.process_name}</h3>
          <dl className="mt-2 space-y-2 break-words text-body font-body">
            <div><dt className="text-caption font-caption text-subtext-color">PID</dt><dd>{selected.process_id}</dd></div>
            {selectedParent && (
              <div><dt className="text-caption font-caption text-subtext-color">Parent</dt><dd>{selectedParent.process_name} ({selectedParent.process_id})</dd></div>
            )}
            {selected.started_at && (
              <div><dt className="text-caption font-caption text-subtext-color">Started</dt><dd><time dateTime={selected.started_at}>{formatAbsoluteTime(selected.started_at, UTC_FORMAT, 'utc')}</time></dd></div>
            )}
            {selected.user_account && (
              <div><dt className="text-caption font-caption text-subtext-color">User account</dt><dd>{selected.user_account}</dd></div>
            )}
            {selected.command_line && (
              <div><dt className="text-caption font-caption text-subtext-color">Command line</dt><dd className="whitespace-pre-wrap text-monospace-body font-monospace-body">{selected.command_line}</dd></div>
            )}
          </dl>
        </section>
      )}
    </div>
  );
}

export function ProcessTreeSnapshot({ processes, timestamp }: { processes: ProcessTreeNode[]; timestamp?: string }) {
  const [open, setOpen] = useState(false);

  return (
    <Accordion
      open={open}
      onOpenChange={setOpen}
      trigger={
        <span className="flex w-full items-center justify-between gap-2 border-t border-neutral-border py-2 text-body-bold font-body-bold">
          View process tree
          <Accordion.Chevron />
        </span>
      }
    >
      <div className="flex w-full flex-col gap-2">
        {timestamp && (
          <div className="text-caption font-caption text-subtext-color">
            Captured <time dateTime={timestamp}>{formatAbsoluteTime(timestamp, UTC_FORMAT, 'utc')}</time>
          </div>
        )}
        <ProcessTreeDetails processes={processes} />
      </div>
    </Accordion>
  );
}
