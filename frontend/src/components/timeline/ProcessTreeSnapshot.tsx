import { useCallback, useMemo, useRef, useState, type RefObject } from 'react';
import { IconButton, Switch, TextField } from '@tidemark-security/ux';
import { Maximize2, Search, X } from 'lucide-react';
import { FullscreenViewer } from '@/components/overlays/FullscreenViewer';
import type { ProcessTreeNode } from '@/types/generated/models/ProcessTreeNode';
import { formatAbsoluteTime } from '@/utils/dateFormatters';
import { PROCESS_TREE_UTC_FORMAT, ProcessSnapshotInspector } from './ProcessSnapshotInspector';
import { ProcessTreeTable } from './ProcessTreeTable';
import { getAttackPath, getProcessTreeRows, indexProcesses, type ProcessTreeRow } from './processTreeRows';

function TreeControls({
  query,
  onQueryChange,
  hasAttackPath,
  attackPathOnly,
  onAttackPathChange,
  showCommandLines,
  onCommandLinesChange,
  inputRef,
}: {
  query: string;
  onQueryChange: (query: string) => void;
  hasAttackPath: boolean;
  attackPathOnly: boolean;
  onAttackPathChange: (checked: boolean) => void;
  showCommandLines: boolean;
  onCommandLinesChange: (checked: boolean) => void;
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  return (
    <div className="flex min-w-0 flex-1 basis-64 flex-wrap items-center gap-x-3 gap-y-2">
      <div className="flex min-w-0 flex-[1_1_14rem] items-center gap-1">
        <TextField className="min-w-0 flex-1" icon={<Search />}>
          <TextField.Input
            ref={inputRef}
            type="search"
            aria-label="Filter processes"
            placeholder="Filter by name, PID or command line"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
          />
        </TextField>
        {query && (
          <IconButton
            type="button" size="small" variant="neutral-tertiary" icon={<X />} aria-label="Clear filter"
            onClick={() => { onQueryChange(''); inputRef.current?.focus(); }}
          />
        )}
      </div>
      {hasAttackPath && (
        <label className="inline-flex items-center gap-2 text-caption font-caption text-default-font">
          <Switch checked={attackPathOnly} onCheckedChange={onAttackPathChange} />
          Attack path only
        </label>
      )}
      <label className="inline-flex items-center gap-2 text-caption font-caption text-default-font">
        <Switch checked={showCommandLines} onCheckedChange={onCommandLinesChange} />
        Command lines
      </label>
    </div>
  );
}

export function ProcessTreeSnapshot({
  processes,
  hostname,
  timestamp,
}: {
  processes: readonly ProcessTreeNode[];
  hostname?: string | null;
  timestamp?: string;
}) {
  const processIndex = useMemo(() => indexProcesses(processes), [processes]);
  const attackPath = useMemo(() => getAttackPath(processIndex), [processIndex]);
  const hasAttackPath = attackPath.size > 0;
  const [selectedId, setSelectedId] = useState<string>();
  const [expansion, setExpansion] = useState<ReadonlyMap<string, boolean>>(() => new Map());
  const [query, setQuery] = useState('');
  const [attackPathOnly, setAttackPathOnly] = useState(true);
  const [showCommandLines, setShowCommandLines] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);
  const maximizeRef = useRef<HTMLButtonElement>(null);
  const previewFilterRef = useRef<HTMLInputElement>(null);
  const viewerFilterRef = useRef<HTMLInputElement>(null);
  const viewerBodyRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement>(null);
  const needle = query.trim().toLowerCase();
  const pathOnly = hasAttackPath && attackPathOnly;
  const rows = useMemo(() => getProcessTreeRows(
    processIndex, attackPath, pathOnly, needle, expansion,
  ), [processIndex, attackPath, pathOnly, needle, expansion]);
  const selected = selectedId ? processIndex.byId.get(selectedId) : undefined;
  const selectedParent = selected?.parent_id ? processIndex.byId.get(selected.parent_id) : undefined;
  const captured = formatAbsoluteTime(timestamp, PROCESS_TREE_UTC_FORMAT, 'utc');

  const returnFocus = useCallback(() => {
    const opener = openerRef.current;
    return opener?.isConnected ? opener : maximizeRef.current;
  }, []);

  function openViewer(opener: HTMLElement, processId?: string) {
    openerRef.current = opener;
    if (processId) {
      setSelectedId(processId);
    } else if (!rows.some((row) => row.process.id === selectedId)) {
      const initialRow = rows.find((row) => row.process.is_alert_source) ?? rows[0];
      setSelectedId(initialRow?.process.id);
    }
    setViewerOpen(true);
  }

  function toggleBranch(row: ProcessTreeRow) {
    setExpansion((previous) => new Map(previous).set(row.process.id, !row.expanded));
  }

  function changeAttackPath(checked: boolean) {
    if (checked) {
      setExpansion((previous) => new Map([...previous].filter(([id]) => !attackPath.has(id))));
    }
    setAttackPathOnly(checked);
  }

  const controls = {
    query,
    onQueryChange: setQuery,
    hasAttackPath,
    attackPathOnly: pathOnly,
    onAttackPathChange: changeAttackPath,
    showCommandLines,
    onCommandLinesChange: setShowCommandLines,
  };
  const tree = { rows, attackPath, selectedId, query, showCommandLines, onToggleBranch: toggleBranch };

  return (
    <div className="flex w-full min-w-0 flex-col gap-2">
      {captured && (
        <div className="text-caption font-caption text-subtext-color">
          Captured <time dateTime={timestamp}>{captured}</time>
        </div>
      )}
      {processes.length === 0 ? (
        <p role="status" className="border-t border-neutral-border py-3 text-body font-body text-subtext-color">
          No process telemetry for this snapshot.
        </p>
      ) : (
        <>
          <div className="flex items-start gap-2">
            <TreeControls {...controls} inputRef={previewFilterRef} />
            <IconButton
              ref={maximizeRef}
              type="button"
              size="medium"
              variant="neutral-secondary"
              icon={<Maximize2 />}
              aria-label="Maximize process tree"
              aria-haspopup="dialog"
              title="Maximize process tree"
              onClick={(event) => openViewer(event.currentTarget)}
            />
          </div>
          <div className="process-tree-scroll max-h-[27.5rem] min-w-0 overflow-auto border border-neutral-border">
            <ProcessTreeTable {...tree} opensViewer onSelect={(id, row) => openViewer(row, id)} />
          </div>

          <FullscreenViewer
            open={viewerOpen}
            onOpenChange={setViewerOpen}
            title={hostname ? `Process tree · ${hostname}` : 'Process tree'}
            description={captured ? `Process snapshot captured ${captured}.` : 'Browse the snapshot and inspect a process.'}
            interactive
            returnFocus={returnFocus}
            toolbar={<TreeControls {...controls} inputRef={viewerFilterRef} />}
          >
            <div ref={viewerBodyRef} className="process-tree-viewer h-full">
              <div className="process-tree-viewer-layout h-full min-h-0">
                <div className="process-tree-scroll min-h-0 min-w-0 overflow-auto bg-default-background">
                  <ProcessTreeTable
                    {...tree}
                    showStarted
                    onSelect={(id, row) => {
                      row.focus();
                      setSelectedId((previous) => previous === id ? undefined : id);
                    }}
                  />
                </div>
                <div className="process-tree-viewer-inspector min-h-0 min-w-0 overflow-auto border-t border-neutral-border bg-neutral-50">
                  {selected ? (
                    <ProcessSnapshotInspector
                      key={selected.id}
                      process={selected}
                      parent={selectedParent}
                      onClose={() => {
                        setSelectedId(undefined);
                        const target = viewerBodyRef.current?.querySelector<HTMLElement>('tr[aria-selected="true"], tr[tabindex="0"]') ?? viewerFilterRef.current;
                        target?.focus();
                      }}
                    />
                  ) : <p className="p-3 text-body font-body text-subtext-color">Select a process to view its details.</p>}
                </div>
              </div>
            </div>
          </FullscreenViewer>
        </>
      )}
    </div>
  );
}
