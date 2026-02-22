/**
 * File Upload Hook
 * 
 * Custom hook for handling file uploads to MinIO object storage via presigned URLs.
 * Implements the complete upload flow:
 * 1. Request presigned upload URL from backend
 * 2. Upload file directly to storage
 * 3. Confirm upload completion with backend
 * 
 * Features:
 * - Progress tracking
 * - Error handling with retry capability
 * - Automatic status updates
 * - File validation (size, type)
 */

import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import { CasesService } from '@/types/generated/services/CasesService';
import type { PresignedUploadRequest, PresignedUploadResponse, UploadStatus } from '@/types/generated';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import { queryKeys } from './queryKeys';

export interface FileUploadProgress {
  /** Upload progress percentage (0-100) */
  percentage: number;
  /** Bytes uploaded */
  loaded: number;
  /** Total bytes */
  total: number;
  /** Upload speed in bytes per second */
  speed?: number;
}

export interface FileUploadState {
  /** Current upload progress */
  progress: FileUploadProgress | null;
  /** Whether upload is in progress */
  isUploading: boolean;
  /** Error if upload failed */
  error: Error | null;
  /** Timeline item ID created for this upload */
  itemId: string | null;
}

interface UseFileUploadOptions {
  /** Alert ID to upload to (optional if caseId is provided) */
  alertId?: number;
  /** Case ID to upload to (optional if alertId is provided) */
  caseId?: number;
  /** Callback when upload succeeds */
  onSuccess?: (itemId: string) => void;
  /** Callback when upload fails */
  onError?: (error: Error) => void;
  /** Maximum file size in MB (default: 50) */
  maxSizeMB?: number;
  /** Allowed MIME types (default: from backend config) */
  allowedTypes?: string[];
}

/**
 * Hook for uploading files to alert or case timeline
 */
