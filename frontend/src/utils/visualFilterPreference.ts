export interface VisualFilterPreference {
  hue: number;
  brightness: number;
  contrast: number;
  grayscale: number;
  saturation: number;
}

export const VISUAL_FILTER_PREFERENCE_STORAGE_KEY = "intercept.visual-filter-preference";

export const VISUAL_FILTER_DEFAULTS: VisualFilterPreference = {
  hue: 0,
  brightness: 100,
  contrast: 100,
  grayscale: 0,
  saturation: 100,
};

const VISUAL_FILTER_LIMITS = {
  hue: { min: 0, max: 360 },
  brightness: { min: 50, max: 150 },
  contrast: { min: 50, max: 150 },
  grayscale: { min: 0, max: 100 },
  saturation: { min: 0, max: 200 },
} as const;

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function normalizeNumberish(value: unknown, fallback: number, min: number, max: number): number {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return fallback;
  }

  return clampNumber(Math.round(value), min, max);
}

export function normalizeVisualFilterPreference(
  value: Partial<VisualFilterPreference> | null | undefined,
): VisualFilterPreference {
  return {
    hue: normalizeNumberish(
      value?.hue,
      VISUAL_FILTER_DEFAULTS.hue,
      VISUAL_FILTER_LIMITS.hue.min,
      VISUAL_FILTER_LIMITS.hue.max,
    ),
    brightness: normalizeNumberish(
      value?.brightness,
      VISUAL_FILTER_DEFAULTS.brightness,
      VISUAL_FILTER_LIMITS.brightness.min,
      VISUAL_FILTER_LIMITS.brightness.max,
    ),
    contrast: normalizeNumberish(
      value?.contrast,
      VISUAL_FILTER_DEFAULTS.contrast,
      VISUAL_FILTER_LIMITS.contrast.min,
      VISUAL_FILTER_LIMITS.contrast.max,
    ),
    grayscale: normalizeNumberish(
      value?.grayscale,
      VISUAL_FILTER_DEFAULTS.grayscale,
      VISUAL_FILTER_LIMITS.grayscale.min,
      VISUAL_FILTER_LIMITS.grayscale.max,
    ),
    saturation: normalizeNumberish(
      value?.saturation,
      VISUAL_FILTER_DEFAULTS.saturation,
      VISUAL_FILTER_LIMITS.saturation.min,
      VISUAL_FILTER_LIMITS.saturation.max,
    ),
  };
}

export function getStoredVisualFilterPreference(): VisualFilterPreference {
  if (typeof window === "undefined") {
    return VISUAL_FILTER_DEFAULTS;
  }

  try {
    const rawValue = window.localStorage.getItem(VISUAL_FILTER_PREFERENCE_STORAGE_KEY);
    if (!rawValue) {
      return VISUAL_FILTER_DEFAULTS;
    }

    const parsed = JSON.parse(rawValue) as Partial<VisualFilterPreference>;
    return normalizeVisualFilterPreference(parsed);
  } catch {
    return VISUAL_FILTER_DEFAULTS;
  }
}

export function setStoredVisualFilterPreference(preference: VisualFilterPreference): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(
      VISUAL_FILTER_PREFERENCE_STORAGE_KEY,
      JSON.stringify(normalizeVisualFilterPreference(preference)),
    );
  } catch {
    // Ignore write failures (e.g., private mode restrictions)
  }
}

export function buildVisualFilterCss(preference: VisualFilterPreference): string {
  const normalized = normalizeVisualFilterPreference(preference);
  return `hue-rotate(${normalized.hue}deg) brightness(${normalized.brightness}%) contrast(${normalized.contrast}%) grayscale(${normalized.grayscale}%) saturate(${normalized.saturation}%)`;
}

export function applyVisualFilterPreference(preference: VisualFilterPreference): void {
  if (typeof document === "undefined") {
    return;
  }

  document.documentElement.style.filter = buildVisualFilterCss(preference);
}

export function getVisualFilterLimits() {
  return VISUAL_FILTER_LIMITS;
}
