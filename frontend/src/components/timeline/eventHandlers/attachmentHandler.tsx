/**
 * Attachment Item Handler
 * 
 * Handler for AttachmentItem timeline items.
 * Attachments display file information with download button.
 */
import React from 'react';
import type { TimelineItem } from '@/types/timeline';
import type { AttachmentItem } from '@/types/generated/models/AttachmentItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';
import { DownloadButton } from './AttachmentDownloadButton';
import { AttachmentImagePreview } from './AttachmentImagePreview';
import { AttachmentTextPreview } from './AttachmentTextPreview';
import { isTextAttachment, isImageAttachment } from '@/utils/fileLanguage';

import { FileText, HardDrive, Link } from 'lucide-react';
/**
 * Check if item is an AttachmentItem
 */
export function isAttachmentItem(item: TimelineItem): item is TimelineItem & AttachmentItem {
  return item.type === 'attachment';
}

/**
 * Format file size for display
 */
function formatFileSize(bytes: number | undefined | null): string | undefined {
  if (bytes === undefined || bytes === null) return undefined;
  
  const sizes = ['B', 'KB', 'MB', 'GB'];
  if (bytes === 0) return '0 B';
  
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const size = bytes / Math.pow(1024, i);
  
  return `${size.toFixed(2)} ${sizes[i]}`;
}

/**
 * Handle AttachmentItem timeline items.
 * 
 * Field mapping:
 * - Title: File name (most important identifier)
 * - Line1: MIME type
 * - Line2: File size
 * - Line3: URL (if present)
 * - Icon: FeatherPaperclip
 * - Color: default (attachments are neutral evidence)
 */
export function handleAttachmentItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isAttachmentItem(item)) {
    throw new Error('Item is not an AttachmentItem');
  }

  const Icon = getTimelineIcon('attachment');
  const sizeDisplay = formatFileSize(item.file_size);
  const IconComponent = Icon ? <Icon /> : undefined;
  const isSuperCompact = options.variant === 'super-compact';

  // Add download button if upload is complete and we have alertId and entityType
  let actionButtons = options.actionButtons;
  if (item.upload_status === 'COMPLETE' && options.alertId && options.entityType) {
    const downloadButton = <DownloadButton item={item} entityId={options.alertId} entityType={options.entityType} />;
    actionButtons = actionButtons ? (
      <>
        {actionButtons}
        {downloadButton}
      </>
    ) : downloadButton;
  }

  let children: React.ReactNode | undefined;
  if (item.upload_status === 'COMPLETE' && options.alertId && options.entityType) {
    if (isImageAttachment(item)) {
      children = <AttachmentImagePreview item={item} entityId={options.alertId} entityType={options.entityType} variant={isSuperCompact ? 'tiny' : 'default'} />;
    } else if (isTextAttachment(item)) {
      children = <AttachmentTextPreview item={item} entityId={options.alertId} entityType={options.entityType} variant={isSuperCompact ? 'tiny' : 'default'} />;
    }
  }

  if (isSuperCompact) {
    return {
      title: item.file_name ? `${item.file_name}` : 'Attachment',
      line1: sizeDisplay || item.mime_type || item.upload_status || undefined,
      line1Icon: sizeDisplay ? <HardDrive /> : item.mime_type ? <FileText /> : undefined,
      baseIcon: IconComponent,
      system: 'default',
      size: 'small',
      className: '!min-h-0 !w-full !max-w-none gap-2 px-3 py-2',
      children,
      _item: item,
    };
  }

  return {
    title: item.file_name ? `${item.file_name}` : 'Attachment',
    line1: item.mime_type || undefined,
    line1Icon: item.mime_type ? <FileText /> : undefined,
    line2: sizeDisplay || undefined,
    line2Icon: sizeDisplay ? <HardDrive /> : undefined,
    line3: item.url || undefined,
    line3Icon: item.url ? <Link /> : undefined,
    baseIcon: IconComponent,
    system: 'default',
    size: options.size || 'large',
    actionButtons,
    children,
    _item: item,
  };
}
