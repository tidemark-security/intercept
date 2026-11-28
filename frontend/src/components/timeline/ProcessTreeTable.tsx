import { useRef, useState, type KeyboardEvent } from 'react';
import { IconButton, IconWrapper, Table } from '@tidemark-security/ux';
import { ChevronDown, ChevronRight, FilePenLine, Globe, ShieldOff } from 'lucide-react';
import type { ProcessTreeNode } from '@/types/generated/models/ProcessTreeNode';
import { cn } from '@/utils/cn';
import { formatAbsoluteTime } from '@/utils/dateFormatters';
import { ProcessIndicators } from './ProcessSnapshotInspector';
import type { ProcessTreeRow } from './processTreeRows';
import './processTreeTable.css';

function BranchGuides({ row, onAttackPath }: { row: ProcessTreeRow; onAttackPath: boolean }) {
  if (row.depth === 0) return null;
  const branchColor = onAttackPath ? 'bg-error-600' : 'bg-neutral-border';

  return (
    <span aria-hidden="true" className="flex shrink-0 items-stretch">
      {row.guides.map((continues, index) => (
        <span className="relative w-2.5" key={index}>
          {continues && <span className="absolute inset-y-0 left-1 w-px bg-neutral-border" />}
        </span>
      ))}
      <span className="relative w-2.5">
        <span className={cn('absolute left-1 top-0 w-px', row.hasNextSibling ? 'h-full' : 'h-[1.125rem]', branchColor)} />
        <span className={cn('absolute left-1 top-[1.125rem] h-px w-1.5', branchColor)} />
      </span>
    </span>
  );
}

function RowSignals({ process }: { process: ProcessTreeNode }) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-1 text-caption font-caption text-subtext-color">
      {process.is_signed === false && (
        <IconWrapper role="img" aria-label="Unsigned image" title="Unsigned image"><ShieldOff /></IconWrapper>
      )}
      {Boolean(process.file_writes) && (
        <IconWrapper role="img" aria-label={`${process.file_writes} file writes`} title={`${process.file_writes} file writes`}>
          <FilePenLine />
        </IconWrapper>
      )}
      {Boolean(process.network_connections) && (
        <IconWrapper role="img" aria-label={`${process.network_connections} network connections`} title={`${process.network_connections} network connections`}>
          <Globe />
        </IconWrapper>
      )}
    </div>
  );
}

