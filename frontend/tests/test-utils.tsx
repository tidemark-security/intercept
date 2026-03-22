import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";

import { BreakpointProvider } from "../src/contexts/BreakpointContext";
import { SessionContext, type SessionContextValue } from "../src/contexts/sessionContext";
import { ThemeProvider } from "../src/contexts/ThemeContext";
import { TimezoneProvider } from "../src/contexts/TimezoneContext";
import { ToastProvider } from "../src/contexts/ToastProvider";
import { VisualFilterProvider } from "../src/contexts/VisualFilterContext";

interface AppRenderOptions extends Omit<RenderOptions, "wrapper"> {
  queryClient?: QueryClient;
  sessionValue?: SessionContextValue;
}

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function renderWithProviders(
  ui: ReactElement,
  { queryClient = createTestQueryClient(), sessionValue, ...renderOptions }: AppRenderOptions = {},
) {
  function Providers({ children }: { children: ReactNode }) {
    const content = sessionValue ? (
      <SessionContext.Provider value={sessionValue}>{children}</SessionContext.Provider>
    ) : (
      children
    );

    return (
      <ThemeProvider>
        <VisualFilterProvider>
          <TimezoneProvider>
            <QueryClientProvider client={queryClient}>
              <BreakpointProvider>
                <ToastProvider>
                  <BrowserRouter>{content}</BrowserRouter>
                </ToastProvider>
              </BreakpointProvider>
            </QueryClientProvider>
          </TimezoneProvider>
        </VisualFilterProvider>
      </ThemeProvider>
    );
  }

  return render(ui, { wrapper: Providers, ...renderOptions });
}