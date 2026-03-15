import React, { useState } from "react";

import { Button } from "@/components/buttons/Button";
import type { AttachmentItem } from "@/types/generated/models/AttachmentItem";
import { useToast } from "@/contexts/ToastContext";

import { getAttachmentDownloadDetails, triggerBrowserDownload, type AttachmentEntityType } from './attachmentDownload';

import { Download, Loader } from 'lucide-react';
interface DownloadButtonProps {
  item: AttachmentItem;
  entityId: number | null;
  entityType: AttachmentEntityType;
}

export function DownloadButton({ item, entityId, entityType }: DownloadButtonProps) {
  const { showToast } = useToast();
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = async () => {
    if (!item.id || !entityId) return;

    setIsDownloading(true);
    try {
      const response = await getAttachmentDownloadDetails(entityType, entityId, item.id, {
        download: true,
      });

      triggerBrowserDownload(response.downloadUrl, response.filename || item.file_name || 'download');
    } catch (error) {
      console.error("Download failed:", error);
      showToast("Download Failed", "Failed to download file", "error");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <Button
      variant="brand-primary"
      size="small"
      icon={isDownloading ? <Loader className="animate-spin" /> : <Download />}
      onClick={handleDownload}
      disabled={isDownloading}
    >
    </Button>
  );
}
