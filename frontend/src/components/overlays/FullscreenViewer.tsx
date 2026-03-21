import React from 'react';
import { Check, Copy, Download, RefreshCcw, X, ZoomIn, ZoomOut } from 'lucide-react';

import { Button } from '@/components/buttons/Button';
import { IconButton } from '@/components/buttons/IconButton';
import { Dialog } from '@/components/overlays/Dialog';
import { cn } from '@/utils/cn';

interface ViewerAction {
  label: string;
  onAction: () => void | Promise<void>;
  icon?: React.ReactNode;
  copied?: boolean;
  disabled?: boolean;
}

interface ContentDimensions {
  width: number;
  height: number;
}

interface FullscreenViewerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  contentDimensions?: ContentDimensions | null;
  copyAction?: ViewerAction;
  downloadAction?: ViewerAction;
  extraActions?: React.ReactNode;
  viewportClassName?: string;
  contentClassName?: string;
  /** When true, viewport scrolls normally, zoom controls font-size, no pan/drag. */
  textMode?: boolean;
}

interface PanState {
  x: number;
  y: number;
}

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
}

const MIN_ZOOM = 0.2;
const MAX_ZOOM = 10;
const ZOOM_STEP = 0.2;

const TEXT_MIN_ZOOM = 0.5;
const TEXT_MAX_ZOOM = 3;
const TEXT_ZOOM_STEP = 0.1;
const TEXT_BASE_FONT_SIZE = 14; // px

const clamp = (value: number, min: number, max: number): number => {
  return Math.min(max, Math.max(min, value));
};

