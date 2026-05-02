import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  addEdge,
  Background,
  BackgroundVariant,
  BaseEdge,
  ConnectionMode,
  Controls,
  EdgeToolbar,
  Handle,
  MarkerType,
  MiniMap,
  NodeResizer,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  getSmoothStepPath,
  reconnectEdge,
  useEdgesState,
  useInternalNode,
  useNodesState,
  useReactFlow,
  useStoreApi,
  type Connection,
  type DefaultEdgeOptions,
  type Edge,
  type EdgeProps,
  type EdgeTypes,
  type Node,
  type NodeProps,
  type NodeTypes,
  type OnConnect,
  type OnReconnect,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Button } from '@/components/buttons/Button';
import { IconButton } from '@/components/buttons/IconButton';
import { CopyableTimestamp } from '@/components/data-display/CopyableTimestamp';
import { Tooltip } from '@/components/overlays/Tooltip';
import { TimelineItemRenderer } from '@/components/timeline/TimelineItemRenderer';
import { useToast } from '@/contexts/ToastContext';
import { useTheme } from '@/contexts/ThemeContext';
import { usePatchTimelineGraph, useTimelineGraph } from '@/hooks/useTimelineGraph';
import { cn } from '@/utils/cn';
import { getTimelineItems } from '@/utils/timelineHelpers';
import {
  getTimelineItemIcon,
  getTimelineItemLabel,
} from '@/utils/timelineMapping';
import type { LinkTemplate } from '@/utils/linkTemplates';
import type { TimelineItem } from '@/types/timeline';
import type { TimelineGraphOperation } from '@/types/generated/models/TimelineGraphOperation';
import type { TimelineGraphRead } from '@/types/generated/models/TimelineGraphRead';
import { ArrowLeft, ArrowLeftRight, ArrowRight, Flag, GitBranch, Group, Highlighter, Magnet, Minus, Pencil, Search, Trash, Trash2, X } from 'lucide-react';

interface TimelineGraphViewProps {
  items: TimelineItem[];
  entityId: number | null;
  entityType: 'case' | 'task';
  sortBy?: 'created_at' | 'timestamp';
  linkTemplates?: LinkTemplate[];
  onSelectItem?: (itemId: string) => void;
  onFlagItem?: (itemId: string) => void;
  onHighlightItem?: (itemId: string) => void;
  onDeleteItem?: (itemId: string) => void;
  onEditItem?: (itemId: string) => void;
}


function GraphNodeActionButton({
  label,
  icon,
  variant,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  variant?: React.ComponentProps<typeof IconButton>['variant'];
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <IconButton
          aria-label={label}
          size="small"
          variant={variant}
          icon={icon}
          onClick={onClick}
        />
      </Tooltip.Trigger>
      <Tooltip.Content side="top" align="center" sideOffset={4}>
        {label}
      </Tooltip.Content>
    </Tooltip.Root>
  );
}
type NodeHandle = 'north' | 'east' | 'south' | 'west';
type EdgeMarkerMode = 'none' | 'forward' | 'reverse' | 'bidirectional';

interface TimelineGraphNodeData extends Record<string, unknown> {
  itemId: string;
  itemType: string;
  title: string;
  subtitle: string;
  label: string;
  timestamp: string;
  timestampValue: string | null;
  createdBy: string;
  createdAtValue: string | null;
  width?: number;
  height?: number;
  autoSize?: boolean;
  flagged: boolean;
  highlighted: boolean;
  item: TimelineItem;
  entityId: number | null;
  entityType: 'case' | 'task';
  sortBy: 'created_at' | 'timestamp';
  linkTemplates?: LinkTemplate[];
}

interface TimelineGraphGroupData extends Record<string, unknown> {
  label: string;
  width: number;
  height: number;
}

interface TimelineGraphEdgeData extends Record<string, unknown> {
  marker: EdgeMarkerMode;
  floating?: boolean;
}

type TimelineGraphNode = Node<TimelineGraphNodeData, 'timelineItem'>;
type TimelineGraphGroupNode = Node<TimelineGraphGroupData, 'timelineGroup'>;
type TimelineFlowNode = TimelineGraphNode | TimelineGraphGroupNode;
type TimelineGraphEdge = Edge<TimelineGraphEdgeData, 'timelineGraph'>;

interface ServerGraphNode {
  id?: string;
  item_id?: string;
  itemId?: string;
  position?: { x: number; y: number };
  width?: number;
  height?: number;
  x?: number;
  y?: number;
  kind?: string;
  label?: string | null;
  parent_node_id?: string | null;
  parentNodeId?: string | null;
}

interface ServerGraphEdge {
  id?: string;
  source?: string;
  target?: string;
  source_handle?: string | null;
  target_handle?: string | null;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  label?: string | null;
  marker?: EdgeMarkerMode | null;
}

const GRID_SIZE = 14;
const SNAP_GRID: [number, number] = [GRID_SIZE, GRID_SIZE];
const NODE_WIDTH = GRID_SIZE * 30;
const NODE_HEIGHT = GRID_SIZE * 22;
const NODE_MIN_WIDTH = GRID_SIZE * 24;
const NODE_MIN_HEIGHT = GRID_SIZE * 14;
const NODE_MAX_WIDTH = GRID_SIZE * 48;
const NODE_MAX_HEIGHT = GRID_SIZE * 38;
const DEFAULT_NODE_POSITION = { x: 80, y: 80 };
const NODE_HANDLES: NodeHandle[] = ['north', 'east', 'south', 'west'];
const GRAPH_LAYOUT_STORAGE_KEY = 'intercept.timeline-graph-layout';
const GRAPH_SETTINGS_STORAGE_KEY = 'intercept.timeline-graph-settings';
const DEFAULT_ITEMS_PANE_WIDTH = 288;
const MIN_ITEMS_PANE_WIDTH = 220;
const MAX_ITEMS_PANE_WIDTH = 520;
const DEFAULT_DETAIL_PANE_HEIGHT = 320;
const MIN_DETAIL_PANE_HEIGHT = 192;
const MAX_DETAIL_PANE_HEIGHT = 560;
const MIN_GRAPH_CANVAS_HEIGHT = 260;
const PROXIMITY_CONNECT_DISTANCE = GRID_SIZE * 15;
const COLLISION_MARGIN = GRID_SIZE * 5;
const MAX_COLLISION_ITERATIONS = 80;
const PROXIMITY_PREVIEW_EDGE_CLASS = 'timeline-graph-proximity-preview';

const handlePositions: Record<NodeHandle, Position> = {
  north: Position.Top,
  east: Position.Right,
  south: Position.Bottom,
  west: Position.Left,
};

const resizeHandleStyle = {
  width: 14,
  height: 14,
  borderRadius: 2,
  border: '1px solid rgb(var(--color-neutral-1000))',
  backgroundColor: 'rgb(var(--color-default-background))',
  boxShadow: '0 0 0 1px rgb(var(--color-default-background)), 0 2px 8px rgb(0 0 0 / 0.28)',
  opacity: 1,
} satisfies React.CSSProperties;

const resizeLineStyle = {
  borderColor: 'rgb(var(--color-neutral-1000))',
} satisfies React.CSSProperties;

const defaultEdgeOptions: DefaultEdgeOptions = {
  type: 'timelineGraph',
  markerEnd: {
    type: MarkerType.ArrowClosed,
    width: 18,
    height: 18,
    color: 'rgb(var(--color-subtext-color))',
  },
  style: {
    stroke: 'rgb(var(--color-subtext-color))',
    strokeWidth: 1.75,
  },
  labelBgStyle: {
    fill: 'rgb(var(--color-default-background))',
  },
  labelStyle: {
    fill: 'rgb(var(--color-default-font))',
    fontSize: 12,
    fontWeight: 500,
  },
  labelBgPadding: [8, 4],
  labelBgBorderRadius: 0,
  interactionWidth: 24,
};

const edgeMarkerOption = {
  type: MarkerType.ArrowClosed,
  width: 18,
  height: 18,
  color: 'rgb(var(--color-subtext-color))',
};

function getEdgeMarkerProps(marker: EdgeMarkerMode): Pick<TimelineGraphEdge, 'markerStart' | 'markerEnd'> {
  if (marker === 'none') return { markerStart: undefined, markerEnd: undefined };
  if (marker === 'reverse') return { markerStart: edgeMarkerOption, markerEnd: undefined };
  if (marker === 'bidirectional') return { markerStart: edgeMarkerOption, markerEnd: edgeMarkerOption };
  return { markerStart: undefined, markerEnd: edgeMarkerOption };
}

function withFloatingEdgeData(edge: TimelineGraphEdge, floating: boolean): TimelineGraphEdge {
  if (isProximityPreviewEdge(edge)) {
    return {
      ...edge,
      data: { marker: edge.data?.marker || 'none', floating: true },
    };
  }

  return {
    ...edge,
    data: { marker: edge.data?.marker || 'forward', floating },
  };
}

function isProximityPreviewEdge(edge: TimelineGraphEdge): boolean {
  return edge.className === PROXIMITY_PREVIEW_EDGE_CLASS;
}

function withoutProximityPreviewEdges(edges: TimelineGraphEdge[]): TimelineGraphEdge[] {
  return edges.filter((edge) => !isProximityPreviewEdge(edge));
}

function getNodeDimension(value: number | null | undefined, fallback: number, min: number, max: number): number {
  return clampSize(typeof value === 'number' ? value : fallback, min, max);
}

function getNodeSize(node: TimelineFlowNode): { width: number; height: number } {
  const maxWidth = node.type === 'timelineGroup' ? NODE_MAX_WIDTH * 2 : NODE_MAX_WIDTH;
  const maxHeight = node.type === 'timelineGroup' ? NODE_MAX_HEIGHT * 2 : NODE_MAX_HEIGHT;
  const measuredWidth = node.measured?.width;
  const measuredHeight = node.measured?.height;

  return {
    width: getNodeDimension(node.width ?? measuredWidth, (node.data.width as number | undefined) ?? NODE_WIDTH, NODE_MIN_WIDTH, maxWidth),
    height: getNodeDimension(node.height ?? measuredHeight, (node.data.height as number | undefined) ?? NODE_HEIGHT, NODE_MIN_HEIGHT, maxHeight),
  };
}

function getNodeAbsolutePosition(node: TimelineFlowNode, nodeById: Map<string, TimelineFlowNode>): { x: number; y: number } {
  if (!node.parentId) {
    return node.position;
  }

  const parentNode = nodeById.get(node.parentId);
  if (!parentNode) {
    return node.position;
  }

  const parentPosition = getNodeAbsolutePosition(parentNode, nodeById);
  return {
    x: parentPosition.x + node.position.x,
    y: parentPosition.y + node.position.y,
  };
}

function getNodeCollisionBounds(
  node: TimelineFlowNode,
  nodeById: Map<string, TimelineFlowNode>,
): { left: number; right: number; top: number; bottom: number; centerX: number; centerY: number } {
  const size = getNodeSize(node);
  const position = getNodeAbsolutePosition(node, nodeById);
  const marginOffset = COLLISION_MARGIN / 2;
  const left = position.x - marginOffset;
  const right = position.x + size.width + marginOffset;
  const top = position.y - marginOffset;
  const bottom = position.y + size.height + marginOffset;

  return {
    left,
    right,
    top,
    bottom,
    centerX: (left + right) / 2,
    centerY: (top + bottom) / 2,
  };
}

function getNodeBounds(
  node: TimelineFlowNode,
  nodeById: Map<string, TimelineFlowNode>,
): { left: number; right: number; top: number; bottom: number } {
  const size = getNodeSize(node);
  const position = getNodeAbsolutePosition(node, nodeById);

  return {
    left: position.x,
    right: position.x + size.width,
    top: position.y,
    bottom: position.y + size.height,
  };
}

function isNodeCenterInsideGroup(
  node: TimelineFlowNode,
  group: TimelineGraphGroupNode,
  nodeById: Map<string, TimelineFlowNode>,
): boolean {
  const nodeCenter = getNodeCenter(node, nodeById);
  const groupBounds = getNodeBounds(group, nodeById);

  return (
    nodeCenter.x >= groupBounds.left &&
    nodeCenter.x <= groupBounds.right &&
    nodeCenter.y >= groupBounds.top &&
    nodeCenter.y <= groupBounds.bottom
  );
}

function getCollisionVector(
  first: TimelineFlowNode,
  second: TimelineFlowNode,
  nodeById: Map<string, TimelineFlowNode>,
): { x: number; y: number } | null {
  const firstBounds = getNodeCollisionBounds(first, nodeById);
  const secondBounds = getNodeCollisionBounds(second, nodeById);
  const overlapX = Math.min(firstBounds.right, secondBounds.right) - Math.max(firstBounds.left, secondBounds.left);
  const overlapY = Math.min(firstBounds.bottom, secondBounds.bottom) - Math.max(firstBounds.top, secondBounds.top);

  if (overlapX <= 0 || overlapY <= 0) {
    return null;
  }

  if (overlapX < overlapY) {
    const direction = firstBounds.centerX <= secondBounds.centerX ? -1 : 1;
    return { x: overlapX * direction, y: 0 };
  }

  const direction = firstBounds.centerY <= secondBounds.centerY ? -1 : 1;
  return { x: 0, y: overlapY * direction };
}

