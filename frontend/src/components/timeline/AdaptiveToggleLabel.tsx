import React from 'react';

import { cn } from '@/utils/cn';

interface AdaptiveToggleLabelProps {
  labels: readonly string[];
  srLabel?: string;
  labelIndex?: number;
  onLabelIndexChange?: (labelIndex: number) => void;
  className?: string;
}

export function AdaptiveToggleLabel({
  labels,
  srLabel,
  labelIndex,
  onLabelIndexChange,
  className,
}: AdaptiveToggleLabelProps) {
  const labelRef = React.useRef<HTMLSpanElement | null>(null);
  const measurementRefs = React.useRef<Array<HTMLSpanElement | null>>([]);
  const [measuredLabelIndex, setMeasuredLabelIndex] = React.useState(0);
  const labelsKey = labels.join('\u0000');
  const visibleLabelIndex = labelIndex ?? measuredLabelIndex;
  const visibleLabel = visibleLabelIndex < labels.length ? labels[visibleLabelIndex] : null;

  React.useLayoutEffect(() => {
    const labelElement = labelRef.current;
    if (!labelElement) {
      return;
    }

    const updateLabel = () => {
      const availableWidth = labelElement.getBoundingClientRect().width;
      const nextLabelIndex = labels.findIndex((_, index) => {
        const measurementElement = measurementRefs.current[index];
        return measurementElement
          ? measurementElement.getBoundingClientRect().width <= availableWidth + 0.5
          : false;
      });
      const nextMeasuredLabelIndex = nextLabelIndex >= 0 ? nextLabelIndex : labels.length;

      setMeasuredLabelIndex(nextMeasuredLabelIndex);
      onLabelIndexChange?.(nextMeasuredLabelIndex);
    };

    updateLabel();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateLabel);
      return () => window.removeEventListener('resize', updateLabel);
    }

    const resizeObserver = new ResizeObserver(updateLabel);
    resizeObserver.observe(labelElement);

    return () => resizeObserver.disconnect();
  }, [labelIndex, labelsKey, labels, onLabelIndexChange]);

  return (
    <span
      ref={labelRef}
      className={cn(
        "relative block min-w-0 max-w-full overflow-hidden whitespace-nowrap text-left",
        !visibleLabel && "w-0 flex-none",
        className,
      )}
    >
      {labels.map((measurementLabel, index) => (
        <span
          key={`${measurementLabel}-${index}`}
          ref={(node) => {
            measurementRefs.current[index] = node;
          }}
          aria-hidden="true"
          className="pointer-events-none invisible absolute left-0 top-0 whitespace-nowrap"
        >
          {measurementLabel}
        </span>
      ))}
      {visibleLabel ? <span aria-hidden={Boolean(srLabel)}>{visibleLabel}</span> : null}
      {srLabel ? <span className="sr-only">{srLabel}</span> : null}
    </span>
  );
}
