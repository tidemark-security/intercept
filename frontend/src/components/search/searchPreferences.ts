import { formatForBackend, parseRelativeTime } from '@/utils/dateFilters';
import type { DateRangeValue } from '@/components/forms/DateRangePicker';
import type { EntityType } from '@/types/generated/models/EntityType';

const FILTER_STORAGE_KEY = 'globalSearch.entityFilters';
const DATE_RANGE_STORAGE_KEY = 'globalSearch.dateRange';
const DEFAULT_DATE_PRESET = '-30d';

const DEFAULT_FILTERS: Record<EntityType, boolean> = {
  alert: true,
  case: true,
  task: true,
};

function computeDateRangeFromPreset(preset: string): DateRangeValue {
  const range = parseRelativeTime(preset);
  if (range) {
    return {
      start: formatForBackend(range.start),
      end: formatForBackend(range.end),
      preset,
    };
  }

  return { start: '', end: '', preset };
}

function loadFilterPreferences(): Record<EntityType, boolean> {
  try {
    const stored = sessionStorage.getItem(FILTER_STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {
    // Ignore parse errors and use defaults
  }

  return { ...DEFAULT_FILTERS };
}

function saveFilterPreferences(filters: Record<EntityType, boolean>): void {
  try {
    sessionStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filters));
  } catch {
    // Ignore storage errors
  }
}

export function loadSelectedEntityTypePreference(): EntityType | 'all' {
  const prefs = loadFilterPreferences();

  if (prefs.alert && prefs.case && prefs.task) return 'all';
  if (prefs.alert) return 'alert';
  if (prefs.case) return 'case';
  if (prefs.task) return 'task';
  return 'all';
}

export function saveSelectedEntityTypePreference(value: EntityType | 'all'): void {
  const filters: Record<EntityType, boolean> = {
    alert: value === 'all' || value === 'alert',
    case: value === 'all' || value === 'case',
    task: value === 'all' || value === 'task',
  };
  saveFilterPreferences(filters);
}

export function loadDateRangePreference(): DateRangeValue | null {
  try {
    const stored = sessionStorage.getItem(DATE_RANGE_STORAGE_KEY);
    if (stored === 'null') {
      return null;
    }

    if (stored) {
      const parsed = JSON.parse(stored);
      if (parsed.preset && parsed.preset !== 'custom' && (!parsed.start || !parsed.end)) {
        return computeDateRangeFromPreset(parsed.preset);
      }
      return parsed;
    }
  } catch {
    // Ignore parse errors and use defaults
  }

  return computeDateRangeFromPreset(DEFAULT_DATE_PRESET);
}

export function saveDateRangePreference(value: DateRangeValue | null): void {
  try {
    if (value === null) {
      sessionStorage.setItem(DATE_RANGE_STORAGE_KEY, 'null');
      return;
    }

    sessionStorage.setItem(DATE_RANGE_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Ignore storage errors
  }
}
