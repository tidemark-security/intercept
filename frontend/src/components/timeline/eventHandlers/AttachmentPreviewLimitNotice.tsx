import React from 'react';
import { EyeOff } from 'lucide-react';

interface AttachmentPreviewLimitNoticeProps {
  fileSizeBytes?: number | null;
  limitBytes: number;
  attachmentTypeLabel: string;
}

function formatFileSize(bytes: number): string {
  if (bytes <= 0) {
    return '0 B';
  }

  const sizes = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    sizes.length - 1,
  );
  const size = bytes / Math.pow(1024, index);

  return `${size.toFixed(index === 0 ? 0 : 1)} ${sizes[index]}`;
}

export function AttachmentPreviewLimitNotice({
  fileSizeBytes,
  limitBytes,
  attachmentTypeLabel,
}: AttachmentPreviewLimitNoticeProps) {
  const resolvedFileSize = fileSizeBytes ?? 0;

  return (
    <div className="flex min-h-[120px] w-full items-center justify-center rounded-md border border-neutral-border bg-neutral-50 px-4 py-5 text-center">
      <div className="flex flex-col items-center gap-2">
        <EyeOff className="h-5 w-5 text-subtext-color" />
        <p className="text-sm font-medium text-default-font">
          Preview unavailable for this {attachmentTypeLabel}.
        </p>
        <p className="text-xs text-subtext-color">
          File size {formatFileSize(resolvedFileSize)} exceeds the preview limit of {formatFileSize(limitBytes)}. Use Download to open the full attachment.
        </p>
      </div>
    </div>
  );
}