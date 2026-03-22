/* eslint-disable react-refresh/only-export-components */

import React from "react";

import {
  applyResolvedTheme,
  getStoredThemePreference,
  resolveThemeFromSystem,
  resolveThemePreference,
  setStoredThemePreference,
  type ResolvedTheme,
  type ThemePreference,
} from "@/utils/themePreference";

interface ThemeContextValue {
  themePreference: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setThemePreference: (preference: ThemePreference) => void;
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [themePreference, setThemePreferenceState] = React.useState<ThemePreference>(() =>
    getStoredThemePreference()
  );
  const [resolvedTheme, setResolvedTheme] = React.useState<ResolvedTheme>(() =>
    resolveThemePreference(getStoredThemePreference())
  );

  React.useEffect(() => {
    const nextResolvedTheme = resolveThemePreference(themePreference);
    setResolvedTheme(nextResolvedTheme);
    setStoredThemePreference(themePreference);
    applyResolvedTheme(nextResolvedTheme);
  }, [themePreference]);

  React.useEffect(() => {
    if (themePreference !== "system" || typeof window.matchMedia !== "function") {
      return;
    }

    const mediaQueryList = window.matchMedia("(prefers-color-scheme: dark)");

    const handleSystemThemeChange = () => {
      const systemTheme = resolveThemeFromSystem();
      setResolvedTheme(systemTheme);
      applyResolvedTheme(systemTheme);
    };

    handleSystemThemeChange();

    if (typeof mediaQueryList.addEventListener === "function") {
      mediaQueryList.addEventListener("change", handleSystemThemeChange);
      return () => mediaQueryList.removeEventListener("change", handleSystemThemeChange);
    }

    mediaQueryList.addListener(handleSystemThemeChange);
    return () => mediaQueryList.removeListener(handleSystemThemeChange);
  }, [themePreference]);

  const value = React.useMemo<ThemeContextValue>(
    () => ({
      themePreference,
      resolvedTheme,
      setThemePreference: setThemePreferenceState,
    }),
    [themePreference, resolvedTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = React.useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
