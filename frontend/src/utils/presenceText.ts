export type PresenceEntityType = 'alert' | 'case' | 'task';

function formatNameList(names: string[]): string {
  if (names.length === 1) return names[0];
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  if (names.length === 3) return `${names[0]}, ${names[1]}, and ${names[2]}`;
  return `${names[0]}, ${names[1]}, and ${names.length - 2} others`;
}

export function formatPresenceText(
  viewers: string[],
  entityType: PresenceEntityType,
  currentUser?: string | null,
): string | null {
  const currentUsername = currentUser?.toLowerCase() ?? null;
  const otherViewers = Array.from(new Set(viewers))
    .filter((viewer) => viewer && viewer.toLowerCase() !== currentUsername)
    .sort((first, second) => first.localeCompare(second));

  if (otherViewers.length === 0) return null;

  const verb = otherViewers.length === 1 ? 'is' : 'are';
  return `${formatNameList(otherViewers)} ${verb} viewing this ${entityType}`;
}