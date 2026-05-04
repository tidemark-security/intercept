# Timeline Graph (React Flow) — Agent Notes

Scope: this file. Rules for working on `TimelineGraphView.tsx` (the React Flow
timeline graph). The timeline forms have their own `AGENTS.md` in
`forms/`.

## Resize handling — match the docs example

We use the stock React Flow `<NodeResizer />` inside both
`TimelineGraphNodeCard` and `TimelineGraphGroupCard` with **no callbacks**.
All resize state flows through React Flow's normal `NodeChange` pipeline
(`useNodesState` → `onNodesChange`). Do **not** reintroduce custom
`onResizeStart`/`onResize`/`onResizeEnd` handlers, document-level pointer
listeners, direction inference, or hand-rolled resize math. We tried that
multiple times and every variant fought React Flow's internal store and
caused snap-back.

If you think you need a custom resizer, re-read
`tmp/node_resizer.md` (the official docs example) first.

## Persisting resize to the backend

Resize persistence happens in **one** place: `handleNodesChange` (wraps
`onNodesChange`). React Flow signals resize-end with a single
`{ type: 'dimensions', resizing: false, dimensions: {...} }` change.
On that signal we send `move_node` + `resize_node` ops via
`sendGraphPatch`.

Two non-obvious bugs we hit and the fixes:

### Bug 1 — Duplicate PATCH → 409 "Graph changed"

Calling `sendGraphPatch` from inside a `setNodes(updater)` callback caused
the patch to fire twice (React may invoke updaters more than once). The
second request still carried the original `base_revision` and lost the
optimistic-concurrency check.

**Rule:** never call `sendGraphPatch` from inside a `setNodes`/`setEdges`
updater. Read current nodes from `nodesRef.current` (kept in sync via a
small `useEffect`) and call the patch directly from the change handler.

### Bug 2 — Children of a resized group "drift"

When a group is resized from the top or left, React Flow's resizer
re-writes each child's *relative* position so they stay anchored in
absolute space (see `XYResizer` in
`@xyflow/system/dist/esm/index.mjs`, the `childChanges` branch). Those
position changes ARE applied to local state via `onNodesChange`, but they
are not part of the resize-end signal — so if we only persist the parent's
`move_node` + `resize_node`, the backend keeps the old child positions and
the next cache reload visually shifts the children.

**Rule:** at resize-end, also emit a `move_node` op for every node whose
`parentId === change.id`, using the current (already-compensated) child
positions from `nodesRef.current`.

## Keep these constraints

- `<NodeResizer />` in cards: no callbacks, no refs, no wrappers.
- `handleNodesChange` is the single resize-persistence path.
- Don't read `nodes` from the closure inside async/deferred paths — use
  `nodesRef.current`.
- Children of a resized group must be persisted alongside the parent.
- One PATCH per resize-end. If you see a `409` toast, you have either
  reintroduced a duplicate-call path or stopped including children.