function clampNodeToParent<TNode extends TimelineFlowNode>(node: TNode, nodeById: Map<string, TimelineFlowNode>): TNode {
  if (!node.parentId) {
    return node;
  }

  const parentNode = nodeById.get(node.parentId);
  if (!parentNode) {
    return node;
  }

  const nodeSize = getNodeSize(node);
  const parentSize = getNodeSize(parentNode);
  return {
    ...node,
    position: {
      x: clampSize(node.position.x, 0, Math.max(0, parentSize.width - nodeSize.width)),
      y: clampSize(node.position.y, 0, Math.max(0, parentSize.height - nodeSize.height)),
    },
  };
}

function moveNodeBy<TNode extends TimelineFlowNode>(node: TNode, deltaX: number, deltaY: number, nodeById?: Map<string, TimelineFlowNode>): TNode {
  const movedNode = {
    ...node,
    position: {
      x: node.position.x + deltaX,
      y: node.position.y + deltaY,
    },
  };

  return nodeById ? clampNodeToParent(movedNode, nodeById) : movedNode;
}

function buildMoveOperations(nodes: TimelineFlowNode[]): TimelineGraphOperation[] {
  return nodes.map((node) => ({
    type: 'move_node' as const,
    node_id: node.id,
    position: node.position,
  }));
}

function shouldResolveNodeCollision(first: TimelineFlowNode, second: TimelineFlowNode): boolean {
  if (first.parentId || second.parentId) {
    return first.parentId === second.parentId;
  }

  return true;
}

function resolveNodeCollisions(allNodes: TimelineFlowNode[], pinnedNodeId?: string): { nodes: TimelineFlowNode[]; movedNodes: TimelineFlowNode[] } {
  const resolvedNodes = allNodes.map((node) => ({ ...node, position: { ...node.position } }));
  const changedNodeIds = new Set<string>();

  for (let iteration = 0; iteration < MAX_COLLISION_ITERATIONS; iteration += 1) {
    let overlapResolved = false;
    const nodeById = new Map(resolvedNodes.map((node) => [node.id, node]));

    for (let firstIndex = 0; firstIndex < resolvedNodes.length; firstIndex += 1) {
      for (let secondIndex = firstIndex + 1; secondIndex < resolvedNodes.length; secondIndex += 1) {
        const firstNode = resolvedNodes[firstIndex];
        const secondNode = resolvedNodes[secondIndex];
        if (!shouldResolveNodeCollision(firstNode, secondNode)) {
          continue;
        }

        const collisionVector = getCollisionVector(firstNode, secondNode, nodeById);

        if (!collisionVector) {
          continue;
        }

        overlapResolved = true;

        if (firstNode.id === pinnedNodeId) {
          resolvedNodes[secondIndex] = moveNodeBy(secondNode, -collisionVector.x, -collisionVector.y, nodeById);
          changedNodeIds.add(secondNode.id);
        } else if (secondNode.id === pinnedNodeId) {
          resolvedNodes[firstIndex] = moveNodeBy(firstNode, collisionVector.x, collisionVector.y, nodeById);
          changedNodeIds.add(firstNode.id);
        } else {
          resolvedNodes[firstIndex] = moveNodeBy(firstNode, collisionVector.x / 2, collisionVector.y / 2, nodeById);
          resolvedNodes[secondIndex] = moveNodeBy(secondNode, -collisionVector.x / 2, -collisionVector.y / 2, nodeById);
          changedNodeIds.add(firstNode.id);
          changedNodeIds.add(secondNode.id);
        }
      }
    }

    if (!overlapResolved) {
      break;
    }
  }

  return {
    nodes: resolvedNodes,
    movedNodes: resolvedNodes.filter((node) => changedNodeIds.has(node.id)),
  };
}

function getNodeCenter(node: TimelineFlowNode, nodeById?: Map<string, TimelineFlowNode>): { x: number; y: number } {
  const size = getNodeSize(node);
  const position = nodeById ? getNodeAbsolutePosition(node, nodeById) : node.position;
  return {
    x: position.x + size.width / 2,
    y: position.y + size.height / 2,
  };
}

function findContainingGroup(node: TimelineFlowNode, allNodes: TimelineFlowNode[]): TimelineGraphGroupNode | null {
  if (node.type !== 'timelineItem') {
    return null;
  }

  const nodeById = new Map(allNodes.map((candidate) => [candidate.id, candidate]));
  const nodeCenter = getNodeCenter(node, nodeById);

  return allNodes
    .filter((candidate): candidate is TimelineGraphGroupNode => candidate.type === 'timelineGroup' && candidate.id !== node.id)
    .filter((group) => {
      const groupBounds = getNodeCollisionBounds(group, nodeById);
      return (
        nodeCenter.x >= groupBounds.left &&
        nodeCenter.x <= groupBounds.right &&
        nodeCenter.y >= groupBounds.top &&
        nodeCenter.y <= groupBounds.bottom
      );
    })
    .sort((first, second) => getNodeSize(first).width * getNodeSize(first).height - getNodeSize(second).width * getNodeSize(second).height)[0] ?? null;
}

function getPositionInGroup(node: TimelineGraphNode, group: TimelineGraphGroupNode, allNodes: TimelineFlowNode[]): { x: number; y: number } {
  const nodeById = new Map(allNodes.map((candidate) => [candidate.id, candidate]));
  const nodePosition = getNodeAbsolutePosition(node, nodeById);
  const groupPosition = getNodeAbsolutePosition(group, nodeById);
  const nodeSize = getNodeSize(node);
  const groupSize = getNodeSize(group);

  return {
    x: clampSize(nodePosition.x - groupPosition.x, 0, Math.max(0, groupSize.width - nodeSize.width)),
    y: clampSize(nodePosition.y - groupPosition.y, 0, Math.max(0, groupSize.height - nodeSize.height)),
  };
}

function attachNodeToGroup(node: TimelineGraphNode, group: TimelineGraphGroupNode, allNodes: TimelineFlowNode[]): TimelineGraphNode {
  return {
    ...node,
    parentId: group.id,
    extent: undefined,
    position: getPositionInGroup(node, group, allNodes),
  };
}

function removeNodesFromGraphState(
  currentNodes: TimelineFlowNode[],
  currentEdges: TimelineGraphEdge[],
  nodeIds: string[],
): { nodes: TimelineFlowNode[]; edges: TimelineGraphEdge[]; operations: TimelineGraphOperation[]; removedItemIds: string[] } {
  const removedNodeIds = new Set(nodeIds);
  const nodeById = new Map(currentNodes.map((node) => [node.id, node]));
  const removedItemIds = currentNodes.flatMap((node) => (
    removedNodeIds.has(node.id) && node.type === 'timelineItem' ? [node.data.itemId] : []
  ));
  const detachedNodes: TimelineFlowNode[] = [];

  const nextNodes = currentNodes.flatMap<TimelineFlowNode>((node) => {
    if (removedNodeIds.has(node.id)) {
      return [];
    }

    if (!node.parentId || !removedNodeIds.has(node.parentId)) {
      return [node];
    }

    const detachedNode = {
      ...node,
      parentId: undefined,
      extent: undefined,
      position: getNodeAbsolutePosition(node, nodeById),
    } as TimelineFlowNode;
    detachedNodes.push(detachedNode);
    return [detachedNode];
  });
  const nextEdges = currentEdges.filter((edge) => !removedNodeIds.has(edge.source) && !removedNodeIds.has(edge.target));

  return {
    nodes: nextNodes,
    edges: nextEdges,
    operations: [
      ...nodeIds.map((nodeId) => ({ type: 'remove_node' as const, node_id: nodeId })),
      ...detachedNodes.flatMap((node) => ([{
        type: 'move_node' as const,
        node_id: node.id,
        position: node.position,
      }, {
        type: 'update_node_metadata' as const,
        node_id: node.id,
        parent_node_id: null,
      }])),
    ],
    removedItemIds,
  };
}

function getMinimumGroupSize(groupId: string, allNodes: TimelineFlowNode[]): { width: number; height: number } {
  const childNodes = allNodes.filter((node) => node.parentId === groupId);

  if (childNodes.length === 0) {
    return { width: NODE_MIN_WIDTH, height: NODE_MIN_HEIGHT };
  }

  return {
    width: Math.max(
      NODE_MIN_WIDTH,
      ...childNodes.map((node) => node.position.x + getNodeSize(node).width + GRID_SIZE),
    ),
    height: Math.max(
      NODE_MIN_HEIGHT,
      ...childNodes.map((node) => node.position.y + getNodeSize(node).height + GRID_SIZE),
    ),
  };
}

function getResizedNodeDimensions(node: TimelineFlowNode, width: number, height: number, allNodes: TimelineFlowNode[]): { width: number; height: number } {
  if (node.type !== 'timelineGroup') {
    return {
      width: getNodeDimension(width, NODE_WIDTH, NODE_MIN_WIDTH, NODE_MAX_WIDTH),
      height: getNodeDimension(height, NODE_HEIGHT, NODE_MIN_HEIGHT, NODE_MAX_HEIGHT),
    };
  }

  const minimumGroupSize = getMinimumGroupSize(node.id, allNodes);
  return {
    width: getNodeDimension(width, NODE_WIDTH * 1.4, minimumGroupSize.width, NODE_MAX_WIDTH * 2),
    height: getNodeDimension(height, NODE_HEIGHT * 1.2, minimumGroupSize.height, NODE_MAX_HEIGHT * 2),
  };
}

function hasEdgeBetween(edges: TimelineGraphEdge[], firstNodeId: string, secondNodeId: string): boolean {
  return edges.some((edge) => (
    (edge.source === firstNodeId && edge.target === secondNodeId) ||
    (edge.source === secondNodeId && edge.target === firstNodeId)
  ));
}

type ProximityRect = {
  left: number;
  right: number;
  top: number;
  bottom: number;
  centerX: number;
  centerY: number;
};

type ProximityEdgeDefinition = Pick<TimelineGraphEdge, 'source' | 'target' | 'sourceHandle' | 'targetHandle'>;

function getRectDistance(first: ProximityRect, second: ProximityRect): number {
  const gapX = Math.max(0, Math.max(first.left, second.left) - Math.min(first.right, second.right));
  const gapY = Math.max(0, Math.max(first.top, second.top) - Math.min(first.bottom, second.bottom));
  return Math.hypot(gapX, gapY);
}

function getGraphNodeProximityRect(node: TimelineFlowNode, nodeById: Map<string, TimelineFlowNode>): ProximityRect {
  const position = getNodeAbsolutePosition(node, nodeById);
  const size = getNodeSize(node);

  return {
    left: position.x,
    right: position.x + size.width,
    top: position.y,
    bottom: position.y + size.height,
    centerX: position.x + size.width / 2,
    centerY: position.y + size.height / 2,
  };
}

function getProximityEdgeHandles(sourceRect: ProximityRect, targetRect: ProximityRect): Pick<TimelineGraphEdge, 'sourceHandle' | 'targetHandle'> {
  const deltaX = targetRect.centerX - sourceRect.centerX;
  const deltaY = targetRect.centerY - sourceRect.centerY;

  if (Math.abs(deltaX) >= Math.abs(deltaY)) {
    return deltaX >= 0
      ? { sourceHandle: 'east-source', targetHandle: 'west-target' }
      : { sourceHandle: 'west-source', targetHandle: 'east-target' };
  }

  return deltaY >= 0
    ? { sourceHandle: 'south-source', targetHandle: 'north-target' }
    : { sourceHandle: 'north-source', targetHandle: 'south-target' };
}

function getClosestGraphProximityEdge(
  node: TimelineFlowNode,
  allNodes: TimelineFlowNode[],
): ProximityEdgeDefinition | null {
  if (node.type !== 'timelineItem') {
    return null;
  }

  const nodeById = new Map(allNodes.map((candidate) => [candidate.id, candidate]));
  const nodeRect = getGraphNodeProximityRect(node, nodeById);
  const closestNode = allNodes.reduce<{
    distance: number;
    node: TimelineGraphNode | null;
    rect: ProximityRect | null;
    centerX: number;
  }>((closest, candidate) => {
    if (candidate.id === node.id || candidate.type !== 'timelineItem') {
      return closest;
    }

    const candidateRect = getGraphNodeProximityRect(candidate, nodeById);
    const distance = getRectDistance(candidateRect, nodeRect);

    if (distance < closest.distance && distance < PROXIMITY_CONNECT_DISTANCE) {
      return { distance, node: candidate, rect: candidateRect, centerX: candidateRect.centerX };
    }

    return closest;
  }, { distance: Number.MAX_VALUE, node: null, rect: null, centerX: 0 });

  if (!closestNode.node || !closestNode.rect) {
    return null;
  }

  const closestNodeIsSource = closestNode.centerX < nodeRect.centerX;
  const sourceRect = closestNodeIsSource ? closestNode.rect : nodeRect;
  const targetRect = closestNodeIsSource ? nodeRect : closestNode.rect;

  return {
    source: closestNodeIsSource ? closestNode.node.id : node.id,
    target: closestNodeIsSource ? node.id : closestNode.node.id,
    ...getProximityEdgeHandles(sourceRect, targetRect),
  };
}

