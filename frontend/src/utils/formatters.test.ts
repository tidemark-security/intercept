/**
 * Unit tests for formatters utility functions
 */

import { describe, it, expect } from 'vitest';
import { formatStatusLabel } from './formatters';
import {
  ALERT_STATUS_OPTIONS,
  CASE_STATUS_OPTIONS,
  TASK_STATUS_OPTIONS,
  formatCaseStatusLabel,
  formatTaskStatusLabel,
} from './statusLabels';
import type { AlertStatus } from '../types/generated/models/AlertStatus';

describe('formatStatusLabel', () => {
  it('converts NEW to New', () => {
    expect(formatStatusLabel('NEW' as AlertStatus)).toBe('New');
  });

  it('converts IN_PROGRESS to In Progress', () => {
    expect(formatStatusLabel('IN_PROGRESS' as AlertStatus)).toBe('In Progress');
  });

  it('converts ESCALATED to Escalated', () => {
    expect(formatStatusLabel('ESCALATED' as AlertStatus)).toBe('Escalated');
  });

  it('converts CLOSED_TP to Closed (True Positive)', () => {
    expect(formatStatusLabel('CLOSED_TP' as AlertStatus)).toBe('Closed (True Positive)');
  });

  it('converts CLOSED_FP to Closed (False Positive)', () => {
    expect(formatStatusLabel('CLOSED_FP' as AlertStatus)).toBe('Closed (False Positive)');
  });

  it('converts CLOSED_BP to Closed (Benign Positive)', () => {
    expect(formatStatusLabel('CLOSED_BP' as AlertStatus)).toBe('Closed (Benign Positive)');
  });

  it('converts CLOSED_DUPLICATE to Closed (Duplicate)', () => {
    expect(formatStatusLabel('CLOSED_DUPLICATE' as AlertStatus)).toBe('Closed (Duplicate)');
  });

  it('converts CLOSED_UNRESOLVED to Closed (Unresolved)', () => {
    expect(formatStatusLabel('CLOSED_UNRESOLVED' as AlertStatus)).toBe('Closed (Unresolved)');
  });

  it('exposes canonical alert status options', () => {
    expect(ALERT_STATUS_OPTIONS).toEqual([
      { value: 'NEW', label: 'New' },
      { value: 'IN_PROGRESS', label: 'In Progress' },
      { value: 'ESCALATED', label: 'Escalated' },
      { value: 'CLOSED_TP', label: 'Closed (True Positive)' },
      { value: 'CLOSED_BP', label: 'Closed (Benign Positive)' },
      { value: 'CLOSED_FP', label: 'Closed (False Positive)' },
      { value: 'CLOSED_UNRESOLVED', label: 'Closed (Unresolved)' },
      { value: 'CLOSED_DUPLICATE', label: 'Closed (Duplicate)' },
    ]);
  });

  it('formats case statuses', () => {
    expect(formatCaseStatusLabel('NEW')).toBe('New');
    expect(formatCaseStatusLabel('IN_PROGRESS')).toBe('In Progress');
    expect(formatCaseStatusLabel('CLOSED')).toBe('Closed');
    expect(CASE_STATUS_OPTIONS).toEqual([
      { value: 'NEW', label: 'New' },
      { value: 'IN_PROGRESS', label: 'In Progress' },
      { value: 'CLOSED', label: 'Closed' },
    ]);
  });

  it('formats task statuses', () => {
    expect(formatTaskStatusLabel('TODO')).toBe('To Do');
    expect(formatTaskStatusLabel('IN_PROGRESS')).toBe('In Progress');
    expect(formatTaskStatusLabel('DONE')).toBe('Done');
    expect(TASK_STATUS_OPTIONS).toEqual([
      { value: 'TODO', label: 'To Do' },
      { value: 'IN_PROGRESS', label: 'In Progress' },
      { value: 'DONE', label: 'Done' },
    ]);
  });
});
