/**
 * Add Attachment Form Component
 * 
 * Functional form for uploading multiple file attachments to timeline.
 * Features drag-and-drop upload, real file upload to MinIO via presigned URLs.
 * Displays upload progress and handles errors gracefully.
 * 
 * NOTE: When editing an attachment we only allow updating description, timestamp, and tags.
 * File contents must still be replaced by deleting the timeline item and re-uploading.
 */

import React, { useRef, useEffect, DragEvent, useState } from "react";

import { cn } from "@/utils/cn";
import { TextArea } from "@/components/forms/TextArea";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { useFileUpload } from "@/hooks/useFileUpload";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { useUpdateTimelineItem } from "@/hooks/useUpdateTimelineItem";
import { useToast } from "@/contexts/ToastContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import { renameClipboardFiles, extractClipboardFiles } from "@/utils/clipboardFiles";
import type { AttachmentItem } from "@/types/generated/models/AttachmentItem";

import { AlertTriangle, CheckCircle, Paperclip, Upload, X } from 'lucide-react';

function ImagePreview({ file }: { file: File }) {
  const [src, setSrc] = React.useState<string | null>(null);

  React.useEffect(() => {
    const url = URL.createObjectURL(file);
    setSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  if (!src) return null;

  return (
    <img
      src={src}
      alt={file.name}
      className="max-h-24 rounded-md border border-solid border-neutral-border object-contain"
    />
  );
}

export interface AddAttachmentFormProps {
  initialData?: AttachmentItem;
  /** Files injected from an external source (e.g. clipboard paste in the quick terminal) */
  pendingFiles?: File[];
  /** Callback to clear pending files after they have been consumed */
  onPendingFilesConsumed?: () => void;
}

interface FileWithStatus {
  file: File;
  status: 'pending' | 'uploading' | 'complete' | 'error';
  progress?: number;
  itemId?: string;
  error?: string;
}

export function AddAttachmentForm({ initialData, pendingFiles, onPendingFilesConsumed }: AddAttachmentFormProps) {
  const { alertId, caseId, taskId, editMode, onSuccess, onCancel } = useTimelineFormContext();
  const { showToast } = useToast();
  
  // Determine entity ID and type
  const entityId = alertId || caseId || taskId;
  const entityType: 'alert' | 'case' | 'task' = alertId ? 'alert' : caseId ? 'case' : 'task';
  
  const initialFormState = React.useMemo(() => {
    const safeTags = Array.isArray(initialData?.tags) ? [...(initialData?.tags ?? [])] : [];
    return {
      description: initialData?.description ?? "",
      timestamp: initialData?.timestamp ?? "",
      tags: safeTags,
      isDragging: false,
    };
  }, [initialData]);
  
  // Form state for metadata (description, tags, timestamp) - managed locally due to complex file upload logic
  const [formState, setFormState] = useState(initialFormState);
  
  // Files state with upload status tracking
  const [files, setFiles] = useState<FileWithStatus[]>([]);
  const [currentUploadIndex, setCurrentUploadIndex] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const updateAttachmentMutation = useUpdateTimelineItem(entityId, entityType, {
    onSuccess: () => {
      onSuccess?.(initialData?.id);
    },
    onError: (error) => {
      console.error("Failed to update attachment metadata:", error);
      showToast("Error", "Failed to update attachment metadata", "error");
    },
  });
  
  // File upload hook
  const { uploadFile, progress } = useFileUpload({
    alertId,
    caseId,
    taskId,
    onSuccess: (itemId) => {
      // Mark current file as complete
      if (currentUploadIndex !== null) {
        setFiles(prev => prev.map((f, i) => 
          i === currentUploadIndex 
            ? { ...f, status: 'complete', itemId, progress: 100 }
            : f
        ));
        
        // Start next upload or finish
        const nextIndex = currentUploadIndex + 1;
        if (nextIndex < files.length) {
          setCurrentUploadIndex(nextIndex);
        } else {
          // All files uploaded! Pass the last uploaded file's itemId for scroll-to
          setCurrentUploadIndex(null);
          setFiles([]);
          onSuccess?.(itemId);  // Pass last itemId for scroll-to
        }
      }
    },
    onError: (error) => {
      // Mark current file as error
      if (currentUploadIndex !== null) {
        setFiles(prev => prev.map((f, i) => 
          i === currentUploadIndex 
            ? { ...f, status: 'error', error: error.message }
            : f
        ));
        setCurrentUploadIndex(null);
      }
      showToast("Upload Failed", error.message, "error");
    },
  });

  
  // Update progress for currently uploading file
  React.useEffect(() => {
    if (currentUploadIndex !== null && progress) {
      setFiles(prev => prev.map((f, i) => 
        i === currentUploadIndex 
          ? { ...f, progress: progress.percentage }
          : f
      ));
    }
  }, [currentUploadIndex, progress]);

  // Start uploading when currentUploadIndex changes
  React.useEffect(() => {
    if (currentUploadIndex !== null && files[currentUploadIndex]) {
      const fileToUpload = files[currentUploadIndex];
      if (fileToUpload.status === 'pending') {
        setFiles(prev => prev.map((f, i) => 
          i === currentUploadIndex 
            ? { ...f, status: 'uploading' }
            : f
        ));
        uploadFile(fileToUpload.file);
      }
    }
  }, [currentUploadIndex, files, uploadFile]);

  // Track the last pendingFiles reference we consumed to prevent double-processing
  // (React strict mode re-runs mount effects before the parent's clearPendingFiles propagates)
  const consumedPendingRef = useRef<File[] | null>(null);

  // Consume pending files injected from the outside (e.g. paste in QuickTerminal)
  useEffect(() => {
    if (pendingFiles && pendingFiles.length > 0 && consumedPendingRef.current !== pendingFiles) {
      consumedPendingRef.current = pendingFiles;
      setFiles(prev => {
        const renamed = renameClipboardFiles(pendingFiles, prev.length + 1);
        return [...prev, ...renamed.map(file => ({
          file,
          status: 'pending' as const,
        }))];
      });
      onPendingFilesConsumed?.();
    }
  }, [pendingFiles, onPendingFilesConsumed]);

  // Listen for clipboard paste events on the document while this form is mounted
  useEffect(() => {
    if (editMode) return; // Don't handle paste in edit mode

    const handlePaste = (e: ClipboardEvent) => {
      // Skip if another handler (e.g. CommandInput) already processed this paste
      if (e.defaultPrevented) return;
      // Don't intercept if currently uploading
      if (currentUploadIndex !== null) return;

      const pastedFiles = extractClipboardFiles(e);
      if (pastedFiles.length === 0) return;

      e.preventDefault();

      // Use functional updater to get accurate file count for numbering
      setFiles(prev => {
        const renamed = renameClipboardFiles(pastedFiles, prev.length + 1);
        return [...prev, ...renamed.map(file => ({
          file,
          status: 'pending' as const,
        }))];
      });
    };

    document.addEventListener('paste', handlePaste);
    return () => document.removeEventListener('paste', handlePaste);
  }, [editMode, currentUploadIndex]);

  const handleClear = () => {
    setFormState(initialFormState);
    setFiles([]);
    setCurrentUploadIndex(null);
  };

  const handleSubmit = () => {
    if (editMode) {
      if (!initialData?.id) {
        showToast("Error", "Attachment is missing an identifier", "error");
        return;
      }

      updateAttachmentMutation.mutate({
        itemId: initialData.id,
        updates: {
          type: "attachment",
          description: formState.description || undefined,
          timestamp: formState.timestamp || initialData.timestamp || new Date().toISOString(),
          tags: formState.tags,
        },
      });
      return;
    }

    if (files.length === 0 || currentUploadIndex !== null) {
      return;
    }

    // Start uploading from first file
    setCurrentUploadIndex(0);
  };

  const handleFileSelect = (selectedFiles: FileList | null) => {
    if (!selectedFiles) return;
    
    const newFiles: FileWithStatus[] = Array.from(selectedFiles).map(file => ({
      file,
      status: 'pending',
    }));
    
    setFiles(prev => [...prev, ...newFiles]);
  };

  const handleRemoveFile = (index: number) => {
    // Don't allow removing files while uploading
    if (currentUploadIndex !== null) {
      return;
    }
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setFormState({ ...formState, isDragging: true });
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setFormState({ ...formState, isDragging: false });
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setFormState({ ...formState, isDragging: false });
    handleFileSelect(e.dataTransfer.files);
  };

  const isUploadingFiles = currentUploadIndex !== null;
  const submitLabel = editMode
    ? "Update Attachment"
    : isUploadingFiles
      ? `Uploading ${currentUploadIndex! + 1}/${files.length}...`
      : `Upload ${files.length} File${files.length !== 1 ? 's' : ''}`;
  const submitDisabled = editMode
    ? updateAttachmentMutation.isPending
    : files.length === 0 || isUploadingFiles;
  const isSubmitting = editMode ? updateAttachmentMutation.isPending : isUploadingFiles;

  return (
    <TimelineFormLayout
      icon={<Paperclip className="text-neutral-600" />}
      title={editMode ? "Edit Attachment" : "Upload Attachment"}
      editMode={editMode}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={submitLabel}
      submitDisabled={submitDisabled}
      isSubmitting={isSubmitting}
      useWell={true}
    >
      {!editMode && (
        <>
          {/* File Upload Area */}
          <div className="flex w-full flex-col items-start gap-2">
            <span className="text-caption-bold font-caption-bold text-default-font">
              File Upload
            </span>
            <div
              className={cn(
                "flex w-full items-center justify-center rounded-md border-2 border-dashed px-6 py-8 cursor-pointer transition-colors",
                formState.isDragging 
                  ? "border-brand-primary bg-brand-50" 
                  : "border-neutral-border bg-neutral-50 hover:border-neutral-400"
              )}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <div className="flex flex-col items-center gap-2 text-center">
                <Upload className="text-body font-body text-subtext-color" />
                <span className="text-body font-body text-default-font">
                  Drop files here or click to browse
                </span>
                <span className="text-caption font-caption text-subtext-color">
                  Supports all file types up to 50MB
                </span>
              </div>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => handleFileSelect(e.target.files)}
            />
          </div>

          {/* Selected Files List */}
          {files.length > 0 && (
            <div className="flex w-full flex-col items-start gap-2">
              <span className="text-caption-bold font-caption-bold text-default-font">
                Selected Files ({files.length})
              </span>
              <div className="flex w-full flex-col items-start gap-2 rounded-md border border-solid border-neutral-border bg-default-background p-3">
                {files.map((fileWithStatus, index) => (
                    <div 
                      key={index}
                      className="flex w-full flex-col gap-1 rounded px-2 py-1 hover:bg-neutral-50"
                    >
                      <div className="flex w-full items-center justify-between gap-2">
                        <div className="flex items-center gap-2 flex-1 min-w-0">
                          {fileWithStatus.status === 'complete' && (
                            <CheckCircle className="text-success-600 flex-shrink-0" />
                          )}
                          {fileWithStatus.status === 'error' && (
                            <AlertTriangle className="text-error-600 flex-shrink-0" />
                          )}
                          {(fileWithStatus.status === 'pending' || fileWithStatus.status === 'uploading') && (
                            <Paperclip className="text-neutral-500 flex-shrink-0" />
                          )}
                          <span className="text-body font-body text-default-font truncate">
                            {fileWithStatus.file.name}
                          </span>
                          <span className="text-caption font-caption text-subtext-color flex-shrink-0">
                            ({(fileWithStatus.file.size / 1024).toFixed(1)} KB)
                          </span>
                          {fileWithStatus.status === 'uploading' && fileWithStatus.progress !== undefined && (
                            <span className="text-caption font-caption text-brand-600 flex-shrink-0">
                              {fileWithStatus.progress}%
                            </span>
                          )}
                        </div>
                        {fileWithStatus.status === 'pending' && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRemoveFile(index);
                            }}
                            className="flex-shrink-0 p-1 hover:bg-neutral-100 rounded"
                          >
                            <X className="text-neutral-500 w-4 h-4" />
                          </button>
                        )}
                      </div>
                      {/* Progress bar for uploading file */}
                      {fileWithStatus.status === 'uploading' && fileWithStatus.progress !== undefined && (
                        <div className="w-full bg-neutral-100 rounded-full h-1.5">
                          <div 
                            className="bg-brand-600 h-1.5 rounded-full transition-all duration-300"
                            style={{ width: `${fileWithStatus.progress}%` }}
                          />
                        </div>
                      )}
                      {/* Error message */}
                      {fileWithStatus.status === 'error' && fileWithStatus.error && (
                        <span className="text-caption font-caption text-error-600">
                          Error: {fileWithStatus.error}
                        </span>
                      )}
                      {/* Image preview */}
                      {fileWithStatus.file.type.startsWith('image/') && (
                        <ImagePreview file={fileWithStatus.file} />
                      )}
                    </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {editMode && (
        <div className="flex w-full flex-col gap-2 rounded-md border border-dashed border-neutral-border bg-neutral-50 px-4 py-3">
          <span className="text-caption-bold font-caption-bold text-default-font">
            File Uploads Locked
          </span>
          <p className="text-caption font-caption text-subtext-color">
            File contents can’t be changed while editing an attachment. Delete the item and re-upload if you need to replace the files.
          </p>
        </div>
      )}

      <TextArea
        className="h-auto w-full flex-none"
        label="Description (optional)"
        helpText="Context about these attachments"
      >
        <TextArea.Input
          className="h-24 w-full flex-none"
          placeholder="Describe the attachments or their relevance..."
          value={formState.description}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => 
            setFormState({ ...formState, description: e.target.value })
          }
        />
      </TextArea>

      <DateTimeManager
        value={formState.timestamp}
        onChange={(timestamp) => setFormState({ ...formState, timestamp })}
        label="Timestamp"
        helpText="When these files were created or collected"
        showNowButton={true}
      />
      
      <TagsManager
        tags={formState.tags}
        onTagsChange={(tags) => setFormState({ ...formState, tags })}
        label="Tags"
        placeholder="Enter tags and press Enter"
      />
    </TimelineFormLayout>
  );
}
