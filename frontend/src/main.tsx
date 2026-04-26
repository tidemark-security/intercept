import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App.tsx";
import "./index.css";
import "@tidemark-security/ux/tokens.css";
import "@tidemark-security/ux/ux.css";
import { ThemeProvider } from "./contexts/ThemeContext";
import { TimezoneProvider } from "./contexts/TimezoneContext";
import { VisualFilterProvider } from "./contexts/VisualFilterContext";
import {
  applyResolvedTheme,
  getStoredThemePreference,
  resolveThemePreference,
} from "./utils/themePreference";
import {
  applyVisualFilterPreference,
  getStoredVisualFilterPreference,
} from "./utils/visualFilterPreference";
import { OpenAPI } from "./types/generated/core/OpenAPI";

// Configure OpenAPI client
// Use the same hostname as the current page to ensure cookies work correctly
const currentHostname = window.location.hostname;
OpenAPI.BASE = import.meta.env.VITE_API_BASE_URL || `http://${currentHostname}:8000`;
OpenAPI.WITH_CREDENTIALS = true;
OpenAPI.CREDENTIALS = "include";

// Create a client for TanStack Query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 10 * 60 * 1000, // 10 minutes
      retry: 3,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    },
  },
});

const initialThemePreference = getStoredThemePreference();
applyResolvedTheme(resolveThemePreference(initialThemePreference));
applyVisualFilterPreference(getStoredVisualFilterPreference());

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <VisualFilterProvider>
        <TimezoneProvider>
          <QueryClientProvider client={queryClient}>
            <App />
          </QueryClientProvider>
        </TimezoneProvider>
      </VisualFilterProvider>
    </ThemeProvider>
  </React.StrictMode>
);