type InternalTimelineGraphNode = ReturnType<typeof useInternalNode<TimelineFlowNode>>;

function getInternalNodeSize(node: NonNullable<InternalTimelineGraphNode>): { width: number; height: number } {
  return {
    width: node.measured.width ?? node.width ?? NODE_WIDTH,
    height: node.measured.height ?? node.height ?? NODE_HEIGHT,
  };
}

function getSimpleFloatingEdgePoint(
  sourceNode: NonNullable<InternalTimelineGraphNode>,
  targetNode: NonNullable<InternalTimelineGraphNode>,
): { x: number; y: number; position: Position } {
  const sourceSize = getInternalNodeSize(sourceNode);
  const targetSize = getInternalNodeSize(targetNode);
  const sourcePosition = sourceNode.internals.positionAbsolute;
  const targetPosition = targetNode.internals.positionAbsolute;
  const sourceCenterX = sourcePosition.x + sourceSize.width / 2;
  const sourceCenterY = sourcePosition.y + sourceSize.height / 2;
  const targetCenterX = targetPosition.x + targetSize.width / 2;
  const targetCenterY = targetPosition.y + targetSize.height / 2;
  const deltaX = targetCenterX - sourceCenterX;
  const deltaY = targetCenterY - sourceCenterY;

  if (Math.abs(deltaX) > Math.abs(deltaY)) {
    return deltaX > 0
      ? { x: sourcePosition.x + sourceSize.width, y: sourceCenterY, position: Position.Right }
      : { x: sourcePosition.x, y: sourceCenterY, position: Position.Left };
  }

  return deltaY > 0
    ? { x: sourceCenterX, y: sourcePosition.y + sourceSize.height, position: Position.Bottom }
    : { x: sourceCenterX, y: sourcePosition.y, position: Position.Top };
}

const neutralNodeClasses = 'border-neutral-border text-default-font shadow-none';
const highlightedNodeClasses = 'border-accent-1-primary text-accent-1-primary shadow-[0_0_34px_rgba(0,255,217,0.28)] ring-2 ring-accent-1-primary/50';
const flaggedNodeClasses = 'border-error-600 text-error-600 shadow-[0_0_34px_rgba(220,38,38,0.32)] ring-2 ring-error-600/50';
const graphPanelChromeClasses = 'rounded-md border border-solid border-neutral-border bg-default-background/95 p-1 shadow-sm shadow-neutral-200';
const graphThemeStyle = {
  '--xy-controls-box-shadow': '2px 2px 0px 0px rgb(var(--color-neutral-200))',
  '--xy-controls-button-background-color': 'rgb(var(--color-neutral-50))',
  '--xy-controls-button-background-color-hover': 'rgb(var(--color-neutral-100))',
  '--xy-controls-button-border-color': 'rgb(var(--color-neutral-border))',
  '--xy-controls-button-color': 'rgb(var(--color-default-font))',
  '--xy-controls-button-color-hover': 'rgb(var(--color-focus-border))',
  '--xy-minimap-background-color': 'rgb(var(--color-neutral-50))',
  '--xy-minimap-mask-background-color': 'rgb(var(--color-default-background) / 0.66)',
  '--xy-minimap-mask-stroke-color': 'rgb(var(--color-focus-border))',
  '--xy-minimap-node-stroke-color': 'rgb(var(--color-default-background))',
} as React.CSSProperties;

type TimelineGraphActions = {
  connectorsVisible: boolean;
  onRemoveNode: (nodeId: string) => void;
  onResizeNode: (nodeId: string, width: number, height: number) => void;
  onGroupLabelCommit: (nodeId: string, label: string) => void;
  onRemoveEdge: (edgeId: string) => void;
  onEdgeLabelCommit: (edgeId: string, label: string) => void;
  onEdgeMarkerChange: (edgeId: string, marker: EdgeMarkerMode) => void;
  onFlagItem?: (itemId: string) => void;
  onHighlightItem?: (itemId: string) => void;
  onDeleteItem?: (itemId: string) => void;
  onEditItem?: (itemId: string) => void;
};

const TimelineGraphActionsContext = React.createContext<TimelineGraphActions | null>(null);

function getTimestamp(item: TimelineItem, sortBy: 'created_at' | 'timestamp'): string | null {
  return sortBy === 'timestamp'
    ? ((item as any).timestamp || item.created_at || null)
    : (item.created_at || (item as any).timestamp || null);
}

