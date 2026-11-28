import { useEffect, useRef, useState, type RefObject } from 'react';
import { ChevronLeft } from 'lucide-react';
import styles from './ThreeColumnLayout.module.css';

interface SplitResizeHandleProps {
  label: string;
  paneId: string;
  layoutRef: RefObject<HTMLDivElement | null>;
  width: number;
  minWidth: number;
  maxWidth: number;
  onWidthCommit: (width: number) => void;
  onCollapse?: () => void;
}

interface Drag {
  pointerId: number;
  startX: number;
  startWidth: number;
  nextWidth: number;
  frame: number | null;
  layout: HTMLDivElement;
}

const PREVIEW_WIDTH = '--split-preview-width';
const KEYBOARD_STEP = 16;

function clearPreview(drag: Drag) {
  if (drag.frame !== null) cancelAnimationFrame(drag.frame);
  drag.layout.style.removeProperty(PREVIEW_WIDTH);
}

export function SplitResizeHandle({
  label, paneId, layoutRef, width, minWidth, maxWidth, onWidthCommit, onCollapse,
}: SplitResizeHandleProps) {
  const dragRef = useRef<Drag | null>(null);
  const moved = useRef(false);
  const [dragging, setDragging] = useState(false);
  const clamp = (value: number) => Math.min(maxWidth, Math.max(minWidth, Math.round(value)));

  useEffect(() => () => {
    if (dragRef.current) clearPreview(dragRef.current);
  }, []);

  const finish = (pointerId: number, clientX?: number) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== pointerId) return;

    dragRef.current = null;
    clearPreview(drag);
    setDragging(false);
    if (clientX !== undefined) {
      const delta = clientX - drag.startX;
      moved.current ||= Math.abs(delta) > 3;
      if (!onCollapse || moved.current) onWidthCommit(clamp(drag.startWidth + delta));
    } else {
      moved.current = true;
    }
  };

  return (
    <div
      className={styles.handle}
      role="separator"
      tabIndex={0}
      aria-label={label}
      aria-controls={paneId}
      aria-orientation="vertical"
      aria-valuemin={minWidth}
      aria-valuemax={maxWidth}
      aria-valuenow={width}
      data-dragging={dragging || undefined}
      onPointerDown={(event) => {
        const layout = layoutRef.current;
        if (!layout || dragRef.current || event.button !== 0) return;

        event.preventDefault();
        event.currentTarget.focus({ preventScroll: true });
        event.currentTarget.setPointerCapture(event.pointerId);
        moved.current = false;
        dragRef.current = {
          pointerId: event.pointerId,
          startX: event.clientX,
          startWidth: width,
          nextWidth: width,
          frame: null,
          layout,
        };
        setDragging(true);
      }}
      onPointerMove={(event) => {
        const drag = dragRef.current;
        if (!drag || drag.pointerId !== event.pointerId) return;

        const delta = event.clientX - drag.startX;
        moved.current ||= Math.abs(delta) > 3;
        const nextWidth = clamp(drag.startWidth + delta);
        if (nextWidth === drag.nextWidth) return;

        drag.nextWidth = nextWidth;
        if (drag.frame === null) {
          drag.frame = requestAnimationFrame(() => {
            drag.frame = null;
            drag.layout.style.setProperty(PREVIEW_WIDTH, `${drag.nextWidth}px`);
          });
        }
      }}
      onPointerUp={(event) => finish(event.pointerId, event.clientX)}
      onPointerCancel={(event) => finish(event.pointerId)}
      onLostPointerCapture={(event) => finish(event.pointerId)}
      onClick={() => {
        if (!moved.current) onCollapse?.();
      }}
      onKeyDown={(event) => {
        const drag = dragRef.current;
        if (drag) {
          if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            finish(drag.pointerId);
            if (event.currentTarget.hasPointerCapture(drag.pointerId)) {
              event.currentTarget.releasePointerCapture(drag.pointerId);
            }
          }
          return;
        }

        let nextWidth: number;
        switch (event.key) {
          case 'Enter':
          case ' ':
            if (onCollapse) {
              event.preventDefault();
              onCollapse();
            }
            return;
          case 'ArrowLeft':
            nextWidth = width - KEYBOARD_STEP;
            break;
          case 'ArrowRight':
            nextWidth = width + KEYBOARD_STEP;
            break;
          case 'Home':
            nextWidth = minWidth;
            break;
          case 'End':
            nextWidth = maxWidth;
            break;
          default:
            return;
        }
        event.preventDefault();
        onWidthCommit(clamp(nextWidth));
      }}
    >
      {onCollapse && (
        <span className={styles.collapseHint} aria-hidden="true">
          <ChevronLeft className="h-4 w-4 text-brand-primary" />
        </span>
      )}
    </div>
  );
}
