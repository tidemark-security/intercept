import React, { useState } from "react";

import { Button } from "@/components/buttons/Button";
import { AlertsService } from "@/types/generated/services/AlertsService";
import { CasesService } from "@/types/generated/services/CasesService";
import { TasksService } from "@/types/generated/services/TasksService";
import type { AttachmentItem } from "@/types/generated/models/AttachmentItem";
import { useToast } from "@/contexts/ToastContext";

import { Download, Loader } from 'lucide-react';
interface DownloadButtonProps {
  item: AttachmentItem;
  entityId: number | null;
  entityType: 'alert' | 'case' | 'task';
}

export function DownloadButton({ item, entityId, entityType }: DownloadButtonProps) {
  const { showToast } = useToast();
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = async () => {
    if (!item.id || !entityId) return;

    setIsDownloading(true);
    try {
      // Use the appropriate service based on entity type
      let response;
      if (entityType === 'case') {
        response = await CasesService.generateDownloadUrlApiV1CasesCaseIdTimelineItemsItemIdDownloadUrlGet({
          caseId: entityId,
          itemId: item.id,
        });
      } else if (entityType === 'task') {
        response = await TasksService.generateDownloadUrlApiV1TasksTaskIdTimelineItemsItemIdDownloadUrlGet({
          taskId: entityId,
          itemId: item.id,
        });
      } else {
        response = await AlertsService.generateDownloadUrlApiV1AlertsAlertIdTimelineItemsItemIdDownloadUrlGet({
          alertId: entityId,
          itemId: item.id,
        });
      }

      const link = document.createElement("a");
      link.href = response.download_url;
      link.download = response.filename || item.file_name || "download";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      showToast("Download Started", `Downloading ${response.filename}`, "success");
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
