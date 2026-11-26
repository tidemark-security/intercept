import { useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { Accordion, Button, IconButton, IconWrapper, Table, TextField } from '@tidemark-security/ux';
import { ChevronDown, ChevronRight, FilePenLine, Globe, Route, Search, ShieldOff, Terminal, X } from 'lucide-react';
import type { ProcessTreeNode } from '@/types/generated/models/ProcessTreeNode';
import { cn } from '@/utils/cn';
import { formatAbsoluteTime } from '@/utils/dateFormatters';
import { PROCESS_TREE_UTC_FORMAT, ProcessIndicators, ProcessSnapshotInspector } from './ProcessSnapshotInspector';
import { getAttackPath, getProcessTreeRows, indexProcesses, type ProcessTreeRow } from './processTreeRows';

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

function ProcessTreeDetails({ processes }: { processes: readonly ProcessTreeNode[] }) {
  const processIndex = useMemo(() => indexProcesses(processes), [processes]);
  const attackPath = useMemo(() => getAttackPath(processIndex), [processIndex]);
  const [selectedId, setSelectedId] = useState<string | null>();
  const [focusedId, setFocusedId] = useState<string>();
  const [expansion, setExpansion] = useState<ReadonlyMap<string, boolean>>(() => new Map());
  const [query, setQuery] = useState('');
  const [attackPathOnly, setAttackPathOnly] = useState(false);
  const [showCommandLines, setShowCommandLines] = useState(true);
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());
  const filterRef = useRef<HTMLInputElement>(null);
  const needle = query.trim().toLowerCase();
  const pathOnly = attackPathOnly && attackPath.size > 0;
  const rows = useMemo(() => getProcessTreeRows(
    processIndex, attackPath, pathOnly, needle, expansion,
  ), [processIndex, attackPath, pathOnly, needle, expansion]);

  const defaultProcess = processes.find((process) => process.is_alert_source) ?? processIndex.byParent.get(null)?.[0];
  const selected = selectedId === null ? undefined :
    (selectedId ? processIndex.byId.get(selectedId) : undefined) ?? defaultProcess;
  const selectedParent = selected?.parent_id ? processIndex.byId.get(selected.parent_id) : undefined;
  const focusableId = rows.find((row) => row.process.id === (focusedId ?? selected?.id))?.process.id ?? rows[0]?.process.id;

  function toggleBranch(row: ProcessTreeRow) {
    setExpansion((previous) => new Map(previous).set(row.process.id, !row.expanded));
  }

  function toggleAttackPath() {
    if (!pathOnly) {
      setExpansion((previous) => new Map([...previous].filter(([id]) => !attackPath.has(id))));
    }
    setAttackPathOnly(!pathOnly);
  }

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
        else if (row.childCount && !needle) toggleBranch(row);
        break;
      case 'ArrowLeft':
        if (row.expanded && !needle) toggleBranch(row);
        else destination = row.process.parent_id;
        break;
      case 'Enter':
      case ' ':
        setSelectedId(row.process.id);
        break;
      default:
        return;
    }

    event.preventDefault();
    if (destination) rowRefs.current.get(destination)?.focus();
  }

  if (!processes.length) {
    return <p role="status" className="p-3 text-body font-body text-subtext-color">No process telemetry for this snapshot.</p>;
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-0 flex-[1_1_14rem] items-center gap-1">
          <TextField className="min-w-0 flex-1" icon={<Search />}>
            <TextField.Input
              ref={filterRef}
              type="search"
              aria-label="Filter processes"
              placeholder="Filter name, PID, command line"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </TextField>
          {query && (
            <IconButton
              type="button" size="small" variant="neutral-tertiary" icon={<X />} aria-label="Clear filter"
              onClick={() => { setQuery(''); filterRef.current?.focus(); }}
            />
          )}
        </div>
        <Button
          type="button" size="small" variant={pathOnly ? 'brand-secondary' : 'neutral-secondary'}
          icon={<Route />} aria-label="Attack path" aria-pressed={pathOnly} disabled={!attackPath.size}
          title={!attackPath.size ? 'No alert source in this snapshot' : undefined}
          onClick={toggleAttackPath}
        >
          Attack path
        </Button>
        <Button
          type="button" size="small" variant={showCommandLines ? 'brand-secondary' : 'neutral-secondary'}
          icon={<Terminal />} aria-label="Command lines" aria-pressed={showCommandLines}
          onClick={() => setShowCommandLines(!showCommandLines)}
        >
          Command lines
        </Button>
      </div>

      <div className="flex w-full flex-wrap items-start border border-neutral-border">
        <div className="min-w-0 flex-[2_1_21rem] overflow-x-auto">
          {rows.length === 0 ? (
            <p role="status" className="break-words p-3 text-body font-body text-subtext-color">No process matches “{query.trim()}”.</p>
          ) : (
            <Table
              role="treegrid"
              aria-label="Process tree"
              className="table-fixed"
              header={
                <Table.HeaderRow>
                  <Table.HeaderCell scope="col">Process</Table.HeaderCell>
                  <Table.HeaderCell scope="col" style={{ width: '4rem' }}>PID</Table.HeaderCell>
                  <Table.HeaderCell scope="col" style={{ width: '4rem' }}>Signals</Table.HeaderCell>
                </Table.HeaderRow>
              }
            >
              {rows.map((row, index) => {
                const { process } = row;
                const isSelected = selected?.id === process.id;
                return (
                  <Table.Row
                    key={process.id}
                    ref={(element) => {
                      if (element) rowRefs.current.set(process.id, element);
                      else rowRefs.current.delete(process.id);
                    }}
                    clickable
                    className={cn(
                      'cursor-pointer focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-focus-border',
                      isSelected && 'bg-neutral-100',
                    )}
                    aria-level={row.depth + 1}
                    aria-selected={isSelected}
                    aria-expanded={row.childCount ? row.expanded : undefined}
                    tabIndex={process.id === focusableId ? 0 : -1}
                    onFocus={() => setFocusedId(process.id)}
                    onClick={() => {
                      rowRefs.current.get(process.id)?.focus();
                      setSelectedId(process.id);
                    }}
                    onKeyDown={(event) => handleRowKey(event, row, index)}
                  >
                    <Table.Cell className="h-auto min-h-9 min-w-0 items-stretch gap-0 px-1">
                      <BranchGuides row={row} onAttackPath={attackPath.has(process.id)} />
                      <span className="flex h-9 w-6 shrink-0 items-center justify-center">
                        {row.childCount > 0 && (needle ? (
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
                              toggleBranch(row);
                            }}
                          />
                        ))}
                      </span>
                      <div className="flex min-w-0 flex-1 flex-col justify-center py-1 pr-1">
                        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                          <span title={process.process_name} className="max-w-full truncate text-body-bold font-body-bold">{process.process_name}</span>
                          <ProcessIndicators process={process} />
                        </div>
                        {showCommandLines && process.command_line && (
                          <span title={process.command_line} className="truncate text-caption font-monospace-body text-subtext-color">
                            {process.command_line}
                          </span>
                        )}
                      </div>
                    </Table.Cell>
                    <Table.Cell className="h-auto min-h-9 px-2 text-caption font-monospace-body tabular-nums">{process.process_id}</Table.Cell>
                    <Table.Cell className="h-auto min-h-9 justify-end px-2"><RowSignals process={process} /></Table.Cell>
                  </Table.Row>
                );
              })}
            </Table>
          )}
        </div>

        <div className="min-w-0 flex-[1_1_15rem] bg-neutral-50 ring-1 ring-inset ring-neutral-border">
          {selected ? (
            <ProcessSnapshotInspector
              key={selected.id}
              process={selected}
              parent={selectedParent}
              onClose={() => {
                setSelectedId(null);
                const target = rowRefs.current.get(selected.id) ?? rowRefs.current.get(focusableId ?? '') ?? filterRef.current;
                target?.focus();
              }}
            />
          ) : <p className="p-3 text-body font-body text-subtext-color">Select a process to view its details.</p>}
        </div>
      </div>
    </>
  );
}

export function ProcessTreeSnapshot({
  processes,
  timestamp,
}: {
  processes: readonly ProcessTreeNode[];
  timestamp?: string;
}) {
  const [open, setOpen] = useState(false);
  const captured = formatAbsoluteTime(timestamp, PROCESS_TREE_UTC_FORMAT, 'utc');

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
        {captured && (
          <div className="text-caption font-caption text-subtext-color">
            Captured <time dateTime={timestamp}>{captured}</time>
          </div>
        )}
        <ProcessTreeDetails processes={processes} />
      </div>
    </Accordion>
  );
}
