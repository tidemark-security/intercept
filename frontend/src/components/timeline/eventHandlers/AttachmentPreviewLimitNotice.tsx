import React from 'react';
import { EyeOff } from 'lucide-react';

interface AttachmentPreviewLimitNoticeProps {
  fileSizeBytes?: number | null;
  limitBytes: number;
  attachmentTypeLabel: string;
  variant?: 'default' | 'tiny';
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
  variant = 'default',
}: AttachmentPreviewLimitNoticeProps) {
  const resolvedFileSize = fileSizeBytes ?? 0;
  const isTiny = variant === 'tiny';

  return (
    <div className={isTiny
      ? "flex min-h-10 w-full items-center gap-2 rounded border border-neutral-border bg-neutral-50 px-2 py-1.5 text-left"
      : "flex min-h-[120px] w-full items-center justify-center rounded-md border border-neutral-border bg-neutral-50 px-4 py-5 text-center"}
    >
      <div className={isTiny ? "flex min-w-0 items-center gap-2" : "flex flex-col items-center gap-2"}>
        <EyeOff className={isTiny ? "h-3.5 w-3.5 flex-none text-subtext-color" : "h-5 w-5 text-subtext-color"} />
        <p className={isTiny ? "truncate text-caption font-caption text-subtext-color" : "text-sm font-medium text-default-font"}>
          Preview unavailable for this {attachmentTypeLabel}.
        </p>
        {!isTiny ? (
          <p className="text-xs text-subtext-color">
            File size {formatFileSize(resolvedFileSize)} exceeds the preview limit of {formatFileSize(limitBytes)}. Use Download to open the full attachment.
          </p>
        ) : null}
      </div>
    </div>
  );
}