function formatTimestamp(item: TimelineItem, sortBy: 'created_at' | 'timestamp'): string {
  const value = getTimestamp(item, sortBy);
  if (!value) return 'No timestamp';

  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getNodeTitle(item: TimelineItem): string {
  const itemAny = item as any;
  return itemAny.title || itemAny.name || itemAny.value || item.description || getTimelineItemLabel(item.type || 'note');
}

function getNodeSubtitle(item: TimelineItem): string {
  const itemAny = item as any;
  const candidates = [
    itemAny.email_subject,
    itemAny.file_name,
    itemAny.filename,
    itemAny.command_line,
    itemAny.process_name,
    itemAny.hostname,
    itemAny.ip_address,
    itemAny.domain,
    itemAny.url,
    item.description,
  ];

  return candidates.find((value) => typeof value === 'string' && value.trim().length > 0) || 'Timeline item';
}

function snapToGridSize(value: number): number {
  return Math.ceil(value / GRID_SIZE) * GRID_SIZE;
}

function getAutoNodeFallbackSize(item: TimelineItem): { width: number; height: number } {
  const itemAny = item as Record<string, unknown>;
  const titleLength = getNodeTitle(item).length;
  const subtitleLength = getNodeSubtitle(item).length;
  const descriptionLength = (item.description || '').length;
  const textFieldLengths = Object.entries(itemAny)
    .filter(([key, value]) => (
      typeof value === 'string' &&
      value.trim().length > 0 &&
      !['id', 'type', 'created_by', 'created_at', 'updated_at', 'modified_at'].includes(key)
    ))
    .map(([, value]) => (value as string).trim().length);
  const replyCount = getTimelineItems({ timeline_items: item.replies ?? null }).length;
  const longestPreviewLine = Math.max(titleLength, subtitleLength, ...textFieldLengths.map((length) => Math.min(length, 120)));
  const previewTextWeight = Math.min(
    textFieldLengths.reduce((total, length) => total + Math.min(length, 420), 0),
    1200,
  );
  const structuredPreviewOffset = item.type && item.type !== 'note' ? GRID_SIZE * 3 : 0;

  return {
    width: snapToGridSize(clampSize(286 + longestPreviewLine * 2.4, NODE_MIN_WIDTH, NODE_MAX_WIDTH)),
    height: snapToGridSize(clampSize(210 + previewTextWeight * 0.08 + replyCount * 36 + structuredPreviewOffset, NODE_MIN_HEIGHT, NODE_MAX_HEIGHT)),
  };
}

function flattenTimelineItems(items: TimelineItem[]): TimelineItem[] {
  const flattened: TimelineItem[] = [];

  const visit = (currentItems: TimelineItem[]) => {
    currentItems.forEach((item) => {
      flattened.push(item);
      const replies = getTimelineItems({ timeline_items: item.replies ?? null });
      if (replies.length > 0) {
        visit(replies);
      }
    });
  };

  visit(items);
  return flattened;
}

function normalizeHandleId(handle: string | null | undefined, handleType: 'source' | 'target'): string | null {
  if (!handle) return null;
  if (handle.endsWith(`-${handleType}`)) return handle;
  if (NODE_HANDLES.includes(handle as NodeHandle)) return `${handle}-${handleType}`;
  return handle;
}

function buildNodeData(
  item: TimelineItem,
  sortBy: 'created_at' | 'timestamp',
  entityId: number | null,
  entityType: 'case' | 'task',
  linkTemplates?: LinkTemplate[],
  width?: number,
  height?: number,
  autoSize = false,
): TimelineGraphNodeData {
  const modifiedAt = (item as any).updated_at || (item as any).modified_at || (item as any).audit?.updated_at || null;
  const timestampValue = (item as any).timestamp || null;
  const fallbackSize = getAutoNodeFallbackSize(item);

  return {
    itemId: item.id || '',
    itemType: item.type || 'note',
    title: getNodeTitle(item),
    subtitle: getNodeSubtitle(item),
    label: getTimelineItemLabel(item.type || 'note'),
    timestamp: formatTimestamp(item, sortBy),
    timestampValue,
    createdBy: item.created_by || 'System',
    createdAtValue: item.created_at || null,
    width: width ?? fallbackSize.width,
    height: height ?? fallbackSize.height,
    autoSize,
    flagged: item.flagged === true,
    highlighted: item.highlighted === true,
    item,
    entityId,
    entityType,
    sortBy,
    linkTemplates,
  };
}

function buildNode(
  item: TimelineItem,
  position: { x: number; y: number },
  sortBy: 'created_at' | 'timestamp',
  entityId: number | null,
  entityType: 'case' | 'task',
  linkTemplates?: LinkTemplate[],
  width?: number,
  height?: number,
): TimelineGraphNode {
  const hasExplicitSize = typeof width === 'number' && typeof height === 'number';
  const nodeData = buildNodeData(item, sortBy, entityId, entityType, linkTemplates, width, height, !hasExplicitSize);
  const node: TimelineGraphNode = {
    id: `node-${item.id}`,
    type: 'timelineItem',
    position,
    data: nodeData,
  };

  if (hasExplicitSize) {
    node.width = width;
    node.height = height;
  }

  return {
    ...node,
  };
}

function buildFlowGraphState(
  graph: { nodes?: Record<string, ServerGraphNode>; edges?: Record<string, ServerGraphEdge> } | null | undefined,
  itemById: Map<string, TimelineItem>,
  sortBy: 'created_at' | 'timestamp',
  entityId: number | null,
  entityType: 'case' | 'task',
  linkTemplates?: LinkTemplate[],
): { nodes: TimelineFlowNode[]; edges: TimelineGraphEdge[] } {
  try {
    if (!graph) {
      return { nodes: [], edges: [] };
    }

    const nodes: TimelineFlowNode[] = Object.entries(graph.nodes || {}).flatMap<TimelineFlowNode>(([nodeId, node]) => {
      if (node.kind === 'group') {
        const width = getNodeDimension(node.width, NODE_WIDTH * 1.4, NODE_MIN_WIDTH, NODE_MAX_WIDTH * 2);
        const height = getNodeDimension(node.height, NODE_HEIGHT * 1.2, NODE_MIN_HEIGHT, NODE_MAX_HEIGHT * 2);

        return [{
          id: node.id || nodeId,
          type: 'timelineGroup',
          position: node.position || { x: node.x ?? DEFAULT_NODE_POSITION.x, y: node.y ?? DEFAULT_NODE_POSITION.y },
          data: {
            label: node.label || 'Group',
            width,
            height,
          },
          width,
          height,
          zIndex: -1,
        } satisfies TimelineGraphGroupNode];
      }

      const itemId = node.item_id || node.itemId;
      if (!itemId) return [];
      const item = itemById.get(itemId);
      if (!item) return [];
      const hasExplicitSize = typeof node.width === 'number' && typeof node.height === 'number';
      const width = hasExplicitSize ? getNodeDimension(node.width, NODE_WIDTH, NODE_MIN_WIDTH, NODE_MAX_WIDTH) : undefined;
      const height = hasExplicitSize ? getNodeDimension(node.height, NODE_HEIGHT, NODE_MIN_HEIGHT, NODE_MAX_HEIGHT) : undefined;

      return [{
        ...buildNode(
          item,
          node.position || { x: node.x ?? DEFAULT_NODE_POSITION.x, y: node.y ?? DEFAULT_NODE_POSITION.y },
          sortBy,
          entityId,
          entityType,
          linkTemplates,
          width,
          height,
        ),
        id: node.id || nodeId || `node-${itemId}`,
        parentId: node.parent_node_id || node.parentNodeId || undefined,
        extent: undefined,
      }];
    });
    const orderedNodes = [
      ...nodes.filter((node) => node.type === 'timelineGroup'),
      ...nodes.filter((node) => node.type !== 'timelineGroup'),
    ];
    const nodeIds = new Set(orderedNodes.map((node) => node.id));
    const edges = Object.entries(graph.edges || {}).flatMap(([edgeId, edge]) => {
      const source = edge.source;
      const target = edge.target;
      if (!source || !target || !nodeIds.has(source) || !nodeIds.has(target)) {
        return [];
      }

      return [{
        ...defaultEdgeOptions,
        id: edge.id || edgeId,
        type: 'timelineGraph',
        source,
        target,
        sourceHandle: normalizeHandleId(edge.source_handle || edge.sourceHandle, 'source'),
        targetHandle: normalizeHandleId(edge.target_handle || edge.targetHandle, 'target'),
        label: edge.label || undefined,
        data: { marker: edge.marker || 'forward' },
        ...getEdgeMarkerProps(edge.marker || 'forward'),
      } satisfies TimelineGraphEdge];
    });

    return { nodes: orderedNodes, edges };
  } catch (error) {
    console.error('Failed to build timeline graph state:', error);
    return { nodes: [], edges: [] };
  }
}

function createEdgeId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `edge-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function createGroupId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `group-${crypto.randomUUID()}`;
  }
  return `group-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function clampSize(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function getGraphLayoutStorageKey(entityType: 'case' | 'task', entityId: number): string {
  return `${GRAPH_LAYOUT_STORAGE_KEY}.${entityType}.${entityId}`;
}

function getGraphSettingsStorageKey(entityType: 'case' | 'task', entityId: number): string {
  return `${GRAPH_SETTINGS_STORAGE_KEY}.${entityType}.${entityId}`;
}

type TimelineGraphSettings = {
  floatingEdges: boolean;
  proximityConnectEnabled: boolean;
};

const DEFAULT_GRAPH_SETTINGS: TimelineGraphSettings = {
  floatingEdges: true,
  proximityConnectEnabled: true,
};

function loadGraphSettings(entityType: 'case' | 'task', entityId: number | null): TimelineGraphSettings {
  if (entityId === null || typeof window === 'undefined') {
    return DEFAULT_GRAPH_SETTINGS;
  }

  try {
    const serialized = window.localStorage.getItem(getGraphSettingsStorageKey(entityType, entityId));
    if (!serialized) {
      return DEFAULT_GRAPH_SETTINGS;
    }
    const parsed = JSON.parse(serialized) as Partial<TimelineGraphSettings>;
    return {
      floatingEdges: parsed.floatingEdges !== false,
      proximityConnectEnabled: parsed.proximityConnectEnabled !== false,
    };
  } catch (error) {
    console.error('Failed to load timeline graph settings:', error);
    return DEFAULT_GRAPH_SETTINGS;
  }
}

function saveGraphSettings(
  entityType: 'case' | 'task',
  entityId: number | null,
  settings: TimelineGraphSettings,
): void {
  if (entityId === null || typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(
      getGraphSettingsStorageKey(entityType, entityId),
      JSON.stringify(settings),
    );
  } catch (error) {
    console.error('Failed to save timeline graph settings:', error);
  }
}

function loadGraphLayout(entityType: 'case' | 'task', entityId: number | null): {
  itemsPaneWidth: number;
  detailPaneHeight: number;
} {
  if (entityId === null || typeof window === 'undefined') {
    return {
      itemsPaneWidth: DEFAULT_ITEMS_PANE_WIDTH,
      detailPaneHeight: DEFAULT_DETAIL_PANE_HEIGHT,
    };
  }

  try {
    const serialized = window.localStorage.getItem(getGraphLayoutStorageKey(entityType, entityId));
    if (!serialized) {
      return {
        itemsPaneWidth: DEFAULT_ITEMS_PANE_WIDTH,
        detailPaneHeight: DEFAULT_DETAIL_PANE_HEIGHT,
      };
    }

    const parsed = JSON.parse(serialized) as Partial<{ itemsPaneWidth: number; detailPaneHeight: number }>;
    return {
      itemsPaneWidth: clampSize(
        typeof parsed.itemsPaneWidth === 'number' ? parsed.itemsPaneWidth : DEFAULT_ITEMS_PANE_WIDTH,
        MIN_ITEMS_PANE_WIDTH,
        MAX_ITEMS_PANE_WIDTH,
      ),
      detailPaneHeight: clampSize(
        typeof parsed.detailPaneHeight === 'number' ? parsed.detailPaneHeight : DEFAULT_DETAIL_PANE_HEIGHT,
        MIN_DETAIL_PANE_HEIGHT,
        MAX_DETAIL_PANE_HEIGHT,
      ),
    };
  } catch (error) {
    console.error('Failed to load timeline graph layout:', error);
    return {
      itemsPaneWidth: DEFAULT_ITEMS_PANE_WIDTH,
      detailPaneHeight: DEFAULT_DETAIL_PANE_HEIGHT,
    };
  }
}

function saveGraphLayout(
  entityType: 'case' | 'task',
  entityId: number | null,
  layout: { itemsPaneWidth: number; detailPaneHeight: number },
): void {
  if (entityId === null || typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(
      getGraphLayoutStorageKey(entityType, entityId),
      JSON.stringify(layout),
    );
  } catch (error) {
    console.error('Failed to save timeline graph layout:', error);
  }
}

function isConflictError(error: unknown): boolean {
  return (error as any)?.status === 409 || (error as any)?.response?.status === 409;
}

function getMiniMapColor(node: TimelineGraphNode): string {
  if (node.data.flagged) return '#dc2626';
  if (node.data.highlighted) return '#00ffd9';
  return '#94a3b8';
}

function TimelineGraphNodeCard({ id, data, selected, isConnectable, width, height }: NodeProps<TimelineGraphNode>) {
  const { resolvedTheme } = useTheme();
  const Icon = getTimelineItemIcon(data.itemType || 'note');
  const graphActions = React.useContext(TimelineGraphActionsContext);
  const isAutoSize = data.autoSize === true;
  const isCompactCardPreview = data.itemType !== 'note';
  const connectorsVisible = graphActions?.connectorsVisible === true;
  const connectorClassName = resolvedTheme === 'light'
    ? cn('!h-3.5 !w-3.5 !border !border-solid !border-neutral-1000 !bg-default-background transition-opacity group-hover/graph-node:opacity-100', connectorsVisible ? 'opacity-100' : 'opacity-0')
    : cn('!h-3.5 !w-3.5 !border !border-solid !border-brand-primary !bg-default-background transition-opacity group-hover/graph-node:opacity-100', connectorsVisible ? 'opacity-100' : 'opacity-0');
  const nodeWidth = getNodeDimension(width, data.width ?? NODE_WIDTH, NODE_MIN_WIDTH, NODE_MAX_WIDTH);
  const nodeHeight = getNodeDimension(height, data.height ?? NODE_HEIGHT, NODE_MIN_HEIGHT, NODE_MAX_HEIGHT);
  const nodeStyle = isAutoSize
    ? {
        minWidth: NODE_MIN_WIDTH,
        maxWidth: NODE_MAX_WIDTH,
        minHeight: NODE_MIN_HEIGHT,
        maxHeight: NODE_MAX_HEIGHT,
        width: data.width ?? NODE_WIDTH,
        height: data.height ?? NODE_HEIGHT,
      } satisfies React.CSSProperties
    : { width: nodeWidth, height: nodeHeight } satisfies React.CSSProperties;

  return (
    <div
      className={cn(
        'group/graph-node relative flex flex-col items-start gap-3 overflow-visible rounded-md border border-solid bg-neutral-0 px-4 py-3 text-left transition-shadow',
        neutralNodeClasses,
        selected && 'border-brand-primary ring-2 ring-brand-primary/40',
        data.highlighted && highlightedNodeClasses,
        data.flagged && flaggedNodeClasses,
      )}
      style={nodeStyle}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={NODE_MIN_WIDTH}
        minHeight={NODE_MIN_HEIGHT}
        maxWidth={NODE_MAX_WIDTH}
        maxHeight={NODE_MAX_HEIGHT}
        autoScale={false}
        handleStyle={resizeHandleStyle}
        lineStyle={resizeLineStyle}
        onResizeEnd={(_, params) => {
          graphActions?.onResizeNode(id, params.width, params.height);
        }}
      />
      {NODE_HANDLES.map((handle) => (
        <React.Fragment key={handle}>
          <Handle
            type="target"
            id={`${handle}-target`}
            position={handlePositions[handle]}
            isConnectable={isConnectable}
            className="!h-6 !w-6 !border-0 !bg-transparent"
          />
          <Handle
            type="source"
            id={`${handle}-source`}
            position={handlePositions[handle]}
            isConnectable={isConnectable}
            className={connectorClassName}
          />
        </React.Fragment>
      ))}
      <div className="flex w-full items-start gap-2">
        <Icon className="h-4 w-4 flex-none text-subtext-color" />
        <span className="min-w-0 grow truncate text-caption-bold font-caption-bold uppercase">
          {data.label}
        </span>
        {data.timestampValue || data.createdAtValue ? (
          <CopyableTimestamp
            value={data.timestampValue || data.createdAtValue}
            showFull
            relativePlacement="below"
            variant="default-left"
            className="min-w-0 max-w-[260px] flex-none justify-end"
          />
        ) : (
          <span className="flex-none text-right text-caption font-caption text-subtext-color">
            {data.timestamp}
          </span>
        )}
      </div>
      <div className="flex min-h-0 w-full grow flex-col overflow-hidden rounded-md border border-solid border-neutral-border bg-default-background/70">
        <div className={cn(
          "nodrag nowheel flex min-h-0 grow flex-col overflow-auto",
          isCompactCardPreview ? "p-0" : "p-2",
        )}>
          <div className="flex min-h-full w-full origin-top-left flex-col" style={{ zoom: 0.78 }}>
            <TimelineItemRenderer
              item={data.item}
              index={0}
              total={1}
              entityId={data.entityId}
              entityType={data.entityType}
              sortBy={data.sortBy}
              linkTemplates={data.linkTemplates}
              compactPreview
            />
          </div>
        </div>
      </div>
      <div className="mt-auto flex w-full items-end justify-between gap-3 text-caption font-caption text-subtext-color">
        <span className="min-w-0 truncate">{data.createdBy}</span>
        <Tooltip.Provider>
          <div className="nodrag nopan flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover/graph-node:opacity-100 group-focus-within/graph-node:opacity-100">
            {graphActions?.onFlagItem ? (
              <GraphNodeActionButton
                label={data.flagged ? 'Unflag' : 'Flag'}
                icon={<Flag />}
                onClick={(event) => {
                  event.stopPropagation();
                  graphActions.onFlagItem?.(data.itemId);
                }}
              />
            ) : null}
            {graphActions?.onHighlightItem ? (
              <GraphNodeActionButton
                label={data.highlighted ? 'Remove Highlight' : 'Highlight'}
                icon={<Highlighter />}
                onClick={(event) => {
                  event.stopPropagation();
                  graphActions.onHighlightItem?.(data.itemId);
                }}
              />
            ) : null}
            {graphActions?.onDeleteItem ? (
              <GraphNodeActionButton
                label="Delete"
                icon={<Trash />}
                onClick={(event) => {
                  event.stopPropagation();
                  graphActions.onDeleteItem?.(data.itemId);
                }}
              />
            ) : null}
            {graphActions?.onEditItem ? (
              <GraphNodeActionButton
                label="Edit"
                icon={<Pencil />}
                onClick={(event) => {
                  event.stopPropagation();
                  graphActions.onEditItem?.(data.itemId);
                }}
              />
            ) : null}
            <div className="mx-1 h-4 w-px bg-neutral-border" />
            <GraphNodeActionButton
              label="Remove from Graph"
              icon={<X />}
              onClick={(event) => {
                event.stopPropagation();
                graphActions?.onRemoveNode(id);
              }}
            />
          </div>
        </Tooltip.Provider>
      </div>
    </div>
  );
}

function TimelineGraphGroupCard({ id, data, selected, width, height }: NodeProps<TimelineGraphGroupNode>) {
  const { resolvedTheme } = useTheme();
  const graphActions = React.useContext(TimelineGraphActionsContext);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const skipNextBlurCommitRef = useRef(false);
  const [isEditingLabel, setIsEditingLabel] = useState(false);
  const [labelDraft, setLabelDraft] = useState(data.label);
  const groupWidth = getNodeDimension(width, data.width, NODE_MIN_WIDTH, NODE_MAX_WIDTH * 2);
  const groupHeight = getNodeDimension(height, data.height, NODE_MIN_HEIGHT, NODE_MAX_HEIGHT * 2);
  const isLightTheme = resolvedTheme === 'light';

  useEffect(() => {
    if (!isEditingLabel) {
      setLabelDraft(data.label);
    }
  }, [data.label, isEditingLabel]);

  useEffect(() => {
    if (isEditingLabel) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [isEditingLabel]);

  const commitLabel = useCallback(() => {
    if (skipNextBlurCommitRef.current) {
      skipNextBlurCommitRef.current = false;
      return;
    }

    const nextLabel = labelDraft.trim() || 'Group';
    setIsEditingLabel(false);
    setLabelDraft(nextLabel);

    if (nextLabel !== data.label) {
      graphActions?.onGroupLabelCommit(id, nextLabel);
    }
  }, [data.label, graphActions, id, labelDraft]);

  const cancelLabelEdit = useCallback(() => {
    skipNextBlurCommitRef.current = true;
    setIsEditingLabel(false);
    setLabelDraft(data.label);
  }, [data.label]);

  return (
    <div
      className={cn(
        'group/graph-group relative h-full w-full rounded-md border border-dashed bg-default-background/35 p-3 text-left',
        isLightTheme ? 'border-neutral-500' : 'border-brand-primary/70',
        selected && 'ring-2 ring-brand-primary/40',
      )}
      style={{ width: groupWidth, height: groupHeight }}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={NODE_MIN_WIDTH}
        minHeight={NODE_MIN_HEIGHT}
        maxWidth={NODE_MAX_WIDTH * 2}
        maxHeight={NODE_MAX_HEIGHT * 2}
        autoScale={false}
        handleStyle={resizeHandleStyle}
        lineStyle={resizeLineStyle}
        onResizeEnd={(_, params) => {
          graphActions?.onResizeNode(id, params.width, params.height);
        }}
      />
      <div className="nodrag nopan relative inline-flex max-w-[calc(100%-2rem)] items-center">
        {isEditingLabel ? (
          <input
            ref={inputRef}
            aria-label="Group label"
            value={labelDraft}
            className={cn(
              'nowheel h-7 min-w-28 max-w-full rounded border border-solid bg-default-background px-2 text-caption-bold font-caption-bold uppercase text-default-font outline-none focus:border-focus-border focus:ring-2 focus:ring-focus-border/30',
              isLightTheme ? 'border-neutral-500' : 'border-brand-primary/70',
            )}
            onChange={(event) => setLabelDraft(event.target.value)}
            onBlur={commitLabel}
            onClick={(event) => event.stopPropagation()}
            onPointerDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                event.currentTarget.blur();
              }

              if (event.key === 'Escape') {
                event.preventDefault();
                cancelLabelEdit();
              }
            }}
          />
        ) : (
          <button
            type="button"
            className={cn(
              'group/group-label relative max-w-full cursor-text truncate rounded-sm pr-6 text-left text-caption-bold font-caption-bold uppercase outline-none transition-colors focus-visible:ring-2 focus-visible:ring-focus-border/50',
              isLightTheme ? 'text-neutral-500 hover:text-neutral-700' : 'text-brand-primary hover:text-brand-primary/80',
            )}
            onClick={(event) => {
              event.stopPropagation();
              setIsEditingLabel(true);
            }}
            onPointerDown={(event) => event.stopPropagation()}
          >
            <span className="block truncate">{data.label}</span>
            <Pencil className="pointer-events-none absolute right-0 top-1/2 h-3.5 w-3.5 -translate-y-1/2 opacity-0 transition-opacity group-hover/group-label:opacity-100 group-focus-visible/group-label:opacity-100" />
          </button>
        )}
      </div>
      <Tooltip.Provider>
        <div className="nodrag nopan absolute bottom-3 right-3 flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover/graph-group:opacity-100 group-focus-within/graph-group:opacity-100">
          <GraphNodeActionButton
            label="Remove from Graph"
            icon={<X />}
            onClick={(event) => {
              event.stopPropagation();
              graphActions?.onRemoveNode(id);
            }}
          />
        </div>
      </Tooltip.Provider>
    </div>
  );
}

