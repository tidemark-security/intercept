import { describe, expect, it } from 'vitest';

import {
  VISUAL_FILTER_DEFAULTS,
  buildVisualFilterCss,
  getVisualFilterLimits,
  normalizeVisualFilterPreference,
} from './visualFilterPreference';

describe('visualFilterPreference', () => {
  it('normalizes out-of-range values', () => {
    expect(
      normalizeVisualFilterPreference({
        hue: 999,
        brightness: 10,
        contrast: 200,
        grayscale: -1,
        saturation: 250,
      }),
    ).toEqual({
      hue: 360,
      brightness: 50,
      contrast: 150,
      grayscale: 0,
      saturation: 200,
    });
  });

  it('uses defaults when payload is invalid', () => {
    expect(normalizeVisualFilterPreference(undefined)).toEqual(VISUAL_FILTER_DEFAULTS);
    expect(
      normalizeVisualFilterPreference({
        hue: Number.NaN,
        brightness: Number.NaN,
        contrast: Number.NaN,
        grayscale: Number.NaN,
        saturation: Number.NaN,
      }),
    ).toEqual(VISUAL_FILTER_DEFAULTS);
  });

  it('builds expected CSS filter string', () => {
    expect(
      buildVisualFilterCss({
        hue: 135,
        brightness: 110,
        contrast: 95,
        grayscale: 12,
        saturation: 150,
      }),
    ).toBe('hue-rotate(135deg) brightness(110%) contrast(95%) grayscale(12%) saturate(150%)');
  });

  it('returns expected slider limits', () => {
    expect(getVisualFilterLimits()).toEqual({
      hue: { min: 0, max: 360 },
      brightness: { min: 50, max: 150 },
      contrast: { min: 50, max: 150 },
      grayscale: { min: 0, max: 100 },
      saturation: { min: 0, max: 200 },
    });
  });

  it('rounds hue values to whole degrees', () => {
    expect(normalizeVisualFilterPreference({ hue: 12.7 }).hue).toBe(13);
    expect(normalizeVisualFilterPreference({ hue: 12.2 }).hue).toBe(12);
    expect(normalizeVisualFilterPreference({ hue: -10 }).hue).toBe(0);
    expect(normalizeVisualFilterPreference({ hue: 999 }).hue).toBe(360);
  });
});
