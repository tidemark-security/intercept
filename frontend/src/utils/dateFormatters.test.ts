/**
 * Tests for date formatting utilities
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  formatTimelineTimestamp,
  formatRelativeTime,
  formatAbsoluteTime,
} from './dateFormatters';

describe('dateFormatters', () => {
  beforeEach(() => {
    // Mock current time to 2024-11-08 12:00:00 UTC for consistent tests
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2024-11-08T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('formatTimelineTimestamp', () => {
    it('should format recent timestamps as relative time', () => {
      const timestamp = '2024-11-08T10:00:00Z'; // 2 hours ago
      const result = formatTimelineTimestamp(timestamp);
      expect(result).toContain('hour');
      expect(result).toContain('ago');
    });

    it('should format old timestamps as absolute time', () => {
      const timestamp = '2024-10-01T10:00:00Z'; // More than 7 days ago
      const result = formatTimelineTimestamp(timestamp);
      expect(result).toContain('Oct');
      expect(result).toContain('2024');
    });

    it('should handle null/undefined timestamps', () => {
      expect(formatTimelineTimestamp(null)).toBe('');
      expect(formatTimelineTimestamp(undefined)).toBe('');
    });

    it('should use custom relative threshold', () => {
      const timestamp = '2024-11-06T12:00:00Z'; // 2 days ago
      const result = formatTimelineTimestamp(timestamp, {
        relativeDaysThreshold: 1, // Only show relative for last day
      });
      expect(result).toContain('Nov');
    });

    it('should use custom absolute format', () => {
      const timestamp = '2024-10-01T10:00:00Z';
      const result = formatTimelineTimestamp(timestamp, {
        absoluteFormat: 'yyyy-MM-dd',
      });
      expect(result).toBe('2024-10-01');
    });

    it('should disable relative time', () => {
      const timestamp = '2024-11-08T10:00:00Z'; // 2 hours ago
      const result = formatTimelineTimestamp(timestamp, {
        useRelative: false,
      });
      expect(result).toContain('Nov');
      expect(result).not.toContain('ago');
    });
  });

  describe('formatRelativeTime', () => {
    it('should format as relative time', () => {
      const timestamp = '2024-11-08T10:00:00Z'; // 2 hours ago
      const result = formatRelativeTime(timestamp);
      expect(result).toContain('hour');
      expect(result).toContain('ago');
    });

    it('should handle Date objects', () => {
      const date = new Date('2024-11-08T10:00:00Z');
      const result = formatRelativeTime(date);
      expect(result).toContain('hour');
    });

    it('should handle null/undefined', () => {
      expect(formatRelativeTime(null)).toBe('');
      expect(formatRelativeTime(undefined)).toBe('');
    });
  });

  describe('formatAbsoluteTime', () => {
    it('should format as absolute time with default format', () => {
      const timestamp = '2024-11-08T10:30:00Z';
      const result = formatAbsoluteTime(timestamp);
      expect(result).toContain('Nov');
      expect(result).toContain('2024');
      expect(result).toMatch(/\d{1,2}:\d{2}/); // Contains time
    });

    it('should use custom format string', () => {
      const timestamp = '2024-11-08T10:30:00Z';
      const result = formatAbsoluteTime(timestamp, 'yyyy-MM-dd HH:mm');
      expect(result).toBe('2024-11-08 10:30');
    });

    it('should handle Date objects', () => {
      const date = new Date('2024-11-08T10:30:00Z');
      const result = formatAbsoluteTime(date, 'yyyy-MM-dd');
      expect(result).toBe('2024-11-08');
    });

    it('should handle null/undefined', () => {
      expect(formatAbsoluteTime(null)).toBe('');
      expect(formatAbsoluteTime(undefined)).toBe('');
    });
  });
});
