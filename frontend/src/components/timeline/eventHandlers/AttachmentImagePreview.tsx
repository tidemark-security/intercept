import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, Copy, Download } from 'lucide-react';

import { FullscreenViewer } from '@/components/overlays/FullscreenViewer';
import { useToast } from '@/contexts/ToastContext';
import { QUERY_STALE_TIMES } from '@/config/queryConfig';
import { useFullscreenViewer } from '@/hooks/useFullscreenViewer';
import type { AttachmentItem } from '@/types/generated/models/AttachmentItem';

import { getAttachmentDownloadDetails, triggerBrowserDownload, type AttachmentEntityType } from './attachmentDownload';

interface AttachmentImagePreviewProps {
  item: AttachmentItem;
  entityId: number;
  entityType: AttachmentEntityType;
}

const isImageAttachment = (item: AttachmentItem): boolean => {
  return Boolean(item.mime_type?.startsWith('image/'));
};

export function AttachmentImagePreview({ item, entityId, entityType }: AttachmentImagePreviewProps) {
  const { showToast } = useToast();
  const viewer = useFullscreenViewer();
  const copyTimeoutRef = React.useRef<number | null>(null);
  const hasRetriedImageLoadRef = React.useRef(false);

  const [imageError, setImageError] = React.useState(false);
  const [naturalDimensions, setNaturalDimensions] = React.useState<{ width: number; height: number } | null>(null);
  const [isCopied, setIsCopied] = React.useState(false);

  const itemId = item.id;
  const filename = item.file_name || 'attachment';

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['attachment-download', entityType, entityId, itemId],
    queryFn: async () => {
      return getAttachmentDownloadDetails(entityType, entityId, itemId as string);
    },
    enabled: isImageAttachment(item) && item.upload_status === 'COMPLETE' && Boolean(itemId),
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

  if (!isImageAttachment(item) || item.upload_status !== 'COMPLETE' || !itemId) {
    return null;
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

  const handleImageLoad = (event: React.SyntheticEvent<HTMLImageElement>) => {
    const image = event.currentTarget;
    setNaturalDimensions({ width: image.naturalWidth, height: image.naturalHeight });
    setImageError(false);
  };

  const handleImageError = () => {
    if (!hasRetriedImageLoadRef.current) {
      hasRetriedImageLoadRef.current = true;
      void refetch();
      return;
    }

    setImageError(true);
  };

  const handleDownload = async () => {
    if (!itemId) {
      return;
    }

    const downloadDetails = await getAttachmentDownloadDetails(entityType, entityId, itemId as string, {
      download: true,
    });

    triggerBrowserDownload(downloadDetails.downloadUrl, downloadDetails.filename || filename);
  };

  const handleCopyImage = async () => {
    if (!data?.downloadUrl || !navigator.clipboard?.write || typeof ClipboardItem === 'undefined') {
      showToast('Copy Failed', 'Clipboard image copy is not supported in this browser.', 'error');
      return;
    }

    try {
      const response = await fetch(data.downloadUrl);
      if (!response.ok) {
        throw new Error('Failed to fetch image for clipboard copy.');
      }

      const sourceBlob = await response.blob();
      const objectUrl = URL.createObjectURL(sourceBlob);

      try {
        const image = await new Promise<HTMLImageElement>((resolve, reject) => {
          const nextImage = new window.Image();
          nextImage.onload = () => resolve(nextImage);
          nextImage.onerror = () => reject(new Error('Failed to decode image for clipboard copy.'));
          nextImage.src = objectUrl;
        });

        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, image.naturalWidth);
        canvas.height = Math.max(1, image.naturalHeight);

        const context = canvas.getContext('2d');
        if (!context) {
          throw new Error('Unable to prepare clipboard image.');
        }

        context.drawImage(image, 0, 0, image.naturalWidth, image.naturalHeight);

        const pngBlob = await new Promise<Blob>((resolve, reject) => {
          canvas.toBlob((blob) => {
            if (blob) {
              resolve(blob);
              return;
            }

            reject(new Error('Failed to encode clipboard image.'));
          }, 'image/png');
        });

        await navigator.clipboard.write([new ClipboardItem({ 'image/png': pngBlob })]);
        markCopied();
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
    } catch (error) {
      console.error('Failed to copy attachment image:', error);
      showToast('Copy Failed', 'Unable to copy the image to the clipboard.', 'error');
    }
  };

  if (isLoading && !data) {
    return <div className="h-[180px] w-full animate-pulse rounded-md bg-neutral-100" aria-hidden="true" />;
  }

  if (!data || imageError) {
    return null;
  }

  return (
    <>
      <button
        type="button"
        className="w-full overflow-hidden rounded-md border border-neutral-border bg-neutral-50 text-left transition hover:border-neutral-400"
        onClick={viewer.open}
      >
        <img
          src={data.downloadUrl}
          alt={filename}
          className="w-full object-contain"
          style={{ maxHeight: 250 }}
          onLoad={handleImageLoad}
          onError={handleImageError}
        />
      </button>

      <FullscreenViewer
        open={viewer.isOpen}
        onOpenChange={viewer.setIsOpen}
        title={filename}
        description="Expanded image attachment viewer with pan, zoom, copy, and download controls."
        contentDimensions={naturalDimensions}
        copyAction={{
          label: 'Copy Image',
          icon: isCopied ? <Check /> : <Copy />,
          copied: isCopied,
          onAction: handleCopyImage,
        }}
        downloadAction={{
          label: 'Download',
          icon: <Download />,
          onAction: handleDownload,
        }}
        contentClassName="[&_img]:max-w-none"
      >
        <img
          src={data.downloadUrl}
          alt={filename}
          className="block h-auto max-w-none"
          onLoad={handleImageLoad}
        />
      </FullscreenViewer>
    </>
  );
}