import type { AttachmentItem } from '@/types/generated/models/AttachmentItem';

const EXTENSION_TO_LANGUAGE: Record<string, string> = {
  // Scripting / programming
  '.ps1': 'powershell',
  '.psm1': 'powershell',
  '.psd1': 'powershell',
  '.py': 'python',
  '.js': 'javascript',
  '.mjs': 'javascript',
  '.cjs': 'javascript',
  '.ts': 'typescript',
  '.tsx': 'tsx',
  '.jsx': 'jsx',
  '.rb': 'ruby',
  '.go': 'go',
  '.rs': 'rust',
  '.c': 'c',
  '.cpp': 'cpp',
  '.h': 'c',
  '.hpp': 'cpp',
  '.cs': 'csharp',
  '.java': 'java',
  '.php': 'php',
  '.lua': 'lua',
  '.pl': 'perl',
  '.r': 'r',
  '.swift': 'swift',
  '.kt': 'kotlin',

  // Shell
  '.sh': 'bash',
  '.bash': 'bash',
  '.zsh': 'bash',
  '.bat': 'batch',
  '.cmd': 'batch',

  // Markup & data
  '.html': 'html',
  '.htm': 'html',
  '.xml': 'xml',
  '.svg': 'xml',
  '.json': 'json',
  '.yaml': 'yaml',
  '.yml': 'yaml',
  '.toml': 'toml',
  '.ini': 'ini',
  '.csv': 'csv',
  '.md': 'markdown',
  '.markdown': 'markdown',

  // Style
  '.css': 'css',
  '.scss': 'scss',
  '.less': 'less',

  // Database
  '.sql': 'sql',

  // Config / infra
  '.dockerfile': 'docker',
  '.tf': 'hcl',
  '.hcl': 'hcl',
  '.conf': 'nginx',
  '.nginx': 'nginx',

  // Log / plain text
  '.txt': 'text',
  '.log': 'text',
  '.env': 'bash',
};

/** Set of extensions we know to be text-previewable */
const TEXT_EXTENSIONS = new Set(Object.keys(EXTENSION_TO_LANGUAGE));

/** MIME types that are always text-previewable */
const TEXT_MIME_PREFIXES = ['text/'];
const TEXT_MIME_EXACT = new Set([
  'application/json',
  'application/xml',
  'application/javascript',
  'application/x-sh',
  'application/x-yaml',
]);

function getExtension(filename: string): string {
  const dot = filename.lastIndexOf('.');
  if (dot === -1) return '';
  return filename.slice(dot).toLowerCase();
}

/**
 * Map a filename to a Prism language identifier for syntax highlighting.
 */
export function getLanguageFromFilename(filename: string): string {
  const ext = getExtension(filename);
  return EXTENSION_TO_LANGUAGE[ext] || 'text';
}

/**
 * Check if an attachment item is an image based on its MIME type.
 */
export function isImageAttachment(item: AttachmentItem): boolean {
  return Boolean(item.mime_type?.startsWith('image/'));
}

/**
 * Determine if an attachment item should be previewed as text content.
 * Checks MIME type first, then falls back to file extension for files
 * served as application/octet-stream.
 */
export function isTextAttachment(item: AttachmentItem): boolean {
  const mime = item.mime_type || '';

  // Explicit text MIME types
  if (TEXT_MIME_PREFIXES.some((prefix) => mime.startsWith(prefix))) {
    return true;
  }

  if (TEXT_MIME_EXACT.has(mime)) {
    return true;
  }

  // Fall back to extension check for generic MIME types
  if (mime === 'application/octet-stream' || mime === '') {
    const filename = item.file_name || '';
    return TEXT_EXTENSIONS.has(getExtension(filename));
  }

  return false;
}
