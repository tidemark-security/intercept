export type ThemePreference = "system" | "dark" | "light";
export type ResolvedTheme = "dark" | "light";

export const THEME_PREFERENCE_STORAGE_KEY = "intercept.theme-preference";

const VALID_THEME_PREFERENCES: ThemePreference[] = ["system", "dark", "light"];

export function isThemePreference(value: string | null | undefined): value is ThemePreference {
  return typeof value === "string" && VALID_THEME_PREFERENCES.includes(value as ThemePreference);
}

export function getStoredThemePreference(): ThemePreference {
  if (typeof window === "undefined") {
    return "system";
  }

  try {
    const storedPreference = window.localStorage.getItem(THEME_PREFERENCE_STORAGE_KEY);
    return isThemePreference(storedPreference) ? storedPreference : "system";
  } catch {
    return "system";
  }
}

export function setStoredThemePreference(preference: ThemePreference): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(THEME_PREFERENCE_STORAGE_KEY, preference);
  } catch {
    // Ignore write failures (e.g., private mode restrictions)
  }
}

export function resolveThemeFromSystem(): ResolvedTheme {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "dark";
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function resolveThemePreference(preference: ThemePreference): ResolvedTheme {
  if (preference === "system") {
    return resolveThemeFromSystem();
  }

  return preference;
}

export function applyResolvedTheme(theme: ResolvedTheme): void {
  if (typeof document === "undefined") {
    return;
  }

  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = theme;
}
