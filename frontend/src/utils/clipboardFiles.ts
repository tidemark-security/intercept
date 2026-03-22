/**
 * Clipboard file naming utilities.
 *
 * When pasting files from the clipboard they typically arrive as `image.png`
 * or with no name at all.  These helpers generate sequential names like
 * `clipboard-01.png`, `clipboard-02.pdf`, etc., so each pasted item gets a
 * recognisable, unique display name.
 */

const MIME_TO_EXT: Record<string, string> = {
  // Images
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/gif": ".gif",
  "image/webp": ".webp",
  "image/svg+xml": ".svg",
  "image/bmp": ".bmp",
  "image/tiff": ".tiff",
  // Documents
  "application/pdf": ".pdf",
  "application/msword": ".doc",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
  "application/vnd.ms-excel": ".xls",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
  "application/vnd.ms-powerpoint": ".ppt",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
  // Text
  "text/plain": ".txt",
  "text/html": ".html",
  "text/csv": ".csv",
  "text/markdown": ".md",
  // Data
  "application/json": ".json",
  "application/xml": ".xml",
  // Archives
  "application/zip": ".zip",
  "application/gzip": ".gz",
  "application/x-7z-compressed": ".7z",
  "application/x-tar": ".tar",
  // Forensics / network
  "application/vnd.tcpdump.pcap": ".pcap",
};

/**
 * Map a MIME type to a file extension.
 * Falls back to extracting the extension from the original filename,
 * or `.bin` if nothing is available.
 */
function mimeToExtension(mimeType: string, originalName?: string): string {
  const mapped = MIME_TO_EXT[mimeType];
  if (mapped) return mapped;

  // Try to extract extension from the original file name
  if (originalName) {
    const dotIndex = originalName.lastIndexOf(".");
    if (dotIndex > 0) return originalName.slice(dotIndex);
  }

  return ".bin";
}

/**
 * Check whether a file has a meaningful original name (i.e. not a generic
 * browser-assigned blob name like "image.png" or "Untitled").
 */
function hasRealName(file: File): boolean {
  const name = file.name;
  if (!name) return false;

  // Generic names browsers assign to pasted screenshots / blobs
  const generic = new Set([
    "image.png", "image.jpg", "image.jpeg", "image.gif", "image.webp",
    "image.bmp", "image.tiff", "image.svg",
    "blob", "file", "untitled",
  ]);
  return !generic.has(name.toLowerCase());
}

/**
 * Prepare a clipboard file for upload.
 *
 * If the file already has a meaningful name (e.g. a copied `.docx`), keep it.
 * Otherwise generate a sequential `clipboard-01.png` style name.
 *
 * @param file  The original clipboard file/blob.
 * @param index 1-based index used for the zero-padded suffix (01, 02, …).
 */
function generateClipboardFile(file: File, index: number): File {
  if (hasRealName(file)) return file;

  const ext = mimeToExtension(file.type, file.name);
  const name = `clipboard-${String(index).padStart(2, "0")}${ext}`;
  return new File([file], name, { type: file.type, lastModified: file.lastModified });
}

/**
 * Rename an array of clipboard files with sequential names.
 *
 * @param files      Files to rename.
 * @param startIndex 1-based starting index (default 1). Use a higher value
 *                   when appending to an existing list so numbering continues.
 */
export function renameClipboardFiles(files: File[], startIndex = 1): File[] {
  return files.map((f, i) => generateClipboardFile(f, startIndex + i));
}

/**
 * Extract `File` objects from a ClipboardEvent.
 *
 * Handles both the `clipboardData.files` FileList and the `DataTransferItemList`
 * which is needed in some browsers when pasting screenshots.
 */
export function extractClipboardFiles(event: ClipboardEvent): File[] {
  const dt = event.clipboardData;
  if (!dt) return [];

  const files: File[] = [];

  // Prefer DataTransferItemList – captures screenshots that only appear as items
  if (dt.items) {
    for (let i = 0; i < dt.items.length; i++) {
      const item = dt.items[i];
      if (item.kind === "file") {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
  }

  // Fallback: FileList (some browsers populate this instead of / in addition to items)
  if (files.length === 0 && dt.files.length > 0) {
    for (let i = 0; i < dt.files.length; i++) {
      files.push(dt.files[i]);
    }
  }

  return files;
}
