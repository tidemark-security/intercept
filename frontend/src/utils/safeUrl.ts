const ALLOWED_URL_SCHEMES = new Set(['http:', 'https:', 'mailto:', 'tel:']);

export function isSafeUrl(value: string | null | undefined): value is string {
  if (!value) {
    return false;
  }
  try {
    const parsed = new URL(value);
    return ALLOWED_URL_SCHEMES.has(parsed.protocol.toLowerCase());
  } catch {
    return false;
  }
}

export function toSafeHref(value: string | null | undefined): string | undefined {
  return isSafeUrl(value) ? value : undefined;
}
