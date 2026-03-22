/**
 * Unit tests for formatters utility functions
 */

import { describe, it, expect } from 'vitest';
import { formatStatusLabel } from './formatters';
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

  it('converts CLOSED_TP to Closed Tp', () => {
    expect(formatStatusLabel('CLOSED_TP' as AlertStatus)).toBe('Closed Tp');
  });

  it('converts CLOSED_FP to Closed Fp', () => {
    expect(formatStatusLabel('CLOSED_FP' as AlertStatus)).toBe('Closed Fp');
  });

  it('converts CLOSED_BP to Closed Bp', () => {
    expect(formatStatusLabel('CLOSED_BP' as AlertStatus)).toBe('Closed Bp');
  });

  it('converts CLOSED_DUPLICATE to Closed Duplicate', () => {
    expect(formatStatusLabel('CLOSED_DUPLICATE' as AlertStatus)).toBe('Closed Duplicate');
  });

  it('converts CLOSED_UNRESOLVED to Closed Unresolved', () => {
    expect(formatStatusLabel('CLOSED_UNRESOLVED' as AlertStatus)).toBe('Closed Unresolved');
  });
});
