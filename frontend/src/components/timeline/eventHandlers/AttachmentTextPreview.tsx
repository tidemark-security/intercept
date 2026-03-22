import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, Copy, Download } from 'lucide-react';

import { CodeBlock } from '@/components/data-display/CodeBlock';
import { FullscreenViewer } from '@/components/overlays/FullscreenViewer';
import { QUERY_STALE_TIMES } from '@/config/queryConfig';
import { useTheme } from '@/contexts/ThemeContext';
import { useAttachmentLimits } from '../../../hooks/useAttachmentLimits';
import { useFullscreenViewer } from '@/hooks/useFullscreenViewer';
import type { AttachmentItem } from '@/types/generated/models/AttachmentItem';
import { getLanguageFromFilename } from '@/utils/fileLanguage';

import { getAttachmentDownloadDetails, triggerBrowserDownload, type AttachmentEntityType } from './attachmentDownload';
import { AttachmentPreviewLimitNotice } from './AttachmentPreviewLimitNotice';

interface AttachmentTextPreviewProps {
  item: AttachmentItem;
  entityId: number;
  entityType: AttachmentEntityType;
}

const SNIPPET_LINES = 15;

export function AttachmentTextPreview({ item, entityId, entityType }: AttachmentTextPreviewProps) {
  const viewer = useFullscreenViewer();
  const { resolvedTheme } = useTheme();
  const { limits } = useAttachmentLimits();
  const copyTimeoutRef = React.useRef<number | null>(null);
  const [isCopied, setIsCopied] = React.useState(false);

  const itemId = item.id;
  const filename = item.file_name || 'attachment';
  const language = getLanguageFromFilename(filename);
  const tooLarge = (item.file_size ?? 0) > limits.max_text_preview_size_bytes;

  // Fetch presigned download URL
  const { data: downloadDetails } = useQuery({
    queryKey: ['attachment-download', entityType, entityId, itemId],
    queryFn: () => getAttachmentDownloadDetails(entityType, entityId, itemId as string),
    enabled: item.upload_status === 'COMPLETE' && Boolean(itemId) && !tooLarge,
    staleTime: QUERY_STALE_TIMES.REALTIME,
    refetchOnWindowFocus: false,
    retry: false,
  });

  // Fetch text content from presigned URL
  const { data: textContent, isLoading } = useQuery({
    queryKey: ['attachment-text-content', entityType, entityId, itemId],
    queryFn: async () => {
      const response = await fetch(downloadDetails!.downloadUrl);
      if (!response.ok) {
        throw new Error(`Failed to fetch text content (${response.status})`);
      }
      return response.text();
    },
    enabled: Boolean(downloadDetails?.downloadUrl) && !tooLarge,
    staleTime: QUERY_STALE_TIMES.REALTIME,
    refetchOnWindowFocus: false,
    retry: false,
  });

  React.useEffect(() => {
    return () => {
      if (copyTimeoutRef.current !== null) {
        window.clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  if (item.upload_status !== 'COMPLETE' || !itemId) {
    return null;
  }

  if (tooLarge) {
    return (
      <AttachmentPreviewLimitNotice
        fileSizeBytes={item.file_size}
        limitBytes={limits.max_text_preview_size_bytes}
        attachmentTypeLabel="text attachment"
      />
    );
  }

  const markCopied = () => {
    if (copyTimeoutRef.current !== null) {
      window.clearTimeout(copyTimeoutRef.current);
    }
    setIsCopied(true);
    copyTimeoutRef.current = window.setTimeout(() => {
      setIsCopied(false);
      copyTimeoutRef.current = null;
    }, 2000);
  };

  const handleCopyText = async () => {
    if (!textContent) return;
    try {
      await navigator.clipboard.writeText(textContent);
      markCopied();
    } catch {
      console.error('Failed to copy text to clipboard');
    }
  };

  const handleDownload = async () => {
    if (!itemId) return;
    const details = await getAttachmentDownloadDetails(entityType, entityId, itemId as string, {
      download: true,
    });
    triggerBrowserDownload(details.downloadUrl, details.filename || filename);
  };

  if (isLoading && !textContent) {
    return <div className="h-[120px] w-full animate-pulse rounded-md bg-neutral-100" aria-hidden="true" />;
  }

  if (!textContent) {
    return null;
  }

  const totalLines = textContent.split('\n').length;
  const isTruncated = totalLines > SNIPPET_LINES;

  return (
    <>
      <button
        type="button"
        className="w-full overflow-hidden border border-neutral-border text-left transition hover:border-neutral-400"
        onClick={viewer.open}
      >
        <CodeBlock
          language={language}
          code={textContent}
          resolvedTheme={resolvedTheme}
          maxLines={SNIPPET_LINES}
          showLineNumbers
          className="pointer-events-none [&_button]:hidden [&_pre]:border-0 [&_pre]:!mb-0"
        />
        {isTruncated && (
          <div className="border-t border-neutral-border bg-neutral-100 px-3 py-1 text-center text-xs text-subtext-color">
            …{totalLines - SNIPPET_LINES} more lines — click to expand
          </div>
        )}
      </button>

      <FullscreenViewer
        open={viewer.isOpen}
        onOpenChange={viewer.setIsOpen}
        title={filename}
        description="Expanded text attachment viewer with zoom, copy, and download controls."
        textMode
        copyAction={{
          label: 'Copy Text',
          icon: isCopied ? <Check /> : <Copy />,
          copied: isCopied,
          onAction: handleCopyText,
        }}
        downloadAction={{
          label: 'Download',
          icon: <Download />,
          onAction: handleDownload,
        }}
      >
        <CodeBlock
          language={language}
          code={textContent}
          resolvedTheme={resolvedTheme}
          showLineNumbers
        />
      </FullscreenViewer>
    </>
  );
}
