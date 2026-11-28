import type { ProcessTreeNode } from '@/types/generated/models/ProcessTreeNode';

export function indexProcesses(processes: readonly ProcessTreeNode[]) {
  const byId = new Map(processes.map((process) => [process.id, process]));
  const byParent = new Map<string | null, ProcessTreeNode[]>();

  for (const process of processes) {
    const parentId = process.parent_id ?? null;
    const siblings = byParent.get(parentId);
    if (siblings) siblings.push(process);
    else byParent.set(parentId, [process]);
  }

  return { byId, byParent };
}

type ProcessIndex = ReturnType<typeof indexProcesses>;

function keepAncestors(index: ProcessIndex, ids: Set<string>, id: string) {
  let current: string | null = id;
  while (current !== null && !ids.has(current)) {
    ids.add(current);
    current = index.byId.get(current)?.parent_id ?? null;
  }
}

export function getAttackPath(index: ProcessIndex) {
  const sources = [...index.byId.values()].filter((process) => process.is_alert_source);
  const ancestry = new Set<string>();
  const descendants = new Set<string>();
  const pending = [...sources];

  for (const source of sources) keepAncestors(index, ancestry, source.id);
  while (pending.length) {
    const process = pending.pop()!;
    if (descendants.has(process.id)) continue;
    descendants.add(process.id);
    for (const child of index.byParent.get(process.id) ?? []) pending.push(child);
  }

  return new Set([...ancestry, ...descendants]);
}

type RowPosition = {
  process: ProcessTreeNode;
  depth: number;
  guides: boolean[];
  hasNextSibling: boolean;
};

export type ProcessTreeRow = RowPosition & { expanded: boolean; childCount: number };

export function getProcessTreeRows(
  index: ProcessIndex,
  attackPath: ReadonlySet<string>,
  attackPathOnly: boolean,
  query: string,
  expansion: ReadonlyMap<string, boolean>,
) {
  const matchingBranches = new Set<string>();
  const isOnDisplayedPath = (process: ProcessTreeNode) => !attackPathOnly || attackPath.has(process.id);

  if (query) {
    for (const process of index.byId.values()) {
      if (isOnDisplayedPath(process) && [
        process.process_name,
        String(process.process_id),
        process.command_line ?? '',
      ].some((field) => field.toLowerCase().includes(query))) {
        keepAncestors(index, matchingBranches, process.id);
      }
    }
  }

  const isVisible = (process: ProcessTreeNode) =>
    isOnDisplayedPath(process) && (!query || matchingBranches.has(process.id));
  const rows: ProcessTreeRow[] = [];
  const pending: RowPosition[] = [];

  function appendSiblings(processes: ProcessTreeNode[], depth: number, guides: boolean[]) {
    for (let i = processes.length - 1; i >= 0; i--) {
      pending.push({ process: processes[i], depth, guides, hasNextSibling: i < processes.length - 1 });
    }
  }

  appendSiblings((index.byParent.get(null) ?? []).filter(isVisible), 0, []);
  while (pending.length) {
    const row = pending.pop()!;
    const children = (index.byParent.get(row.process.id) ?? []).filter(isVisible);
    const expanded = children.length > 0 && (Boolean(query) || (expansion.get(row.process.id) ?? attackPath.has(row.process.id)));
    rows.push({ ...row, expanded, childCount: children.length });

    if (expanded) {
      const guides = row.depth === 0 ? row.guides : [...row.guides.slice(-5), row.hasNextSibling];
      appendSiblings(children, row.depth + 1, guides);
    }
  }

  return rows;
}