export function FullscreenViewer({
  open,
  onOpenChange,
  title,
  description,
  children,
  contentDimensions,
  copyAction,
  downloadAction,
  extraActions,
  viewportClassName,
  contentClassName,
  textMode = false,
}: FullscreenViewerProps) {
  const dragStateRef = React.useRef<DragState | null>(null);
  const viewportRef = React.useRef<HTMLDivElement | null>(null);
  const contentRef = React.useRef<HTMLDivElement | null>(null);

  const [zoom, setZoom] = React.useState(1);
  const [pan, setPan] = React.useState<PanState>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = React.useState(false);
  const [fitScale, setFitScale] = React.useState(1);

  const resetViewport = React.useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  const updateFitScale = React.useCallback(() => {
    if (!open || !viewportRef.current || !contentRef.current) {
      return;
    }

    const { clientWidth, clientHeight } = viewportRef.current;
    const measuredWidth = contentDimensions?.width ?? contentRef.current.offsetWidth;
    const measuredHeight = contentDimensions?.height ?? contentRef.current.offsetHeight;

    if (clientWidth <= 0 || clientHeight <= 0 || measuredWidth <= 0 || measuredHeight <= 0) {
      return;
    }

    setFitScale(Math.min(clientWidth / measuredWidth, clientHeight / measuredHeight));
  }, [contentDimensions?.height, contentDimensions?.width, open]);

  React.useEffect(() => {
    if (!open) {
      return;
    }

    resetViewport();

    const frameId = window.requestAnimationFrame(() => {
      updateFitScale();
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [open, resetViewport, updateFitScale]);

  React.useEffect(() => {
    if (!open || !viewportRef.current) {
      return;
    }

    const viewport = viewportRef.current;
    const resizeObserver = new ResizeObserver(() => {
      updateFitScale();
    });

    resizeObserver.observe(viewport);

    return () => {
      resizeObserver.disconnect();
    };
  }, [open, updateFitScale]);

  React.useEffect(() => {
    if (!open) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      updateFitScale();
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [children, contentDimensions, open, updateFitScale]);

  const effectiveZoom = textMode ? zoom : fitScale * zoom;

  const handleZoomIn = React.useCallback(() => {
    if (textMode) {
      setZoom((prev) => clamp(prev + TEXT_ZOOM_STEP, TEXT_MIN_ZOOM, TEXT_MAX_ZOOM));
    } else {
      setZoom((prev) => clamp(prev + ZOOM_STEP, MIN_ZOOM, MAX_ZOOM));
    }
  }, [textMode]);

  const handleZoomOut = React.useCallback(() => {
    if (textMode) {
      setZoom((prev) => clamp(prev - TEXT_ZOOM_STEP, TEXT_MIN_ZOOM, TEXT_MAX_ZOOM));
    } else {
      setZoom((prev) => clamp(prev - ZOOM_STEP, MIN_ZOOM, MAX_ZOOM));
    }
  }, [textMode]);

  const handleWheel = React.useCallback((event: React.WheelEvent<HTMLDivElement>) => {
    event.preventDefault();

    const factor = event.deltaY < 0 ? 1 + ZOOM_STEP : 1 - ZOOM_STEP;
    setZoom((prev) => clamp(prev * factor, MIN_ZOOM, MAX_ZOOM));
  }, []);

  const handlePointerDown = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) {
      return;
    }

    event.preventDefault();

    dragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: pan.x,
      originY: pan.y,
    };

    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }, [pan.x, pan.y]);

  const handlePointerMove = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const dragState = dragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return;
    }

    const deltaX = event.clientX - dragState.startX;
    const deltaY = event.clientY - dragState.startY;

    setPan({
      x: dragState.originX + deltaX,
      y: dragState.originY + deltaY,
    });
  }, []);

  const handlePointerUp = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const dragState = dragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return;
    }

    dragStateRef.current = null;
    setIsDragging(false);
    event.currentTarget.releasePointerCapture(event.pointerId);
  }, []);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <Dialog.Content className="h-[calc(100vh-1.5rem)] w-[calc(100vw-1.5rem)] max-h-[calc(100vh-1.5rem)] max-w-[calc(100vw-1.5rem)] overflow-hidden p-0">
        <Dialog.Title className="sr-only">{title}</Dialog.Title>
        <Dialog.Description className="sr-only">
          {description || `Expanded viewer for ${title}.`}
        </Dialog.Description>

        <div className="flex h-full w-full flex-col">
          <div className="flex w-full flex-wrap items-center justify-between gap-2 border-b border-neutral-border px-3 py-2">
            <div className="flex items-center gap-1">
              <IconButton
                size="small"
                variant="neutral-tertiary"
                icon={<ZoomOut />}
                aria-label="Zoom out"
                title="Zoom out"
                onClick={handleZoomOut}
              />
              <IconButton
                size="small"
                variant="neutral-tertiary"
                icon={<ZoomIn />}
                aria-label="Zoom in"
                title="Zoom in"
                onClick={handleZoomIn}
              />
              <IconButton
                size="small"
                variant="neutral-tertiary"
                icon={<RefreshCcw />}
                aria-label="Reset zoom and pan"
                title="Reset view"
                onClick={resetViewport}
              />
              <span className="ml-2 text-xs text-subtext-color">{Math.round((textMode ? zoom : effectiveZoom) * 100)}%</span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {extraActions}
              {copyAction ? (
                <Button
                  size="small"
                  variant="neutral-secondary"
                  icon={copyAction.copied ? <Check /> : copyAction.icon || <Copy />}
                  onClick={() => {
                    void copyAction.onAction();
                  }}
                  disabled={copyAction.disabled}
                >
                  {copyAction.label}
                </Button>
              ) : null}
              {downloadAction ? (
                <Button
                  size="small"
                  variant="neutral-secondary"
                  icon={downloadAction.icon || <Download />}
                  onClick={() => {
                    void downloadAction.onAction();
                  }}
                  disabled={downloadAction.disabled}
                >
                  {downloadAction.label}
                </Button>
              ) : null}
              <IconButton
                size="small"
                variant="neutral-tertiary"
                icon={<X />}
                aria-label="Close viewer"
                title="Close"
                onClick={() => onOpenChange(false)}
              />
            </div>
          </div>

          {textMode ? (
            <div
              ref={viewportRef}
              className={cn(
                'min-h-0 flex-1 overflow-auto bg-neutral-50',
                viewportClassName
              )}
            >
              <div
                ref={contentRef}
                className={cn('w-full p-6', contentClassName)}
                style={{ fontSize: `${TEXT_BASE_FONT_SIZE * zoom}px` }}
              >
                {children}
              </div>
            </div>
          ) : (
            <div
              ref={viewportRef}
              className={cn(
                'relative min-h-0 flex-1 overflow-hidden bg-neutral-50 select-none',
                isDragging ? 'cursor-grabbing' : 'cursor-grab',
                viewportClassName
              )}
              style={{ userSelect: 'none', WebkitUserSelect: 'none' }}
              onWheel={handleWheel}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
            >
              <div className="absolute inset-0 flex items-center justify-center">
                <div
                  ref={contentRef}
                  className={contentClassName}
                  style={{
                    transform: `translate(${pan.x}px, ${pan.y}px) scale(${effectiveZoom})`,
                    transformOrigin: 'center center',
                    userSelect: 'none',
                    WebkitUserSelect: 'none',
                  }}
                >
                  {children}
                </div>
              </div>
            </div>
          )}
        </div>
      </Dialog.Content>
    </Dialog>
  );
}