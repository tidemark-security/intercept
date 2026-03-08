import React from 'react';
import { Bot, Check, Copy, Download, Expand, Image as ImageIcon, Paintbrush, RefreshCcw, Sparkles, X, ZoomIn, ZoomOut } from 'lucide-react';

import { Button } from '@/components/buttons/Button';
import { IconButton } from '@/components/buttons/IconButton';
import { Dialog } from '@/components/overlays/Dialog';
import { useTheme } from '@/contexts/ThemeContext';
import { cn } from '@/utils/cn';

interface MermaidRendererProps {
  code: string;
  isStreaming?: boolean;
}

type MermaidTheme = 'dark' | 'default';

let mermaidInitTheme: MermaidTheme | null = null;
const mermaidRenderCache = new Map<string, string>();
const MERMAID_RENDER_CACHE_LIMIT = 200;

const getCacheKey = (theme: MermaidTheme, code: string): string => {
  return `${theme}::${code}`;
};

const setCachedSvg = (key: string, svg: string): void => {
  if (mermaidRenderCache.has(key)) {
    mermaidRenderCache.delete(key);
  }

  mermaidRenderCache.set(key, svg);

  if (mermaidRenderCache.size > MERMAID_RENDER_CACHE_LIMIT) {
    const oldestKey = mermaidRenderCache.keys().next().value;
    if (typeof oldestKey === 'string') {
      mermaidRenderCache.delete(oldestKey);
    }
  }
};

const getMermaidClient = async (theme: MermaidTheme) => {
  const mermaidModule = await import('mermaid');
  const mermaid = mermaidModule.default;

  if (mermaidInitTheme !== theme) {
    mermaid.initialize({
      startOnLoad: false,
      htmlLabels: false,
      flowchart: {
        htmlLabels: false,
      },
      securityLevel: 'strict',
      theme,
    });
    mermaidInitTheme = theme;
  }

  return mermaid;
};

const MermaidStreamingPlaceholder = () => {
  return (
    <div
      className="my-3 overflow-hidden rounded-sm border border-neutral-border bg-default-background"
      data-testid="mermaid-streaming-placeholder"
    >
      <div className="flex items-center justify-between border-b border-neutral-border bg-neutral-50 px-3 py-2">
        <div className="flex items-center gap-3">
          <div className="relative flex h-10 w-10 items-center justify-center rounded-sm border border-brand-primary/40 bg-brand-primary/10 text-brand-primary">
            <Bot className="h-5 w-5" />
            <Sparkles className="absolute -right-1 -top-1 h-3 w-3 animate-pulse text-accent-2-primary-blush" />
          </div>
          <div>
            <p className="text-sm font-semibold text-default-font">AI is sketching the diagram</p>
            <p className="text-xs text-subtext-color">
              The preview is paused until the Mermaid source finishes streaming.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1" aria-hidden="true">
          <span className="h-2 w-2 animate-bounce rounded-full bg-brand-primary" style={{ animationDelay: '0ms' }} />
          <span className="h-2 w-2 animate-bounce rounded-full bg-accent-2-primary-blush" style={{ animationDelay: '120ms' }} />
          <span className="h-2 w-2 animate-bounce rounded-full bg-accent-3-primary-blush" style={{ animationDelay: '240ms' }} />
        </div>
      </div>

      <div className="p-3">
        <div className="rounded-sm border border-dashed border-neutral-border bg-neutral-50/70 p-3">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.12em] text-subtext-color">
            <Paintbrush className="h-4 w-4 text-brand-primary" />
            Thinking Through Nodes
          </div>

          <div className="mt-3 space-y-2">
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-brand-primary/70" />
              <span className="h-2 w-32 animate-pulse rounded-full bg-neutral-300" />
            </div>
            <div className="ml-5 h-px w-12 bg-neutral-border" />
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-accent-2-primary-blush/80" />
              <span className="h-2 w-40 animate-pulse rounded-full bg-neutral-300" style={{ animationDelay: '120ms' }} />
            </div>
            <div className="ml-5 h-px w-20 bg-neutral-border" />
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-accent-3-primary-blush/80" />
              <span className="h-2 w-24 animate-pulse rounded-full bg-neutral-300" style={{ animationDelay: '240ms' }} />
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-neutral-border px-3 py-2 text-xs text-subtext-color">
        Streaming Mermaid can be temporarily invalid. The renderer will switch to the final diagram when the AI finishes painting.
      </div>
    </div>
  );
};

