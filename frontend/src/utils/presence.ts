export function getOtherViewers(
  viewers: readonly string[],
  currentUser?: string | null,
): string[] {
  const currentUsername = currentUser?.toLowerCase() ?? null;
  return [...new Set(viewers)]
    .filter((viewer) => viewer && viewer.toLowerCase() !== currentUsername)
    .sort((first, second) => first.localeCompare(second));
}

export function getViewerInitials(viewer: string): string {
  const accountName = viewer.split('@', 1)[0];
  const [firstName = '', ...remainingNames] = accountName.match(/[\p{L}\p{N}]+/gu) ?? [];
  const lastName = remainingNames[remainingNames.length - 1] ?? '';
  const [firstInitial = ''] = firstName;
  const [lastInitial = ''] = lastName;
  return `${firstInitial}${lastInitial}`.toLocaleUpperCase() || '?';
}