export function useFileUpload({
  alertId,
  caseId,
  onSuccess,
  onError,
  maxSizeMB = 50,
  allowedTypes,
}: UseFileUploadOptions) {
  const queryClient = useQueryClient();
  const [uploadState, setUploadState] = useState<FileUploadState>({
    progress: null,
    isUploading: false,
    error: null,
    itemId: null,
  });

  // Mutation to get presigned upload URL
  const getUploadUrlMutation = useMutation({
    mutationFn: async (request: PresignedUploadRequest) => {
      if (alertId) {
        return AlertsService.generateUploadUrlApiV1AlertsAlertIdTimelineAttachmentsUploadUrlPost({
          alertId,
          requestBody: request,
        });
      } else if (caseId) {
        return CasesService.generateUploadUrlApiV1CasesCaseIdTimelineAttachmentsUploadUrlPost({
          caseId,
          requestBody: request,
        });
      }
      throw new Error('Either alertId or caseId must be provided');
    },
  });

  // Mutation to update upload status
  const updateStatusMutation = useMutation({
    mutationFn: async ({ itemId, status, fileHash }: { 
      itemId: string; 
      status: UploadStatus;
      fileHash?: string;
    }) => {
      if (alertId) {
        return AlertsService.updateAttachmentStatusApiV1AlertsAlertIdTimelineItemsItemIdStatusPatch({
          alertId,
          itemId,
          requestBody: { status, file_hash: fileHash },
        });
      } else if (caseId) {
        return CasesService.updateAttachmentStatusApiV1CasesCaseIdTimelineItemsItemIdStatusPatch({
          caseId,
          itemId,
          requestBody: { status, file_hash: fileHash },
        });
      }
      throw new Error('Either alertId or caseId must be provided');
    },
    // Cache update is handled manually in the upload flow to ensure synchronous update
  });

  /**
   * Validate file before upload
   */
  const validateFile = useCallback((file: File): string | null => {
    // Check file size
    const maxSizeBytes = maxSizeMB * 1024 * 1024;
    if (file.size > maxSizeBytes) {
      return `File size ${(file.size / 1024 / 1024).toFixed(1)}MB exceeds limit of ${maxSizeMB}MB`;
    }

    // Check file type if allowedTypes is specified
    if (allowedTypes && allowedTypes.length > 0) {
      if (!allowedTypes.includes(file.type)) {
        return `File type ${file.type || 'unknown'} is not allowed`;
      }
    }

    return null;
  }, [maxSizeMB, allowedTypes]);

  /**
   * Calculate SHA256 hash of file
   */
  const calculateFileHash = async (file: File): Promise<string> => {
    const buffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    return hashHex;
  };

  /**
   * Upload file directly to storage using presigned URL
   */
  const uploadToStorage = async (
    file: File,
    uploadUrl: string,
    onProgress?: (progress: FileUploadProgress) => void
  ): Promise<void> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const startTime = Date.now();
      let lastLoaded = 0;
      let lastTime = startTime;

      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          const now = Date.now();
          const timeDiff = (now - lastTime) / 1000; // seconds
          const loadedDiff = event.loaded - lastLoaded;
          const speed = timeDiff > 0 ? loadedDiff / timeDiff : 0;

          const progress: FileUploadProgress = {
            percentage: Math.round((event.loaded / event.total) * 100),
            loaded: event.loaded,
            total: event.total,
            speed,
          };

          lastLoaded = event.loaded;
          lastTime = now;

          onProgress?.(progress);
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve();
        } else {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'));
      });

      xhr.addEventListener('abort', () => {
        reject(new Error('Upload aborted'));
      });

      xhr.open('PUT', uploadUrl);
      xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
      xhr.send(file);
    });
  };

  /**
   * Main upload function
   */
  const uploadFile = useCallback(async (file: File) => {
    let currentItemId: string | null = null;

    // Reset state
    setUploadState({
      progress: null,
      isUploading: true,
      error: null,
      itemId: null,
    });

    try {
      // Validate file
      const validationError = validateFile(file);
      if (validationError) {
        throw new Error(validationError);
      }

      // Step 1: Get presigned upload URL
      const uploadResponse = await getUploadUrlMutation.mutateAsync({
        filename: file.name,
        file_size: file.size,
        mime_type: file.type || undefined,
      });

      currentItemId = uploadResponse.item_id;

      setUploadState(prev => ({
        ...prev,
        itemId: uploadResponse.item_id,
      }));

      // Step 2: Upload file to storage
      await uploadToStorage(file, uploadResponse.upload_url, (progress) => {
        setUploadState(prev => ({
          ...prev,
          progress,
        }));
      });

      // Step 3: Calculate file hash (optional but recommended)
      let fileHash: string | undefined;
      try {
        fileHash = await calculateFileHash(file);
      } catch (err) {
        console.warn('Failed to calculate file hash:', err);
      }

      // Step 4: Confirm upload completion
      const updatedAlert = await updateStatusMutation.mutateAsync({
        itemId: uploadResponse.item_id,
        status: 'COMPLETE' as UploadStatus,
        fileHash,
      });

      // Ensure cache is updated immediately with the correct query key
      if (alertId) {
        queryClient.setQueryData(queryKeys.alert.detailBase(alertId), updatedAlert);
      } else if (caseId) {
        // Use partial key matching for cases (they may have options like includeLinkedTimelines)
        queryClient.setQueriesData({ queryKey: queryKeys.case.detailBase(caseId), exact: false }, updatedAlert);
      }

      // Success!
      setUploadState({
        progress: { percentage: 100, loaded: file.size, total: file.size },
        isUploading: false,
        error: null,
        itemId: uploadResponse.item_id,
      });

      onSuccess?.(uploadResponse.item_id);

    } catch (error) {
      const err = error instanceof Error ? error : new Error('Upload failed');
      
      setUploadState(prev => ({
        ...prev,
        isUploading: false,
        error: err,
      }));

      // If we have an item ID, mark it as failed
      if (currentItemId) {
        try {
          await updateStatusMutation.mutateAsync({
            itemId: currentItemId,
            status: 'FAILED' as UploadStatus,
          });
        } catch (statusError) {
          console.error('Failed to update status to failed:', statusError);
        }
      }

      onError?.(err);
    }
  }, [
    alertId,
    caseId,
    validateFile,
    getUploadUrlMutation,
    updateStatusMutation,
    onSuccess,
    onError,
    queryClient,
  ]);

  /**
   * Reset upload state
   */
  const reset = useCallback(() => {
    setUploadState({
      progress: null,
      isUploading: false,
      error: null,
      itemId: null,
    });
  }, []);

  return {
    uploadFile,
    reset,
    ...uploadState,
  };
}
