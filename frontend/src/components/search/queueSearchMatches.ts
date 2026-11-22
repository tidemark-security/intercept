import { createContext, useContext } from "react";

export const QueueSearchPatternContext = createContext<RegExp | null>(null);

const escapeRegex = (value: string) => value.replace(/[.*+?^{}$()|[\]\\]/g, "\\$&");

/** Keep the spelling from displayed text. Ignore search operators and negated terms. */
export function buildQueueSearchPattern(query: string): RegExp | null {
  if (!query) return null;
  const entityId = /^(ALT|CAS|TSK)-(\d{1,9})$/i.exec(query);
  if (entityId) return new RegExp("\\b" + entityId[1] + "-0*" + Number(entityId[2]) + "(?!\\d)", "gi");

  const terms = new Set<string>();
  for (const [, negate, phrase, word] of query.matchAll(/(-?)(?:"([^"]+)"|([^\s"]+))/g)) {
    if (negate || (!phrase && /^or$/i.test(word))) continue;
    const term = (phrase || word).replace(/^\*+|\*+$/g, "");
    if (term) terms.add(term);
  }
  const sorted = [...terms].sort((a, b) => b.length - a.length);
  return sorted.length ? new RegExp(sorted.map(escapeRegex).join("|"), "gi") : null;
}

export type SearchTextPart = { text: string; match: boolean };

export function splitQueueSearchText(text: string, pattern: RegExp | null): SearchTextPart[] | null {
  if (!pattern || !text) return null;
  const parts: SearchTextPart[] = [];
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (cursor < match.index) parts.push({ text: text.slice(cursor, match.index), match: false });
    parts.push({ text: match[0], match: true });
    cursor = match.index + match[0].length;
  }
  if (!parts.length) return null;
  if (cursor < text.length) parts.push({ text: text.slice(cursor), match: false });
  return parts;
}

export function useQueueSearchPattern() {
  return useContext(QueueSearchPatternContext);
}