const MIN_ZOOM = 0.2;
const MAX_ZOOM = 10;
const ZOOM_STEP = 0.2;

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

const clamp = (value: number, min: number, max: number): number => {
  return Math.min(max, Math.max(min, value));
};

const getSvgElementFromMarkup = (markup: string): SVGSVGElement | null => {
  if (!markup) {
    return null;
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(markup, 'image/svg+xml');
  return doc.querySelector('svg');
};

const getSvgDimensions = (svgElement: SVGSVGElement): { width: number; height: number } | null => {
  const viewBox = svgElement.getAttribute('viewBox');
  if (viewBox) {
    const [, , width, height] = viewBox.split(/[\s,]+/).map((value) => Number.parseFloat(value));

    if (Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0) {
      return { width, height };
    }
  }

  const width = Number.parseFloat(svgElement.getAttribute('width') || '');
  const height = Number.parseFloat(svgElement.getAttribute('height') || '');

  if (Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0) {
    return { width, height };
  }

  return null;
};

const serializeSvg = (svgElement: SVGSVGElement): string => {
  if (!svgElement.getAttribute('xmlns')) {
    svgElement.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  }

  if (!svgElement.getAttribute('xmlns:xlink')) {
    svgElement.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
  }

  return new XMLSerializer().serializeToString(svgElement);
};

const getFullscreenSvgMarkup = (markup: string): string => {
  if (!markup) {
    return '';
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(markup, 'image/svg+xml');
  const svgElement = doc.querySelector('svg');

  if (!svgElement) {
    return markup;
  }

  const viewBox = svgElement.getAttribute('viewBox');
  if (viewBox) {
    const [, , width, height] = viewBox.split(/[\s,]+/).map((value) => Number.parseFloat(value));

    if (Number.isFinite(width) && width > 0) {
      svgElement.setAttribute('width', String(width));
    }

    if (Number.isFinite(height) && height > 0) {
      svgElement.setAttribute('height', String(height));
    }
  }

  const styleAttribute = svgElement.getAttribute('style');
  if (styleAttribute) {
    const normalizedStyle = styleAttribute
      .split(';')
      .map((rule) => rule.trim())
      .filter((rule) => rule && !rule.startsWith('max-width:'))
      .join('; ');

    if (normalizedStyle) {
      svgElement.setAttribute('style', normalizedStyle);
    } else {
      svgElement.removeAttribute('style');
    }
  }

  return svgElement.outerHTML;
};

const MermaidRenderer: React.FC<MermaidRendererProps> = ({ code, isStreaming = false }) => {
  const { resolvedTheme } = useTheme();
  const dragStateRef = React.useRef<DragState | null>(null);
  const viewportRef = React.useRef<HTMLDivElement | null>(null);
  const diagramRef = React.useRef<HTMLDivElement | null>(null);
  const mermaidCopyTimeoutRef = React.useRef<number | null>(null);
  const imageCopyTimeoutRef = React.useRef<number | null>(null);

  const [svgMarkup, setSvgMarkup] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [zoom, setZoom] = React.useState(1);
  const [pan, setPan] = React.useState<PanState>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = React.useState(false);
  const [fitScale, setFitScale] = React.useState(1);
  const [isMermaidCopied, setIsMermaidCopied] = React.useState(false);
  const [isImageCopied, setIsImageCopied] = React.useState(false);

  const clearCopyTimeout = React.useCallback((timeoutRef: React.MutableRefObject<number | null>) => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const markCopied = React.useCallback(
    (
      setCopied: React.Dispatch<React.SetStateAction<boolean>>,
      timeoutRef: React.MutableRefObject<number | null>
    ) => {
      clearCopyTimeout(timeoutRef);
      setCopied(true);
      timeoutRef.current = window.setTimeout(() => {
        setCopied(false);
        timeoutRef.current = null;
      }, 2000);
    },
    [clearCopyTimeout]
  );

  React.useEffect(() => {
    return () => {
      clearCopyTimeout(mermaidCopyTimeoutRef);
      clearCopyTimeout(imageCopyTimeoutRef);
    };
  }, [clearCopyTimeout]);

  const resetViewport = React.useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  const updateFitScale = React.useCallback(() => {
    if (!isModalOpen || !viewportRef.current || !diagramRef.current) {
      return;
    }

    const svgElement = diagramRef.current.querySelector('svg');
    if (!svgElement) {
      return;
    }

    const viewBox = svgElement.viewBox.baseVal;
    const diagramWidth = viewBox && viewBox.width > 0 ? viewBox.width : svgElement.getBBox().width;
    const diagramHeight = viewBox && viewBox.height > 0 ? viewBox.height : svgElement.getBBox().height;
    const { clientWidth, clientHeight } = viewportRef.current;
    if (clientWidth <= 0 || clientHeight <= 0 || diagramWidth <= 0 || diagramHeight <= 0) {
      return;
    }

    setFitScale(Math.min(clientWidth / diagramWidth, clientHeight / diagramHeight));
  }, [isModalOpen]);

  React.useEffect(() => {
    if (!svgMarkup) {
      setFitScale(1);
      return;
    }

    if (!isModalOpen) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      updateFitScale();
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [isModalOpen, svgMarkup, updateFitScale]);

  React.useEffect(() => {
    if (!isModalOpen || !viewportRef.current) {
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
  }, [isModalOpen, updateFitScale]);

  const effectiveZoom = fitScale * zoom;
  const fullscreenSvgMarkup = React.useMemo(() => getFullscreenSvgMarkup(svgMarkup), [svgMarkup]);

  React.useEffect(() => {
    let cancelled = false;

    const renderDiagram = async () => {
      const trimmedCode = code.trim();

      if (isStreaming) {
        setError(null);
        return;
      }

      if (!trimmedCode) {
        setSvgMarkup('');
        setError(null);
        return;
      }

      const theme: MermaidTheme = resolvedTheme === 'dark' ? 'dark' : 'default';
      const cacheKey = getCacheKey(theme, trimmedCode);
      const cachedMarkup = mermaidRenderCache.get(cacheKey);

      if (cachedMarkup) {
        setSvgMarkup(cachedMarkup);
        setError(null);
        return;
      }

      const renderHost = document.createElement('div');
      renderHost.setAttribute('aria-hidden', 'true');
      renderHost.style.position = 'absolute';
      renderHost.style.left = '-10000px';
      renderHost.style.top = '0';
      renderHost.style.visibility = 'hidden';
      renderHost.style.pointerEvents = 'none';
      renderHost.style.zIndex = '-1';
      document.body.appendChild(renderHost);

      try {
        const mermaid = await getMermaidClient(theme);

        const renderId = `mermaid-${Math.random().toString(36).slice(2)}`;
        const { svg } = await mermaid.render(renderId, trimmedCode, renderHost);

        if (cancelled) {
          return;
        }

        setSvgMarkup(svg);
        setCachedSvg(cacheKey, svg);
        setError(null);
        resetViewport();
      } catch (renderError) {
        if (cancelled) {
          return;
        }

        setSvgMarkup('');
        setError('Unable to render Mermaid diagram.');
        console.error('Failed to render Mermaid diagram:', renderError);
      } finally {
        renderHost.remove();
      }
    };

    void renderDiagram();

    return () => {
      cancelled = true;
    };
  }, [code, isStreaming, resetViewport, resolvedTheme]);

  const handleDownload = React.useCallback(() => {
    if (!svgMarkup) {
      return;
    }

    const svgElement = getSvgElementFromMarkup(svgMarkup);

    if (!svgElement) {
      return;
    }

    const serialized = serializeSvg(svgElement);
    const blob = new Blob([serialized], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = url;
    link.download = 'mermaid-diagram.svg';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(url);
  }, [svgMarkup]);

  const handleCopyMermaid = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      markCopied(setIsMermaidCopied, mermaidCopyTimeoutRef);
    } catch (copyError) {
      console.error('Failed to copy Mermaid source:', copyError);
    }
  }, [code, markCopied]);

  const handleCopyImage = React.useCallback(async () => {
    if (!fullscreenSvgMarkup || !navigator.clipboard?.write || typeof ClipboardItem === 'undefined') {
      console.error('Clipboard image copy is not supported in this browser.');
      return;
    }

    const svgElement = getSvgElementFromMarkup(fullscreenSvgMarkup);
    if (!svgElement) {
      return;
    }

    const dimensions = getSvgDimensions(svgElement);
    if (!dimensions) {
      console.error('Unable to determine Mermaid image size for clipboard copy.');
      return;
    }

    const serializedSvg = serializeSvg(svgElement);
    const svgBlob = new Blob([serializedSvg], { type: 'image/svg+xml;charset=utf-8' });
    const svgUrl = URL.createObjectURL(svgBlob);

    try {
      const image = await new Promise<HTMLImageElement>((resolve, reject) => {
        const nextImage = new window.Image();
        nextImage.onload = () => resolve(nextImage);
        nextImage.onerror = () => reject(new Error('Failed to load Mermaid SVG for clipboard copy.'));
        nextImage.src = svgUrl;
      });

      const deviceScale = Math.max(window.devicePixelRatio || 1, 1);
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(dimensions.width * deviceScale));
      canvas.height = Math.max(1, Math.round(dimensions.height * deviceScale));

      const context = canvas.getContext('2d');
      if (!context) {
        throw new Error('Unable to create canvas context for clipboard copy.');
      }

      context.scale(deviceScale, deviceScale);
      context.drawImage(image, 0, 0, dimensions.width, dimensions.height);

      const pngBlob = await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob((blob) => {
          if (blob) {
            resolve(blob);
            return;
          }

          reject(new Error('Failed to create PNG blob for clipboard copy.'));
        }, 'image/png');
      });

      await navigator.clipboard.write([new ClipboardItem({ 'image/png': pngBlob })]);
      markCopied(setIsImageCopied, imageCopyTimeoutRef);
    } catch (copyError) {
      console.error('Failed to copy Mermaid image:', copyError);
    } finally {
      URL.revokeObjectURL(svgUrl);
    }
  }, [fullscreenSvgMarkup, markCopied]);

  const handleZoomIn = React.useCallback(() => {
    setZoom((prev) => clamp(prev + ZOOM_STEP, MIN_ZOOM, MAX_ZOOM));
  }, []);

  const handleZoomOut = React.useCallback(() => {
    setZoom((prev) => clamp(prev - ZOOM_STEP, MIN_ZOOM, MAX_ZOOM));
  }, []);

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

  if (error) {
    return (
      <div className="my-3 rounded-sm border border-warning-500 bg-warning-100 p-3 text-sm text-default-font">
        <p className="mb-2">{error}</p>
        <pre className="overflow-x-auto rounded-sm border border-neutral-border bg-default-background p-2 text-xs">
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  if (isStreaming && !svgMarkup) {
    return <MermaidStreamingPlaceholder />;
  }

  if (!svgMarkup) {
    return null;
  }

  return (
    <>
      <div className="my-3 rounded-sm border border-neutral-border bg-default-background p-3">
        <div className="mb-2 flex items-center justify-end gap-1">
          <IconButton
            size="small"
            variant="neutral-tertiary"
            icon={isMermaidCopied ? <Check /> : <Copy />}
            aria-label="Copy Mermaid source"
            title={isMermaidCopied ? 'Copied Mermaid source' : 'Copy Mermaid source'}
            onClick={handleCopyMermaid}
          />
          <IconButton
            size="small"
            variant="neutral-tertiary"
            icon={isImageCopied ? <Check /> : <ImageIcon />}
            aria-label="Copy Mermaid diagram as image"
            title={isImageCopied ? 'Copied Mermaid image' : 'Copy Mermaid diagram as image'}
            onClick={handleCopyImage}
          />
          <IconButton
            size="small"
            variant="neutral-tertiary"
            icon={<Download />}
            aria-label="Download Mermaid diagram as SVG"
            title="Download SVG"
            onClick={handleDownload}
          />
          <IconButton
            size="small"
            variant="neutral-tertiary"
            icon={<Expand />}
            aria-label="Maximize Mermaid diagram"
            title="Maximize diagram"
            onClick={() => setIsModalOpen(true)}
          />
        </div>

        <div className="overflow-x-auto" data-testid="mermaid-diagram">
          <div
            className="[&_svg]:h-auto [&_svg]:max-w-full [&_svg]:w-full"
            dangerouslySetInnerHTML={{ __html: svgMarkup }}
          />
        </div>
      </div>

      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <Dialog.Content className="h-[calc(100vh-1.5rem)] w-[calc(100vw-1.5rem)] max-h-[calc(100vh-1.5rem)] max-w-[calc(100vw-1.5rem)] overflow-hidden p-0">
          <Dialog.Title className="sr-only">Mermaid diagram viewer</Dialog.Title>
          <Dialog.Description className="sr-only">
            Enlarged Mermaid diagram with pan, zoom, and SVG download controls.
          </Dialog.Description>
          <div className="flex h-full w-full flex-col">
            <div className="flex w-full items-center justify-between border-b border-neutral-border px-3 py-2">
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
                <span className="ml-2 text-xs text-subtext-color">{Math.round(zoom * 100)}%</span>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  size="small"
                  variant="neutral-secondary"
                  icon={isMermaidCopied ? <Check /> : <Copy />}
                  onClick={handleCopyMermaid}
                >
                  Copy Mermaid
                </Button>
                <Button
                  size="small"
                  variant="neutral-secondary"
                  icon={isImageCopied ? <Check /> : <ImageIcon />}
                  onClick={handleCopyImage}
                >
                  Copy Image
                </Button>
                <Button
                  size="small"
                  variant="neutral-secondary"
                  icon={<Download />}
                  onClick={handleDownload}
                >
                  Download SVG
                </Button>
                <IconButton
                  size="small"
                  variant="neutral-tertiary"
                  icon={<X />}
                  aria-label="Close diagram modal"
                  title="Close"
                  onClick={() => setIsModalOpen(false)}
                />
              </div>
            </div>

            <div
              ref={viewportRef}
              className={cn(
                'relative min-h-0 flex-1 overflow-hidden bg-neutral-50 select-none',
                isDragging ? 'cursor-grabbing' : 'cursor-grab'
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
                  ref={diagramRef}
                  style={{
                    transform: `translate(${pan.x}px, ${pan.y}px) scale(${effectiveZoom})`,
                    transformOrigin: 'center center',
                    userSelect: 'none',
                    WebkitUserSelect: 'none',
                  }}
                  className="[&_svg]:h-auto [&_svg]:max-w-none [&_svg]:w-auto"
                  dangerouslySetInnerHTML={{ __html: fullscreenSvgMarkup }}
                />
              </div>
            </div>
          </div>
        </Dialog.Content>
      </Dialog>
    </>
  );
};

export default MermaidRenderer;