const nodeTypes: NodeTypes = {
  timelineItem: TimelineGraphNodeCard,
  timelineGroup: TimelineGraphGroupCard,
};

function TimelineGraphEdgeView(props: EdgeProps<TimelineGraphEdge>) {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    markerStart,
    markerEnd,
    style,
    label,
    selected,
    data,
    source,
    target,
  } = props;
  const graphActions = React.useContext(TimelineGraphActionsContext);
  const sourceNode = useInternalNode<TimelineGraphNode>(source);
  const targetNode = useInternalNode<TimelineGraphNode>(target);
  const labelInputRef = useRef<HTMLInputElement | null>(null);
  const [labelDraft, setLabelDraft] = useState(typeof label === 'string' ? label : '');
  const marker = data?.marker || 'forward';
  const floatingPoints = data?.floating && sourceNode && targetNode
    ? {
        source: getSimpleFloatingEdgePoint(sourceNode, targetNode),
        target: getSimpleFloatingEdgePoint(targetNode, sourceNode),
      }
    : null;
  const [edgePath, labelX, labelY] = floatingPoints
    ? getSmoothStepPath({
        sourceX: floatingPoints.source.x,
        sourceY: floatingPoints.source.y,
        sourcePosition: floatingPoints.source.position,
        targetX: floatingPoints.target.x,
        targetY: floatingPoints.target.y,
        targetPosition: floatingPoints.target.position,
      })
    : getSmoothStepPath({
        sourceX,
        sourceY,
        targetX,
        targetY,
        sourcePosition,
        targetPosition,
      });

  useEffect(() => {
    setLabelDraft(typeof label === 'string' ? label : '');
  }, [label]);

  useEffect(() => {
    if (!selected) {
      return;
    }

    const animationFrameId = window.requestAnimationFrame(() => {
      labelInputRef.current?.focus();
      labelInputRef.current?.select();
    });

    return () => window.cancelAnimationFrame(animationFrameId);
  }, [selected]);

  const handleLabelBlur = useCallback(() => {
    const nextLabel = labelDraft.trim();
    const currentLabel = typeof label === 'string' ? label : '';

    if (nextLabel === currentLabel) {
      return;
    }

    graphActions?.onEdgeLabelCommit(id, labelDraft);
  }, [graphActions, id, label, labelDraft]);

  const keepLabelInputFocused = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
  }, []);

  const markerOptions: Array<{ marker: EdgeMarkerMode; label: string; icon: React.ReactNode }> = [
    { marker: 'none', label: 'No marker', icon: <Minus /> },
    { marker: 'forward', label: 'Forward marker', icon: <ArrowRight /> },
    { marker: 'reverse', label: 'Reverse marker', icon: <ArrowLeft /> },
    { marker: 'bidirectional', label: 'Bidirectional markers', icon: <ArrowLeftRight /> },
  ];

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerStart={markerStart}
        markerEnd={markerEnd}
        style={style}
        interactionWidth={24}
        label={label}
        labelX={labelX}
        labelY={labelY}
        labelBgStyle={{ fill: 'rgb(var(--color-default-background))' }}
        labelStyle={{ fill: 'rgb(var(--color-default-font))', fontSize: 12, fontWeight: 500 }}
        labelBgPadding={[8, 4]}
        labelBgBorderRadius={0}
      />
      <EdgeToolbar edgeId={id} x={labelX} y={labelY} isVisible={selected}>
        <Tooltip.Provider>
          <div className="nodrag nopan flex items-center gap-1 rounded-md border border-solid border-neutral-border bg-default-background p-1 shadow-sm shadow-neutral-200">
            <input
              ref={labelInputRef}
              className="h-8 w-40 rounded-md border border-solid border-neutral-border bg-default-background px-2 text-caption font-caption text-default-font outline-none focus:border-brand-primary"
              value={labelDraft}
              placeholder="Label"
              onChange={(event) => setLabelDraft(event.target.value)}
              onBlur={handleLabelBlur}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.currentTarget.blur();
                }
              }}
            />
            {markerOptions.map((option) => (
              <Tooltip.Root key={option.marker}>
                <Tooltip.Trigger asChild>
                  <IconButton
                    aria-label={option.label}
                    size="small"
                    variant={marker === option.marker ? 'brand-tertiary' : 'neutral-tertiary'}
                    icon={option.icon}
                    onMouseDown={keepLabelInputFocused}
                    onClick={(event) => {
                      event.stopPropagation();
                      graphActions?.onEdgeMarkerChange(id, option.marker);
                    }}
                  />
                </Tooltip.Trigger>
                <Tooltip.Content side="top" align="center" sideOffset={4}>
                  {option.label}
                </Tooltip.Content>
              </Tooltip.Root>
            ))}
            <Tooltip.Root>
              <Tooltip.Trigger asChild>
                <IconButton
                  aria-label="Remove link"
                  size="small"
                  variant="destructive-tertiary"
                  icon={<Trash2 />}
                  onMouseDown={keepLabelInputFocused}
                  onClick={(event) => {
                    event.stopPropagation();
                    graphActions?.onRemoveEdge(id);
                  }}
                />
              </Tooltip.Trigger>
              <Tooltip.Content side="top" align="center" sideOffset={4}>
                Remove link
              </Tooltip.Content>
            </Tooltip.Root>
          </div>
        </Tooltip.Provider>
      </EdgeToolbar>
    </>
  );
}

const edgeTypes: EdgeTypes = {
  timelineGraph: TimelineGraphEdgeView,
};