export function ProcessTreeTable({
  rows,
  attackPath,
  selectedId,
  query,
  showCommandLines,
  showStarted = false,
  opensViewer = false,
  onToggleBranch,
  onSelect,
}: {
  rows: readonly ProcessTreeRow[];
  attackPath: ReadonlySet<string>;
  selectedId?: string;
  query: string;
  showCommandLines: boolean;
  showStarted?: boolean;
  opensViewer?: boolean;
  onToggleBranch: (row: ProcessTreeRow) => void;
  onSelect: (id: string, row: HTMLTableRowElement) => void;
}) {
  const [focusedId, setFocusedId] = useState<string>();
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());
  const filtering = Boolean(query.trim());
  const focusableId = rows.some((row) => row.process.id === (focusedId ?? selectedId))
    ? focusedId ?? selectedId
    : rows[0]?.process.id;

  function handleRowKey(event: KeyboardEvent<HTMLTableRowElement>, row: ProcessTreeRow, index: number) {
    if (event.target !== event.currentTarget || event.altKey || event.ctrlKey || event.metaKey) return;
    let destination: string | null | undefined;

    switch (event.key) {
      case 'ArrowDown':
        destination = rows[index + 1]?.process.id;
        break;
      case 'ArrowUp':
        destination = rows[index - 1]?.process.id;
        break;
      case 'Home':
        destination = rows[0]?.process.id;
        break;
      case 'End':
        destination = rows.at(-1)?.process.id;
        break;
      case 'ArrowRight':
        if (row.expanded) destination = rows[index + 1]?.process.id;
        else if (row.childCount && !filtering) onToggleBranch(row);
        break;
      case 'ArrowLeft':
        if (row.expanded && !filtering) onToggleBranch(row);
        else destination = row.process.parent_id;
        break;
      case 'Enter':
      case ' ':
        onSelect(row.process.id, event.currentTarget);
        break;
      default:
        return;
    }

    event.preventDefault();
    if (destination) rowRefs.current.get(destination)?.focus();
  }

  if (!rows.length) {
    return <p role="status" className="break-words p-4 text-body font-body text-subtext-color">No process matches “{query.trim()}”.</p>;
  }

  return (
    <Table
      role="treegrid"
      aria-label="Process tree"
      className="process-tree-table table-fixed"
      header={
        <Table.HeaderRow className="sticky top-0 z-10 border-b border-neutral-border bg-default-background">
          <Table.HeaderCell scope="col">Process</Table.HeaderCell>
          <Table.HeaderCell scope="col" data-column="pid">PID</Table.HeaderCell>
          <Table.HeaderCell scope="col" data-column="user">User</Table.HeaderCell>
          {showStarted && <Table.HeaderCell scope="col" data-column="started">Started (UTC)</Table.HeaderCell>}
          <Table.HeaderCell scope="col" data-column="signals">Signals</Table.HeaderCell>
        </Table.HeaderRow>
      }
    >
      {rows.map((row, index) => {
        const { process } = row;
        const commandLine = showCommandLines ? process.command_line : undefined;
        const started = showStarted ? formatAbsoluteTime(process.started_at, 'HH:mm:ss', 'utc') : undefined;
        return (
          <Table.Row
            key={process.id}
            ref={(element) => {
              if (element) rowRefs.current.set(process.id, element);
              else rowRefs.current.delete(process.id);
            }}
            clickable
            className={cn(
              'relative cursor-pointer focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-focus-border',
              process.id === selectedId && 'bg-neutral-100',
            )}
            aria-level={row.depth + 1}
            aria-selected={process.id === selectedId}
            aria-expanded={row.childCount ? row.expanded : undefined}
            aria-haspopup={opensViewer ? 'dialog' : undefined}
            tabIndex={process.id === focusableId ? 0 : -1}
            onFocus={() => setFocusedId(process.id)}
            onClick={(event) => onSelect(process.id, event.currentTarget)}
            onKeyDown={(event) => handleRowKey(event, row, index)}
          >
            <Table.Cell className="h-auto min-h-9 min-w-0 items-stretch gap-0 px-1">
              <BranchGuides row={row} onAttackPath={attackPath.has(process.id)} />
              <span className="flex h-9 w-6 shrink-0 items-center justify-center">
                {row.childCount > 0 && (filtering ? (
                  <IconWrapper aria-hidden="true" className="text-caption font-caption text-subtext-color"><ChevronDown /></IconWrapper>
                ) : (
                  <IconButton
                    type="button" size="small" variant="neutral-tertiary" tabIndex={-1}
                    aria-label={`${row.expanded ? 'Collapse' : 'Expand'} ${process.process_name} (PID ${process.process_id})`}
                    aria-expanded={row.expanded}
                    icon={row.expanded ? <ChevronDown /> : <ChevronRight />}
                    onClick={(event) => {
                      event.stopPropagation();
                      rowRefs.current.get(process.id)?.focus();
                      onToggleBranch(row);
                    }}
                  />
                ))}
              </span>
              <div className={cn('flex min-w-0 flex-1 flex-col justify-center py-1 pr-1', commandLine && 'pb-5')}>
                <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                  <span title={process.process_name} className="max-w-full truncate text-body-bold font-body-bold">{process.process_name}</span>
                  <span className="process-tree-inline-pid text-caption font-monospace-body text-subtext-color">PID {process.process_id}</span>
                  <ProcessIndicators process={process} />
                </div>
                {commandLine && (
                  <span
                    title={commandLine}
                    className="pointer-events-none absolute bottom-1 end-2 truncate text-caption font-monospace-body text-subtext-color"
                    style={{ insetInlineStart: 28 + (row.depth ? row.guides.length + 1 : 0) * 10 }}
                  >
                    {commandLine}
                  </span>
                )}
              </div>
            </Table.Cell>
            <Table.Cell data-column="pid" className="h-9 px-2 text-caption font-monospace-body tabular-nums">{process.process_id}</Table.Cell>
            <Table.Cell data-column="user" className="h-9 min-w-0 px-2 text-caption font-caption"><span className="truncate">{process.user_account}</span></Table.Cell>
            {showStarted && (
              <Table.Cell data-column="started" className="h-9 px-2 text-caption font-monospace-body tabular-nums">
                {started && <time dateTime={process.started_at ?? undefined}>{started}</time>}
              </Table.Cell>
            )}
            <Table.Cell data-column="signals" className="h-9 justify-end px-2"><RowSignals process={process} /></Table.Cell>
          </Table.Row>
        );
      })}
    </Table>
  );
}
