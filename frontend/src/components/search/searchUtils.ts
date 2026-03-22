/**
 * Search utilities - shared functions for search result rendering
 */

import type { SearchResultItem } from '@/types/generated/models/SearchResultItem';

export const MIN_SEARCH_QUERY_LENGTH = 2;

/**
 * Extended search result with optional metadata fields
 */
export interface ExtendedSearchResultItem extends SearchResultItem {
  priority?: string;
  status?: string;
  assignee?: string;
  updated_at?: string;
}

/**
 * Determine whether a search query is valid for execution
 */
export function isSearchQueryValid(query: string): boolean {
  const trimmed = query.trim();
  return trimmed === '*' || trimmed.length >= MIN_SEARCH_QUERY_LENGTH;
}

/**
 * Get the route path for a search result entity
 */
export function getEntityPath(item: SearchResultItem): string {
  let basePath: string;
  switch (item.entity_type) {
    case 'alert':
      basePath = `/alerts/${item.human_id}`;
      break;
    case 'case':
      basePath = `/cases/${item.human_id}`;
      break;
    case 'task':
      basePath = `/tasks/${item.human_id}`;
      break;
    default:
      basePath = '/';
  }

  if (item.timeline_item_id) {
    return `${basePath}?scrollTo=${item.timeline_item_id}`;
  }

  return basePath;
}

/**
 * Map priority string to Priority component prop
 */
export function mapPriority(priority?: string): "info" | "low" | "medium" | "high" | "critical" | "extreme" {
  switch (priority?.toLowerCase()) {
    case 'extreme': return 'extreme';
    case 'critical': return 'critical';
    case 'high': return 'high';
    case 'medium': return 'medium';
    case 'low': return 'low';
    default: return 'info';
  }
}

/**
 * Map status string to State component prop
 */
export function mapState(status?: string, entityType?: string): "new" | "in_progress" | "closed" | "escalated" | "tsk_todo" | "tsk_in_progress" | "tsk_done" {
  if (entityType === 'task') {
    switch (status?.toLowerCase()) {
      case 'todo': return 'tsk_todo';
      case 'in_progress': return 'tsk_in_progress';
      case 'done': return 'tsk_done';
      default: return 'tsk_todo';
    }
  }
  switch (status?.toLowerCase()) {
    case 'new': return 'new';
    case 'in_progress': return 'in_progress';
    case 'escalated': return 'escalated';
    case 'closed': return 'closed';
    default: return 'new';
  }
}

/**
 * Try to parse a snippet as a JSON timeline item
 * Returns the parsed object if valid, null otherwise
 */
export function tryParseTimelineItemJson(snippet: string): Record<string, unknown> | null {
  const trimmed = snippet.trim();
  if (!trimmed.startsWith('{') || !trimmed.includes('"type"')) {
    return null;
  }
  
  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && typeof parsed === 'object' && typeof parsed.type === 'string') {
      return parsed;
    }
  } catch {
    // Try to extract fields from truncated JSON
    const typeMatch = trimmed.match(/"type"\s*:\s*"([^"]+)"/);
    if (typeMatch) {
      const extractField = (field: string): string | null => {
        const regex = new RegExp(`"${field}"\\s*:\\s*"([^"]*)"`, 'i');
        const match = trimmed.match(regex);
        return match ? match[1] : null;
      };
      
      const extractArrayField = (field: string): string[] | null => {
        const regex = new RegExp(`"${field}"\\s*:\\s*\\[([^\\]]*)]`, 'i');
        const match = trimmed.match(regex);
        if (match) {
          try {
            return JSON.parse(`[${match[1]}]`);
          } catch {
            return null;
          }
        }
        return null;
      };
      
      return {
        type: typeMatch[1],
        id: extractField('id'),
        title: extractField('title'),
        description: extractField('description'),
        tags: extractArrayField('tags'),
        process_name: extractField('process_name'),
        command_line: extractField('command_line'),
        destination_ip: extractField('destination_ip'),
        source_ip: extractField('source_ip'),
        observable_value: extractField('observable_value'),
        observable_type: extractField('observable_type'),
        hostname: extractField('hostname'),
        mitre_id: extractField('mitre_id'),
        file_name: extractField('file_name'),
        url: extractField('url'),
        subject: extractField('subject'),
        registry_key: extractField('registry_key'),
        name: extractField('name'),
      };
    }
  }
  
  return null;
}