function TimelineGraphViewInner({
  items,
  entityId,
  entityType,
  sortBy = 'timestamp',
  linkTemplates,
  onSelectItem,
  onFlagItem,
  onHighlightItem,
  onDeleteItem,
  onEditItem,
}: TimelineGraphViewProps) {
  const { resolvedTheme } = useTheme();
  const { showToast } = useToast();
  const gridDotColor = resolvedTheme === 'dark'
    ? 'rgba(208,255,0,0.26)'
    : 'rgba(23,23,23,0.22)';
  const graphCanvasColor = resolvedTheme === 'dark'
    ? 'rgb(var(--color-neutral-50))'
    : 'rgb(var(--color-neutral-200))';
  const store = useStoreApi();
  const { screenToFlowPosition, getInternalNode } = useReactFlow<TimelineFlowNode, TimelineGraphEdge>();
  const timelineGraphQuery = useTimelineGraph(entityType, entityId);
  const patchGraphMutation = usePatchTimelineGraph(entityType, entityId);
  const [nodes, setNodes, onNodesChange] = useNodesState<TimelineFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<TimelineGraphEdge>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const selectedEdgeIdRef = useRef<string | null>(null);
  const [isDraggingGraphNode, setIsDraggingGraphNode] = useState(false);
  const [isDraggingTimelineItem, setIsDraggingTimelineItem] = useState(false);
  const [graphLayout, setGraphLayout] = useState(() => loadGraphLayout(entityType, entityId));
  const [graphSettings, setGraphSettings] = useState(() => loadGraphSettings(entityType, entityId));
  const proximityConnectEnabled = graphSettings.proximityConnectEnabled;
  const graphContainerRef = useRef<HTMLDivElement>(null);
  const graphLayoutKey = entityId === null ? null : getGraphLayoutStorageKey(entityType, entityId);
  const graphSettingsKey = entityId === null ? null : getGraphSettingsStorageKey(entityType, entityId);
  const loadedGraphLayoutKeyRef = useRef<string | null>(graphLayoutKey);
  const loadedGraphSettingsKeyRef = useRef<string | null>(graphSettingsKey);
  const skipNextGraphLayoutSaveRef = useRef(false);
  const skipNextGraphSettingsSaveRef = useRef(false);

  const allItems = useMemo(() => flattenTimelineItems(items), [items]);
  const itemById = useMemo(() => new Map(allItems.filter((item) => item.id).map((item) => [item.id!, item])), [allItems]);
  const nodeItemIds = useMemo(() => new Set(nodes.flatMap((node) => (
    node.type === 'timelineItem' ? [node.data.itemId] : []
  ))), [nodes]);
  const timelineNodeIds = useMemo(() => new Set(nodes.flatMap((node) => (
    node.type === 'timelineItem' ? [node.id] : []
  ))), [nodes]);
  const stagedItems = useMemo(() => allItems.filter((item) => item.id && !nodeItemIds.has(item.id)), [allItems, nodeItemIds]);
  const selectedNode = selectedNodeId ? nodes.find((node) => node.id === selectedNodeId) : null;
  const selectedEdge = selectedEdgeId ? edges.find((edge) => edge.id === selectedEdgeId) : null;
  const flowEdges = useMemo(
    () => edges.map((edge) => withFloatingEdgeData(edge, graphSettings.floatingEdges)),
    [edges, graphSettings.floatingEdges],
  );
  const selectedItem = useMemo(() => {
    if (selectedNode?.type === 'timelineItem') {
      return itemById.get(selectedNode.data.itemId) ?? null;
    }

    if (selectedItemId) {
      return itemById.get(selectedItemId) ?? null;
    }

    return null;
  }, [itemById, selectedItemId, selectedNode]);
  const selectedItemModifiedAt = useMemo(() => {
    if (!selectedItem) {
      return null;
    }

    return (selectedItem as any).updated_at ||
      (selectedItem as any).modified_at ||
      (selectedItem as any).audit?.updated_at ||
      null;
  }, [selectedItem]);
  const connectorsVisible = proximityConnectEnabled && (isDraggingGraphNode || isDraggingTimelineItem);

  selectedEdgeIdRef.current = selectedEdgeId;

  useEffect(() => {
    loadedGraphLayoutKeyRef.current = graphLayoutKey;
    skipNextGraphLayoutSaveRef.current = true;
    setGraphLayout(loadGraphLayout(entityType, entityId));
  }, [entityId, entityType, graphLayoutKey]);

  useEffect(() => {
    loadedGraphSettingsKeyRef.current = graphSettingsKey;
    skipNextGraphSettingsSaveRef.current = true;
    setGraphSettings(loadGraphSettings(entityType, entityId));
  }, [entityId, entityType, graphSettingsKey]);

  useEffect(() => {
    if (skipNextGraphLayoutSaveRef.current) {
      skipNextGraphLayoutSaveRef.current = false;
      return;
    }

    if (loadedGraphLayoutKeyRef.current !== graphLayoutKey) {
      return;
    }

    saveGraphLayout(entityType, entityId, graphLayout);
  }, [entityId, entityType, graphLayout, graphLayoutKey]);

  useEffect(() => {
    if (skipNextGraphSettingsSaveRef.current) {
      skipNextGraphSettingsSaveRef.current = false;
      return;
    }

    if (loadedGraphSettingsKeyRef.current !== graphSettingsKey) {
      return;
    }

    saveGraphSettings(entityType, entityId, graphSettings);
  }, [entityId, entityType, graphSettings, graphSettingsKey]);

  const handleItemsPaneResizeStart = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const pointerId = event.pointerId;
    const handle = event.currentTarget;
    const startX = event.clientX;
    const startWidth = graphLayout.itemsPaneWidth;

    handle.setPointerCapture(pointerId);

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const containerWidth = graphContainerRef.current?.clientWidth ?? 0;
      const maxWidth = containerWidth > 0
        ? Math.min(MAX_ITEMS_PANE_WIDTH, Math.max(MIN_ITEMS_PANE_WIDTH, containerWidth - 480))
        : MAX_ITEMS_PANE_WIDTH;

      setGraphLayout((currentLayout) => ({
        ...currentLayout,
        itemsPaneWidth: clampSize(startWidth + moveEvent.clientX - startX, MIN_ITEMS_PANE_WIDTH, maxWidth),
      }));
    };

    const handlePointerUp = () => {
      handle.releasePointerCapture(pointerId);
      handle.removeEventListener('pointermove', handlePointerMove);
      handle.removeEventListener('pointerup', handlePointerUp);
      handle.removeEventListener('pointercancel', handlePointerUp);
    };

    handle.addEventListener('pointermove', handlePointerMove);
    handle.addEventListener('pointerup', handlePointerUp);
    handle.addEventListener('pointercancel', handlePointerUp);
  }, [graphLayout.itemsPaneWidth]);

  const handleDetailPaneResizeStart = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const pointerId = event.pointerId;
    const handle = event.currentTarget;
    const startY = event.clientY;
    const startHeight = graphLayout.detailPaneHeight;

    handle.setPointerCapture(pointerId);

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const containerHeight = graphContainerRef.current?.clientHeight ?? 0;
      const maxHeight = containerHeight > 0
        ? Math.min(MAX_DETAIL_PANE_HEIGHT, Math.max(MIN_DETAIL_PANE_HEIGHT, containerHeight - MIN_GRAPH_CANVAS_HEIGHT))
        : MAX_DETAIL_PANE_HEIGHT;

      setGraphLayout((currentLayout) => ({
        ...currentLayout,
        detailPaneHeight: clampSize(startHeight - (moveEvent.clientY - startY), MIN_DETAIL_PANE_HEIGHT, maxHeight),
      }));
    };

    const handlePointerUp = () => {
      handle.releasePointerCapture(pointerId);
      handle.removeEventListener('pointermove', handlePointerMove);
      handle.removeEventListener('pointerup', handlePointerUp);
      handle.removeEventListener('pointercancel', handlePointerUp);
    };

    handle.addEventListener('pointermove', handlePointerMove);
    handle.addEventListener('pointerup', handlePointerUp);
    handle.addEventListener('pointercancel', handlePointerUp);
  }, [graphLayout.detailPaneHeight]);

  const applyGraphRead = useCallback((graphRead: TimelineGraphRead | null | undefined, keepSelectedEdge = false) => {
    const graphState = buildFlowGraphState(graphRead?.graph as any, itemById, sortBy, entityId, entityType, linkTemplates);
    const edgeIdToKeepSelected = keepSelectedEdge ? selectedEdgeIdRef.current : null;
    const selectedEdgeStillExists = Boolean(
      edgeIdToKeepSelected && graphState.edges.some((edge) => edge.id === edgeIdToKeepSelected),
    );

    setNodes(graphState.nodes);
    setEdges(graphState.edges.map((edge) => ({
      ...edge,
      selected: selectedEdgeStillExists && edge.id === edgeIdToKeepSelected,
    })));
    setSelectedNodeId(null);
    setSelectedNodeIds([]);
    setSelectedEdgeId(selectedEdgeStillExists ? edgeIdToKeepSelected : null);
    setSelectedItemId(null);
  }, [entityId, entityType, itemById, linkTemplates, setEdges, setNodes, sortBy]);

  useEffect(() => {
    if (!timelineGraphQuery.data) return;
    applyGraphRead(timelineGraphQuery.data, true);
  }, [applyGraphRead, timelineGraphQuery.data]);

  useEffect(() => {
    if (proximityConnectEnabled) {
      return;
    }

    setEdges((currentEdges) => withoutProximityPreviewEdges(currentEdges));
  }, [proximityConnectEnabled, setEdges]);

  const sendGraphPatch = useCallback(async (operations: TimelineGraphOperation[]) => {
    if (entityId === null || operations.length === 0) return;

    try {
      const graphRead = await patchGraphMutation.mutateAsync({
        base_revision: timelineGraphQuery.data?.revision ?? 0,
        operations,
      });
      applyGraphRead(graphRead, true);
    } catch (error) {
      if (isConflictError(error)) {
        showToast(
          'Graph changed',
          'Your conflicting graph edit was not applied. The latest shared graph has been loaded.',
          'error',
        );
      } else {
        showToast('Graph save failed', 'The graph could not be saved. The latest shared graph has been loaded.', 'error');
      }
      const refreshed = await timelineGraphQuery.refetch();
      applyGraphRead(refreshed.data);
    }
  }, [applyGraphRead, entityId, patchGraphMutation, showToast, timelineGraphQuery]);

  const handleConnect = useCallback<OnConnect>((connection: Connection) => {
    if (!connection.source || !connection.target) {
      return;
    }

    const edgeId = createEdgeId();
    setEdges((currentEdges) => addEdge({
      ...connection,
      ...defaultEdgeOptions,
      id: edgeId,
      data: { marker: 'forward', floating: graphSettings.floatingEdges },
      ...getEdgeMarkerProps('forward'),
    }, currentEdges));
    void sendGraphPatch([{
      type: 'add_edge',
      edge_id: edgeId,
      source: connection.source,
      target: connection.target,
      source_handle: connection.sourceHandle ?? undefined,
      target_handle: connection.targetHandle ?? undefined,
      marker: 'forward',
    }]);
  }, [graphSettings.floatingEdges, sendGraphPatch, setEdges]);

  const getClosestProximityEdge = useCallback((node: TimelineFlowNode): ProximityEdgeDefinition | null => {
    if (!timelineNodeIds.has(node.id)) {
      return null;
    }

    const internalNode = getInternalNode(node.id);
    if (!internalNode) {
      return null;
    }

    const { nodeLookup } = store.getState();
    const internalSize = getInternalNodeSize(internalNode as NonNullable<InternalTimelineGraphNode>);
    const internalPosition = internalNode.internals.positionAbsolute;
    const internalRect: ProximityRect = {
      left: internalPosition.x,
      right: internalPosition.x + internalSize.width,
      top: internalPosition.y,
      bottom: internalPosition.y + internalSize.height,
      centerX: internalPosition.x + internalSize.width / 2,
      centerY: internalPosition.y + internalSize.height / 2,
    };
    const closestNode = Array.from(nodeLookup.values()).reduce<{
      distance: number;
      id: string | null;
      rect: ProximityRect | null;
      centerX: number;
    }>((closest, candidate) => {
      if (candidate.id === internalNode.id || !timelineNodeIds.has(candidate.id)) {
        return closest;
      }

      const candidateWidth = candidate.measured.width ?? candidate.width ?? NODE_WIDTH;
      const candidateHeight = candidate.measured.height ?? candidate.height ?? NODE_HEIGHT;
      const candidatePosition = candidate.internals.positionAbsolute;
      const candidateRect: ProximityRect = {
        left: candidatePosition.x,
        right: candidatePosition.x + candidateWidth,
        top: candidatePosition.y,
        bottom: candidatePosition.y + candidateHeight,
        centerX: candidatePosition.x + candidateWidth / 2,
        centerY: candidatePosition.y + candidateHeight / 2,
      };
      const distance = getRectDistance(candidateRect, internalRect);

      if (distance < closest.distance && distance < PROXIMITY_CONNECT_DISTANCE) {
        return { distance, id: candidate.id, rect: candidateRect, centerX: candidateRect.centerX };
      }

      return closest;
    }, { distance: Number.MAX_VALUE, id: null, rect: null, centerX: 0 });

    if (!closestNode.id || !closestNode.rect) {
      return null;
    }

    const closestNodeIsSource = closestNode.centerX < internalRect.centerX;
    const sourceRect = closestNodeIsSource ? closestNode.rect : internalRect;
    const targetRect = closestNodeIsSource ? internalRect : closestNode.rect;

    return {
      source: closestNodeIsSource ? closestNode.id : node.id,
      target: closestNodeIsSource ? node.id : closestNode.id,
      ...getProximityEdgeHandles(sourceRect, targetRect),
    };
  }, [getInternalNode, store, timelineNodeIds]);

  const handleNodeDrag = useCallback((_: React.MouseEvent, node: TimelineFlowNode) => {
    if (!proximityConnectEnabled) {
      setEdges((currentEdges) => withoutProximityPreviewEdges(currentEdges));
      return;
    }

    const closestEdge = getClosestProximityEdge(node);

    setEdges((currentEdges) => {
      const nextEdges = withoutProximityPreviewEdges(currentEdges);

      if (!closestEdge || hasEdgeBetween(nextEdges, closestEdge.source, closestEdge.target)) {
        return nextEdges;
      }

      return [...nextEdges, {
        ...defaultEdgeOptions,
        id: `${PROXIMITY_PREVIEW_EDGE_CLASS}-${closestEdge.source}-${closestEdge.target}`,
        type: 'timelineGraph',
        source: closestEdge.source,
        target: closestEdge.target,
        sourceHandle: closestEdge.sourceHandle,
        targetHandle: closestEdge.targetHandle,
        className: PROXIMITY_PREVIEW_EDGE_CLASS,
        selectable: false,
        data: { marker: 'none', floating: true },
          ...getEdgeMarkerProps('none'),
        style: {
          stroke: 'rgb(var(--color-focus-border))',
          strokeDasharray: '6 5',
          strokeWidth: 1.75,
        },
      } satisfies TimelineGraphEdge];
    });
  }, [getClosestProximityEdge, proximityConnectEnabled, setEdges]);

  const handleReconnect = useCallback<OnReconnect<TimelineGraphEdge>>((oldEdge, connection) => {
    if (!connection.source || !connection.target) {
      return;
    }

    setEdges((currentEdges) => reconnectEdge(oldEdge, connection, currentEdges));
    void sendGraphPatch([{
      type: 'reconnect_edge',
      edge_id: oldEdge.id,
      source: connection.source,
      target: connection.target,
      source_handle: connection.sourceHandle ?? undefined,
      target_handle: connection.targetHandle ?? undefined,
    }]);
  }, [sendGraphPatch, setEdges]);

  const handleDrop = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const itemId = event.dataTransfer.getData('application/x-timeline-item-id');
    const item = itemById.get(itemId);
    if (!item || nodeItemIds.has(itemId)) {
      return;
    }

    const fallbackSize = getAutoNodeFallbackSize(item);
    const node = buildNode(
      item,
      screenToFlowPosition({ x: event.clientX - fallbackSize.width / 2, y: event.clientY - fallbackSize.height / 2 }),
      sortBy,
      entityId,
      entityType,
      linkTemplates,
    );
    const containingGroup = findContainingGroup(node, nodes);
    const graphNode = containingGroup ? attachNodeToGroup(node, containingGroup, [...nodes, node]) : node;
    const resolvedGraph = resolveNodeCollisions([...nodes, graphNode], graphNode.id);
    const resolvedNode = resolvedGraph.nodes.find((currentNode) => currentNode.id === graphNode.id) ?? graphNode;
    const closestEdge = proximityConnectEnabled && resolvedNode.type === 'timelineItem'
      ? getClosestGraphProximityEdge(resolvedNode, resolvedGraph.nodes)
      : null;
    const newEdgeId = closestEdge && !hasEdgeBetween(edges, closestEdge.source, closestEdge.target) ? createEdgeId() : null;

    setNodes(resolvedGraph.nodes);
    if (closestEdge && newEdgeId) {
      setEdges((currentEdges) => {
        const nextEdges = withoutProximityPreviewEdges(currentEdges);
        if (hasEdgeBetween(nextEdges, closestEdge.source, closestEdge.target)) {
          return nextEdges;
        }

        return addEdge({
          ...defaultEdgeOptions,
          type: 'timelineGraph',
          id: newEdgeId,
          source: closestEdge.source,
          target: closestEdge.target,
          sourceHandle: closestEdge.sourceHandle,
          targetHandle: closestEdge.targetHandle,
          data: { marker: 'forward', floating: graphSettings.floatingEdges },
          ...getEdgeMarkerProps('forward'),
        } satisfies TimelineGraphEdge, nextEdges);
      });
    }
    setSelectedNodeId(graphNode.id);
    setSelectedEdgeId(null);
    setSelectedItemId(graphNode.data.itemId);
    void sendGraphPatch([
      {
        type: 'add_node',
        node_id: graphNode.id,
        item_id: graphNode.data.itemId,
        position: resolvedNode.position,
        parent_node_id: resolvedNode.parentId,
      },
      ...buildMoveOperations(resolvedGraph.movedNodes),
      ...(closestEdge && newEdgeId ? [{
        type: 'add_edge' as const,
        edge_id: newEdgeId,
        source: closestEdge.source,
        target: closestEdge.target,
        source_handle: closestEdge.sourceHandle ?? undefined,
        target_handle: closestEdge.targetHandle ?? undefined,
        marker: 'forward' as const,
      }] : []),
    ]);
  }, [edges, entityId, entityType, graphSettings.floatingEdges, itemById, linkTemplates, nodeItemIds, nodes, proximityConnectEnabled, screenToFlowPosition, sendGraphPatch, setEdges, setNodes, sortBy]);

  const handleDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  }, []);

  const handleNodeDragStart = useCallback(() => {
    setIsDraggingGraphNode(true);
  }, []);

  const handleRemoveNode = useCallback((nodeId: string) => {
    const removalUpdate = removeNodesFromGraphState(nodes, edges, [nodeId]);

    setNodes(removalUpdate.nodes);
    setEdges(removalUpdate.edges);
    setSelectedNodeId(null);
    setSelectedNodeIds((currentIds) => currentIds.filter((id) => id !== nodeId));
    setSelectedEdgeId(null);
    if (selectedItemId && removalUpdate.removedItemIds.includes(selectedItemId)) {
      setSelectedItemId(null);
    }
    void sendGraphPatch(removalUpdate.operations);
  }, [edges, nodes, selectedItemId, sendGraphPatch, setEdges, setNodes]);

  const handleRemoveSelectedNodes = useCallback(() => {
    if (selectedNodeIds.length === 0) {
      return;
    }

    const removalUpdate = removeNodesFromGraphState(nodes, edges, selectedNodeIds);

    setNodes(removalUpdate.nodes);
    setEdges(removalUpdate.edges);
    setSelectedNodeId(null);
    setSelectedNodeIds([]);
    setSelectedEdgeId(null);
    if (selectedItemId && removalUpdate.removedItemIds.includes(selectedItemId)) {
      setSelectedItemId(null);
    }
    void sendGraphPatch(removalUpdate.operations);
  }, [edges, nodes, selectedItemId, selectedNodeIds, sendGraphPatch, setEdges, setNodes]);

  const handleGroupSelectedNodes = useCallback(() => {
    const selectedTimelineNodes = nodes.filter((node): node is TimelineGraphNode => (
      node.type === 'timelineItem' && selectedNodeIds.includes(node.id) && !node.parentId
    ));

    if (selectedTimelineNodes.length < 2) {
      showToast('Select nodes to group', 'Select at least two ungrouped graph nodes before creating a group.', 'error');
      return;
    }

    const padding = GRID_SIZE * 3;
    const minX = Math.min(...selectedTimelineNodes.map((node) => node.position.x));
    const minY = Math.min(...selectedTimelineNodes.map((node) => node.position.y));
    const maxX = Math.max(...selectedTimelineNodes.map((node) => node.position.x + getNodeSize(node).width));
    const maxY = Math.max(...selectedTimelineNodes.map((node) => node.position.y + getNodeSize(node).height));
    const groupId = createGroupId();
    const groupPosition = { x: minX - padding, y: minY - padding };
    const groupWidth = maxX - minX + padding * 2;
    const groupHeight = maxY - minY + padding * 2;
    const groupNode: TimelineGraphGroupNode = {
      id: groupId,
      type: 'timelineGroup',
      position: groupPosition,
      data: {
        label: 'Group',
        width: groupWidth,
        height: groupHeight,
      },
      width: groupWidth,
      height: groupHeight,
      selected: true,
      zIndex: -1,
    };

    setNodes((currentNodes) => {
      const existingGroups = currentNodes.filter((node) => node.type === 'timelineGroup');
      const otherNodes = currentNodes.filter((node) => node.type !== 'timelineGroup').map((node) => {
        if (!selectedNodeIds.includes(node.id)) {
          return { ...node, selected: false };
        }

        return {
          ...node,
          parentId: groupId,
          extent: undefined,
          position: {
            x: node.position.x - groupPosition.x,
            y: node.position.y - groupPosition.y,
          },
          selected: false,
        };
      });

      return [...existingGroups, groupNode, ...otherNodes];
    });
    setSelectedNodeId(groupId);
    setSelectedNodeIds([groupId]);
    setSelectedEdgeId(null);
    setSelectedItemId(null);

    void sendGraphPatch([
      {
        type: 'add_group',
        node_id: groupId,
        position: groupPosition,
        width: groupWidth,
        height: groupHeight,
        label: 'Group',
      },
      ...selectedTimelineNodes.flatMap((node) => [{
        type: 'move_node' as const,
        node_id: node.id,
        position: {
          x: node.position.x - groupPosition.x,
          y: node.position.y - groupPosition.y,
        },
      }, {
        type: 'update_node_metadata' as const,
        node_id: node.id,
        parent_node_id: groupId,
      }]),
    ]);
  }, [nodes, selectedNodeIds, sendGraphPatch, setNodes, showToast]);

  const handleResizeNode = useCallback((nodeId: string, width: number, height: number) => {
    const nodeToResize = nodes.find((node) => node.id === nodeId);
    if (!nodeToResize) {
      return;
    }

    const { width: nextWidth, height: nextHeight } = getResizedNodeDimensions(nodeToResize, width, height, nodes);
    const resizedNodes = nodes.map((node) => (
      node.id === nodeId
        ? {
            ...node,
            width: nextWidth,
            height: nextHeight,
            data: { ...node.data, width: nextWidth, height: nextHeight, autoSize: false },
          } as TimelineFlowNode
        : node
    ));
    const resolvedGraph = resolveNodeCollisions(resizedNodes, nodeId);

    setNodes(resolvedGraph.nodes);
    void sendGraphPatch([
      { type: 'resize_node', node_id: nodeId, width: nextWidth, height: nextHeight },
      ...buildMoveOperations(resolvedGraph.movedNodes),
    ]);
  }, [nodes, sendGraphPatch, setNodes]);

  const handleGroupLabelCommit = useCallback((nodeId: string, label: string) => {
    const nextLabel = label.trim() || 'Group';

    setNodes((currentNodes) => currentNodes.map((node) => (
      node.id === nodeId && node.type === 'timelineGroup'
        ? { ...node, data: { ...node.data, label: nextLabel } }
        : node
    )));
    void sendGraphPatch([{ type: 'update_node_metadata', node_id: nodeId, label: nextLabel }]);
  }, [sendGraphPatch, setNodes]);

  const handleRemoveEdge = useCallback((edgeId: string) => {
    setEdges((currentEdges) => currentEdges.filter((edge) => edge.id !== edgeId));
    setSelectedEdgeId(null);
    void sendGraphPatch([{ type: 'remove_edge', edge_id: edgeId }]);
  }, [sendGraphPatch, setEdges]);

  const handleEdgeLabelCommit = useCallback((edgeId: string, label: string) => {
    setEdges((currentEdges) => currentEdges.map((edge) => (
      edge.id === edgeId
        ? { ...edge, label: label.trim().length > 0 ? label.trim() : undefined }
        : edge
    )));
    void sendGraphPatch([{ type: 'update_edge_label', edge_id: edgeId, label: label.trim() || undefined }]);
  }, [sendGraphPatch, setEdges]);

  const handleEdgeMarkerChange = useCallback((edgeId: string, marker: EdgeMarkerMode) => {
    setEdges((currentEdges) => currentEdges.map((edge) => (
      edge.id === edgeId
        ? {
            ...edge,
            data: { ...(edge.data || {}), marker },
            markerStart: undefined,
            markerEnd: undefined,
            ...getEdgeMarkerProps(marker),
          }
        : edge
    )));
    void sendGraphPatch([{ type: 'update_edge_metadata', edge_id: edgeId, marker }]);
  }, [sendGraphPatch, setEdges]);

  const handleNodeDragStop = useCallback((_: React.MouseEvent, node: TimelineFlowNode) => {
    setIsDraggingGraphNode(false);
    const nodeById = new Map(nodes.map((currentNode) => [
      currentNode.id,
      currentNode.id === node.id ? node : currentNode,
    ]));
    let graphNode = node;
    let parentNodeId: string | null | undefined;

    if (node.type === 'timelineItem' && node.parentId) {
      const parentNode = nodeById.get(node.parentId);
      if (parentNode?.type === 'timelineGroup' && !isNodeCenterInsideGroup(node, parentNode, nodeById)) {
        graphNode = {
          ...node,
          parentId: undefined,
          extent: undefined,
          position: getNodeAbsolutePosition(node, nodeById),
        };
        parentNodeId = null;
      }
    }

    const containingGroup = node.type === 'timelineItem' && !node.parentId
      ? findContainingGroup(node, nodes.map((currentNode) => (currentNode.id === node.id ? node : currentNode)))
      : null;

    if (node.type === 'timelineItem' && !node.parentId && containingGroup) {
      graphNode = attachNodeToGroup(node, containingGroup, nodes.map((currentNode) => (
        currentNode.id === node.id ? node : currentNode
      )));
      parentNodeId = containingGroup.id;
    }

    const nextNodes = nodes.map((currentNode) => (currentNode.id === graphNode.id ? graphNode : currentNode));
    const resolvedGraph = resolveNodeCollisions(nextNodes, node.id);
    const resolvedNode = resolvedGraph.nodes.find((currentNode) => currentNode.id === node.id) ?? node;
    const persistedEdges = withoutProximityPreviewEdges(edges);
    const closestEdge = proximityConnectEnabled && resolvedNode.type === 'timelineItem'
      ? getClosestGraphProximityEdge(resolvedNode, resolvedGraph.nodes)
      : null;
    const shouldAddProximityEdge = Boolean(
      closestEdge && !hasEdgeBetween(persistedEdges, closestEdge.source, closestEdge.target),
    );
    const newEdgeId = shouldAddProximityEdge ? createEdgeId() : null;

    setNodes(resolvedGraph.nodes);
    setEdges((currentEdges) => {
      const nextEdges = withoutProximityPreviewEdges(currentEdges);
      if (!closestEdge || !newEdgeId || hasEdgeBetween(nextEdges, closestEdge.source, closestEdge.target)) {
        return nextEdges;
      }

      return addEdge({
        ...defaultEdgeOptions,
        type: 'timelineGraph',
        id: newEdgeId,
        source: closestEdge.source,
        target: closestEdge.target,
        sourceHandle: closestEdge.sourceHandle,
        targetHandle: closestEdge.targetHandle,
        data: { marker: 'forward', floating: graphSettings.floatingEdges },
        ...getEdgeMarkerProps('forward'),
      } satisfies TimelineGraphEdge, nextEdges);
    });

    void sendGraphPatch([
      {
        type: 'move_node',
        node_id: node.id,
        position: resolvedNode.position,
      },
      ...(parentNodeId !== undefined ? [{
        type: 'update_node_metadata' as const,
        node_id: node.id,
        parent_node_id: parentNodeId,
      }] : []),
      ...buildMoveOperations(resolvedGraph.movedNodes),
      ...(closestEdge && newEdgeId ? [{
        type: 'add_edge' as const,
        edge_id: newEdgeId,
        source: closestEdge.source,
        target: closestEdge.target,
        source_handle: closestEdge.sourceHandle ?? undefined,
        target_handle: closestEdge.targetHandle ?? undefined,
        marker: 'forward' as const,
      }] : []),
    ]);
  }, [edges, graphSettings.floatingEdges, nodes, proximityConnectEnabled, sendGraphPatch, setEdges, setNodes]);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: TimelineFlowNode) => {
    setSelectedNodeId(node.id);
    setSelectedNodeIds([node.id]);
    setSelectedEdgeId(null);
    setSelectedItemId(node.type === 'timelineItem' ? node.data.itemId : null);
  }, []);

  const handleEdgeClick = useCallback((_: React.MouseEvent, edge: TimelineGraphEdge) => {
    setSelectedEdgeId(edge.id);
    setSelectedNodeId(null);
    setSelectedNodeIds([]);
    setSelectedItemId(null);
  }, []);

  const handlePaneClick = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedNodeIds([]);
    setSelectedEdgeId(null);
    setSelectedItemId(null);
  }, []);

  const handleGraphKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Backspace' && event.key !== 'Delete') {
      return;
    }

    const target = event.target as HTMLElement | null;
    if (target?.closest('input, textarea, [contenteditable="true"]')) {
      return;
    }

    if (selectedNodeIds.length === 0 && !selectedEdgeId) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    if (selectedNodeIds.length > 0) {
      handleRemoveSelectedNodes();
      return;
    }

    if (selectedEdgeId) {
      handleRemoveEdge(selectedEdgeId);
    }
  }, [handleRemoveEdge, handleRemoveSelectedNodes, selectedEdgeId, selectedNodeIds.length]);

  const handleSelectionChange = useCallback(({ nodes: selectedNodes }: { nodes: TimelineFlowNode[] }) => {
    setSelectedNodeIds(selectedNodes.map((node) => node.id));
    if (selectedNodes.length === 1) {
      setSelectedNodeId(selectedNodes[0].id);
      setSelectedItemId(selectedNodes[0].type === 'timelineItem' ? selectedNodes[0].data.itemId : null);
      return;
    }

    if (selectedNodes.length === 0) {
      setSelectedNodeId(null);
      setSelectedItemId(null);
    }
  }, []);

  const latestGraphActionsRef = useRef<TimelineGraphActions | null>(null);
  latestGraphActionsRef.current = {
    connectorsVisible,
    onRemoveNode: handleRemoveNode,
    onResizeNode: handleResizeNode,
    onGroupLabelCommit: handleGroupLabelCommit,
    onRemoveEdge: handleRemoveEdge,
    onEdgeLabelCommit: handleEdgeLabelCommit,
    onEdgeMarkerChange: handleEdgeMarkerChange,
    onFlagItem,
    onHighlightItem,
    onDeleteItem,
    onEditItem,
  };

  const graphActions = useMemo<TimelineGraphActions>(() => ({
    connectorsVisible,
    onRemoveNode: (nodeId) => latestGraphActionsRef.current?.onRemoveNode(nodeId),
    onResizeNode: (nodeId, width, height) => latestGraphActionsRef.current?.onResizeNode(nodeId, width, height),
    onGroupLabelCommit: (nodeId, label) => latestGraphActionsRef.current?.onGroupLabelCommit(nodeId, label),
    onRemoveEdge: (edgeId) => latestGraphActionsRef.current?.onRemoveEdge(edgeId),
    onEdgeLabelCommit: (edgeId, label) => latestGraphActionsRef.current?.onEdgeLabelCommit(edgeId, label),
    onEdgeMarkerChange: (edgeId, marker) => latestGraphActionsRef.current?.onEdgeMarkerChange(edgeId, marker),
    ...(onFlagItem ? { onFlagItem: (itemId: string) => latestGraphActionsRef.current?.onFlagItem?.(itemId) } : {}),
    ...(onHighlightItem ? { onHighlightItem: (itemId: string) => latestGraphActionsRef.current?.onHighlightItem?.(itemId) } : {}),
    ...(onDeleteItem ? { onDeleteItem: (itemId: string) => latestGraphActionsRef.current?.onDeleteItem?.(itemId) } : {}),
    ...(onEditItem ? { onEditItem: (itemId: string) => latestGraphActionsRef.current?.onEditItem?.(itemId) } : {}),
  }), [
    connectorsVisible,
    onDeleteItem,
    onEditItem,
    onFlagItem,
    onHighlightItem,
  ]);

  return (
    <div ref={graphContainerRef} className="flex h-full min-h-0 w-full overflow-hidden border border-solid border-neutral-border bg-default-background">
      <aside
        className="relative flex min-h-0 flex-none flex-col border-r border-solid border-neutral-border mobile:!w-60"
        style={{ width: graphLayout.itemsPaneWidth }}
      >
        <div className="flex flex-col gap-1 border-b border-solid border-neutral-border px-4 py-3">
          <span className="text-heading-3 font-heading-3 text-default-font">Timeline items</span>
          <span className="text-caption font-caption text-subtext-color">{stagedItems.length} available</span>
        </div>
        <div className="flex min-h-0 grow flex-col gap-2 overflow-auto p-3">
          {stagedItems.length > 0 ? stagedItems.map((item) => {
            const Icon = getTimelineItemIcon(item.type || 'note');

            return (
              <div
                key={item.id}
                draggable
                role="button"
                tabIndex={0}
                aria-pressed={selectedItemId === item.id}
                className={cn(
                  'flex cursor-grab flex-col gap-2 rounded-md border border-solid border-neutral-border bg-neutral-0 px-3 py-3 text-left active:cursor-grabbing',
                  selectedItemId === item.id && 'border-brand-primary ring-2 ring-brand-primary/40',
                )}
                onClick={() => {
                  setSelectedNodeId(null);
                  setSelectedNodeIds([]);
                  setSelectedEdgeId(null);
                  setSelectedItemId(item.id || null);
                }}
                onKeyDown={(event) => {
                  if (event.key !== 'Enter' && event.key !== ' ') {
                    return;
                  }

                  event.preventDefault();
                  setSelectedNodeId(null);
                  setSelectedNodeIds([]);
                  setSelectedEdgeId(null);
                  setSelectedItemId(item.id || null);
                }}
                onDragStart={(event) => {
                  setIsDraggingTimelineItem(true);
                  event.dataTransfer.setData('application/x-timeline-item-id', item.id || '');
                  event.dataTransfer.effectAllowed = 'copy';
                }}
                onDragEnd={() => setIsDraggingTimelineItem(false)}
              >
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 flex-none text-subtext-color" />
                  <span className="truncate text-caption-bold font-caption-bold uppercase text-subtext-color">
                    {getTimelineItemLabel(item.type || 'note')}
                  </span>
                </div>
                <span className="line-clamp-2 text-body-bold font-body-bold text-default-font">
                  {getNodeTitle(item)}
                </span>
                <span className="text-caption font-caption text-subtext-color">
                  {formatTimestamp(item, sortBy)}
                </span>
              </div>
            );
          }) : (
            <div className="flex min-h-[160px] items-center justify-center rounded-md border border-dashed border-neutral-border px-4 text-center">
              <span className="text-body font-body text-subtext-color">All timeline items are on the graph</span>
            </div>
          )}
        </div>
        <div
          role="separator"
          aria-label="Resize timeline items pane"
          aria-orientation="vertical"
          tabIndex={0}
          className="absolute right-[-4px] top-0 z-10 h-full w-2 cursor-col-resize bg-transparent outline-none transition-colors hover:bg-brand-primary/20 focus:bg-brand-primary/20 mobile:hidden"
          onPointerDown={handleItemsPaneResizeStart}
        />
      </aside>

      <div className="flex min-w-0 grow flex-col overflow-hidden">
        <div className="relative min-h-0 grow" onKeyDownCapture={handleGraphKeyDown}>
          <TimelineGraphActionsContext.Provider
            value={graphActions}
          >
            <ReactFlow
              nodes={nodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              defaultEdgeOptions={defaultEdgeOptions}
              connectionMode={ConnectionMode.Loose}
              snapToGrid
              snapGrid={SNAP_GRID}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeDragStart={handleNodeDragStart}
              onNodeDrag={handleNodeDrag}
              onNodeDragStop={handleNodeDragStop}
              onConnect={handleConnect}
              onReconnect={handleReconnect}
              onDrop={(event) => {
                setIsDraggingTimelineItem(false);
                handleDrop(event);
              }}
              onDragOver={handleDragOver}
              onNodeClick={handleNodeClick}
              onEdgeClick={handleEdgeClick}
              onPaneClick={handlePaneClick}
              onSelectionChange={handleSelectionChange}
              deleteKeyCode={null}
              fitView
              minZoom={0.35}
              maxZoom={2.5}
              proOptions={{ hideAttribution: true }}
              nodesDraggable
              nodesConnectable
              edgesReconnectable
              elementsSelectable
              colorMode={resolvedTheme}
              className="timeline-graph-flow"
              style={{
                ...graphThemeStyle,
                '--xy-background-color': graphCanvasColor,
              } as React.CSSProperties}
            >
              <Background variant={BackgroundVariant.Dots} gap={GRID_SIZE} size={1.4} color={gridDotColor} />
              <Controls
                position="top-left"
                showInteractive={false}
                className={graphPanelChromeClasses}
              />
              <MiniMap
                position="top-right"
                pannable
                zoomable
                className={graphPanelChromeClasses}
                nodeColor={(node) => getMiniMapColor(node as TimelineGraphNode)}
                nodeStrokeColor="rgb(var(--color-default-background))"
                nodeStrokeWidth={3}
                bgColor="rgb(var(--color-neutral-50))"
                maskColor="rgb(var(--color-default-background) / 0.66)"
                maskStrokeColor="rgb(var(--color-focus-border))"
              />
              <Panel position="bottom-left" className={cn('flex items-center gap-1', graphPanelChromeClasses)}>
                <button
                  type="button"
                  aria-label="Toggle floating edges"
                  title="Floating edges"
                  className={cn(
                    'flex h-8 w-8 items-center justify-center rounded-md border border-solid text-default-font transition-colors hover:bg-neutral-100 disabled:cursor-default disabled:opacity-50',
                    graphSettings.floatingEdges ? 'border-brand-primary bg-brand-primary text-black' : 'border-neutral-border bg-default-background'
                  )}
                  onClick={() => setGraphSettings((currentSettings) => ({
                    ...currentSettings,
                    floatingEdges: !currentSettings.floatingEdges,
                  }))}
                >
                  <GitBranch className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label="Toggle proximity connect"
                  title="Proximity connect"
                  className={cn(
                    'flex h-8 w-8 items-center justify-center rounded-md border border-solid text-default-font transition-colors hover:bg-neutral-100 disabled:cursor-default disabled:opacity-50',
                    proximityConnectEnabled ? 'border-brand-primary bg-brand-primary text-black' : 'border-neutral-border bg-default-background'
                  )}
                  onClick={() => setGraphSettings((currentSettings) => ({
                    ...currentSettings,
                    proximityConnectEnabled: !currentSettings.proximityConnectEnabled,
                  }))}
                >
                  <Magnet className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label="Group selected nodes"
                  title="Group selected nodes"
                  className="flex h-8 w-8 items-center justify-center rounded-md border border-solid border-neutral-border bg-default-background text-default-font transition-colors hover:bg-neutral-100 disabled:cursor-default disabled:opacity-50"
                  disabled={selectedNodeIds.length < 2}
                  onClick={handleGroupSelectedNodes}
                >
                  <Group className="h-4 w-4" />
                </button>
              </Panel>
              {nodes.length === 0 ? (
                <Panel position="top-center" className="pointer-events-none">
                  <div className="rounded-md border border-dashed border-neutral-border bg-default-background/95 px-4 py-3 text-center">
                    <span className="text-body font-body text-subtext-color">Empty graph</span>
                  </div>
                </Panel>
              ) : null}
            </ReactFlow>
          </TimelineGraphActionsContext.Provider>
        </div>

        <section
          className="relative flex flex-none flex-col gap-4 overflow-hidden border-t border-solid border-neutral-border p-4 mobile:!h-96"
          style={{ height: graphLayout.detailPaneHeight }}
        >
          <div
            role="separator"
            aria-label="Resize graph detail pane"
            aria-orientation="horizontal"
            tabIndex={0}
            className="absolute left-0 top-[-4px] z-10 h-2 w-full cursor-row-resize bg-transparent outline-none transition-colors hover:bg-brand-primary/20 focus:bg-brand-primary/20 mobile:hidden"
            onPointerDown={handleDetailPaneResizeStart}
          />
          {selectedEdge ? (
            <div className="flex min-h-0 flex-col gap-3 overflow-auto">
              <span className="text-caption-bold font-caption-bold uppercase text-subtext-color">Selected link</span>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-caption font-caption text-subtext-color mobile:grid-cols-1">
                <span>ID: {selectedEdge.id}</span>
                <span>Label: {typeof selectedEdge.label === 'string' && selectedEdge.label.trim().length > 0 ? selectedEdge.label : 'None'}</span>
                <span>Source: {selectedEdge.source}</span>
                <span>Target: {selectedEdge.target}</span>
                <span>Marker: {selectedEdge.data?.marker || 'forward'}</span>
              </div>
              <span className="text-body font-body text-subtext-color">Use the edge toolbar on the canvas to label, mark, reconnect, or remove this link.</span>
            </div>
          ) : selectedItem ? (
            <div className="flex min-h-0 grow flex-col gap-4 overflow-auto">
              <div className="flex flex-col gap-2">
                <span className="text-caption-bold font-caption-bold uppercase text-subtext-color">
                  {selectedNode?.type === 'timelineItem' ? 'Selected node' : 'Selected item'}
                </span>
                <span className="text-heading-3 font-heading-3 text-default-font">{getNodeTitle(selectedItem)}</span>
                <span className="text-body font-body text-subtext-color">{getNodeSubtitle(selectedItem)}</span>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-caption font-caption text-subtext-color mobile:grid-cols-1">
                <span>ID: {selectedItem.id || 'Not recorded'}</span>
                <span>Type: {getTimelineItemLabel(selectedItem.type || 'note')}</span>
                <div className="flex min-w-0 items-center gap-1">
                  <span className="shrink-0">Timestamp:</span>
                  {(selectedItem as any).timestamp ? (
                    <CopyableTimestamp
                      value={(selectedItem as any).timestamp || null}
                      showFull
                      variant="default-left"
                      className="min-w-0"
                    />
                  ) : (
                    <span>Not recorded</span>
                  )}
                </div>
                <div className="flex min-w-0 items-center gap-1">
                  <span className="shrink-0">Created:</span>
                  {selectedItem.created_at ? (
                    <CopyableTimestamp
                      value={selectedItem.created_at || null}
                      showFull
                      variant="default-left"
                      className="min-w-0"
                    />
                  ) : (
                    <span>Not recorded</span>
                  )}
                </div>
                <div className="flex min-w-0 items-center gap-1">
                  <span className="shrink-0">Modified:</span>
                  {selectedItemModifiedAt ? (
                    <CopyableTimestamp
                      value={selectedItemModifiedAt}
                      showFull
                      variant="default-left"
                      className="min-w-0"
                    />
                  ) : (
                    <span>Not recorded</span>
                  )}
                </div>
                <span>Created by: {selectedItem.created_by || 'System'}</span>
              </div>
              <div className="mt-auto flex flex-wrap gap-2">
                <Button variant="neutral-secondary" size="small" icon={<Search />} onClick={() => selectedItem.id && onSelectItem?.(selectedItem.id)}>
                  Find in timeline
                </Button>
              </div>
            </div>
          ) : (
            <span className="text-body font-body text-subtext-color">No graph selection</span>
          )}
        </section>
      </div>
    </div>
  );
}

export function TimelineGraphView(props: TimelineGraphViewProps) {
  return (
    <ReactFlowProvider>
      <TimelineGraphViewInner {...props} />
    </ReactFlowProvider>
  );
}

export default TimelineGraphView;
