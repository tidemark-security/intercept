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

import { FileText, HardDrive, Link } from 'lucide-react';
/**
 * Check if item is an AttachmentItem
 */
export function isAttachmentItem(item: TimelineItem): item is AttachmentItem {
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
 * - Line1: File name (most important identifier)
 * - Line2: MIME type
 * - Line3: File size
 * - Line4: URL (if present)
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

  return {
    title: item.file_name ? `${item.file_name}` : 'Attachment',
    line1: item.file_name || 'Untitled File',
    line1Icon: <FileText />,
    line2: item.mime_type || undefined,
    line2Icon: item.mime_type ? <FileText /> : undefined,
    line3: sizeDisplay || undefined,
    line3Icon: sizeDisplay ? <HardDrive /> : undefined,
    line4: item.url || undefined,
    line4Icon: item.url ? <Link /> : undefined,
    baseIcon: IconComponent,
    system: 'default',
    size: options.size || 'large',
    actionButtons,
    _item: item,
  };
}
